"""Verify HTTP inference against direct bundle predictions."""

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

import mlflow
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:5001"


def predict_http(frame):
    payload = {
        "dataframe_records": frame.to_dict(orient="records")
    }
    request = Request(
        BASE_URL + "/invocations",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        assert response.status == 200
        body = json.load(response)

    return pd.DataFrame(body["predictions"])


def main():
    with urlopen(BASE_URL + "/ping", timeout=10) as response:
        assert response.status == 200

    validation_path = ROOT / "data/splits/validation.csv"
    metadata = json.loads(
        (ROOT / "reports/candidate_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert hashlib.sha256(validation_path.read_bytes()).hexdigest() == (
        metadata["input_hashes"]["validation"]
    ), "Validation data differs from candidate training."

    validation = pd.read_csv(validation_path, keep_default_na=False)
    inputs = validation[["subject", "description"]]
    model = mlflow.pyfunc.load_model(
        str(ROOT / "artifacts/serving/candidate-001")
    )

    direct = model.predict(inputs).reset_index(drop=True)
    served = predict_http(inputs).reset_index(drop=True)

    pd.testing.assert_frame_equal(
        direct,
        served,
        check_dtype=False,
        check_exact=False,
        rtol=1e-10,
        atol=1e-12,
    )
    assert served["model_version"].eq("candidate-001").all()

    # An illustrative request, not an accuracy-test example.
    example = pd.DataFrame([{
        "subject": "Cannot connect to office Wi-Fi",
        "description": (
            "My laptop cannot connect to the office Wi-Fi. "
            "Other employees can connect normally."
        ),
    }])
    example_result = predict_http(example)

    report = {
        "server_url": BASE_URL,
        "health_status": 200,
        "validation_rows_checked": len(inputs),
        "http_matches_direct_bundle": True,
        "model_version": "candidate-001",
        "test_set_used": False,
        "example_prediction": example_result.to_dict(orient="records"),
    }
    destination = ROOT / "reports/model_http_check.json"
    destination.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nMODEL HTTP CHECK PASSED")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
