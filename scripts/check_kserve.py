"""Verify KServe-managed inference against the original serving bundle."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
import mlflow
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:15001"


def main():
    output = subprocess.check_output([
        "kubectl", "--context=aiopsdesk", "-n", "aiopsdesk",
        "get", "inferenceservice", "aiopsdesk-ticket", "-o", "json",
    ], text=True)
    service = json.loads(output)
    ready = any(
        condition["type"] == "Ready" and condition["status"] == "True"
        for condition in service["status"]["conditions"]
    )
    assert ready, "InferenceService is not ready."

    validation_path = ROOT / "data/splits/validation.csv"
    validation_hash = hashlib.sha256(
        validation_path.read_bytes()
    ).hexdigest()
    metadata = json.loads(
        (ROOT / "reports/candidate_metrics.json").read_text()
    )
    assert validation_hash == metadata["input_hashes"]["validation"]

    validation = pd.read_csv(validation_path, keep_default_na=False)
    inputs = validation[["subject", "description"]]

    model = mlflow.pyfunc.load_model(
        str(ROOT / "artifacts/serving/candidate-001")
    )
    expected = model.predict(inputs).reset_index(drop=True)

    with httpx.Client(timeout=20, trust_env=False) as client:
        health = client.get(BASE_URL + "/ping")
        health.raise_for_status()

        response = client.post(
            BASE_URL + "/invocations",
            json={"dataframe_records": inputs.to_dict("records")},
        )
        response.raise_for_status()
        actual = pd.DataFrame(response.json()["predictions"])

    assert len(actual) == len(inputs)
    assert set(actual.columns) == set(expected.columns)
    actual = actual[expected.columns].reset_index(drop=True)
    assert set(actual["model_version"]) == {"candidate-001"}

    pd.testing.assert_frame_equal(
        expected, actual,
        check_exact=False, rtol=1e-12, atol=1e-12,
    )

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "context": "aiopsdesk",
        "namespace": "aiopsdesk",
        "inference_service": "aiopsdesk-ticket",
        "deployment_mode": service["metadata"]["annotations"][
            "serving.kserve.io/deploymentMode"
        ],
        "inference_service_ready": ready,
        "server_url": BASE_URL,
        "access_method": "deployment_port_forward",
        "health_status": health.status_code,
        "validation_rows_checked": len(inputs),
        "validation_sha256": validation_hash,
        "http_matches_local_bundle": True,
        "model_version": "candidate-001",
        "test_set_used": False,
    }
    path = ROOT / "reports/kserve_check.json"
    path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("KSERVE INFERENCE CHECK PASSED")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
