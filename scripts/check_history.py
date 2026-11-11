"""Verify prediction-history ownership, review access and pagination."""

import json
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = []
    headers = {}
    created = {"viewer": [], "operator": []}

    def check(name, condition):
        if not condition:
            raise AssertionError(f"FAILED: {name}")
        checks.append(name)
        print("PASS:", name)

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

        for role in ("viewer", "viewer", "operator"):
            response = client.post(
                "/v1/predict",
                headers=headers[role],
                json={
                    "subject": "Account access demonstration",
                    "description": "I cannot sign in to my work account.",
                },
            )
            check(f"{role}: demonstration prediction", response.status_code == 200)
            created[role].append(response.json()["prediction_id"])

        check(
            "Unauthenticated history rejected",
            client.get("/v1/predictions").status_code == 401,
        )

        response = client.get(
            "/v1/predictions", headers=headers["viewer"]
        )
        check(
            "Viewer history contains only own records",
            response.status_code == 200
            and all(
                item["owner_username"] == "viewer"
                for item in response.json()["items"]
            ),
        )

        viewer_id = created["viewer"][0]
        operator_id = created["operator"][0]

        check(
            "Viewer can inspect own prediction",
            client.get(
                f"/v1/predictions/{viewer_id}",
                headers=headers["viewer"],
            ).status_code == 200,
        )
        check(
            "Viewer cannot inspect operator prediction",
            client.get(
                f"/v1/predictions/{operator_id}",
                headers=headers["viewer"],
            ).status_code == 404,
        )
        check(
            "Operator can inspect viewer prediction",
            client.get(
                f"/v1/predictions/{viewer_id}",
                headers=headers["operator"],
            ).status_code == 200,
        )
        check(
            "Maintainer can inspect operator prediction",
            client.get(
                f"/v1/predictions/{operator_id}",
                headers=headers["maintainer"],
            ).status_code == 200,
        )

        response = client.get(
            "/v1/predictions",
            params={"limit": 1},
            headers=headers["viewer"],
        )
        response.raise_for_status()
        first_page = response.json()
        check("Page limit respected", len(first_page["items"]) == 1)
        check("Next cursor supplied", first_page["next_cursor"] is not None)

        response = client.get(
            "/v1/predictions",
            params={"limit": 1, "cursor": first_page["next_cursor"]},
            headers=headers["viewer"],
        )
        response.raise_for_status()
        second_page = response.json()
        check(
            "Next page returns a different owned record",
            len(second_page["items"]) == 1
            and second_page["items"][0]["owner_username"] == "viewer"
            and second_page["items"][0]["prediction_id"]
            != first_page["items"][0]["prediction_id"],
        )

        check(
            "Oversized history limit rejected",
            client.get(
                "/v1/predictions",
                params={"limit": 101},
                headers=headers["viewer"],
            ).status_code == 422,
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
        "demonstration_prediction_ids": created,
        "test_set_used": False,
    }
    (ROOT / "reports/history_check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nHISTORY CHECK PASSED: {len(checks)} checks.")


if __name__ == "__main__":
    main()
