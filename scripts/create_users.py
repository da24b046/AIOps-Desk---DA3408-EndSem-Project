"""Interactively create local demo accounts without logging passwords."""

import json
from getpass import getpass
from pathlib import Path

from src.auth import (
    create_user,
    get_user,
    initialize_users,
    verify_user,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    initialize_users()

    for role in ("viewer", "operator", "maintainer"):
        if get_user(role):
            print(f"Account already exists; unchanged: {role}")
            continue

        print(f"\nCreating account: {role}")

        while True:
            password = getpass("Password (at least 10 characters): ")
            confirmation = getpass("Confirm password: ")

            if password != confirmation:
                print("Passwords do not match. Try again.")
            elif len(password) < 10:
                print("Password is too short. Try again.")
            else:
                break

        create_user(role, password, role)

        assert verify_user(role, password) == {
            "username": role,
            "role": role,
        }
        assert verify_user(role, password + "__wrong") is None
        print(f"Created and password verification checked: {role}")

    accounts = []
    for username in ("viewer", "operator", "maintainer"):
        user = get_user(username)
        assert user is not None
        assert user["role"] == username
        assert user["password_hash"].startswith("$argon2")
        accounts.append({
            "username": username,
            "role": user["role"],
            "argon2_hash_present": True,
        })

    report = {"accounts": accounts}
    (ROOT / "reports/user_setup.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nLOCAL ACCOUNTS READY")
    for account in accounts:
        print(f"{account['username']}: {account['role']}")
    print("Passwords and hashes are excluded from this report.")


if __name__ == "__main__":
    main()
