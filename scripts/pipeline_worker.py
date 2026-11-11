"""Host worker for the fixed local DVC pipeline; never deploys models."""

import argparse
import fcntl
import hashlib
import json
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

import httpx

from scripts.pipeline_process import PipelineStopped, run_process

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/pipeline_console.json").read_text())
STAGES = ("spark_etl", "train", "evaluate")
BASE = "/v1/pipeline-worker"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(relative):
    return json.loads((ROOT / relative).read_text())


def stage_counts(stage):
    if stage == "spark_etl":
        report = read_json("reports/spark_etl.json")
        return {
            "input_rows": report["input_rows"],
            "retained_rows": report["retained_rows"],
            "rejected_rows": report["total_excluded_rows"],
        }
    if stage == "train":
        report = read_json("artifacts/pipeline_candidate/training_manifest.json")
        return {"train_rows": report["train_rows"]}
    report = read_json("reports/pipeline_evaluation.json")
    return {"validation_rows": report["validation_rows"]}


def process_job(client, job, secret, server_config):
    job_id = job["job_id"]
    endpoint = f"{BASE}/{job_id}"
    worker_headers = {"X-Pipeline-Worker-Token": secret}
    evidence = ROOT / "evidence/pipeline-console" / job_id
    evidence.mkdir(parents=True, exist_ok=True)

    def request(method, suffix="", **kwargs):
        response = client.request(
            method, endpoint + suffix, headers=worker_headers, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def cancelled():
        return request("GET")["status"] == "cancel_requested"

    outcome = {"status": "succeeded", "summary": {}}
    interrupted = False

    try:
        assert server_config == CONFIG, "Worker/API configuration mismatch."
        summary = {
            "git_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "git_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()),
            "train_sha256": sha(ROOT / "data/splits/train.csv"),
            "validation_sha256": sha(ROOT / "data/splits/validation.csv"),
            "test_set_used": False,
            "deployment_attempted": False,
        }

        for stage in STAGES:
            if cancelled():
                raise PipelineStopped("cancelled")

            request("POST", "/stage-start", json={"stage_id": stage})
            started = time.monotonic()
            reused = False

            if not job["force_rebuild"]:
                status_log = evidence / f"{stage}-status.json"
                code = run_process(
                    [sys.executable, "-m", "dvc", "status", "--json", stage],
                    cwd=ROOT,
                    log_path=status_log,
                    timeout=30,
                    should_cancel=cancelled,
                )
                if code:
                    raise RuntimeError("DVC status failed.")
                changes = json.loads(status_log.read_text())
                if not isinstance(changes, dict):
                    raise ValueError("Unexpected DVC status format.")
                reused = not changes

            if not reused:
                code = run_process(
                    [
                        sys.executable, "-m", "dvc", "repro",
                        "--single-item", "--force", "--no-run-cache", stage,
                    ],
                    cwd=ROOT,
                    log_path=evidence / f"{stage}.log",
                    timeout=CONFIG["stage_timeout_seconds"],
                    should_cancel=cancelled,
                )
                if code:
                    raise RuntimeError("DVC stage failed.")

            if cancelled():
                raise PipelineStopped("cancelled")

            state = "reused" if reused else "succeeded"
            request("POST", "/stage-finish", json={
                "stage_id": stage,
                "status": state,
                "elapsed_seconds": time.monotonic() - started,
                "counts": stage_counts(stage),
            })
            print(f"{stage}: {state}", flush=True)

        evaluation = read_json("reports/pipeline_evaluation.json")
        if evaluation["gate_passed"] is not True:
            outcome = {"status": "failed", "error_code": "quality_gate_failed"}
        else:
            assert evaluation["test_set_used"] is False
            summary.update({
                "quality_gate_passed": True,
                "validation_rows": evaluation["validation_rows"],
                "dvc_lock_sha256": sha(ROOT / "dvc.lock"),
                "category_macro_f1": evaluation["models"]["category"]["macro_f1"],
                "priority_macro_f1": evaluation["models"]["priority"]["macro_f1"],
            })
            outcome["summary"] = summary

    except PipelineStopped as stopped:
        outcome = (
            {"status": "cancelled"}
            if stopped.reason == "cancelled"
            else {"status": "failed", "error_code": "stage_timeout"}
        )
    except KeyboardInterrupt:
        interrupted = True
        outcome = {"status": "interrupted", "error_code": "worker_interrupted"}
    except httpx.HTTPError:
        outcome = {
            "status": "interrupted",
            "error_code": "worker_connection_lost",
        }
    except (OSError, ValueError, KeyError, AssertionError, RuntimeError):
        outcome = {"status": "failed", "error_code": "stage_failed"}

    # Recheck cancellation to handle a request arriving at the final boundary.
    saved = None
    for attempt in range(5):
        try:
            if outcome["status"] == "succeeded" and cancelled():
                outcome = {"status": "cancelled"}
            saved = request("POST", "/finish", json=outcome)
            break
        except httpx.HTTPError:
            if attempt < 4:
                time.sleep(2)

    if saved is None:
        raise RuntimeError(
            "Could not record final state. Worker stopped; "
            "the API job remains locked pending recovery."
        )

    content = json.dumps(saved, indent=2) + "\n"
    (evidence / "job.json").write_text(content)
    (ROOT / "reports/pipeline_console_latest.json").write_text(content)
    print(f"Job {job_id}: {saved['status']}", flush=True)
    return interrupted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="Wait for and process one job, then exit.")
    args = parser.parse_args()

    lock_path = ROOT / "state/pipeline-worker/worker.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A worker is already running for this checkout.")

        username = input("Maintainer username [maintainer]: ").strip() or "maintainer"
        password = getpass("Maintainer password: ")

        with httpx.Client(
            base_url="http://127.0.0.1:8000", timeout=5, trust_env=False
        ) as client:
            login = client.post(
                "/v1/session", json={"username": username, "password": password}
            )
            del password
            login.raise_for_status()
            session = login.json()
            if session["user"]["role"] != "maintainer":
                client.delete(
                    "/v1/session",
                    headers={"Authorization": "Bearer " + session["access_token"]},
                )
                raise SystemExit("Maintainer role required.")

            client.headers["Authorization"] = "Bearer " + session["access_token"]
            expires = datetime.fromisoformat(session["expires_at"]).timestamp()

            try:
                print("Worker ready. Waiting for a queued job. Ctrl+C to stop.")
                while True:
                    # Leave enough session lifetime for all three bounded stages.
                    reserve = 3 * (CONFIG["stage_timeout_seconds"] + 60) + 60
                    if expires - time.time() < reserve:
                        print("Session renewal needed. Restart the worker.")
                        break

                    secret = secrets.token_urlsafe(32)
                    response = client.post(
                        BASE + "/claim", json={"worker_token": secret}
                    )
                    response.raise_for_status()
                    claim = response.json()
                    job = claim["job"]

                    if job is None:
                        time.sleep(CONFIG["poll_interval_seconds"])
                        continue

                    print("Claimed job:", job["job_id"], flush=True)
                    interrupted = process_job(
                        client, job, secret, claim["config"]
                    )
                    if args.once or interrupted:
                        break
            except KeyboardInterrupt:
                print("\nIdle worker stopped.")
            finally:
                try:
                    client.delete("/v1/session").raise_for_status()
                except httpx.HTTPError:
                    print("Logout could not be confirmed; session will expire.")


if __name__ == "__main__":
    main()
