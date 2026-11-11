"""Execute the existing DVC pipeline inside an MLflow Project run."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import mlflow

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()

    run_id = os.environ.get("MLFLOW_RUN_ID")
    if not run_id:
        raise SystemExit("Launch this entry point using 'mlflow run'.")

    command = ["dvc", "repro"]
    if args.force:
        command.append("--force")
    command.append("evaluate")

    evidence = ROOT / "evidence/mlproject" / run_id
    evidence.mkdir(parents=True, exist_ok=True)
    log_path = evidence / "pipeline.log"

    with mlflow.start_run(run_id=run_id):
        mlflow.set_tags({
            "workflow": "MLflow Project invoking DVC pipeline",
            "environment_manager": "local",
            "test_set_used": "false",
            "deployment_attempted": "false",
        })
        mlflow.log_params({
            "category_C": 2.0,
            "priority_C": 0.5,
            "pipeline_target": "evaluate",
        })

        print("Running:", " ".join(command), flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

        print(log_path.read_text(encoding="utf-8"))
        mlflow.log_artifact(str(log_path), artifact_path="execution")

        if result.returncode:
            raise RuntimeError(
                f"DVC pipeline failed with exit code {result.returncode}."
            )

        evaluation_path = ROOT / "reports/pipeline_evaluation.json"
        evaluation = json.loads(evaluation_path.read_text())
        assert evaluation["gate_passed"] is True
        assert evaluation["evaluation_split"] == "validation"
        assert evaluation["test_set_used"] is False

        for target, values in evaluation["models"].items():
            mlflow.log_metrics({
                f"validation_{target}_accuracy": values["accuracy"],
                f"validation_{target}_macro_f1": values["macro_f1"],
            })

        report = {
            "mlflow_run_id": run_id,
            "tracking_uri": mlflow.get_tracking_uri(),
            "entry_point": "main",
            "environment_manager": "local",
            "python_version": sys.version,
            "force_requested": bool(args.force),
            "command": command,
            "pipeline_exit_code": result.returncode,
            "validation_rows": evaluation["validation_rows"],
            "quality_gate_passed": True,
            "dvc_lock_sha256": sha(ROOT / "dvc.lock"),
            "requirements_sha256": sha(ROOT / "requirements.txt"),
            "git_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "git_dirty": bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()),
            "test_set_used": False,
            "deployment_attempted": False,
        }
        report_path = ROOT / "reports/mlproject_run.json"
        report_path.write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

        for relative in (
            "MLproject",
            "scripts/run_mlproject.py",
            "requirements.txt",
            "configs/selected_models.json",
            "dvc.yaml",
            "dvc.lock",
            "reports/pipeline_evaluation.json",
            "reports/mlproject_run.json",
        ):
            mlflow.log_artifact(str(ROOT / relative), artifact_path="provenance")

        mlflow.log_artifacts(
            str(ROOT / "artifacts/pipeline_candidate"),
            artifact_path="pipeline_candidate",
        )

        print("MLFLOW PROJECT PASSED")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
