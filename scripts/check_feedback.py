"""Verify feedback permissions, persistence and prediction preservation."""

import json
from getpass import getpass
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = []
    headers = {}

    def check(name, condition):
        if not condition:
            raise AssertionError(f"FAILED: {name}")
        checks.append(name)
        print("PASS:", name)

    history = json.loads(
        (ROOT / "reports/history_check.json").read_text(encoding="utf-8")
    )
    prediction_id = history["demonstration_prediction_ids"]["operator"][0]

    payload = {
        "prediction_id": prediction_id,
        "category": "Network",
        "reason": "Synthetic correction to demonstrate the feedback workflow.",
        "label_source": "synthetic_demo",
    }

    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=15,
        trust_env=False,
    ) as client:
        for role in ("viewer", "operator", "maintainer"):
            password = getpass(f"Password for {role}: ")
            response = client.post(
                "/v1/session",
                json={"username": role, "password": password},
            )
            del password
            check(f"{role}: login", response.status_code == 200)
            headers[role] = {
                "Authorization": "Bearer " + response.json()["access_token"]
            }

        response = client.get(
            f"/v1/predictions/{prediction_id}",
            headers=headers["operator"],
        )
        response.raise_for_status()
        original = response.json()

        check(
            "Unauthenticated feedback rejected",
            client.post("/v1/feedback", json=payload).status_code == 401,
        )
        check(
            "Viewer feedback rejected",
            client.post(
                "/v1/feedback", json=payload, headers=headers["viewer"]
            ).status_code == 403,
        )

        response = client.post(
            "/v1/feedback", json=payload, headers=headers["operator"]
        )
        check("Operator feedback accepted", response.status_code == 201)
        feedback = response.json()

        check(
            "Feedback recorded as pending with correct author",
            feedback["status"] == "pending"
            and feedback["author_username"] == "operator"
            and feedback["labels"] == {"category": "Network"}
            and feedback["label_source"] == "synthetic_demo",
        )

        response = client.get(
            f"/v1/predictions/{prediction_id}",
            headers=headers["operator"],
        )
        check(
            "Original prediction unchanged",
            response.status_code == 200 and response.json() == original,
        )

        check(
            "Viewer feedback history rejected",
            client.get(
                "/v1/feedback", headers=headers["viewer"]
            ).status_code == 403,
        )

        response = client.get("/v1/feedback", headers=headers["operator"])
        check(
            "Operator sees own submitted feedback",
            response.status_code == 200
            and all(
                item["author_username"] == "operator"
                for item in response.json()["items"]
            )
            and any(
                item["feedback_id"] == feedback["feedback_id"]
                for item in response.json()["items"]
            ),
        )

        response = client.get("/v1/feedback", headers=headers["maintainer"])
        check(
            "Maintainer can see pending feedback",
            response.status_code == 200
            and any(
                item["feedback_id"] == feedback["feedback_id"]
                for item in response.json()["items"]
            ),
        )

        check(
            "Unsupported category rejected",
            client.post(
                "/v1/feedback",
                json={**payload, "category": "Billing"},
                headers=headers["operator"],
            ).status_code == 422,
        )
        check(
            "Unknown prediction rejected",
            client.post(
                "/v1/feedback",
                json={**payload, "prediction_id": str(uuid4())},
                headers=headers["operator"],
            ).status_code == 404,
        )

        for role in headers:
            check(
                f"{role}: logout",
                client.delete(
                    "/v1/session", headers=headers[role]
                ).status_code == 204,
            )

    report = {
        "status": "passed",
        "checks_passed": len(checks),
        "checks": checks,
        "feedback_id": feedback["feedback_id"],
        "prediction_id": prediction_id,
        "label_source": "synthetic_demo",
    }
    (ROOT / "reports/feedback_check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nFEEDBACK CHECK PASSED: {len(checks)} checks.")


if __name__ == "__main__":
    main()
