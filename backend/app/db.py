"""SQLite：每個 connection 啟用 FK/WAL/busy_timeout；migrations 為有序 .sql 檔。"""
from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import clock

MIGRATIONS = Path(__file__).parent / "migrations"


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.stem in done:
            continue
        conn.executescript("BEGIN;\n" + f.read_text(encoding="utf-8") + "\nCOMMIT;")
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(?,?)", (f.stem, clock.now_iso()))
        applied.append(f.stem)
    return applied


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """短交易：BEGIN IMMEDIATE 先取寫鎖。LLM / 網路請求絕不放在這裡面。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def jdump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def jload(s: str | None, default=None):
    return json.loads(s) if s else default


def page(conn, sql_from: str, params: tuple, page_no: int, size: int, order: str, select: str = "*") -> dict:
    """一致的分頁格式：{items,total,page,page_size}。sql_from 含 FROM/WHERE。"""
    page_no = max(1, page_no)
    size = min(max(1, size), 200)
    total = conn.execute(f"SELECT COUNT(*) c {sql_from}", params).fetchone()["c"]
    items = rows(conn.execute(f"SELECT {select} {sql_from} ORDER BY {order} LIMIT ? OFFSET ?", (*params, size, (page_no - 1) * size)))
    return {"items": items, "total": total, "page": page_no, "page_size": size}
