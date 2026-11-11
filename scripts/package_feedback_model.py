"""Package the feedback candidate for an explicitly labelled exercise."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import cloudpickle
import mlflow
import pandas as pd
from mlflow.models import infer_signature
from sklearn.metrics import accuracy_score, f1_score

import scripts.package_model as packaging

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = ROOT / "artifacts/serving/feedback-demo-001"
    if destination.exists():
        raise SystemExit("Bundle already exists; refusing to overwrite.")

    training_path = ROOT / "reports/feedback_candidate_metrics.json"
    training = json.loads(training_path.read_text())
    decision = json.loads(
        (ROOT / "reports/promotion_decision.json").read_text()
    )
    original = json.loads(
        (ROOT / "reports/candidate_metrics.json").read_text()
    )

    assert training["candidate_id"] == "feedback-demo-001"
    assert training["label_source"] == "synthetic_demo"
    assert decision["candidate_report_sha256"] == sha(training_path)
    assert decision["candidate_id"] == training["candidate_id"]
    assert decision["decision"] == "keep_current_model"

    for package, expected in original["versions"].items():
        assert version(package) == expected, f"{package} version changed."

    validation_path = ROOT / "data/splits/validation.csv"
    assert sha(validation_path) == training["input_hashes"]["validation"]
    validation = pd.read_csv(validation_path, keep_default_na=False)
    inputs = validation[["subject", "description"]]

    source = ROOT / training["artifact_directory"]
    for target in ("category", "priority"):
        assert sha(source / f"{target}.pkl") == training["artifact_hashes"][target]

    metadata_path = ROOT / "reports/feedback_serving_metadata.json"
    metadata = {
        "candidate_id": training["candidate_id"],
        "label_source": training["label_source"],
        "exercise_only": True,
        "models": {
            target: {
                "artifact_sha256": training["artifact_hashes"][target]
            }
            for target in ("category", "priority")
        },
    }
    artifacts = {
        target: str(source / f"{target}.pkl")
        for target in ("category", "priority")
    }
    artifacts["metadata"] = str(metadata_path)

    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("AIOpsDesk-feedback-demo")

    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    wrapper = packaging.TicketModel()
    wrapper.load_context(SimpleNamespace(artifacts=artifacts))
    expected = wrapper.predict(None, inputs)

    serving_metrics = {
        "accuracy": float(accuracy_score(
            validation["category"], expected["category"]
        )),
        "macro_f1": float(f1_score(
            validation["category"], expected["category"],
            average="macro", zero_division=0,
        )),
    }
    for name, value in serving_metrics.items():
        assert abs(
            value - training["category_validation_after"][name]
        ) < 1e-12, f"Serving preprocessing changed category {name}."

    # Include the wrapper implementation in the serialized bundle,
    # so the serving container does not need the scripts package.
    cloudpickle.register_pickle_by_value(packaging)
    try:
        with mlflow.start_run(run_name="package_feedback_demo_001") as run:
            mlflow.set_tags({
                "model_version": "feedback-demo-001",
                "label_source": "synthetic_demo",
                "exercise_only": "true",
                "promotion_decision": "keep_current_model",
                "test_set_used": "false",
            })

            mlflow.pyfunc.save_model(
                path=str(destination),
                python_model=packaging.TicketModel(),
                artifacts=artifacts,
                signature=infer_signature(inputs, expected),
                input_example=inputs.head(3),
                pip_requirements=[
                    f"{package}=={version(package)}"
                    for package in (
                        "mlflow", "pandas", "scikit-learn", "cloudpickle"
                    )
                ],
            )

            restored = mlflow.pyfunc.load_model(str(destination))
            actual = restored.predict(inputs)
            pd.testing.assert_frame_equal(
                expected, actual,
                check_exact=False, rtol=1e-12, atol=1e-12,
            )
            assert set(actual["model_version"]) == {"feedback-demo-001"}

            report = {
                "model_version": "feedback-demo-001",
                "bundle_path": str(destination.relative_to(ROOT)),
                "mlflow_run_id": run.info.run_id,
                "training_report_sha256": sha(training_path),
                "metadata_sha256": sha(metadata_path),
                "validation_rows_checked": len(inputs),
                "category_serving_metrics": serving_metrics,
                "saved_bundle_parity": True,
                "exercise_only": True,
                "promotion_decision": "keep_current_model",
                "test_set_used": False,
                "deployment_attempted": False,
            }
            report_path = ROOT / "reports/feedback_model_package.json"
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

            mlflow.log_metrics({
                f"validation_category_{name}": value
                for name, value in serving_metrics.items()
            })
            mlflow.log_artifacts(
                str(destination), artifact_path="serving_bundle"
            )
            for path in (
                report_path,
                training_path,
                ROOT / "reports/promotion_decision.json",
                Path(__file__).resolve(),
            ):
                mlflow.log_artifact(str(path))

            print("FEEDBACK SERVING BUNDLE VERIFIED")
            print(json.dumps(report, indent=2))
    finally:
        cloudpickle.unregister_pickle_by_value(packaging)


if __name__ == "__main__":
    main()
