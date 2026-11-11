import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy.stats import ks_2samp

ROOT = Path(__file__).resolve().parents[1]


def assess(data, reference, config):
    required = {"subject", "description"}
    if not required.issubset(data.columns):
        raise ValueError("Input must contain subject and description.")

    if len(data) < config["minimum_current_rows"]:
        return {
            "rows": len(data),
            "status": "insufficient_data",
            "drift_detected": None,
        }

    texts = (
        data["subject"].astype(str).str.strip()
        + " "
        + data["description"].astype(str).str.strip()
    ).str.strip()

    pattern = re.compile(reference["token_pattern"])
    vocabulary = set(reference["vocabulary"])
    token_count = 0
    unknown_count = 0

    for text in texts:
        tokens = [token.lower() for token in pattern.findall(text)]
        token_count += len(tokens)
        unknown_count += sum(token not in vocabulary for token in tokens)

    if not token_count:
        return {
            "rows": len(data),
            "status": "no_usable_tokens",
            "drift_detected": None,
        }

    lengths = texts.str.len().tolist()
    distance = float(
        ks_2samp(reference["text_lengths"], lengths).statistic
    )
    unknown_fraction = unknown_count / token_count

    signals = {
        "text_length": distance > config["text_length_ks_threshold"],
        "unfamiliar_vocabulary": (
            unknown_fraction > config["unknown_token_fraction_threshold"]
        ),
    }

    return {
        "rows": len(data),
        "status": "evaluated",
        "text_length_ks_distance": distance,
        "unknown_token_fraction": unknown_fraction,
        "signals": signals,
        "drift_detected": any(signals.values()),
    }


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--synthetic-demo", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config_path = ROOT / "configs/drift.json"
    reference_path = ROOT / "artifacts/drift/reference.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    reference = json.loads(reference_path.read_text(encoding="utf-8"))

    if config["token_pattern"] != reference["token_pattern"]:
        raise ValueError("Token pattern differs from the saved reference.")

    if args.synthetic_demo:
        unfamiliar_text = (
            "zygomatrix quasarflux nebulacore xenowave plasmagrid "
            "orbitmesh cryovault photonweave "
        )
        data = pd.DataFrame({
            "subject": ["Synthetic vocabulary shift"] * 81,
            "description": [unfamiliar_text * 40] * 81,
        })
        batch = {
            "kind": "synthetic_shift_demo",
            "source": "generated_in_memory",
        }
    else:
        data = pd.read_csv(args.input, keep_default_na=False)
        batch = {
            "kind": "csv_batch",
            "source": str(args.input),
            "sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        }

    result = assess(data, reference, config)
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reference_version": reference["reference_version"],
        "reference_sha256": hashlib.sha256(
            reference_path.read_bytes()
        ).hexdigest(),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "batch": batch,
        "thresholds": {
            "minimum_current_rows": config["minimum_current_rows"],
            "text_length_ks": config["text_length_ks_threshold"],
            "unknown_token_fraction": config["unknown_token_fraction_threshold"],
        },
        "result": result,
        "retraining_triggered": False,
        "model_changed": False,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("DRIFT CHECK")
    print("Batch:", batch["kind"])
    print(json.dumps(result, indent=2))
    print("Retraining triggered: False")
    print("Model changed: False")
    print("Report:", args.output)


if __name__ == "__main__":
    main()
