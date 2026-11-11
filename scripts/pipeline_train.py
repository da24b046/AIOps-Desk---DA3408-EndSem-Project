"""Train separate pipeline candidates from Spark data and frozen split IDs."""

import hashlib
import json
import pickle
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config_path = ROOT / "configs/selected_models.json"
    assignments_path = ROOT / "data/splits/assignments.csv"

    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = pd.read_parquet(ROOT / "data/spark/tickets.parquet")
    assignments = pd.read_csv(
        assignments_path,
        dtype={"ticket_id": str, "group_id": str, "split": str},
        keep_default_na=False,
    )

    assert 0 < len(data) <= 10000, "Unexpected dataset size."
    assert data["ticket_id"].is_unique
    assert assignments["ticket_id"].is_unique
    assert set(data["ticket_id"]) == set(assignments["ticket_id"])
    assert set(assignments["split"]) == {"train", "validation", "test"}
    assert assignments.groupby("group_id")["split"].nunique().max() == 1

    # Split membership is fixed; no new random split is generated.
    training_ids = assignments.loc[
        assignments["split"] == "train", "ticket_id"
    ]
    train = (
        data[data["ticket_id"].isin(training_ids)]
        .sort_values("ticket_id")
        .reset_index(drop=True)
    )
    assert len(train) == len(training_ids)

    text = train["subject"] + "\n" + train["description"]
    destination = ROOT / "artifacts/pipeline_candidate"
    models = {}
    manifest = {
        "purpose": "working candidate; not deployed",
        "source": "Spark Parquet with frozen training IDs",
        "train_rows": len(train),
        "training_ids_sha256": hashlib.sha256(
            "\n".join(train["ticket_id"]).encode("utf-8")
        ).hexdigest(),
        "assignments_sha256": checksum(assignments_path),
        "config_sha256": checksum(config_path),
        "test_set_used_for_training_or_evaluation": False,
        "versions": {
            package: version(package)
            for package in ("pandas", "scikit-learn", "pyarrow")
        },
        "models": {},
    }

    for target in ("category", "priority"):
        assert train[target].nunique() >= 2
        vectorizer = dict(config["tfidf"])
        vectorizer["ngram_range"] = tuple(vectorizer["ngram_range"])

        model = Pipeline([
            ("tfidf", TfidfVectorizer(**vectorizer)),
            ("classifier", LogisticRegression(
                **config["models"][target],
                random_state=config["seed"],
            )),
        ])
        model.fit(text, train[target])
        content = pickle.dumps(model)
        models[target] = content

        manifest["models"][target] = {
            "parameters": config["models"][target],
            "classes": model.classes_.tolist(),
            "artifact_sha256": hashlib.sha256(content).hexdigest(),
        }

    destination.mkdir(parents=True, exist_ok=True)

    for target, content in models.items():
        (destination / f"{target}.pkl").write_bytes(content)

    (destination / "training_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print("\nPIPELINE TRAINING PASSED")
    print("Training rows:", len(train))
    for target in models:
        print(f"{target}: C={config['models'][target]['C']}")
    print("Output:", destination.relative_to(ROOT))
    print("Test set used for training or evaluation: False")


if __name__ == "__main__":
    main()
