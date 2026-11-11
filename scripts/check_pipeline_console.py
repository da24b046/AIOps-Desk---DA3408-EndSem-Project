"""Submit and verify one real pipeline job through the authenticated API."""

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
        login = client.post(
            "/v1/session", json={"username": username, "password": password}
        )
        del password
        login.raise_for_status()
        session = login.json()
        client.headers["Authorization"] = "Bearer " + session["access_token"]

        job_id = None
        try:
            assert session["user"]["role"] == "maintainer"

            response = client.post("/v1/pipeline-runs", json={
                "reason": "Real pipeline console integration check",
                "force_rebuild": True,
            })
            response.raise_for_status()
            job_id = response.json()["job_id"]
            endpoint = f"/v1/pipeline-runs/{job_id}"
            print("Submitted job:", job_id, flush=True)

            deadline = time.monotonic() + 1200
            previous = None

            while time.monotonic() < deadline:
                response = client.get(endpoint)
                response.raise_for_status()
                job = response.json()
                state = (
                    job["status"],
                    tuple(stage["status"] for stage in job["stages"]),
                )
                if state != previous:
                    print(
                        job["status"],
                        " | ".join(
                            f"{stage['id']}: {stage['status']}"
                            for stage in job["stages"]
                        ),
                        flush=True,
                    )
                    previous = state

                if job["status"] in TERMINAL:
                    break
                time.sleep(2)
            else:
                client.post(
                    endpoint + "/cancel",
                    json={"reason": "Integration check exceeded its wait limit"},
                ).raise_for_status()
                raise RuntimeError(
                    "Wait limit reached; cancellation requested. Check the worker."
                )

            report_path = ROOT / "reports/pipeline_console_check.json"
            report_path.write_text(
                json.dumps(job, indent=2) + "\n", encoding="utf-8"
            )

            assert job["status"] == "succeeded", (
                f"Job ended as {job['status']}; error code: {job['error_code']}"
            )
            assert all(
                stage["status"] == "succeeded" for stage in job["stages"]
            ), "Forced run did not record all three executed stages."
            assert job["summary"]["quality_gate_passed"] is True
            assert job["summary"]["test_set_used"] is False
            assert job["summary"]["deployment_attempted"] is False

            readiness = client.get("/health/ready")
            readiness.raise_for_status()
            release = readiness.json()
            assert release["model_version"] == "candidate-001"
            assert release["policy_version"] == "policy-001"

            print("\nPIPELINE CONSOLE INTEGRATION PASSED")
            for stage in job["stages"]:
                print(
                    f"{stage['id']}: {stage['status']}, "
                    f"{stage['elapsed_seconds']:.2f}s, "
                    f"counts={stage['counts']}"
                )
            print("Quality gate: passed")
            print("Serving release unchanged: candidate-001 / policy-001")
            print("Report:", report_path.relative_to(ROOT))

        except KeyboardInterrupt:
            if job_id:
                response = client.post(
                    f"/v1/pipeline-runs/{job_id}/cancel",
                    json={"reason": "Integration check interrupted by user"},
                )
                response.raise_for_status()
                print("\nCancellation requested; let the worker finish cleanup.")
            raise
        finally:
            client.delete("/v1/session").raise_for_status()


if __name__ == "__main__":
    main()
