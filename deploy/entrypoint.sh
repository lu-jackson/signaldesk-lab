#!/bin/sh
# 一個容器內：單一 worker + API。worker 有 heartbeat 單例保護。
set -e
python -m app.seed
python -m app.worker &
exec python -m uvicorn app.main:app_factory --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
