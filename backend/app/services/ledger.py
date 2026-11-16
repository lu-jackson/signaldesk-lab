"""使用量帳本（虛擬 units，無現金價值）。Append-only；(operation_id, entry_type) 唯一，所以重試不會重複扣。

available = grant − reserve + release；settle 只是把已預留的 units 標為「已使用」，不改可用額度。
unknown 結果的投遞保持 reserved，直到 reconcile 後 settle 或 release。
"""
from __future__ import annotations

import sqlite3

from .. import clock
from ..db import new_id, rows
from ..errors import Conflict

RATES = {  # 示例費率，僅供學習計量
    "classify": 1,
    "draft": 3,
    "send": 2,
    "agent_turn": 5,
}
INITIAL_GRANT = 1000


def ensure_grant(conn) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO usage_ledger(id,operation_id,entry_type,units,category,note,created_at) VALUES(?,?,?,?,?,?,?)",
        (new_id("led"), "initial-grant", "grant", INITIAL_GRANT, "grant", "示例起始額度（無現金價值）", clock.now_iso()),
    )


def _sum(conn, entry_type: str) -> int:
    return conn.execute("SELECT COALESCE(SUM(units),0) s FROM usage_ledger WHERE entry_type=?", (entry_type,)).fetchone()["s"]


def balance(conn) -> dict:
    g, r, s, rel = (_sum(conn, t) for t in ("grant", "reserve", "settle", "release"))
    return {
        "granted": g,
        "reserved_total": r,
        "settled": s,
        "released": rel,
        "in_flight": r - s - rel,
        "available": g - r + rel,
        "unit_note": "虛擬 units，無現金價值，不代表任何真實 token 或帳單",
    }


def _insert(conn, op: str, typ: str, units: int, category: str, note: str = "") -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO usage_ledger(id,operation_id,entry_type,units,category,note,created_at) VALUES(?,?,?,?,?,?,?)",
        (new_id("led"), op, typ, units, category, note, clock.now_iso()),
    )
    return cur.rowcount == 1


def reserve(conn, operation_id: str, category: str, units: int | None = None) -> bool:
    """回傳 True=新預留；False=此 operation 先前已預留（重試不重複）。額度不足丟 Conflict。"""
    units = RATES[category] if units is None else units
    exists = conn.execute("SELECT 1 FROM usage_ledger WHERE operation_id=? AND entry_type='reserve'", (operation_id,)).fetchone()
    if exists:
        return False
    if balance(conn)["available"] < units:
        raise Conflict("示例額度不足", "insufficient_units")
    return _insert(conn, operation_id, "reserve", units, category)


def _reserved_units(conn, operation_id: str) -> tuple[int, str] | None:
    r = conn.execute("SELECT units, category FROM usage_ledger WHERE operation_id=? AND entry_type='reserve'", (operation_id,)).fetchone()
    return (r["units"], r["category"]) if r else None


def settle(conn, operation_id: str) -> bool:
    res = _reserved_units(conn, operation_id)
    if not res:
        return False
    if conn.execute("SELECT 1 FROM usage_ledger WHERE operation_id=? AND entry_type='release'", (operation_id,)).fetchone():
        return False
    return _insert(conn, operation_id, "settle", res[0], res[1])


def release(conn, operation_id: str, note: str = "") -> bool:
    res = _reserved_units(conn, operation_id)
    if not res:
        return False
    if conn.execute("SELECT 1 FROM usage_ledger WHERE operation_id=? AND entry_type='settle'", (operation_id,)).fetchone():
        return False
    return _insert(conn, operation_id, "release", res[0], res[1], note)


def entries(conn, limit: int = 100) -> list[dict]:
    return rows(conn.execute("SELECT * FROM usage_ledger ORDER BY rowid DESC LIMIT ?", (limit,)))
