"""Evaluate pipeline candidates on validation data and record gate decisions."""

import hashlib
import json
import math
import pickle
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score

ROOT = Path(__file__).resolve().parents[1]


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    acceptance_path = ROOT / "configs/pipeline_acceptance.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    assert acceptance["evaluation_split"] == "validation"

    candidate = ROOT / "artifacts/pipeline_candidate"
    manifest_path = candidate / "training_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assignments_path = ROOT / "data/splits/assignments.csv"
    assert checksum(assignments_path) == manifest["assignments_sha256"]
    assert checksum(ROOT / "configs/selected_models.json") == (
        manifest["config_sha256"]
    )
    for package, expected in manifest["versions"].items():
        assert version(package) == expected, f"{package} version changed."

    assignments = pd.read_csv(
        assignments_path,
        dtype={"ticket_id": str, "group_id": str, "split": str},
        keep_default_na=False,
    )
    data = pd.read_parquet(ROOT / "data/spark/tickets.parquet")

    assert data["ticket_id"].is_unique
    assert assignments["ticket_id"].is_unique
    assert set(data["ticket_id"]) == set(assignments["ticket_id"])
    assert assignments.groupby("group_id")["split"].nunique().max() == 1

    def select_split(name):
        ids = assignments.loc[assignments["split"] == name, "ticket_id"]
        selected = data[data["ticket_id"].isin(ids)].sort_values("ticket_id")
        assert len(selected) == len(ids) and len(selected) > 0
        return selected.reset_index(drop=True)

    train = select_split("train")
    validation = select_split("validation")
    assert set(train["ticket_id"]).isdisjoint(validation["ticket_id"])

    training_digest = hashlib.sha256(
        "\n".join(train["ticket_id"]).encode("utf-8")
    ).hexdigest()
    assert training_digest == manifest["training_ids_sha256"]

    text = validation["subject"] + "\n" + validation["description"]
    report = {
        "evaluation_split": "validation",
        "validation_rows": len(validation),
        "test_set_used": False,
        "training_manifest_sha256": checksum(manifest_path),
        "acceptance_config_sha256": checksum(acceptance_path),
        "models": {},
    }

    for target in ("category", "priority"):
        model_path = candidate / f"{target}.pkl"
        assert checksum(model_path) == (
            manifest["models"][target]["artifact_sha256"]
        )

        model = pickle.loads(model_path.read_bytes())
        predicted = model.predict(text)
        probabilities = model.predict_proba(text)
        labels = set(model.classes_)

        baseline = DummyClassifier(strategy="most_frequent")
        baseline.fit([[0]] * len(train), train[target])
        baseline_predicted = baseline.predict([[0]] * len(validation))

        macro_f1 = float(f1_score(
            validation[target], predicted,
            average="macro", zero_division=0,
        ))
        baseline_f1 = float(f1_score(
            validation[target], baseline_predicted,
            average="macro", zero_division=0,
        ))

        valid_probabilities = all(
            math.isfinite(float(value)) and 0 <= value <= 1
            for row in probabilities for value in row
        ) and all(
            abs(float(total) - 1) <= acceptance["probability_sum_tolerance"]
            for total in probabilities.sum(axis=1)
        )

        checks = {
            "macro_f1_beats_majority": (
                macro_f1 - baseline_f1
                > acceptance["minimum_macro_f1_gain_over_majority"]
            ),
            "validation_has_all_model_classes": (
                set(validation[target]) == labels
            ),
            "all_classes_predicted": (
                not acceptance["require_all_classes_predicted"]
                or set(predicted) == labels
            ),
            "valid_probabilities": bool(valid_probabilities),
        }

        report["models"][target] = {
            "accuracy": float(accuracy_score(validation[target], predicted)),
            "macro_f1": macro_f1,
            "majority_macro_f1": baseline_f1,
            "classification_report": classification_report(
                validation[target], predicted,
                output_dict=True, zero_division=0,
            ),
            "checks": checks,
            "gate_passed": all(checks.values()),
        }

    report["gate_passed"] = all(
        result["gate_passed"] for result in report["models"].values()
    )

    report_path = ROOT / "reports/pipeline_evaluation.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nPIPELINE VALIDATION RESULTS")
    for target, result in report["models"].items():
        print(
            f"{target}: macro-F1={result['macro_f1']:.4f}, "
            f"majority={result['majority_macro_f1']:.4f}, "
            f"gate_passed={result['gate_passed']}"
        )
        for name, passed in result["checks"].items():
            print(f"  {name}: {passed}")

    print("Test set used: False")
    print("QUALITY GATE:", "PASSED" if report["gate_passed"] else "REJECTED")

    if not report["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
