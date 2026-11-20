#!/bin/sh
# 一個容器內：單一 worker + API。worker 有 heartbeat 單例保護，所以此服務只能有 1 個實例。
# 託管平台（Render 等）會用環境變數 PORT 指定要監聽的埠；沒有時用 8000。
set -e
python -m app.seed
python -m app.worker &
exec python -m uvicorn app.main:app_factory --factory --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
