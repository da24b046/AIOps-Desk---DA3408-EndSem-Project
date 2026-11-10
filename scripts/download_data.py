"""Download a pinned dataset snapshot and print a basic inspection."""

import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATASET = "Console-AI/IT-helpdesk-synthetic-tickets"
DESTINATION = ROOT / "data/raw/tickets.csv"
MANIFEST = ROOT / "data/metadata/source.json"


def fetch(url):
    with urlopen(url, timeout=60) as response:
        return response.read()


def main():
    if DESTINATION.exists() or MANIFEST.exists():
        raise SystemExit(
            "Dataset or manifest already exists. Stopping to avoid overwriting."
        )

    # Resolve the current revision, then download that exact revision.
    metadata_url = f"https://huggingface.co/api/datasets/{DATASET}"
    metadata = json.loads(fetch(metadata_url))
    revision = metadata["sha"]
    download_url = (
        f"https://huggingface.co/datasets/{DATASET}"
        f"/resolve/{revision}/tickets.csv"
    )

    print("Downloading dataset revision:", revision)
    content = fetch(download_url)

    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    columns = reader.fieldnames or []
    rows = list(reader)

    required = {"id", "subject", "description", "category", "priority"}
    if not required.issubset(columns):
        raise SystemExit(f"Unexpected columns: {columns}")
    if not rows:
        raise SystemExit("Downloaded CSV contains no records.")

    digest = hashlib.sha256(content).hexdigest()
    manifest = {
        "dataset": DATASET,
        "source_url": f"https://huggingface.co/datasets/{DATASET}",
        "revision": revision,
        "download_url": download_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": digest,
        "bytes": len(content),
        "rows": len(rows),
        "columns": columns,
        "license": metadata.get("cardData", {}).get("license"),
    }

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_bytes(content)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("\nRows:", len(rows))
    print("Columns:", ", ".join(columns))
    print("Size:", len(content), "bytes")
    print("SHA-256:", digest)

    for field in ("category", "priority"):
        print(f"\n{field.upper()} COUNTS")
        counts = Counter(row[field].strip() for row in rows)
        for label, count in counts.most_common():
            print(f"  {label or '[EMPTY]'}: {count}")

    print("\nMISSING REQUIRED VALUES")
    for field in sorted(required):
        missing = sum(not row[field].strip() for row in rows)
        print(f"  {field}: {missing}")

    ids = [row["id"].strip() for row in rows]
    texts = [
        (row["subject"].strip(), row["description"].strip())
        for row in rows
    ]
    print("\nDuplicate IDs:", len(ids) - len(set(ids)))
    print("Duplicate subject/description pairs:", len(texts) - len(set(texts)))
    print("\nSaved:", DESTINATION.relative_to(ROOT))
    print("Saved:", MANIFEST.relative_to(ROOT))


if __name__ == "__main__":
    main()
