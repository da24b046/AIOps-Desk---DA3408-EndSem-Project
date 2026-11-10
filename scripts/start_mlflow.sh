#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p state/mlflow/artifacts

exec mlflow server \
  --backend-store-uri sqlite:///state/mlflow/mlflow.db \
  --artifacts-destination state/mlflow/artifacts \
  --host 127.0.0.1 \
  --port 5000 \
  --workers 1
