"""Verify review permissions, decisions and preservation of original data."""

import json
from getpass import getpass
from pathlib import Path

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

    previous = json.loads(
        (ROOT / "reports/feedback_check.json").read_text(encoding="utf-8")
    )
    prediction_id = previous["prediction_id"]
    payload = {
        "prediction_id": prediction_id,
        "category": "Network",
        "reason": "Synthetic feedback for review verification.",
        "label_source": "synthetic_demo",
    }
    decision = {
        "decision": "approved",
        "reason": "Approved as a synthetic workflow demonstration.",
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
            headers=headers["maintainer"],
        )
        response.raise_for_status()
        original = response.json()

        fixtures = {}
        for name, author in (
            ("approve", "operator"),
            ("reject", "operator"),
            ("self_review", "maintainer"),
        ):
            response = client.post(
                "/v1/feedback", json=payload, headers=headers[author]
            )
            check(f"Created {name} fixture", response.status_code == 201)
            fixtures[name] = response.json()

        approved_id = fixtures["approve"]["feedback_id"]
        endpoint = f"/v1/feedback/{approved_id}/review"

        check(
            "Unauthenticated review rejected",
            client.post(endpoint, json=decision).status_code == 401,
        )
        for role in ("viewer", "operator"):
            check(
                f"{role}: review forbidden",
                client.post(
                    endpoint, json=decision, headers=headers[role]
                ).status_code == 403,
            )

        response = client.post(
            endpoint, json=decision, headers=headers["maintainer"]
        )
        check("Maintainer approval accepted", response.status_code == 200)
        approved = response.json()
        check(
            "Approval records reviewer and timestamp",
            approved["decision"] == "approved"
            and approved["reviewer_username"] == "maintainer"
            and bool(approved["reviewed_at"]),
        )

        response = client.get(endpoint, headers=headers["operator"])
        check(
            "Author can inspect saved review",
            response.status_code == 200 and response.json() == approved,
        )
        check(
            "Second decision rejected",
            client.post(
                endpoint,
                json={**decision, "decision": "rejected"},
                headers=headers["maintainer"],
            ).status_code == 409,
        )
        check(
            "Original review preserved",
            client.get(
                endpoint, headers=headers["maintainer"]
            ).json() == approved,
        )

        rejected_id = fixtures["reject"]["feedback_id"]
        response = client.post(
            f"/v1/feedback/{rejected_id}/review",
            json={
                "decision": "rejected",
                "reason": "Rejected synthetic demonstration.",
            },
            headers=headers["maintainer"],
        )
        check(
            "Maintainer rejection accepted",
            response.status_code == 200
            and response.json()["decision"] == "rejected",
        )

        self_id = fixtures["self_review"]["feedback_id"]
        check(
            "Self-review forbidden",
            client.post(
                f"/v1/feedback/{self_id}/review",
                json=decision,
                headers=headers["maintainer"],
            ).status_code == 403,
        )

        response = client.get(
            "/v1/feedback",
            params={"limit": 100},
            headers=headers["maintainer"],
        )
        response.raise_for_status()
        saved = {
            item["feedback_id"]: item
            for item in response.json()["items"]
        }
        check(
            "Feedback statuses reflect decisions",
            saved[approved_id]["status"] == "approved"
            and saved[rejected_id]["status"] == "rejected"
            and saved[self_id]["status"] == "pending",
        )
        check(
            "Proposed labels and author preserved",
            saved[approved_id]["labels"] == fixtures["approve"]["labels"]
            and saved[approved_id]["author_username"] == "operator",
        )
        check(
            "Original prediction unchanged",
            client.get(
                f"/v1/predictions/{prediction_id}",
                headers=headers["maintainer"],
            ).json() == original,
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
        "approved_feedback_id": approved_id,
        "rejected_feedback_id": rejected_id,
        "self_review_feedback_id": self_id,
        "label_source": "synthetic_demo",
    }
    (ROOT / "reports/review_check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nREVIEW CHECK PASSED: {len(checks)} checks.")


if __name__ == "__main__":
    main()
