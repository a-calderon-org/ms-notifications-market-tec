#!/bin/sh
set -eu

exec python -m uvicorn ms_notifications.api.main:app \
  --app-dir src \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
