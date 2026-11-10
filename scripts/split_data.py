"""Create deterministic grouped splits without fitting model features."""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

ROOT = Path(__file__).resolve().parents[1]
SEED = 42
SIMILARITY_THRESHOLD = 0.85


def main():
    source = ROOT / "data/processed/tickets_clean.csv"
    output = ROOT / "data/splits"
    report_path = ROOT / "reports/data_splits.json"

    if any(output.glob("*.csv")) or report_path.exists():
        raise SystemExit("Splits already exist. Stopping to preserve them.")

    df = pd.read_csv(source, keep_default_na=False)
    assert df["ticket_id"].is_unique, "Duplicate ticket IDs found."

    # Connect descriptions with at least 85% token-set overlap.
    tokens = [
        set(re.findall(r"\w+", text.casefold()))
        for text in df["description"]
    ]
    assert all(tokens), "A description has no usable tokens."
    parents = list(range(len(df)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    similar_pairs = 0
    for i in range(len(df)):
        for j in range(i):
            similarity = len(tokens[i] & tokens[j]) / len(tokens[i] | tokens[j])
            if similarity >= SIMILARITY_THRESHOLD:
                parents[root(i)] = root(j)
                similar_pairs += 1

    df["group_id"] = [f"group_{root(i):04d}" for i in range(len(df))]

    # Select by split size and label balance only, never model scores.
    def balance_score(parts):
        score = 0.0
        for part, fraction in zip(parts, (0.6, 0.2, 0.2)):
            score += abs(len(part) / len(df) - fraction)
            for field in ("category", "priority"):
                if set(part[field]) != set(df[field]):
                    return float("inf")
                reference = df[field].value_counts(normalize=True)
                observed = part[field].value_counts(normalize=True)
                score += (reference - observed).abs().sum()
        return score

    best = None
    best_score = float("inf")
    outer = GroupShuffleSplit(
        n_splits=100, test_size=0.2, random_state=SEED
    )

    for attempt, (remaining_ids, test_ids) in enumerate(
        outer.split(df, groups=df["group_id"])
    ):
        remaining = df.iloc[remaining_ids]
        inner = GroupShuffleSplit(
            n_splits=1, test_size=0.25, random_state=SEED + attempt
        )
        train_ids, validation_ids = next(
            inner.split(remaining, groups=remaining["group_id"])
        )
        parts = (
            remaining.iloc[train_ids],
            remaining.iloc[validation_ids],
            df.iloc[test_ids],
        )
        score = balance_score(parts)
        if score < best_score:
            best, best_score = parts, score

    if best is None:
        raise SystemExit("Could not create splits with all labels present.")

    names = ("train", "validation", "test")
    for i in range(3):
        for j in range(i):
            for field in ("ticket_id", "group_id"):
                assert set(best[i][field]).isdisjoint(best[j][field])

    assert sum(len(part) for part in best) == len(df)

    report = {
        "seed": SEED,
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "similarity_method": "description token-set Jaccard",
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "similar_pairs": similar_pairs,
        "groups": int(df["group_id"].nunique()),
        "largest_group": int(df["group_id"].value_counts().max()),
        "checks": {
            "ticket_ids_disjoint": True,
            "detected_groups_disjoint": True,
            "all_rows_assigned": True,
            "all_labels_present_in_each_split": True,
        },
        "splits": {},
    }

    output.mkdir(parents=True, exist_ok=True)
    assignments = []

    for name, part in zip(names, best):
        part = part.sort_values("ticket_id")
        part.to_csv(output / f"{name}.csv", index=False)
        assignments.append(
            part[["ticket_id", "group_id"]].assign(split=name)
        )
        report["splits"][name] = {
            "rows": len(part),
            "percentage": round(100 * len(part) / len(df), 2),
            "category_counts": {
                key: int(value)
                for key, value in part["category"].value_counts().items()
            },
            "priority_counts": {
                key: int(value)
                for key, value in part["priority"].value_counts().items()
            },
        }

    pd.concat(assignments).sort_values("ticket_id").to_csv(
        output / "assignments.csv", index=False
    )
    report_path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
