#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec mlflow models serve \
  --model-uri artifacts/serving/candidate-001 \
  --host 127.0.0.1 \
  --port 5001 \
  --env-manager local \
  --workers 1
