"""Build a separate candidate using approved synthetic demonstration feedback."""

import hashlib
import json
import pickle
import subprocess
from pathlib import Path

import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score, f1_score

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(model, texts, labels):
    predictions = model.predict(texts)
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(
            labels, predictions, average="macro", zero_division=0
        )),
    }


def main():
    destination = ROOT / "artifacts/feedback_candidate"
    if destination.exists():
        raise SystemExit("Feedback candidate already exists; refusing to overwrite.")

    export = json.loads(
        (ROOT / "reports/feedback_snapshot.json").read_text()
    )
    snapshot = ROOT / export["snapshot_directory"]
    manifest = json.loads((snapshot / "manifest.json").read_text())
    verification = json.loads(
        (ROOT / "reports/feedback_training_check.json").read_text()
    )
    rows_path = snapshot / "rows.jsonl"

    assert sha(rows_path) == manifest["rows_sha256"]
    assert verification["rows_sha256"] == manifest["rows_sha256"]
    assert verification["snapshot_id"] == manifest["snapshot_id"]
    assert verification["eligible_for_demo_training"] is True
    assert verification["heldout_overlaps"] == []
    assert manifest["label_source"] == "synthetic_demo"

    rows = [
        json.loads(line)
        for line in rows_path.read_text().splitlines() if line.strip()
    ]
    assert rows and len(rows) == manifest["unique_predictions"]
    assert len({row["prediction_id"] for row in rows}) == len(rows)

    # This demonstration supports category-only corrections.
    for row in rows:
        assert row["label_source"] == "synthetic_demo"
        assert set(row["labels"]) == {"category"}
        assert row["label_provenance"]["category"]["review_id"]

    train_path = ROOT / "data/splits/train.csv"
    validation_path = ROOT / "data/splits/validation.csv"
    train = pd.read_csv(train_path, keep_default_na=False)
    validation = pd.read_csv(validation_path, keep_default_na=False)

    original_report = json.loads(
        (ROOT / "reports/candidate_metrics.json").read_text()
    )
    assert sha(train_path) == original_report["input_hashes"]["train"]
    assert sha(validation_path) == original_report["input_hashes"]["validation"]
    assert set(train["ticket_id"]).isdisjoint(validation["ticket_id"])
    assert set(train["group_id"]).isdisjoint(validation["group_id"])

    train_text = (train["subject"] + "\n" + train["description"]).tolist()
    validation_text = validation["subject"] + "\n" + validation["description"]
    extra_text = [
        row["subject"] + "\n" + row["description"] for row in rows
    ]
    extra_labels = [row["labels"]["category"] for row in rows]

    def normalized(text):
        return " ".join(text.lower().split())

    extra_keys = [normalized(text) for text in extra_text]
    assert len(set(extra_keys)) == len(extra_keys), "Duplicate feedback text."
    assert set(extra_keys).isdisjoint(
        normalized(text) for text in train_text
    ), "Feedback duplicates an original training ticket."

    category_path = ROOT / "artifacts/candidate/category.pkl"
    priority_path = ROOT / "artifacts/candidate/priority.pkl"

    # Load only our own locally generated model artifact.
    original = pickle.loads(category_path.read_bytes())
    assert set(extra_labels).issubset(set(original.classes_))

    candidate = clone(original)
    candidate.fit(
        train_text + extra_text,
        train["category"].tolist() + extra_labels,
    )

    before = metrics(original, validation_text, validation["category"])
    after = metrics(candidate, validation_text, validation["category"])

    serialized = pickle.dumps(candidate)
    restored = pickle.loads(serialized)
    assert (
        restored.predict(validation_text)
        == candidate.predict(validation_text)
    ).all()

    priority_bytes = priority_path.read_bytes()
    destination.mkdir(parents=True)
    (destination / "category.pkl").write_bytes(serialized)
    (destination / "priority.pkl").write_bytes(priority_bytes)

    report = {
        "candidate_id": "feedback-demo-001",
        "artifact_directory": str(destination.relative_to(ROOT)),
        "purpose": "synthetic_feedback_retraining_demonstration",
        "snapshot_id": manifest["snapshot_id"],
        "snapshot_rows_sha256": manifest["rows_sha256"],
        "label_source": "synthetic_demo",
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()),
        "input_hashes": {
            "train": sha(train_path),
            "validation": sha(validation_path),
            "original_category": sha(category_path),
            "original_priority": sha(priority_path),
        },
        "category_training_rows": len(train) + len(rows),
        "approved_category_rows_added": len(rows),
        "priority_retrained": False,
        "priority_artifact_unchanged": (
            sha(destination / "priority.pkl") == sha(priority_path)
        ),
        "validation_rows": len(validation),
        "category_validation_before": before,
        "category_validation_after": after,
        "category_macro_f1_change": after["macro_f1"] - before["macro_f1"],
        "artifact_hashes": {
            name: sha(destination / f"{name}.pkl")
            for name in ("category", "priority")
        },
        "saved_pipeline_prediction_parity": True,
        "test_set_used": False,
        "deployment_attempted": False,
    }

    (ROOT / "reports/feedback_candidate_metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("FEEDBACK CANDIDATE TRAINING PASSED")
    print("Candidate: feedback-demo-001")
    print("Category training rows:", report["category_training_rows"])
    print("Approved category rows added:", len(rows))
    print(f"Category validation macro-F1 before: {before['macro_f1']:.4f}")
    print(f"Category validation macro-F1 after:  {after['macro_f1']:.4f}")
    print("Priority artifact unchanged:", report["priority_artifact_unchanged"])
    print("Saved pipeline prediction parity: PASSED")
    print("Test set used: False")
    print("Deployment attempted: False")


if __name__ == "__main__":
    main()
