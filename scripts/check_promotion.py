"""Evaluate a feedback candidate without changing the deployed model."""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    policy_path = ROOT / "configs/promotion.json"
    report_path = ROOT / "reports/feedback_candidate_metrics.json"
    policy = json.loads(policy_path.read_text())
    candidate = json.loads(report_path.read_text())
    directory = ROOT / candidate["artifact_directory"]

    before = candidate["category_validation_before"]
    after = candidate["category_validation_after"]

    for metrics in (before, after):
        for name in ("accuracy", "macro_f1"):
            value = metrics[name]
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid metric: {name}")

    improvement = after["macro_f1"] - before["macro_f1"]
    checks = {
        "candidate_artifacts_match_recorded_hashes": all(
            sha(directory / f"{target}.pkl")
            == candidate["artifact_hashes"][target]
            for target in ("category", "priority")
        ),
        "original_category_matches_recorded_hash": (
            sha(ROOT / "artifacts/candidate/category.pkl")
            == candidate["input_hashes"]["original_category"]
        ),
        "original_priority_matches_recorded_hash": (
            sha(ROOT / "artifacts/candidate/priority.pkl")
            == candidate["input_hashes"]["original_priority"]
        ),
        "training_data_matches_recorded_hash": (
            sha(ROOT / "data/splits/train.csv")
            == candidate["input_hashes"]["train"]
        ),
        "validation_data_matches_recorded_hash": (
            sha(ROOT / "data/splits/validation.csv")
            == candidate["input_hashes"]["validation"]
        ),
        "required_feedback_source": (
            candidate["label_source"] == policy["required_label_source"]
        ),
        "minimum_macro_f1_improvement": (
            improvement
            >= policy["minimum_category_macro_f1_improvement"]
        ),
        "accuracy_requirement": (
            policy["allow_category_accuracy_regression"]
            or after["accuracy"] >= before["accuracy"]
        ),
        "priority_artifact_unchanged": (
            candidate["priority_artifact_unchanged"]
            and sha(directory / "priority.pkl")
            == candidate["input_hashes"]["original_priority"]
        ),
        "serialization_verified": (
            candidate["saved_pipeline_prediction_parity"] is True
        ),
        "test_set_not_used": candidate["test_set_used"] is False,
    }

    eligible = all(checks.values())
    decision = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": policy["policy_version"],
        "policy_sha256": sha(policy_path),
        "candidate_report_sha256": sha(report_path),
        "candidate_id": candidate["candidate_id"],
        "category_macro_f1_improvement": improvement,
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
        "eligible_for_promotion": eligible,
        "decision": "eligible_for_review" if eligible else "keep_current_model",
        "deployment_attempted": False,
    }

    output = ROOT / "reports/promotion_decision.json"
    output.write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )

    print("PROMOTION DECISION")
    print("Candidate:", candidate["candidate_id"])
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'BLOCK'}: {name}")
    print("Decision:", decision["decision"])
    print("Deployment attempted: False")
    print("Report:", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
