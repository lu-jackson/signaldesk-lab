"""設定：環境變數 + 後端 .env。秘密只在後端讀取，前端只看到 configured 布林值。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _load_dotenv() -> None:
    for p in (ROOT / ".env", BACKEND / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def db_path() -> str:
    return os.environ.get("SIGNALDESK_DB", str(ROOT / "data" / "signaldesk.db"))


def base_url() -> str:
    return os.environ.get("SIGNALDESK_BASE_URL", "http://127.0.0.1:8000")


def allowed_origins() -> set[str]:
    extra = os.environ.get("SIGNALDESK_ORIGINS", "")
    base = {"http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5173", "http://localhost:5173"}
    return base | {o.strip() for o in extra.split(",") if o.strip()}


def tracking_allowed_hosts() -> set[str]:
    raw = os.environ.get("TRACKING_ALLOWED_HOSTS", "127.0.0.1,localhost")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def anthropic_model() -> str | None:
    return os.environ.get("ANTHROPIC_MODEL") or None


def threads_token() -> str | None:
    return os.environ.get("THREADS_ACCESS_TOKEN") or None


def static_dir() -> Path:
    return ROOT / "frontend" / "dist"


def public_demo() -> bool:
    """公開展示模式：只允許白名單內的沙盒寫入，並限流；用於 signaldesk 公開網站。"""
    return os.environ.get("SIGNALDESK_PUBLIC_DEMO", "").lower() in ("1", "true", "yes")


def reset_interval_hours() -> float:
    return float(os.environ.get("SIGNALDESK_RESET_HOURS", "0") or 0)
