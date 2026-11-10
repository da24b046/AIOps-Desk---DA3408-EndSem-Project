"""Run six bounded Ray Tune trials and record results in MLflow."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path
from time import perf_counter

# Limit numerical-library threads in the driver and inherited workers.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import mlflow
import pandas as pd
import ray
from ray import tune
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


def train_trial(config, project_root, model_config):
    root = Path(project_root)
    train = pd.read_csv(root / "data/splits/train.csv", keep_default_na=False)
    validation = pd.read_csv(
        root / "data/splits/validation.csv", keep_default_na=False
    )
    assert set(train["ticket_id"]).isdisjoint(validation["ticket_id"])
    assert set(train["group_id"]).isdisjoint(validation["group_id"])

    vectorizer = dict(model_config["tfidf"])
    vectorizer["ngram_range"] = tuple(vectorizer["ngram_range"])
    classifier = dict(model_config["logistic_regression"])
    classifier["C"] = config["C"]

    model = Pipeline([
        ("tfidf", TfidfVectorizer(**vectorizer)),
        ("classifier", LogisticRegression(
            **classifier, random_state=model_config["seed"]
        )),
    ])

    train_text = train["subject"] + "\n" + train["description"]
    validation_text = validation["subject"] + "\n" + validation["description"]

    started = perf_counter()
    model.fit(train_text, train[config["target"]])
    fit_seconds = perf_counter() - started
    predicted = model.predict(validation_text)

    tune.report({
        "accuracy": float(accuracy_score(
            validation[config["target"]], predicted
        )),
        "macro_f1": float(f1_score(
            validation[config["target"]], predicted,
            average="macro", zero_division=0
        )),
        "fit_seconds": fit_seconds,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-ui", action="store_true")
    args = parser.parse_args()

    search_config = json.loads(
        (ROOT / "configs/ray.json").read_text(encoding="utf-8")
    )
    model_config = json.loads(
        (ROOT / "configs/model.json").read_text(encoding="utf-8")
    )

    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("AIOpsDesk-ray-search")

    try:
        ray.init(
            num_cpus=search_config["num_cpus"],
            object_store_memory=128 * 1024 * 1024,
            include_dashboard=True,
            dashboard_host="127.0.0.1",
            dashboard_port=8265,
            _node_ip_address="127.0.0.1",
        )

        with mlflow.start_run(run_name="ray_parameter_search") as parent:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
            git_dirty = bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip())
            mlflow.set_tags({
                "git_sha": git_sha,
                "git_dirty": str(git_dirty).lower(),
                "test_set_used": "false",
                "evaluation_split": "validation",
            })
            for name in ("train", "validation"):
                path = ROOT / f"data/splits/{name}.csv"
                mlflow.set_tag(
                    f"{name}_sha256",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )

            trainable = tune.with_parameters(
                train_trial,
                project_root=str(ROOT),
                model_config=model_config,
            )
            tuner = tune.Tuner(
                tune.with_resources(trainable, {"cpu": 1}),
                param_space={
                    "target": tune.grid_search(search_config["targets"]),
                    "C": tune.grid_search(search_config["C_values"]),
                },
                tune_config=tune.TuneConfig(
                    max_concurrent_trials=search_config[
                        "max_concurrent_trials"
                    ],
                ),
                run_config=tune.RunConfig(
                    name=f"search_{parent.info.run_id}",
                    storage_path=str(ROOT / "state/ray/results"),
                    verbose=1,
                ),
            )
            results = tuner.fit()
            records = []

            for result in results:
                if result.error:
                    raise RuntimeError(
                        f"Ray trial failed: {result.config}"
                    ) from result.error

                record = {
                    "target": result.config["target"],
                    "C": result.config["C"],
                    **{
                        key: float(result.metrics[key])
                        for key in ("accuracy", "macro_f1", "fit_seconds")
                    },
                }
                with mlflow.start_run(
                    run_name=f"{record['target']}_C_{record['C']}",
                    nested=True,
                ) as child:
                    mlflow.log_params({
                        "target": record["target"],
                        "C": record["C"],
                        "model_config": json.dumps(model_config),
                    })
                    mlflow.log_metrics({
                        key: record[key]
                        for key in ("accuracy", "macro_f1", "fit_seconds")
                    })
                    mlflow.set_tags({
                        "executor": "ray_tune",
                        "evaluation_split": "validation",
                        "test_set_used": "false",
                    })
                    record["mlflow_run_id"] = child.info.run_id
                records.append(record)

            expected = (
                len(search_config["targets"])
                * len(search_config["C_values"])
            )
            assert len(records) == expected

            best = {}
            for target in search_config["targets"]:
                candidates = [
                    row for row in records if row["target"] == target
                ]
                best[target] = sorted(
                    candidates, key=lambda row: (-row["macro_f1"], row["C"])
                )[0]

            report = {
                "parent_run_id": parent.info.run_id,
                "ray_version": ray.__version__,
                "test_set_used": False,
                "search_config": search_config,
                "trials": records,
                "best_validation_settings": best,
            }
            report_path = ROOT / "reports/ray_search.json"
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

            mlflow.log_params(search_config)
            for relative in (
                "configs/ray.json",
                "configs/model.json",
                "scripts/ray_search.py",
                "requirements.txt",
                "reports/ray_search.json",
            ):
                mlflow.log_artifact(str(ROOT / relative))

        print("\nRAY SEARCH PASSED")
        table = pd.DataFrame(records).drop(columns=["mlflow_run_id"])
        print(table.to_string(index=False, float_format="%.4f"))
        print("\nBEST VALIDATION SETTINGS")
        for target, row in best.items():
            print(f"{target}: C={row['C']}, macro-F1={row['macro_f1']:.4f}")
        print("\nTest set used: False")
        print("Ray dashboard: http://127.0.0.1:8265")

        if args.inspect_ui:
            print("Inspect the dashboard, then press Ctrl+C once to stop Ray.")
            try:
                while True:
                    signal.pause()
            except KeyboardInterrupt:
                print("\nEnding dashboard inspection.")

    finally:
        ray.shutdown()
        print("Ray shut down.")


if __name__ == "__main__":
    main()
