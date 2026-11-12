"""Connect the current local Ray session to the project monitoring services."""

import argparse
import ipaddress
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "monitoring/ray"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, default=Path("/tmp/ray/session_latest"))
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--minimum-targets", type=int, default=3)
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    if args.clear:
        (RUNTIME / "session.targets.json").write_text("[]\n")
        print("Ray scrape targets cleared; application monitoring retained.")
        return

    session = args.session_dir.resolve()
    source = session / "metrics/grafana/dashboards"
    discovery = session / "prom_metrics_service_discovery.json"
    if not source.is_dir() or not discovery.is_file():
        raise SystemExit("Ray dashboard/metric files are not ready. Start Ray and try again.")
    targets = json.loads(discovery.read_text())
    if not targets or not any(group.get("targets") for group in targets):
        raise SystemExit("Ray has not published any metric targets yet. Try again shortly.")
    count = sum(len(group.get("targets", [])) for group in targets)
    if count < args.minimum_targets:
        raise SystemExit("Waiting for the node, head and autoscaler metric endpoints. Try again shortly.")
    for group in targets:
        for target in group["targets"]:
            host, _, port = target.rpartition(":")
            if ipaddress.ip_address(host.strip("[]")).is_loopback:
                raise SystemExit("Ray metrics use loopback, which Docker cannot reach. Restart using start_ray_dashboard.sh.")
            if not port.isdecimal():
                raise SystemExit("Unexpected Ray metric target.")

    destination = RUNTIME / "dashboards"
    destination.mkdir(exist_ok=True)
    paths = sorted(source.glob("*.json"))
    if not paths:
        raise SystemExit("No generated Ray dashboards found.")
    for path in paths:
        dashboard = json.loads(path.read_text())
        if not dashboard.get("uid") or not dashboard.get("panels"):
            raise SystemExit(f"Invalid Ray dashboard: {path.name}")
        shutil.copyfile(path, destination / path.name)
    (RUNTIME / "session.targets.json").write_text(json.dumps(targets, indent=2) + "\n")
    print(f"Connected {len(paths)} Ray dashboards and {sum(len(item['targets']) for item in targets)} metric endpoints.")


if __name__ == "__main__":
    main()
