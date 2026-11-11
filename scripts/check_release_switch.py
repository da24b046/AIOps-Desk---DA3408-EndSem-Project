import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def docker_json(*arguments):
    output = subprocess.check_output(
        ["docker", *arguments], text=True
    )
    return json.loads(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("exercise", "rollback"))
    args = parser.parse_args()

    filename = (
        "feedback-demo-001.json"
        if args.phase == "exercise" else "stable-001.json"
    )
    release = json.loads(
        (ROOT / "deploy/releases" / filename).read_text()
    )
    if args.phase == "exercise":
        expected_model = release["model_version"]
        expected_policy = release["policy_version"]
    else:
        expected_model = release["readiness"]["model_version"]
        expected_policy = release["readiness"]["policy_version"]

    checks = {}
    for name, url in {
        "direct_api": "http://127.0.0.1:8000/health/ready",
        "frontend_proxy": "http://127.0.0.1:3002/api/health/ready",
    }.items():
        with urlopen(url, timeout=10) as response:
            data = json.load(response)
        assert data["status"] == "ready", data
        assert data["model_version"] == expected_model, data
        assert data["policy_version"] == expected_policy, data
        checks[name] = data

    for service in ("api", "model"):
        container = docker_json(
            "inspect", f"aiopsdesk-{service}-1"
        )[0]
        assert container["Image"] == release["images"][service]["image_id"]
        checks[f"{service}_image_matches"] = True

        if service == "api":
            assert any(
                mount.get("Name") == "aiopsdesk_app_data"
                and mount["Destination"] == "/app/state/app"
                for mount in container["Mounts"]
            )
            checks["existing_database_volume_mounted"] = True

    policy = docker_json(
        "compose", "exec", "-T", "api",
        "python", "-c",
        "from pathlib import Path; print(Path('/app/configs/policy.json').read_text())",
    )
    assert policy["expected_model_version"] == expected_model
    assert policy["policy_version"] == expected_policy
    checks["policy_matches"] = True

    path = ROOT / "reports/release_switch_check.json"
    report = json.loads(path.read_text()) if path.exists() else {}
    report[args.phase] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "release_id": release["release_id"],
        "checks": checks,
        "passed": True,
    }

    if args.phase == "rollback":
        assert report.get("exercise", {}).get("passed") is True, (
            "Original release restored, but successful exercise evidence is missing."
        )
        report["switch_and_rollback_verified"] = True

    path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(f"{args.phase.upper()} RELEASE VERIFIED")
    print("Model:", expected_model)
    print("Policy:", expected_policy)
    print("Direct API and frontend proxy: ready")
    print("Image IDs and database volume: verified")
    if args.phase == "rollback":
        print("SWITCH AND ROLLBACK PASSED")


if __name__ == "__main__":
    main()
