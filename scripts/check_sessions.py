"""Verify login and logout without printing passwords or tokens."""

import json
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = []

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
        check(
            "Missing token rejected",
            client.get("/v1/session").status_code == 401,
        )
        check(
            "Invalid token rejected",
            client.get(
                "/v1/session",
                headers={"Authorization": "Bearer invalid-demo-token"},
            ).status_code == 401,
        )

        for role in ("viewer", "operator", "maintainer"):
            password = getpass(f"\nPassword for {role}: ")
            response = client.post(
                "/v1/session",
                json={"username": role, "password": password},
            )
            del password

            check(f"{role}: login accepted", response.status_code == 200)
            session = response.json()

            check(
                f"{role}: correct identity returned",
                session["user"] == {"username": role, "role": role},
            )

            headers = {
                "Authorization": f"Bearer {session['access_token']}"
            }
            response = client.get("/v1/session", headers=headers)
            check(
                f"{role}: authenticated session works",
                response.status_code == 200
                and response.json() == {"username": role, "role": role},
            )

            response = client.delete("/v1/session", headers=headers)
            check(f"{role}: logout accepted", response.status_code == 204)

            check(
                f"{role}: logged-out token rejected",
                client.get(
                    "/v1/session", headers=headers
                ).status_code == 401,
            )

    report = {
        "status": "passed",
        "checks_passed": len(checks),
        "checks": checks,
    }
    (ROOT / "reports/session_check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\nSESSION CHECK PASSED: {len(checks)} checks.")


if __name__ == "__main__":
    main()
