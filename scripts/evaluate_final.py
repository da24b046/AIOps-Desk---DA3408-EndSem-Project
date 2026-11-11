"""Evaluate the frozen serving bundle on the held-out test set once."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import mlflow
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
)

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / "reports/final_test_evaluation.json"
    if output.exists():
        raise SystemExit(
            "Final test report already exists. Preserve it; do not repeat tuning."
        )

    bundle_path = ROOT / "artifacts/serving/candidate-001-explained"
    policy_path = ROOT / "configs/policy.json"
    settings_path = ROOT / "configs/selected_models.json"
    policy = json.loads(policy_path.read_text())
    settings = json.loads(settings_path.read_text())

    paths = {
        split: ROOT / f"data/splits/{split}.csv"
        for split in ("train", "validation", "test")
    }
    frozen_inputs = {
        **{split: sha(path) for split, path in paths.items()},
        "policy": sha(policy_path),
        "selected_settings": sha(settings_path),
        "evaluation_code": sha(Path(__file__).resolve()),
        "bundle_files": {
            str(path.relative_to(bundle_path)): sha(path)
            for path in sorted(bundle_path.rglob("*"))
            if path.is_file()
        },
    }
    plan_path = ROOT / "reports/final_evaluation_plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        assert plan["frozen_inputs"] == frozen_inputs, "Frozen inputs changed."
    else:
        plan = {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "git_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()),
            "model_version": policy["expected_model_version"],
            "policy_version": policy["policy_version"],
            "frozen_inputs": frozen_inputs,
            "review_thresholds": policy["review_thresholds"],
        }
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    splits = {
        split: pd.read_csv(path, keep_default_na=False)
        for split, path in paths.items()
    }
    for left, right in (
        ("train", "validation"), ("train", "test"), ("validation", "test")
    ):
        for field in ("ticket_id", "group_id"):
            assert set(splits[left][field]).isdisjoint(splits[right][field])

    test = splits["test"]
    inputs = test[["subject", "description"]]
    bundle = mlflow.pyfunc.load_model(str(bundle_path))
    wrapper = bundle.unwrap_python_model()
    predictions = bundle.predict(inputs).reset_index(drop=True)

    assert len(predictions) == len(test)
    assert set(predictions["model_version"]) == {policy["expected_model_version"]}

    normalized_text = [
        wrapper.normalize(row["subject"]) + "\n" + wrapper.normalize(row["description"])
        for row in inputs.to_dict("records")
    ]

    above_thresholds = pd.Series(True, index=predictions.index)
    for field, threshold in policy["review_thresholds"].items():
        above_thresholds &= predictions[field] >= threshold

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_split": "test",
        "test_rows": len(test),
        "model_version": policy["expected_model_version"],
        "policy_version": policy["policy_version"],
        "evaluation_plan_sha256": sha(plan_path),
        "split_ids_and_detected_groups_disjoint": True,
        "input_fields": ["subject", "description"],
        "versions": {
            package: version(package)
            for package in ("pandas", "scikit-learn", "mlflow")
        },
        "review_policy": {
            "thresholds": policy["review_thresholds"],
            "above_both_thresholds_rows": int(above_thresholds.sum()),
            "requires_review_rows": int((~above_thresholds).sum()),
            "above_both_thresholds_fraction": float(above_thresholds.mean()),
        },
        "models": {},
        "test_set_used": True,
        "retrained": False,
        "deployment_attempted": False,
        "limitations": [
            "Small held-out sample from a synthetic dataset.",
            "Model scores have not been calibrated.",
            "These results do not establish real-world service-desk performance.",
        ],
    }

    for target in ("category", "priority"):
        model = wrapper.models[target]
        classifier = model.named_steps["classifier"]
        assert classifier.C == settings["models"][target]["C"]
        assert classifier.random_state == settings["seed"]

        labels = model.classes_.tolist()
        truth = test[target]
        predicted = predictions[target]
        probabilities = model.predict_proba(normalized_text)
        majority = splits["train"][target].mode().iloc[0]

        details = {
            "accuracy": float(accuracy_score(truth, predicted)),
            "balanced_accuracy": float(balanced_accuracy_score(truth, predicted)),
            "macro_f1": float(f1_score(
                truth, predicted, labels=labels, average="macro", zero_division=0
            )),
            "weighted_f1": float(f1_score(
                truth, predicted, labels=labels, average="weighted", zero_division=0
            )),
            "log_loss": float(log_loss(truth, probabilities, labels=labels)),
            "majority_baseline_macro_f1": float(f1_score(
                truth, [majority] * len(test),
                labels=labels, average="macro", zero_division=0,
            )),
            "class_support": {
                label: int((truth == label).sum()) for label in labels
            },
            "classification_report": classification_report(
                truth, predicted, labels=labels,
                output_dict=True, zero_division=0,
            ),
            "confusion_matrix_labels": labels,
            "confusion_matrix": confusion_matrix(
                truth, predicted, labels=labels
            ).tolist(),
            "accuracy_above_both_review_thresholds": (
                float(accuracy_score(
                    truth[above_thresholds], predicted[above_thresholds]
                )) if above_thresholds.any() else None
            ),
        }
        report["models"][target] = details

    output.write_text(json.dumps(report, indent=2) + "\n")

    print("FINAL HELD-OUT EVALUATION COMPLETE")
    print("Test rows:", len(test))
    for target, values in report["models"].items():
        print(
            f"{target}: accuracy={values['accuracy']:.4f}, "
            f"macro-F1={values['macro_f1']:.4f}, "
            f"majority macro-F1={values['majority_baseline_macro_f1']:.4f}"
        )
        print("  Class support:", values["class_support"])
    print("Review policy:", report["review_policy"])
    print("Retrained: False")
    print("Deployment attempted: False")
    print("Saved:", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
