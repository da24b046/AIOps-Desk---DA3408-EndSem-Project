import csv
import hashlib
import json
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"


def main():
    policy = json.loads(
        (ROOT / "configs/policy.json").read_text(encoding="utf-8")
    )
    username = input("Username [operator]: ").strip() or "operator"
    password = getpass("Password: ")

    with httpx.Client(
        base_url=BASE_URL, timeout=10, trust_env=False
    ) as client:
        login = client.post(
            "/v1/session",
            json={"username": username, "password": password},
        )
        del password
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = client.get(
                "/v1/predictions",
                params={"limit": 100},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload["items"]

            selected = [
                item for item in items
                if item["model_version"] == policy["expected_model_version"]
                and item["policy_version"] == policy["policy_version"]
            ]

            rows = []
            for item in selected:
                redacted = item["redacted_input"]
                subject = redacted["subject"]
                description = redacted["description"]
                if not isinstance(subject, str) or not isinstance(description, str):
                    raise ValueError("Saved input contains non-text fields.")
                rows.append({
                    "subject": subject,
                    "description": description,
                })

            output = ROOT / "state/drift/recent_tickets.csv"
            output.parent.mkdir(parents=True, exist_ok=True)

            with output.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["subject", "description"]
                )
                writer.writeheader()
                writer.writerows(rows)

            report = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": "authenticated_prediction_history_api",
                "selection": "latest 100 records visible to authenticated user",
                "history_rows_fetched": len(items),
                "matching_rows_exported": len(rows),
                "other_version_rows_excluded": len(items) - len(rows),
                "older_history_available": payload["next_cursor"] is not None,
                "model_version": policy["expected_model_version"],
                "policy_version": policy["policy_version"],
                "redacted_inputs_only": True,
                "output": str(output.relative_to(ROOT)),
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "oldest_selected_at": (
                    min(item["created_at"] for item in selected)
                    if selected else None
                ),
                "newest_selected_at": (
                    max(item["created_at"] for item in selected)
                    if selected else None
                ),
            }
            report_path = ROOT / "reports/recent_input_export.json"
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

            print("RECENT INPUT EXPORT PASSED")
            print(json.dumps(report, indent=2))

        finally:
            logout = client.delete("/v1/session", headers=headers)
            logout.raise_for_status()
            print("Session logged out.")


if __name__ == "__main__":
    main()
