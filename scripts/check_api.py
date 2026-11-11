"""Check API prediction, persistence, redaction and invalid inputs."""

import json
import sqlite3
from contextlib import closing
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "state/app/aiops.db"
BASE_URL = "http://127.0.0.1:8000"


def main():
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(f"FAILED: {name}")
        checks.append(name)
        print("PASS:", name)

    def row_count():
        with closing(sqlite3.connect(DATABASE)) as database:
            return database.execute(
                "SELECT COUNT(*) FROM predictions"
            ).fetchone()[0]

    policy = json.loads(
        (ROOT / "configs/policy.json").read_text(encoding="utf-8")
    )

    with httpx.Client(base_url=BASE_URL, timeout=10, trust_env=False) as client:
        response = client.post(
            "/v1/predict",
            json={"subject": "Help", "description": "Cannot sign in."},
        )
        check("Unauthenticated prediction rejected", response.status_code == 401)

        password = getpass("Operator password: ")
        response = client.post(
            "/v1/session",
            json={"username": "operator", "password": password},
        )
        del password
        check("Operator login accepted", response.status_code == 200)
        client.headers["Authorization"] = (
            "Bearer " + response.json()["access_token"]
        )

        response = client.get("/health/ready")
        check("API readiness", response.status_code == 200)

        payload = {
            "subject": "Account access problem",
            "description": (
                "I cannot sign in to my account. "
                "Contact demo.user@example.test."
            ),
        }
        response = client.post("/v1/predict", json=payload)
        check("Valid request accepted", response.status_code == 200)
        body = response.json()
        result = body["result"]

        check(
            "Expected model and policy versions",
            body["model_version"] == policy["expected_model_version"]
            and body["policy_version"] == policy["policy_version"],
        )
        check(
            "Team routing follows policy",
            result["team"] == policy["category_to_team"][result["category"]],
        )
        expected_reasons = [
            f"low_{field}"
            for field, threshold in policy["review_thresholds"].items()
            if result[field] < threshold
        ]
        check(
            "Manual-review rules follow policy",
            result["review_reasons"] == expected_reasons
            and result["needs_review"] == bool(expected_reasons),
        )

        with closing(sqlite3.connect(DATABASE)) as database:
            stored = database.execute(
                """
                SELECT redacted_input_json, result_json,
                       model_version, policy_version, created_at, owner_username
                FROM predictions WHERE prediction_id = ?
                """,
                (body["prediction_id"],),
            ).fetchone()

        check("Prediction exists in SQLite", stored is not None)
        check(
            "Stored result matches API response",
            json.loads(stored[1]) == result
            and stored[2] == body["model_version"]
            and stored[3] == body["policy_version"]
            and stored[4] == body["created_at"],
        )
        check("Prediction owner recorded", stored[5] == "operator")
        stored_input = json.loads(stored[0])
        check(
            "Stored email is redacted",
            stored_input["description"]
            == payload["description"].replace(
                "demo.user@example.test", "[EMAIL]"
            ),
        )

        invalid_requests = {
            "Missing description": {"subject": "Help"},
            "Whitespace-only subject": {
                "subject": "   ", "description": "Cannot sign in."
            },
            "Unexpected field": {
                "subject": "Help",
                "description": "Cannot sign in.",
                "category": "Account",
            },
            "Combined text exceeds limit": {
                "subject": "x",
                "description": "x" * policy["max_combined_text_characters"],
            },
        }

        before = row_count()

        for name, invalid_payload in invalid_requests.items():
            response = client.post("/v1/predict", json=invalid_payload)
            check(name + " rejected with 422", response.status_code == 422)

        check("Invalid requests created no records", row_count() == before)

        response = client.delete("/v1/session")
        check("Operator logout accepted", response.status_code == 204)
        response = client.post("/v1/predict", json=payload)
        check(
            "Logged-out prediction rejected",
            response.status_code == 401,
        )

    report = {
        "status": "passed",
        "checks_passed": len(checks),
        "checks": checks,
        "verified_prediction_id": body["prediction_id"],
        "test_set_used": False,
    }
    destination = ROOT / "reports/api_check.json"
    destination.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\nAPI CHECK PASSED: {len(checks)} checks.")
    print("Report saved: reports/api_check.json")


if __name__ == "__main__":
    main()
