#!/usr/bin/env sh
# macOS / Linux：啟動。用法：sh scripts/dev.sh [start|dev]
exec python3 "$(dirname "$0")/launcher.py" "${1:-start}"
