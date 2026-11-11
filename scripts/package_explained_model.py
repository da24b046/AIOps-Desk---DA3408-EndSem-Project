"""Add explanations to the original fitted models without retraining."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cloudpickle
import mlflow
import pandas as pd
from mlflow.models import infer_signature

import scripts.package_model as packaging
import src.linear_explanations as explanations

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExplainedTicketModel(packaging.TicketModel):
    def predict(self, context, model_input, params=None):
        result = super().predict(context, model_input, params)
        details = []

        for ticket in model_input.to_dict("records"):
            try:
                text = (
                    self.normalize(ticket["subject"])
                    + "\n"
                    + self.normalize(ticket["description"])
                )
                explanation = {
                    "status": "available",
                    **{
                        target: explanations.explain_pipeline(model, text)
                        for target, model in self.models.items()
                    },
                }
            except Exception:
                # Explanation failure must not discard successful inference.
                explanation = {
                    "status": "unavailable",
                    "category": None,
                    "priority": None,
                }
            details.append(json.dumps(explanation, allow_nan=False))

        result["explanation_json"] = details
        return result


def main():
    destination = ROOT / "artifacts/serving/candidate-001-explained"
    if destination.exists():
        raise SystemExit("Bundle already exists; refusing to overwrite.")

    original_metadata = json.loads(
        (ROOT / "reports/candidate_metrics.json").read_text()
    )
    validation_path = ROOT / "data/splits/validation.csv"
    assert sha(validation_path) == original_metadata["input_hashes"]["validation"]
    inputs = pd.read_csv(
        validation_path,
        usecols=["subject", "description"],
        keep_default_na=False,
    )

    metadata = {
        "candidate_id": "candidate-001",
        "bundle_version": "explanations-001",
        "models": {},
    }
    artifacts = {}
    for target in ("category", "priority"):
        path = ROOT / f"artifacts/candidate/{target}.pkl"
        digest = sha(path)
        assert digest == original_metadata["models"][target]["artifact_sha256"]
        artifacts[target] = str(path)
        metadata["models"][target] = {"artifact_sha256": digest}

    metadata_path = ROOT / "reports/explained_serving_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    artifacts["metadata"] = str(metadata_path)

    original = mlflow.pyfunc.load_model(
        str(ROOT / "artifacts/serving/candidate-001")
    ).predict(inputs)

    wrapper = ExplainedTicketModel()
    wrapper.load_context(SimpleNamespace(artifacts=artifacts))
    expected = wrapper.predict(None, inputs)

    pd.testing.assert_frame_equal(
        original, expected[original.columns],
        check_exact=False, rtol=1e-12, atol=1e-12,
    )
    assert expected["explanation_json"].map(
        lambda value: json.loads(value)["status"] == "available"
    ).all()

    modules = (packaging, explanations)
    for module in modules:
        cloudpickle.register_pickle_by_value(module)
    try:
        mlflow.pyfunc.save_model(
            path=str(destination),
            python_model=ExplainedTicketModel(),
            artifacts=artifacts,
            signature=infer_signature(inputs, expected),
            input_example=inputs.head(1),
            pip_requirements=(
                ROOT / "deploy/docker/requirements-model.txt"
            ).read_text().splitlines(),
        )
    finally:
        for module in modules:
            cloudpickle.unregister_pickle_by_value(module)

    restored = mlflow.pyfunc.load_model(str(destination)).predict(inputs)
    pd.testing.assert_frame_equal(
        expected, restored, check_exact=False, rtol=1e-12, atol=1e-12
    )

    report = {
        "model_version": "candidate-001",
        "bundle_version": "explanations-001",
        "bundle_path": str(destination.relative_to(ROOT)),
        "validation_rows_checked": len(inputs),
        "prediction_and_score_parity": True,
        "saved_bundle_parity": True,
        "all_explanations_available": True,
        "fitted_artifact_hashes": {
            target: metadata["models"][target]["artifact_sha256"]
            for target in ("category", "priority")
        },
        "explanation_code_sha256": sha(ROOT / "src/linear_explanations.py"),
        "test_set_used": False,
        "retrained": False,
    }
    (ROOT / "reports/explained_model_package.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print("EXPLAINED BUNDLE VERIFIED")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
