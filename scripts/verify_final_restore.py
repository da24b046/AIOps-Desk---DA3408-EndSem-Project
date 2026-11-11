"""Compare all declared DVC-owned outputs with a fresh restored checkout."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def output_roots(root):
    outputs = set()
    for folder in ("data", "artifacts"):
        for pointer in (root / folder).rglob("*.dvc"):
            specification = yaml.safe_load(pointer.read_text())
            for output in specification.get("outs", []):
                path = (pointer.parent / output["path"]).resolve()
                outputs.add(path.relative_to(root))

    pipeline = yaml.safe_load((root / "dvc.yaml").read_text())
    for stage in pipeline["stages"].values():
        for output in stage.get("outs", []):
            if isinstance(output, dict):
                if len(output) != 1:
                    raise ValueError("Unexpected DVC stage output specification.")
                output = next(iter(output))
            outputs.add((root / output).resolve().relative_to(root))
    return sorted(outputs)


def inventory(root, outputs):
    records = {}
    for relative in outputs:
        path = root / relative
        if not path.exists():
            raise ValueError(f"Declared output is missing: {relative}")
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for file in files:
            records[file.relative_to(root).as_posix()] = sha(file)
    return records


def git(root, *arguments):
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("restore_directory", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    source = args.source.resolve()
    restored = args.restore_directory.resolve()
    if source == restored:
        raise SystemExit("Use a separate restored checkout.")

    outputs = output_roots(source)
    assert outputs == output_roots(restored), "DVC output declarations differ."
    expected = inventory(source, outputs)
    actual = inventory(restored, outputs)
    mismatches = sorted(
        name for name in expected.keys() | actual.keys()
        if expected.get(name) != actual.get(name)
    )
    source_commit = git(source, "rev-parse", "HEAD")
    restored_commit = git(restored, "rev-parse", "HEAD")
    assert source_commit == restored_commit, "Checkout commits differ."
    assert not git(restored, "status", "--porcelain", "--untracked-files=all"), (
        "Restored checkout has unexpected changes."
    )

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "restored_commit": restored_commit,
        "declared_output_roots": [path.as_posix() for path in outputs],
        "files_compared": len(expected),
        "mismatches": mismatches,
        "all_files_match": not mismatches,
        "restored_checkout_clean": True,
        "file_sha256": expected,
        "scope": "Git checkout plus DVC-owned data/models; application database is separate",
    }
    (source / "reports/final_restore_check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if mismatches:
        raise SystemExit(f"RESTORE FAILED: {len(mismatches)} mismatches. See report.")
    print("FINAL DVC RESTORE PASSED")
    print("Source commit:", source_commit)
    print("Declared output roots:", len(outputs))
    print("Files matched:", len(expected))
    print("Restored checkout: clean")
    print("Report: reports/final_restore_check.json")


if __name__ == "__main__":
    main()
