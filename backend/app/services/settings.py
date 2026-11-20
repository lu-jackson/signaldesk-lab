"""模式設定。三個開關互相獨立；DB 只存非敏感值，API key 一律從環境變數讀。"""
from __future__ import annotations

from .. import clock, config
from ..errors import DomainError

DEFAULTS = {
    "social_source": "demo",       # demo | threads_readonly
    "ai_provider": "demo",         # demo | anthropic
    "delivery_mode": "simulation",  # 目前只允許 simulation
    "inject_public_reply": "none",  # 模擬器失敗注入
    "inject_dm": "none",
    "inject_draft_reply": "none",
}
ALLOWED = {
    "social_source": {"demo", "threads_readonly"},
    "ai_provider": {"demo", "anthropic"},
    "delivery_mode": {"simulation"},
    "inject_public_reply": {"none", "success", "permission_revoked", "rate_limit", "terminal_failure", "unknown"},
    "inject_dm": {"none", "success", "permission_revoked", "rate_limit", "terminal_failure", "unknown"},
    "inject_draft_reply": {"none", "success", "permission_revoked", "rate_limit", "terminal_failure", "unknown"},
}


def get(conn, key: str) -> str:
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else DEFAULTS[key]


def set_value(conn, key: str, value: str) -> None:
    if key not in ALLOWED or value not in ALLOWED[key]:
        raise DomainError(f"設定 {key} 不接受值 {value!r}", "invalid_setting")
    conn.execute(
        "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, clock.now_iso()),
    )


def capabilities(conn) -> dict:
    """能力狀態：只回 configured 布林值，不回任何秘密。"""
    return {
        "social_source": get(conn, "social_source"),
        "ai_provider": get(conn, "ai_provider"),
        "delivery_mode": get(conn, "delivery_mode"),
        "public_demo": config.public_demo(),
        "anthropic_configured": bool(config.anthropic_key() and config.anthropic_model()),
        "anthropic_model": config.anthropic_model(),
        "threads_configured": bool(config.threads_token()),
        "injection": {k: get(conn, k) for k in ("inject_public_reply", "inject_dm", "inject_draft_reply")},
        "labels": {
            "ai": "規則／模板（非 LLM）" if get(conn, "ai_provider") == "demo" else "Anthropic Live AI",
            "social": ("合成 Demo 資料" if config.synthetic_enabled() else "本機資料庫（手動／CSV 匯入）") if get(conn, "social_source") == "demo" else "Threads 唯讀",
            "delivery": "僅本機模擬，不會送到任何真實平台",
        },
    }
