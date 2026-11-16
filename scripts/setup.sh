#!/usr/bin/env sh
# macOS / Linux：一次安裝。用法：sh scripts/setup.sh
set -e
command -v python3 >/dev/null 2>&1 || { echo "找不到 python3（需要 3.11+）" >&2; exit 1; }
python3 "$(dirname "$0")/launcher.py" setup
