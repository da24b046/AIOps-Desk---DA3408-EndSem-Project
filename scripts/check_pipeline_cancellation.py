"""Verify cancellation acknowledgement for an actively running pipeline job."""

import json
import time
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


def main():
    username = input("Maintainer username [maintainer]: ").strip() or "maintainer"
    password = getpass("Maintainer password: ")

    with httpx.Client(
        base_url="http://127.0.0.1:8000", timeout=10, trust_env=False
    ) as client:
        response = client.post(
            "/v1/session", json={"username": username, "password": password}
        )
        del password
        response.raise_for_status()
        session = response.json()
        client.headers["Authorization"] = "Bearer " + session["access_token"]

        job_id = None
        try:
            assert session["user"]["role"] == "maintainer"
            response = client.post("/v1/pipeline-runs", json={
                "reason": "Active pipeline cancellation demonstration",
                "force_rebuild": True,
            })
            response.raise_for_status()
            job_id = response.json()["job_id"]
            endpoint = f"/v1/pipeline-runs/{job_id}"
            print("Submitted job:", job_id, flush=True)

            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                response = client.get(endpoint)
                response.raise_for_status()
                job = response.json()

                if any(stage["status"] == "running" for stage in job["stages"]):
                    break
                if job["status"] in TERMINAL:
                    raise RuntimeError("Job finished before cancellation could be tested.")
                time.sleep(0.5)
            else:
                raise RuntimeError("No running stage observed; check the worker.")

            running_stages = [
                stage["id"] for stage in job["stages"]
                if stage["status"] == "running"
            ]
            response = client.post(endpoint + "/cancel", json={
                "reason": "Controlled cancellation after a stage started",
            })
            response.raise_for_status()
            requested = response.json()
            assert requested["status"] == "cancel_requested"
            print("Cancellation requested during:", ", ".join(running_stages), flush=True)

            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                response = client.get(endpoint)
                response.raise_for_status()
                final = response.json()
                if final["status"] in TERMINAL:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Worker has not acknowledged cancellation.")

            assert final["status"] == "cancelled", final["status"]
            assert final["finished_at"] is not None
            assert not any(
                stage["status"] in ("pending", "running")
                for stage in final["stages"]
            )

            response = client.get("/health/ready")
            response.raise_for_status()
            readiness = response.json()
            assert readiness["model_version"] == "candidate-001"
            assert readiness["policy_version"] == "policy-001"

            report = {
                "running_stages_at_request": running_stages,
                "cancel_requested_observed": True,
                "worker_acknowledged_cancellation": True,
                "final_job": final,
                "serving_release_after_cancellation": readiness,
            }
            path = ROOT / "reports/pipeline_cancellation_check.json"
            path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

            print("ACTIVE PIPELINE CANCELLATION PASSED")
            for stage in final["stages"]:
                print(f"{stage['id']}: {stage['status']}")
            print("Serving release unchanged: candidate-001 / policy-001")
            print("Report:", path.relative_to(ROOT))

        finally:
            client.delete("/v1/session").raise_for_status()


if __name__ == "__main__":
    main()
