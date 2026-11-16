"""模擬投遞核心：去重 + 計量 + 結果狀態機。公開回覆與 DM 各自一筆 attempt，狀態互不影響。

dedup_key 是「全局去重鍵」，不含 workflow version：
  草稿回覆：  draft:{draft_id}:public_reply
  留言自動化：comment:{comment_id}:{channel}
所以改 workflow 版本、重複點擊、重複事件都不會對同一目標再送一次。
"""
from __future__ import annotations

from .. import clock
from ..db import new_id, row, rows, tx
from ..errors import Conflict, NotFound
from ..providers.social import SimulatedDelivery
from . import ledger, settings

_provider = SimulatedDelivery()


def get_attempt(conn, attempt_id: str) -> dict:
    r = row(conn.execute("SELECT * FROM delivery_attempts WHERE id=?", (attempt_id,)).fetchone())
    if not r:
        raise NotFound("找不到投遞紀錄")
    return r


def deliver(conn, *, dedup_key: str, kind: str, fields: dict) -> tuple[dict, bool]:
    """回傳 (attempt, replayed)。replayed=True 表示沒有做任何新副作用／計量。"""
    inject_key = {"draft_reply": "inject_draft_reply", "public_reply": "inject_public_reply", "dm": "inject_dm"}[kind]
    with tx(conn):
        ex = conn.execute("SELECT attempt_id FROM delivery_dedup WHERE dedup_key=?", (dedup_key,)).fetchone()
        if ex:
            a = get_attempt(conn, ex["attempt_id"])
            if a["status"] != "failed_retryable":
                return a, True  # sent / terminal / unknown / pending：不重做
            aid = a["id"]       # 可重試：沿用同一筆 attempt 與同一個 reserve
        else:
            aid = new_id("att")
            ts = clock.now_iso()
            conn.execute(
                "INSERT INTO delivery_attempts(id,kind,draft_id,comment_id,rule_id,rule_version,recipient,body,operation_id,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, kind, fields.get("draft_id"), fields.get("comment_id"), fields.get("rule_id"), fields.get("rule_version"),
                 fields.get("recipient"), fields.get("body", ""), dedup_key, "pending", ts, ts))
            conn.execute("INSERT INTO delivery_dedup(dedup_key,attempt_id,created_at) VALUES(?,?,?)", (dedup_key, aid, ts))
            ledger.reserve(conn, dedup_key, "send")  # 額度不足會 rollback 整個交易（attempt/dedup 一起消失）
    # 網路／外部呼叫在交易之外
    outcome = _provider.simulate_delivery(kind, settings.get(conn, inject_key))
    with tx(conn):
        conn.execute("UPDATE delivery_attempts SET status=?, error=?, attempts=attempts+1, updated_at=? WHERE id=?",
                     (outcome.status, outcome.error, clock.now_iso(), aid))
        if outcome.status == "simulated_sent":
            ledger.settle(conn, dedup_key)
        elif outcome.status == "failed_terminal":
            ledger.release(conn, dedup_key, outcome.error or "")
        # failed_retryable / unknown：保持 reserved
    return get_attempt(conn, aid), False


def reconcile(conn, attempt_id: str, resolution: str) -> dict:
    """人工（或模擬對帳）確認 unknown 的真實結果：sent → settle；not_sent → 釋放並改為可重試。"""
    a = get_attempt(conn, attempt_id)
    if a["status"] != "unknown":
        raise Conflict("只有結果不明的投遞需要 reconcile")
    if resolution not in ("sent", "not_sent"):
        raise Conflict("resolution 必須是 sent 或 not_sent")
    with tx(conn):
        if resolution == "sent":
            conn.execute("UPDATE delivery_attempts SET status='simulated_sent', error=NULL, updated_at=? WHERE id=?", (clock.now_iso(), attempt_id))
            ledger.settle(conn, a["operation_id"])
            if a["draft_id"]:
                conn.execute("UPDATE drafts SET status='sent', updated_at=? WHERE id=?", (clock.now_iso(), a["draft_id"]))
        else:
            conn.execute("UPDATE delivery_attempts SET status='failed_retryable', error='reconcile：確認未送出，可重試', updated_at=? WHERE id=?", (clock.now_iso(), attempt_id))
    return get_attempt(conn, attempt_id)


def list_attempts(conn, limit: int = 100) -> list[dict]:
    return rows(conn.execute("SELECT * FROM delivery_attempts ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)))
