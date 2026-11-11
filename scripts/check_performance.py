"""Bounded end-to-end demonstration: 20 requests, two concurrent clients."""

import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

import httpx

from src.api import PredictionResponse

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"
REQUESTS = 20
CONCURRENCY = 2
P95_BUDGET = 1.0


def main():
    password = getpass("Operator password: ")
    with httpx.Client(
        base_url=BASE_URL, timeout=10, trust_env=False
    ) as control:
        response = control.post(
            "/v1/session", json={"username": "operator", "password": password}
        )
        del password
        response.raise_for_status()
        token = response.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        control.headers.update(headers)

        try:
            ready = control.get("/health/ready")
            ready.raise_for_status()
            release = ready.json()
            assert release["model_version"] == "candidate-001"
            assert release["policy_version"] == "policy-001"

            runtime_images = {}
            for service in ("api", "model", "frontend"):
                details = json.loads(subprocess.check_output([
                    "docker", "inspect", f"aiopsdesk-{service}-1"
                ], text=True))[0]
                runtime_images[service] = {
                    "image_id": details["Image"],
                    "image_reference": details["Config"]["Image"],
                }

            def run_worker(worker_number):
                results = []
                with httpx.Client(
                    base_url=BASE_URL,
                    headers=headers,
                    timeout=10,
                    trust_env=False,
                ) as client:
                    for index in range(worker_number, REQUESTS, CONCURRENCY):
                        started = time.perf_counter()
                        status = None
                        valid = False
                        error_type = None

                        try:
                            response = client.post("/v1/predict", json={
                                "subject": f"[PERFORMANCE DEMO {index + 1}] Office Wi-Fi issue",
                                "description": (
                                    "Synthetic performance demonstration ticket. "
                                    "My laptop cannot connect to office Wi-Fi."
                                ),
                            })
                            status = response.status_code
                            response.raise_for_status()
                            prediction = PredictionResponse.model_validate(
                                response.json()
                            )
                            assert prediction.model_version == release["model_version"]
                            assert prediction.policy_version == release["policy_version"]
                            assert prediction.result.explanation.status == "available"
                            valid = True
                        except (
                            httpx.HTTPError, ValueError, KeyError,
                            AssertionError, AttributeError,
                        ) as error:
                            error_type = type(error).__name__

                        results.append({
                            "request_number": index + 1,
                            "latency_seconds": time.perf_counter() - started,
                            "http_status": status,
                            "valid_response": valid,
                            "error_type": error_type,
                        })
                return results

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
                batches = list(executor.map(run_worker, range(CONCURRENCY)))
            wall_seconds = time.perf_counter() - started

            results = sorted(
                [result for batch in batches for result in batch],
                key=lambda result: result["request_number"],
            )
            assert len(results) == REQUESTS
            latencies = sorted(result["latency_seconds"] for result in results)

            def percentile(fraction):
                return latencies[math.ceil(fraction * len(latencies)) - 1]

            failures = sum(not result["valid_response"] for result in results)
            p95 = percentile(0.95)
            passed = failures == 0 and p95 <= P95_BUDGET

            report = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "scope": "Short demonstration with 20 requests at concurrency 2",
                "source_marker": "PERFORMANCE DEMO in saved ticket subjects",
                "requests": REQUESTS,
                "concurrency": CONCURRENCY,
                "failed_requests": failures,
                "latency_scope": "Client request, response parsing and validation",
                "percentile_method": "nearest rank over all attempts",
                "p50_seconds": percentile(0.50),
                "p95_seconds": p95,
                "maximum_seconds": max(latencies),
                "wall_seconds": wall_seconds,
                "observed_requests_per_second": REQUESTS / wall_seconds,
                "acceptance": {
                    "maximum_failed_requests": 0,
                    "p95_seconds_limit": P95_BUDGET,
                    "passed": passed,
                },
                "runtime_images": runtime_images,
                "model_version": release["model_version"],
                "policy_version": release["policy_version"],
                "request_results": results,
            }
            Path(ROOT / "reports/performance_check.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )

            print("BOUNDED PERFORMANCE CHECK COMPLETE")
            print("Requests:", REQUESTS)
            print("Concurrency:", CONCURRENCY)
            print("Failed requests:", failures)
            print(f"p50: {report['p50_seconds']:.3f}s")
            print(f"p95: {p95:.3f}s")
            print(f"Maximum: {report['maximum_seconds']:.3f}s")
            print(f"Observed throughput: {REQUESTS / wall_seconds:.2f} requests/s")
            print("Demo budget passed:", passed)
            print("Saved: reports/performance_check.json")

        finally:
            control.delete("/v1/session").raise_for_status()


if __name__ == "__main__":
    main()
