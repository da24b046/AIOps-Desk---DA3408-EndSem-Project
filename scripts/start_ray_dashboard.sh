#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export RAY_GRAFANA_HOST="http://127.0.0.1:3001"
export RAY_GRAFANA_IFRAME_HOST="http://127.0.0.1:3001"
export RAY_PROMETHEUS_HOST="http://127.0.0.1:9090"
export RAY_PROMETHEUS_NAME="Prometheus"
export RAY_AUTH_MODE="token"
ray get-auth-token --generate >/dev/null

ray start --head \
  --num-cpus=2 \
  --num-gpus=0 \
  --disable-usage-stats \
  --object-store-memory=134217728 \
  --include-dashboard=true \
  --dashboard-host=127.0.0.1 \
  --dashboard-port=8265

for attempt in $(seq 1 20); do
  if python scripts/configure_ray_monitoring.py; then
    printf '\nRay: http://127.0.0.1:8265\nGrafana: http://127.0.0.1:3001\n'
    exit 0
  fi
  sleep 1
done
printf 'Ray started; monitoring files are not ready. Retry configure_ray_monitoring.py.\n' >&2
exit 1
