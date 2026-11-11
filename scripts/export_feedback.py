"""Export approved feedback after verifying a maintainer account."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from getpass import getpass
from pathlib import Path

from src.auth import PASSWORD_HASH, verify_user
from src.snapshots import ROOT, export_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=("operator_review", "synthetic_demo"),
        default="operator_review",
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Explicit SQLite backup; opened read-only.",
    )
    parser.add_argument("--username", default="maintainer")
    args = parser.parse_args()

    selected_database = (
        args.database.resolve(strict=True) if args.database else None
    )

    password = getpass("Maintainer password: ")
    try:
        if selected_database is None:
            user = verify_user(args.username, password)
        else:
            with closing(sqlite3.connect(
                selected_database.as_uri() + "?mode=ro",
                uri=True,
                timeout=3,
            )) as database:
                database.row_factory = sqlite3.Row
                row = database.execute(
                    "SELECT username, password_hash, role FROM users "
                    "WHERE username = ?",
                    (args.username,),
                ).fetchone()

            user = None
            if row is not None and PASSWORD_HASH.verify(
                password, row["password_hash"]
            ):
                user = {"username": row["username"], "role": row["role"]}
    finally:
        del password

    if user is None or user["role"] != "maintainer":
        raise SystemExit("Maintainer authentication failed.")

    try:
        directory, manifest, reused = export_snapshot(
            args.source,
            user["username"],
            database_path=selected_database,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None

    report = {
        "snapshot_directory": str(directory.relative_to(ROOT)),
        "database_source": (
            "explicit_sqlite_backup"
            if selected_database else "default_local_database"
        ),
        "database_backup_sha256": (
            hashlib.sha256(selected_database.read_bytes()).hexdigest()
            if selected_database else None
        ),
        "reused": reused,
        "manifest": manifest,
    }
    (ROOT / "reports/feedback_snapshot.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nFEEDBACK SNAPSHOT READY")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
