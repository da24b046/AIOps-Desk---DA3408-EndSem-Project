import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads(
        (ROOT / "configs/drift.json").read_text(encoding="utf-8")
    )
    source = ROOT / config["reference_data"]
    data = pd.read_csv(source, keep_default_na=False)

    required = {"subject", "description"}
    if not required.issubset(data.columns):
        raise ValueError(f"Missing columns: {required - set(data.columns)}")
    if len(data) < config["minimum_current_rows"]:
        raise ValueError("Not enough training rows to build a reference.")

    # Use the same text construction in the upcoming drift checker.
    texts = (
        data["subject"].astype(str).str.strip()
        + " "
        + data["description"].astype(str).str.strip()
    ).str.strip()

    token_pattern = re.compile(config["token_pattern"])
    vocabulary = sorted({
        token.lower()
        for text in texts
        for token in token_pattern.findall(text)
    })
    lengths = [len(text) for text in texts]

    reference = {
        "reference_version": "drift-reference-001",
        "source": config["reference_data"],
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "rows": len(data),
        "text_construction": "stripped subject + space + stripped description",
        "token_pattern": config["token_pattern"],
        "text_lengths": lengths,
        "vocabulary": vocabulary,
        "test_set_used": False,
    }

    output = ROOT / "artifacts/drift/reference.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(reference, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "reference_version": reference["reference_version"],
        "source": reference["source"],
        "source_sha256": reference["source_sha256"],
        "training_rows": len(data),
        "vocabulary_size": len(vocabulary),
        "text_length_min": min(lengths),
        "text_length_median": float(pd.Series(lengths).median()),
        "text_length_max": max(lengths),
        "reference_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "test_set_used": False,
    }

    report = ROOT / "reports/drift_reference.json"
    report.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print("DRIFT REFERENCE CREATED")
    print(json.dumps(summary, indent=2))
    print("Reference:", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
