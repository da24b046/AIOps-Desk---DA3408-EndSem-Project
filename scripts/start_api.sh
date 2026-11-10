#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 1
