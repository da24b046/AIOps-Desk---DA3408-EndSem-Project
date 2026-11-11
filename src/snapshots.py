"""Export approved feedback as content-addressed, non-overwritten snapshots."""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from src.feedback import connect

ROOT = Path(__file__).resolve().parents[1]


def export_snapshot(label_source, created_by, *, database_path=None):
    if label_source not in ("operator_review", "synthetic_demo"):
        raise ValueError("Unsupported label source.")

    cutoff = datetime.now(timezone.utc).isoformat()

    if database_path is None:
        connection = connect()
    else:
        selected_database = Path(database_path).resolve(strict=True)
        connection = sqlite3.connect(
            selected_database.as_uri() + "?mode=ro",
            uri=True,
            timeout=3,
        )
        connection.row_factory = sqlite3.Row

    with closing(connection) as database:
        database.execute("BEGIN")
        events = database.execute(
            """
            SELECT f.feedback_id, f.prediction_id, f.labels_json,
                   r.review_id, r.reviewed_at, r.reviewer_username,
                   p.redacted_input_json, p.model_version, p.policy_version
            FROM feedback AS f
            JOIN feedback_reviews AS r ON r.feedback_id = f.feedback_id
            JOIN predictions AS p ON p.prediction_id = f.prediction_id
            WHERE f.status = 'approved'
              AND r.decision = 'approved'
              AND f.label_source = ?
              AND f.created_at <= ?
              AND r.reviewed_at <= ?
            ORDER BY r.reviewed_at DESC, f.feedback_id DESC
            LIMIT 10001
            """,
            (label_source, cutoff, cutoff),
        ).fetchall()

    if len(events) > 10000:
        raise ValueError("Snapshot exceeds the current bounded export limit.")
    if not events:
        raise ValueError(
            f"No approved {label_source} feedback. No snapshot created."
        )

    records = {}

    for event in events:
        prediction_id = event["prediction_id"]

        if prediction_id not in records:
            text = json.loads(event["redacted_input_json"])
            records[prediction_id] = {
                "prediction_id": prediction_id,
                "subject": text["subject"],
                "description": text["description"],
                "original_model_version": event["model_version"],
                "original_policy_version": event["policy_version"],
                "label_source": label_source,
                "labels": {},
                "label_provenance": {},
            }

        record = records[prediction_id]

        for target, label in json.loads(event["labels_json"]).items():
            if target not in ("category", "priority"):
                raise ValueError("Unexpected feedback label field.")
            if target not in record["labels"]:
                record["labels"][target] = label
                record["label_provenance"][target] = {
                    "feedback_id": event["feedback_id"],
                    "review_id": event["review_id"],
                    "reviewer_username": event["reviewer_username"],
                    "reviewed_at": event["reviewed_at"],
                }

    rows = [records[key] for key in sorted(records)]
    content = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
        for row in rows
    ).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    snapshot_id = f"{label_source}-{digest[:16]}"
    directory = ROOT / "data/feedback" / snapshot_id

    if directory.exists():
        manifest = json.loads(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        existing_digest = hashlib.sha256(
            (directory / "rows.jsonl").read_bytes()
        ).hexdigest()
        if existing_digest != digest or manifest["rows_sha256"] != digest:
            raise ValueError("Existing snapshot failed its checksum check.")
        return directory, manifest, True

    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "label_source": label_source,
        "created_by": created_by,
        "cutoff": cutoff,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "unique_predictions": len(rows),
        "rows_sha256": digest,
        "selection_policy": "latest approved correction per prediction and label",
        "label_counts": {
            target: dict(Counter(
                row["labels"][target]
                for row in rows if target in row["labels"]
            ))
            for target in ("category", "priority")
        },
    }

    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(
        prefix=".snapshot-", dir=directory.parent
    ))

    try:
        (temporary / "rows.jsonl").write_bytes(content)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        os.rename(temporary, directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    return directory, manifest, False
