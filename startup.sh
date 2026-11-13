#!/bin/sh
set -eu

APP_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="${APP_ROOT}/.python_packages/lib/site-packages:${APP_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

exec python -m uvicorn ms_notifications.api.main:app \
  --app-dir "${APP_ROOT}/src" \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
