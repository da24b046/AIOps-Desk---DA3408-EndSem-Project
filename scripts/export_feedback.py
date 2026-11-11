"""Export a feedback snapshot after verifying the maintainer password."""

import argparse
import json
from getpass import getpass
from pathlib import Path

from src.auth import verify_user
from src.snapshots import ROOT, export_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=("operator_review", "synthetic_demo"),
        default="operator_review",
    )
    args = parser.parse_args()

    password = getpass("Maintainer password: ")
    user = verify_user("maintainer", password)
    del password

    if user is None or user["role"] != "maintainer":
        raise SystemExit("Maintainer authentication failed.")

    try:
        directory, manifest, reused = export_snapshot(
            args.source, user["username"]
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None

    report = {
        "snapshot_directory": str(directory.relative_to(ROOT)),
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
