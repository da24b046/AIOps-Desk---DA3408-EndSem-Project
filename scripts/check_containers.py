"""Verify containerized inference and persistence across API recreation."""

import argparse
import json
import subprocess
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/container_check.json"


def container_info():
    container_id = subprocess.check_output(
        ["docker", "compose", "ps", "-q", "api"],
        cwd=ROOT,
        text=True,
    ).strip()
    if not container_id:
        raise RuntimeError("API container is not running.")

    information = json.loads(subprocess.check_output(
        ["docker", "inspect", container_id], text=True
    ))[0]

    return container_id, information


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(f"FAILED: {name}")
        checks.append(name)
        print("PASS:", name)

    container_id, information = container_info()
    check(
        "Named application volume mounted",
        any(
            mount.get("Name") == "aiopsdesk_app_data"
            and mount["Destination"] == "/app/state/app"
            and mount["RW"]
            for mount in information["Mounts"]
        ),
    )

    if args.verify_existing:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        check(
            "API container was recreated",
            container_id != report["api_container_id_before"],
        )
    else:
        report = {
            "api_container_id_before": container_id,
            "api_image_id": information["Image"],
            "database_volume": "aiopsdesk_app_data",
            "test_set_used": False,
        }

    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=15,
        trust_env=False,
    ) as client:
        check(
            "Containerized API ready",
            client.get("/health/ready").status_code == 200,
        )

        password = getpass("Operator password: ")
        response = client.post(
            "/v1/session",
            json={"username": "operator", "password": password},
        )
        del password
        check("Existing operator account works", response.status_code == 200)

        client.headers["Authorization"] = (
            "Bearer " + response.json()["access_token"]
        )

        if not args.verify_existing:
            response = client.post(
                "/v1/predict",
                json={
                    "subject": "Container persistence demonstration",
                    "description": (
                        "I cannot sign in to my account. "
                        "Contact demo.user@example.test."
                    ),
                },
            )
            check(
                "Containerized prediction accepted",
                response.status_code == 200,
            )
            report["prediction_id"] = response.json()["prediction_id"]

        response = client.get(
            f"/v1/predictions/{report['prediction_id']}"
        )
        check("Saved prediction accessible", response.status_code == 200)
        saved = response.json()

        check(
            "Prediction owner preserved",
            saved["owner_username"] == "operator",
        )
        check(
            "Stored email redacted",
            "demo.user@example.test"
            not in saved["redacted_input"]["description"]
            and "[EMAIL]" in saved["redacted_input"]["description"],
        )

        if args.verify_existing:
            check(
                "Prediction unchanged after recreation",
                saved == report["saved_prediction"],
            )
            report["api_container_id_after"] = container_id
            report["verified_after_recreation"] = True
            report["recreation_checks"] = checks
        else:
            report["saved_prediction"] = saved
            report["verified_after_recreation"] = False
            report["initial_checks"] = checks

        check(
            "Logout accepted",
            client.delete("/v1/session").status_code == 204,
        )

    REPORT.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    if args.verify_existing:
        print("\nCONTAINER RECREATION PERSISTENCE PASSED")
    else:
        print("\nCONTAINER CHECK PASSED")
    print("Prediction:", report["prediction_id"])
    print("Report: reports/container_check.json")


if __name__ == "__main__":
    main()
