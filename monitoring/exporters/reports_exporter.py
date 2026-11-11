"""Expose bounded summaries of existing reports; never run analysis."""

import json
import math
import threading
from datetime import datetime
from pathlib import Path

from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import GaugeMetricFamily

REPORTS = {
    "pipeline": "pipeline_console_latest.json",
    "ci": "ci_latest.json",
    "drift": "drift_recent.json",
}


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timezone required.")
    return number(parsed.timestamp())


def number(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid nonnegative measurement.")
    return value


class ReportCollector:
    def collect(self):
        readable = GaugeMetricFamily(
            "aiopsdesk_report_read_success", "Report parsed successfully",
            labels=["report"],
        )
        times = GaugeMetricFamily(
            "aiopsdesk_report_timestamp_seconds", "Time recorded by the report",
            labels=["report"],
        )
        states = GaugeMetricFamily(
            "aiopsdesk_report_state", "Recorded state; value 1 identifies the state",
            labels=["report", "state"],
        )
        success = GaugeMetricFamily(
            "aiopsdesk_last_report_success", "Last pipeline or CI report succeeded",
            labels=["report"],
        )
        durations = GaugeMetricFamily(
            "aiopsdesk_last_stage_duration_seconds", "Last recorded stage duration",
            labels=["stage"],
        )
        drift_rows = GaugeMetricFamily(
            "aiopsdesk_drift_current_rows", "Rows in the last application drift check",
        )
        ci_tests = GaugeMetricFamily(
            "aiopsdesk_ci_last_test_count", "Test counts from the last CI report",
            labels=["outcome"],
        )

        for name, filename in REPORTS.items():
            try:
                with (Path("/reports") / filename).open("rb") as handle:
                    raw = handle.read(131073)
                if len(raw) > 131072:
                    raise ValueError("Report too large.")
                data = json.loads(raw)
                extra = []

                if name == "pipeline":
                    state = data["status"]
                    if state not in {"succeeded", "failed", "cancelled", "interrupted"}:
                        raise ValueError("Expected a completed pipeline report.")
                    checked = timestamp(data["finished_at"])
                    passed = state == "succeeded"
                    for stage in data["stages"]:
                        if stage["id"] not in {"spark_etl", "train", "evaluate"}:
                            raise ValueError("Unknown stage.")
                        if stage["elapsed_seconds"] is not None:
                            extra.append((
                                durations, [stage["id"]],
                                number(stage["elapsed_seconds"]),
                            ))

                elif name == "ci":
                    state = data["status"]
                    if state not in {"passed", "failed"}:
                        raise ValueError("Unknown CI state.")
                    checked = timestamp(data["finished_at"])
                    passed = state == "passed"
                    for outcome in ("total", "passed", "failed", "errors", "skipped"):
                        extra.append((
                            ci_tests, [outcome],
                            number(data["test_counts"][outcome]),
                        ))

                else:
                    result = data["result"]
                    state = result["status"]
                    if state == "evaluated":
                        if not isinstance(result["drift_detected"], bool):
                            raise ValueError("Missing drift decision.")
                        state = "drift" if result["drift_detected"] else "no_drift"
                    elif state not in {"insufficient_data", "no_usable_tokens"}:
                        raise ValueError("Unknown drift state.")
                    checked = timestamp(data["checked_at"])
                    extra.append((drift_rows, [], number(result["rows"])))

                # Publish measurements only after validating this whole report.
                readable.add_metric([name], 1)
                times.add_metric([name], checked)
                states.add_metric([name, state], 1)
                if name != "drift":
                    success.add_metric([name], int(passed))
                for family, labels, value in extra:
                    family.add_metric(labels, value)

            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                readable.add_metric([name], 0)

        yield from (
            readable, times, states, success, durations, drift_rows, ci_tests
        )


if __name__ == "__main__":
    registry = CollectorRegistry()
    registry.register(ReportCollector())
    start_http_server(9108, addr="0.0.0.0", registry=registry)
    threading.Event().wait()
