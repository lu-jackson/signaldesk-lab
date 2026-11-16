"""FastAPI 依賴：每個 request 一條 SQLite connection；Idempotency-Key 支援。"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterator

from fastapi import Header, Request

from . import clock, db


def get_conn(request: Request) -> Iterator:
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def idempotent(conn, key: str | None, scope: str, fn: Callable[[], Any]) -> Any:
    """帶 Idempotency-Key 的寫入：同 key 同 scope 重送，回傳第一次的結果，不再執行副作用。"""
    if not key:
        return fn()
    ex = conn.execute("SELECT response FROM idempotency_keys WHERE key=? AND scope=?", (key, scope)).fetchone()
    if ex:
        return json.loads(ex["response"])
    res = fn()
    conn.execute("INSERT OR IGNORE INTO idempotency_keys(key,scope,response,created_at) VALUES(?,?,?,?)",
                 (key, scope, json.dumps(res, ensure_ascii=False, default=str), clock.now_iso()))
    return res


def idem_header(idempotency_key: str | None = Header(default=None)) -> str | None:
    return idempotency_key
