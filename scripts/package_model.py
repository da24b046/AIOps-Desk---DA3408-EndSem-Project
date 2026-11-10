"""Package category and priority pipelines behind one MLflow interface."""

import hashlib
import json
import pickle
import re
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import mlflow
import pandas as pd
from mlflow.models import infer_signature
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parents[1]


class TicketModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        metadata_path = Path(context.artifacts["metadata"])
        self.metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )
        self.models = {}

        for target in ("category", "priority"):
            content = Path(context.artifacts[target]).read_bytes()
            expected = self.metadata["models"][target]["artifact_sha256"]
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f"{target} artifact checksum mismatch.")
            self.models[target] = pickle.loads(content)

    @staticmethod
    def normalize(value):
        value = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[EMAIL]",
            value,
        )
        return re.sub(r"\s+", " ", value).strip()

    def predict(self, context, model_input, params=None):
        for field in ("subject", "description"):
            if field not in model_input:
                raise ValueError(f"Missing field: {field}")
            if not model_input[field].map(
                lambda value: isinstance(value, str) and bool(value.strip())
            ).all():
                raise ValueError(f"{field} must contain nonempty text.")

        subject = model_input["subject"].map(self.normalize)
        description = model_input["description"].map(self.normalize)
        text = subject + "\n" + description

        output = {}
        for target, model in self.models.items():
            output[target] = model.predict(text)
            output[f"{target}_score"] = model.predict_proba(text).max(axis=1)

        result = pd.DataFrame(output)
        result["model_version"] = self.metadata["candidate_id"]
        return result


def main():
    destination = ROOT / "artifacts/serving/candidate-001"
    if destination.exists():
        raise SystemExit("Serving bundle already exists; not overwriting.")

    metadata_path = ROOT / "reports/candidate_metrics.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    for package, expected in metadata["versions"].items():
        assert version(package) == expected, (
            f"{package} changed since candidate training."
        )

    validation_path = ROOT / "data/splits/validation.csv"
    assert hashlib.sha256(validation_path.read_bytes()).hexdigest() == (
        metadata["input_hashes"]["validation"]
    ), "Validation data changed since candidate training."

    validation = pd.read_csv(validation_path, keep_default_na=False)
    inputs = validation[["subject", "description"]]

    artifacts = {
        "category": str(ROOT / "artifacts/candidate/category.pkl"),
        "priority": str(ROOT / "artifacts/candidate/priority.pkl"),
        "metadata": str(metadata_path),
    }

    wrapper = TicketModel()
    wrapper.load_context(SimpleNamespace(artifacts=artifacts))
    expected = wrapper.predict(None, inputs)

    for target in ("category", "priority"):
        score = f1_score(
            validation[target], expected[target],
            average="macro", zero_division=0,
        )
        assert abs(score - metadata["models"][target]["macro_f1"]) < 1e-9

    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("AIOpsDesk-packaging")

    with mlflow.start_run(run_name="package_candidate_001") as run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        mlflow.pyfunc.save_model(
            path=str(destination),
            python_model=TicketModel(),
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

        loaded = mlflow.pyfunc.load_model(str(destination))
        actual = loaded.predict(inputs)
        pd.testing.assert_frame_equal(
            expected, actual, check_exact=False, rtol=1e-12, atol=1e-12
        )

        report = {
            "model_version": metadata["candidate_id"],
            "bundle_path": str(destination.relative_to(ROOT)),
            "mlflow_run_id": run.info.run_id,
            "validation_rows_checked": len(inputs),
            "saved_bundle_parity": True,
            "test_set_used": False,
        }
        report_path = ROOT / "reports/model_package.json"
        report_path.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

        mlflow.set_tags({
            "model_version": metadata["candidate_id"],
            "test_set_used": "false",
        })
        mlflow.log_param("validation_rows_checked", len(inputs))
        mlflow.log_artifacts(str(destination), artifact_path="serving_bundle")
        mlflow.log_artifact(str(report_path))
        mlflow.log_artifact(str(ROOT / "scripts/package_model.py"))

        print("\nMODEL PACKAGE VERIFIED")
        print(json.dumps(report, indent=2))
        print("\nExample outputs:")
        print(actual.head(3).to_string(index=False))


if __name__ == "__main__":
    main()
