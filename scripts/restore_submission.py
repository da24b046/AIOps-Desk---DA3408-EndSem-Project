"""Restore bundled data/model objects after cloning this repository.

Run with the project environment: python scripts/restore_submission.py
Only local state/DVC configuration and DVC-owned outputs are written.
"""

import configparser
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "reproducibility/dvc-store.tar.gz"
EXPECTED_SHA256 = "764562649d78fbdf9a28b189904b5fce98046a75c9da7305c23842131ff7f56f"
REMOTE_NAME = "submission-bundle"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_dvc(*arguments):
    subprocess.run([sys.executable, "-m", "dvc", *arguments], cwd=ROOT, check=True)


def main():
    if not BUNDLE.is_file() or digest(BUNDLE) != EXPECTED_SHA256:
        raise SystemExit("Bundled DVC backup is missing or its checksum does not match.")

    state = ROOT / "state"
    state.mkdir(exist_ok=True)
    destination = state / ("submission-dvc-store-" + EXPECTED_SHA256[:12])
    with tarfile.open(BUNDLE, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts
                    or path.parts[:2] != ("files", "md5")):
                raise SystemExit("Unexpected path/type in the bundled DVC backup.")

        if destination.exists():
            for member in members:
                existing = destination / member.name
                expected = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                if not existing.is_file() or digest(existing) != expected:
                    raise SystemExit("Extracted store differs from the bundle; restore into a clean checkout.")
        else:
            pending = Path(tempfile.mkdtemp(prefix="dvc-restore-", dir=state))
            try:
                archive.extractall(pending, filter="data")
                pending.rename(destination)
            finally:
                if pending.exists():
                    shutil.rmtree(pending)

    config = configparser.ConfigParser()
    config.read([ROOT / ".dvc/config", ROOT / ".dvc/config.local"])
    arguments = ["remote", "add", "--local", "--force"]
    if not config.get("core", "remote", fallback=None):
        arguments.append("--default")
    run_dvc(*arguments, REMOTE_NAME, str(destination))
    run_dvc("pull", "--remote", REMOTE_NAME)

    expected_files = json.loads((ROOT / "reports/final_restore_check.json").read_text())["file_sha256"]
    for name, expected in expected_files.items():
        path = ROOT / name
        if not path.is_file() or digest(path) != expected:
            raise SystemExit(f"Restored file does not match: {name}")
    run_dvc("status")
    print(f"REPOSITORY-ONLY RESTORE PASSED: {len(expected_files)} data/model files match.")


if __name__ == "__main__":
    main()
