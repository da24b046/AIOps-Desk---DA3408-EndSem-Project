"""Compare original and restored datasets/models by SHA-256."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    "data/raw",
    "data/processed",
    "data/splits",
    "artifacts/baseline",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/verify_restore.py RESTORED_REPO")

    restored = Path(sys.argv[1]).resolve()
    results = []

    for directory in DIRECTORIES:
        original_files = {
            path.relative_to(ROOT)
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
        }
        restored_files = {
            path.relative_to(restored)
            for path in (restored / directory).rglob("*")
            if path.is_file()
        }

        if not original_files or original_files != restored_files:
            raise SystemExit(f"File inventory mismatch: {directory}")

        for relative in sorted(original_files):
            expected = digest(ROOT / relative)
            actual = digest(restored / relative)

            if expected != actual:
                raise SystemExit(f"Checksum mismatch: {relative}")

            results.append({
                "file": str(relative),
                "sha256": actual,
                "matches": True,
            })
            print("MATCH:", relative)

    report = {
        "check": "artifact_restore",
        "restored_repository": str(restored),
        "files_verified": len(results),
        "all_checksums_match": True,
        "files": results,
    }
    destination = ROOT / "reports/restore_check.json"
    destination.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\nRESTORE PASSED: {len(results)} files match.")
    print("Report saved: reports/restore_check.json")


if __name__ == "__main__":
    main()
