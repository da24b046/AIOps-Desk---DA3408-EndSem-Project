"""Verify inference while the local tracking port is closed."""

import json
import runpy
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    try:
        connection = socket.create_connection(
            ("127.0.0.1", 5000), timeout=3
        )
    except ConnectionRefusedError:
        print("Tracking port 5000: CLOSED")
    else:
        connection.close()
        raise SystemExit(
            "Port 5000 is still accepting connections. Stop tracking first."
        )

    # Reuse our existing complete HTTP parity check.
    runpy.run_path(
        str(ROOT / "scripts/check_model_server.py"),
        run_name="__main__",
    )

    inference = json.loads(
        (ROOT / "reports/model_http_check.json").read_text(
            encoding="utf-8"
        )
    )
    report = {
        "tracking_port_closed": True,
        "inference_health_status": inference["health_status"],
        "validation_rows_checked": inference["validation_rows_checked"],
        "http_matches_direct_bundle": inference["http_matches_direct_bundle"],
        "model_version": inference["model_version"],
        "test_set_used": False,
    }
    destination = ROOT / "reports/serving_independence.json"
    destination.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print("\nSERVING INDEPENDENCE PASSED")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
