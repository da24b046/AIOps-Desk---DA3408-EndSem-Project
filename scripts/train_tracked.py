"""Run baseline training and record its results in local MLflow."""

import json
import runpy
import subprocess
from pathlib import Path

import mlflow

ROOT = Path(__file__).resolve().parents[1]
TRACKING_URI = "http://127.0.0.1:5000"


def git_output(*arguments):
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True
    ).strip()


def main():
    mlflow.set_tracking_uri(TRACKING_URI)
    experiment = mlflow.set_experiment("AIOpsDesk-baselines")

    git_sha = git_output("rev-parse", "HEAD")
    git_dirty = bool(git_output("status", "--porcelain"))

    with mlflow.start_run(run_name="baseline_training") as parent:
        mlflow.set_tags({
            "git_sha": git_sha,
            "git_dirty": str(git_dirty).lower(),
            "dataset_kind": "synthetic",
            "evaluation_split": "validation",
            "test_set_used": "false",
        })

        # Training executes inside this parent run.
        runpy.run_path(
            str(ROOT / "scripts/train_baseline.py"),
            run_name="__main__",
        )

        report = json.loads(
            (ROOT / "reports/baseline_metrics.json").read_text(
                encoding="utf-8"
            )
        )
        config = report["config"]

        mlflow.log_params({
            "seed": config["seed"],
            "train_rows": report["train_rows"],
            "validation_rows": report["validation_rows"],
            "input_fields": ",".join(report["input_fields"]),
        })
        mlflow.set_tags({
            "train_sha256": report["input_hashes"]["train"],
            "validation_sha256": report["input_hashes"]["validation"],
            "config_sha256": report["config_sha256"],
        })

        for relative_path in (
            "configs/data.json",
            "configs/model.json",
            "data/metadata/source.json",
            "reports/data_preparation.json",
            "reports/data_splits.json",
            "reports/baseline_metrics.json",
            "requirements.txt",
            "scripts/train_baseline.py",
            "scripts/train_tracked.py",
        ):
            mlflow.log_artifact(
                str(ROOT / relative_path),
                artifact_path=(str(Path(relative_path).parent) if Path(relative_path).parent != Path(".") else None),
            )

        child_runs = {}

        for target, models in report["results"].items():
            for model_name, metrics in models.items():
                run_name = f"{target}_{model_name}"

                with mlflow.start_run(run_name=run_name, nested=True) as child:
                    mlflow.set_tags({
                        "target": target,
                        "model_family": model_name,
                        "evaluation_split": "validation",
                        "test_set_used": "false",
                    })
                    mlflow.log_params({
                        "target": target,
                        "model_family": model_name,
                        "train_rows": report["train_rows"],
                        "validation_rows": report["validation_rows"],
                    })
                    mlflow.log_metrics({
                        key: metrics[key]
                        for key in (
                            "accuracy", "macro_f1",
                            "weighted_f1", "fit_seconds"
                        )
                    })
                    mlflow.log_dict(metrics, "evaluation.json")

                    if model_name == "logistic_regression":
                        mlflow.log_params({
                            **config["logistic_regression"],
                            **{
                                f"tfidf_{key}": str(value)
                                for key, value in config["tfidf"].items()
                            },
                        })
                        mlflow.set_tag(
                            "artifact_sha256",
                            metrics["artifact_sha256"],
                        )
                        mlflow.log_artifact(
                            str(ROOT / f"artifacts/baseline/{target}.pkl"),
                            artifact_path="model_files",
                        )

                    child_runs[run_name] = child.info.run_id

        record = {
            "tracking_uri": TRACKING_URI,
            "experiment_id": experiment.experiment_id,
            "parent_run_id": parent.info.run_id,
            "child_run_ids": child_runs,
            "git_sha": git_sha,
            "git_dirty": git_dirty,
            "test_set_used": False,
        }
        destination = ROOT / "reports/mlflow_baseline.json"
        destination.write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        mlflow.log_dict(record, "lineage.json")

        print("\nMLFLOW TRACKING COMPLETE")
        print(json.dumps(record, indent=2))
        print(
            f"\nOpen: {TRACKING_URI}/#/experiments/"
            f"{experiment.experiment_id}"
        )


if __name__ == "__main__":
    main()
