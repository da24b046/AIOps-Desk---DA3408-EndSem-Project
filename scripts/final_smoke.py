"""Read-only application/monitoring checks after a deliberate Compose restart."""

import json
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    checks = {}
    with httpx.Client(timeout=10, trust_env=False) as client:
        for name, url in {
            "frontend": "http://127.0.0.1:3002/health/live",
            "api": "http://127.0.0.1:8000/health/ready",
            "frontend_proxy": "http://127.0.0.1:3002/api/health/ready",
            "prometheus": "http://127.0.0.1:9090/-/ready",
            "grafana": "http://127.0.0.1:3001/api/health",
        }.items():
            response = client.get(url)
            response.raise_for_status()
            if name in ("api", "frontend_proxy"):
                release = response.json()
                assert release["status"] == "ready"
                assert release["model_version"] == "candidate-001"
                assert release["policy_version"] == "policy-001"
            checks[name] = response.status_code

        password = getpass("Operator password (verify account/history survived restart): ")
        response = client.post("http://127.0.0.1:8000/v1/session", json={
            "username": "operator", "password": password,
        })
        del password
        response.raise_for_status()
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        try:
            history = client.get(
                "http://127.0.0.1:8000/v1/predictions?limit=1", headers=headers
            )
            history.raise_for_status()
            assert history.json()["items"], "Expected existing saved history."
            checks["existing_operator_login"] = True
            checks["saved_history_accessible"] = True
        finally:
            client.delete("http://127.0.0.1:8000/v1/session", headers=headers).raise_for_status()

        def query(expression):
            response = client.get("http://127.0.0.1:9090/api/v1/query", params={"query": expression})
            response.raise_for_status()
            payload = response.json()
            assert payload["status"] == "success"
            return payload["data"]["result"]

        required = {
            "aiopsdesk-api": 1, "prometheus": 1, "blackbox": 1,
            "aiopsdesk-http-probes": 4, "grafana": 1,
            "node-exporter": 1, "reports-exporter": 1,
        }
        print("Checking monitoring targets after restart...", flush=True)
        for _ in range(30):
            targets = [row for row in query("up") if row["metric"].get("job") in required]
            probes = query('probe_success{job="aiopsdesk-http-probes"}')
            readable = query("aiopsdesk_report_read_success")
            counts = Counter(row["metric"]["job"] for row in targets)
            if (
                dict(counts) == required
                and all(float(row["value"][1]) == 1 for row in targets)
                and len(probes) == 4
                and all(float(row["value"][1]) == 1 for row in probes)
                and len(readable) == 3
                and all(float(row["value"][1]) == 1 for row in readable)
            ):
                break
            time.sleep(2)
        else:
            raise RuntimeError("Monitoring checks did not recover within one minute.")

    ids = subprocess.check_output(
        ["docker", "compose", "--profile", "observe", "ps", "-q"],
        cwd=ROOT, text=True,
    ).split()
    containers = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True))
    assert len(containers) == 8, "Expected eight project containers."
    runtime = {}
    for container in containers:
        assert container["State"]["Running"] is True
        health = container["State"].get("Health", {}).get("Status", "not_configured")
        assert health in ("healthy", "not_configured")
        runtime[container["Name"].lstrip("/")] = {
            "image_id": container["Image"], "image_reference": container["Config"]["Image"],
            "health": health,
        }
    api = next(c for c in containers if c["Config"]["Labels"].get("com.docker.compose.service") == "api")
    assert any(m.get("Name") == "aiopsdesk_app_data" for m in api["Mounts"])

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "required_prometheus_targets_up": dict(counts),
        "http_probes_successful": 4,
        "reports_readable": 3,
        "application_volume_preserved": True,
        "runtime_containers": runtime,
        "all_passed": True,
    }
    (ROOT / "reports/final_startup_check.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("FINAL STARTUP REHEARSAL PASSED")
    print("Eight project containers running; API/proxy ready.")
    print("Existing account and saved history accessible.")
    print("Ten Prometheus targets up; four HTTP probes successful.")
    print("Model: candidate-001; policy: policy-001")
    print("Report: reports/final_startup_check.json")


if __name__ == "__main__":
    main()
