"""Prepare a small ticket dataset without modifying the raw snapshot."""

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def clean_text(value):
    value = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL]",
        value,
    )
    return re.sub(r"\s+", " ", value).strip()


def main():
    config = json.loads(
        (ROOT / "configs/data.json").read_text(encoding="utf-8")
    )

    with (ROOT / "data/raw/tickets.csv").open(
        encoding="utf-8-sig", newline=""
    ) as source:
        rows = list(csv.DictReader(source))

    retained = []
    exclusions = []
    seen = set()

    for row in rows:
        reason = None

        if row["category"] not in config["categories"]:
            reason = "excluded_category"
        elif row["priority"] not in config["priorities"]:
            reason = "excluded_priority"
        else:
            subject = clean_text(row["subject"])
            description = clean_text(row["description"])
            key = (subject.casefold(), description.casefold())

            if not subject or not description:
                reason = "empty_text_after_cleaning"
            elif key in seen:
                reason = "duplicate_cleaned_text"
            else:
                seen.add(key)
                retained.append({
                    "ticket_id": row["id"],
                    "subject": subject,
                    "description": description,
                    "category": row["category"],
                    "priority": row["priority"],
                })

        if reason:
            exclusions.append({
                "ticket_id": row["id"],
                "reason": reason,
            })

    if not retained:
        raise SystemExit("No tickets retained. Check the configuration.")

    output = ROOT / "data/processed"
    output.mkdir(parents=True, exist_ok=True)

    with (output / "tickets_clean.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=list(retained[0]))
        writer.writeheader()
        writer.writerows(retained)

    with (output / "excluded_rows.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=["ticket_id", "reason"])
        writer.writeheader()
        writer.writerows(exclusions)

    report = {
        "input_rows": len(rows),
        "retained_rows": len(retained),
        "excluded_rows": len(exclusions),
        "exclusion_reasons": dict(Counter(
            row["reason"] for row in exclusions
        )),
        "category_counts": dict(Counter(
            row["category"] for row in retained
        )),
        "priority_counts": dict(Counter(
            row["priority"] for row in retained
        )),
        "model_input_fields": ["subject", "description"],
        "config": config,
    }

    assert len(rows) == len(retained) + len(exclusions)

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "data_preparation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
