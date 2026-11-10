"""Train simple baselines and evaluate on validation data only."""

import hashlib
import json
import pickle
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


def main():
    config_path = ROOT / "configs/model.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    paths = {
        name: ROOT / f"data/splits/{name}.csv"
        for name in ("train", "validation")
    }
    train = pd.read_csv(paths["train"], keep_default_na=False)
    validation = pd.read_csv(paths["validation"], keep_default_na=False)

    assert set(train["ticket_id"]).isdisjoint(validation["ticket_id"])
    assert set(train["group_id"]).isdisjoint(validation["group_id"])

    # Only these two fields become model inputs.
    train_text = train["subject"] + "\n" + train["description"]
    validation_text = (
        validation["subject"] + "\n" + validation["description"]
    )

    report = {
        "evaluation_split": "validation",
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_set_used": False,
        "input_fields": ["subject", "description"],
        "config": config,
        "versions": {
            package: version(package)
            for package in ("pandas", "scikit-learn")
        },
        "input_hashes": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in paths.items()
        },
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "results": {},
    }

    artifacts = ROOT / "artifacts/baseline"
    artifacts.mkdir(parents=True, exist_ok=True)
    summary = []

    for target in ("category", "priority"):
        tfidf_options = dict(config["tfidf"])
        tfidf_options["ngram_range"] = tuple(tfidf_options["ngram_range"])

        models = {
            "majority": DummyClassifier(strategy="most_frequent"),
            "logistic_regression": Pipeline([
                ("tfidf", TfidfVectorizer(**tfidf_options)),
                ("classifier", LogisticRegression(
                    **config["logistic_regression"],
                    random_state=config["seed"],
                )),
            ]),
        }
        report["results"][target] = {}

        for name, model in models.items():
            start = perf_counter()
            model.fit(train_text, train[target])
            fit_seconds = perf_counter() - start
            predicted = model.predict(validation_text)
            labels = sorted(train[target].unique().tolist())

            metrics = {
                "accuracy": float(accuracy_score(
                    validation[target], predicted
                )),
                "macro_f1": float(f1_score(
                    validation[target], predicted,
                    average="macro", zero_division=0
                )),
                "weighted_f1": float(f1_score(
                    validation[target], predicted,
                    average="weighted", zero_division=0
                )),
                "fit_seconds": fit_seconds,
                "labels": labels,
                "confusion_matrix": confusion_matrix(
                    validation[target], predicted, labels=labels
                ).tolist(),
                "classification_report": classification_report(
                    validation[target], predicted,
                    labels=labels, output_dict=True, zero_division=0
                ),
            }
            report["results"][target][name] = metrics
            summary.append({
                "target": target,
                "model": name,
                **{
                    key: metrics[key]
                    for key in ("accuracy", "macro_f1", "weighted_f1")
                },
            })

            if name == "logistic_regression":
                # Save preprocessing and classifier together.
                destination = artifacts / f"{target}.pkl"
                destination.write_bytes(pickle.dumps(model))
                metrics["artifact_sha256"] = hashlib.sha256(
                    destination.read_bytes()
                ).hexdigest()

                print(f"\n{target.upper()} — VALIDATION REPORT")
                print(classification_report(
                    validation[target], predicted,
                    labels=labels, zero_division=0
                ))

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "baseline_metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nVALIDATION COMPARISON")
    print(pd.DataFrame(summary).to_string(index=False, float_format="%.4f"))
    print("\nSaved category and priority pipelines.")
    print("Test set used: False")


if __name__ == "__main__":
    main()
