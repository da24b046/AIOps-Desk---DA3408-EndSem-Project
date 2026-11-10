"""Clean tickets with Spark and verify parity with Python preparation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

from pyspark.sql import SparkSession, functions as F

ROOT = Path(__file__).resolve().parents[1]
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"


def clean_text(column):
    redacted = F.regexp_replace(F.col(column), EMAIL_PATTERN, "[EMAIL]")
    return F.trim(F.regexp_replace(redacted, r"(?U)\s+", " "))


def read_csv(spark, path, schema):
    return (
        spark.read.schema(schema)
        .option("header", True)
        .option("multiLine", True)
        .option("escape", '"')
        .option("mode", "FAILFAST")
        .csv(str(path))
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-ui", action="store_true")
    args = parser.parse_args()

    config = json.loads(
        (ROOT / "configs/data.json").read_text(encoding="utf-8")
    )
    source = ROOT / "data/raw/tickets.csv"
    destination = ROOT / "data/spark/tickets.parquet"
    manifest = json.loads(
        (ROOT / "data/metadata/source.json").read_text(encoding="utf-8")
    )

    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    started = perf_counter()
    spark = (
        SparkSession.builder.appName("AIOpsDesk-Ticket-ETL")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    startup_seconds = perf_counter() - started
    spark.sparkContext.setLogLevel("WARN")

    try:
        etl_started = perf_counter()

        raw = read_csv(
            spark,
            source,
            "id STRING, subject STRING, description STRING, "
            "priority STRING, category STRING, createdAt STRING, "
            "requesterEmail STRING",
        )
        raw_count = raw.count()
        assert raw_count == manifest["rows"], "Raw row count mismatch."

        category_filtered = raw.filter(
            F.col("category").isin(config["categories"])
        )
        category_count = category_filtered.count()

        clean = (
            category_filtered
            .filter(F.col("priority").isin(config["priorities"]))
            .select(
                F.col("id").alias("ticket_id"),
                clean_text("subject").alias("subject"),
                clean_text("description").alias("description"),
                "category",
                "priority",
            )
        )

        invalid = clean.filter(
            F.col("ticket_id").isNull()
            | (F.trim(F.col("ticket_id")) == "")
            | F.col("subject").isNull()
            | (F.col("subject") == "")
            | F.col("description").isNull()
            | (F.col("description") == "")
        ).count()
        assert invalid == 0, "Invalid retained rows detected."

        clean = (
            clean
            .withColumn("_subject_key", F.lower("subject"))
            .withColumn("_description_key", F.lower("description"))
            .dropDuplicates(["_subject_key", "_description_key"])
            .drop("_subject_key", "_description_key")
            .cache()
        )
        retained_count = clean.count()
        assert clean.select("ticket_id").distinct().count() == retained_count

        destination.parent.mkdir(parents=True, exist_ok=True)
        clean.orderBy("ticket_id").write.mode("overwrite").parquet(
            str(destination)
        )
        etl_seconds = perf_counter() - etl_started

        # Compare all five columns, including duplicate multiplicities.
        schema = (
            "ticket_id STRING, subject STRING, description STRING, "
            "category STRING, priority STRING"
        )
        reference = read_csv(
            spark, ROOT / "data/processed/tickets_clean.csv", schema
        )
        restored = spark.read.parquet(str(destination)).select(
            *reference.columns
        )
        differences = (
            restored.exceptAll(reference).count()
            + reference.exceptAll(restored).count()
        )
        assert differences == 0, "Spark/Python output mismatch."

        report = {
            "spark_version": spark.version,
            "master": spark.sparkContext.master,
            "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "input_rows": raw_count,
            "excluded_category_rows": raw_count - category_count,
            "retained_rows": retained_count,
            "total_excluded_rows": raw_count - retained_count,
            "output": str(destination.relative_to(ROOT)),
            "output_format": "parquet",
            "python_output_matches": True,
            "parquet_readback_matches": True,
            "startup_seconds": round(startup_seconds, 3),
            "etl_seconds_including_validation_and_write": round(
                etl_seconds, 3
            ),
            "input_rows_per_etl_second": round(
                raw_count / etl_seconds, 2
            ),
        }
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        (reports / "spark_etl.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )

        print("\nSPARK ETL PASSED")
        print(json.dumps(report, indent=2))

        if args.inspect_ui:
            print("\nSpark UI:", spark.sparkContext.uiWebUrl)
            input("Inspect the UI, then press Enter to stop Spark: ")

    finally:
        spark.stop()
        print("Spark session stopped.")


if __name__ == "__main__":
    main()
