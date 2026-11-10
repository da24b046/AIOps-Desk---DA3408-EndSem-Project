"""Fit selected settings and verify saved candidate pipelines."""

import hashlib
import json
import pickle
import subprocess
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config_path = ROOT / "configs/selected_models.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    search_path = ROOT / "reports/ray_search.json"
    search = json.loads(search_path.read_text(encoding="utf-8"))

    assert checksum(search_path) == config["source_report_sha256"], (
        "Ray report changed after settings were selected."
    )

    destination = ROOT / "artifacts/candidate"
    if destination.exists():
        raise SystemExit(
            "Candidate directory already exists. Stopping to avoid overwriting."
        )

    paths = {
        name: ROOT / f"data/splits/{name}.csv"
        for name in ("train", "validation")
    }
    train = pd.read_csv(paths["train"], keep_default_na=False)
    validation = pd.read_csv(paths["validation"], keep_default_na=False)

    assert set(train["ticket_id"]).isdisjoint(validation["ticket_id"])
    assert set(train["group_id"]).isdisjoint(validation["group_id"])

    train_text = train["subject"] + "\n" + train["description"]
    validation_text = validation["subject"] + "\n" + validation["description"]

    report = {
        "candidate_id": "candidate-001",
        "artifact_directory": str(destination.relative_to(ROOT)),
        "selection_config_sha256": checksum(config_path),
        "ray_parent_run_id": config["ray_parent_run_id"],
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()),
        "input_hashes": {
            name: checksum(path) for name, path in paths.items()
        },
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_set_used": False,
        "versions": {
            name: version(name) for name in ("pandas", "scikit-learn")
        },
        "models": {},
    }
    fitted = {}

    for target in ("category", "priority"):
        vectorizer = dict(config["tfidf"])
        vectorizer["ngram_range"] = tuple(vectorizer["ngram_range"])

        model = Pipeline([
            ("tfidf", TfidfVectorizer(**vectorizer)),
            ("classifier", LogisticRegression(
                **config["models"][target],
                random_state=config["seed"],
            )),
        ])
        model.fit(train_text, train[target])
        predicted = model.predict(validation_text)
        macro_f1 = float(f1_score(
            validation[target], predicted,
            average="macro", zero_division=0
        ))

        expected = search["best_validation_settings"][target]["macro_f1"]
        assert abs(macro_f1 - expected) < 1e-9, (
            f"{target}: validation result differs from selected Ray trial."
        )

        # Verify serialization before writing any candidate files.
        serialized = pickle.dumps(model)
        restored = pickle.loads(serialized)
        assert (restored.predict(validation_text) == predicted).all()
        fitted[target] = serialized

        report["models"][target] = {
            "C": config["models"][target]["C"],
            "accuracy": float(accuracy_score(validation[target], predicted)),
            "macro_f1": macro_f1,
            "classification_report": classification_report(
                validation[target], predicted,
                output_dict=True, zero_division=0
            ),
            "artifact_sha256": hashlib.sha256(serialized).hexdigest(),
            "saved_pipeline_prediction_parity": True,
        }

    destination.mkdir(parents=True)

    for target, content in fitted.items():
        (destination / f"{target}.pkl").write_bytes(content)

    report_path = ROOT / "reports/candidate_metrics.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nSELECTED MODELS VERIFIED")
    for target, metrics in report["models"].items():
        print(
            f"{target}: C={metrics['C']}, "
            f"accuracy={metrics['accuracy']:.4f}, "
            f"macro-F1={metrics['macro_f1']:.4f}"
        )
    print("Saved pipeline prediction parity: PASSED")
    print("Test set used: False")
    print("Candidate directory:", destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
