"""SQLite 持久化工作佇列。

* claim：BEGIN IMMEDIATE 內一次 SELECT+UPDATE，原子取得；同一 job 不會被兩個 worker 同時 claim。
* lease：running 的 job 有 lease_until；worker 當掉後 lease 過期，由下一個 claim 回收。
  - 無副作用的工作 → 回到 queued 重跑；
  - 有副作用（side_effect=1）的工作 → 標為 unknown，不盲目重跑（結果可能已送出），需要 reconcile。
* retry：RetryableError → 指數 backoff（base * 2^(attempts-1)），超過 max_attempts → failed。
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from .. import clock
from ..db import jdump, jload, new_id, page, row, rows, tx
from ..errors import Conflict, NotFound

LEASE_SECONDS = 60
BACKOFF_BASE = 5


class RetryableError(Exception):
    pass


class UnknownOutcome(Exception):
    """外部結果不明：停在 unknown，不重跑。"""


class TerminalError(Exception):
    pass


def enqueue(conn, type_: str, payload: dict, *, idempotency_key: str | None = None, run_at: str | None = None,
            side_effect: bool = False, max_attempts: int = 4) -> dict:
    """idempotency_key 相同則回傳既有 job（不重複 enqueue）。"""
    jid, ts = new_id("job"), clock.now_iso()
    with tx(conn):
        if idempotency_key:
            ex = conn.execute("SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if ex:
                return _out(dict(ex))
        conn.execute("INSERT INTO jobs(id,type,payload,status,max_attempts,run_at,side_effect,idempotency_key,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (jid, type_, jdump(payload), "queued", max_attempts, run_at or ts, int(side_effect), idempotency_key, ts, ts))
    return get(conn, jid)


def _out(j: dict) -> dict:
    j["payload"] = jload(j["payload"], {})
    j["result"] = jload(j["result"], None)
    return j


def get(conn, job_id: str) -> dict:
    r = row(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    if not r:
        raise NotFound("找不到工作")
    return _out(r)


def list_jobs(conn, status: str | None = None, page_no=1, size=30) -> dict:
    where, params = ("WHERE status=?", (status,)) if status else ("", ())
    res = page(conn, f"FROM jobs {where}", params, page_no, size, "created_at DESC, rowid DESC")
    res["items"] = [_out(j) for j in res["items"]]
    return res


def recover_expired(conn) -> int:
    """回收 lease 已過期的 running job。"""
    now = clock.now_iso()
    n = 0
    with tx(conn):
        for j in rows(conn.execute("SELECT * FROM jobs WHERE status='running' AND lease_until<?", (now,))):
            if j["side_effect"]:
                conn.execute("UPDATE jobs SET status='unknown', last_error=?, lease_until=NULL, locked_by=NULL, updated_at=? WHERE id=?",
                             ("worker 中斷，副作用結果不明，需人工 reconcile", now, j["id"]))
            elif j["attempts"] >= j["max_attempts"]:
                conn.execute("UPDATE jobs SET status='failed', last_error='lease 過期且已達最大嘗試次數', lease_until=NULL, locked_by=NULL, updated_at=? WHERE id=?", (now, j["id"]))
            else:
                conn.execute("UPDATE jobs SET status='queued', lease_until=NULL, locked_by=NULL, last_error='lease 過期，重新排入', updated_at=? WHERE id=?", (now, j["id"]))
            n += 1
    return n


def claim(conn, worker_id: str) -> dict | None:
    recover_expired(conn)
    now = clock.now_iso()
    with tx(conn):
        j = conn.execute("SELECT * FROM jobs WHERE status='queued' AND run_at<=? ORDER BY run_at, rowid LIMIT 1", (now,)).fetchone()
        if not j:
            return None
        lease = clock.iso(clock.now() + timedelta(seconds=LEASE_SECONDS))
        conn.execute("UPDATE jobs SET status='running', attempts=attempts+1, locked_by=?, lease_until=?, updated_at=? WHERE id=?",
                     (worker_id, lease, now, j["id"]))
    return get(conn, j["id"])


def _finish(conn, job_id: str, status: str, *, error: str | None = None, result=None, run_at: str | None = None) -> None:
    with tx(conn):
        cur = conn.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        if cur and cur["cancel_requested"] and status in ("queued",):
            status = "cancelled"
        conn.execute("UPDATE jobs SET status=?, last_error=?, result=?, lease_until=NULL, locked_by=NULL, run_at=COALESCE(?,run_at), updated_at=? WHERE id=?",
                     (status, error, jdump(result) if result is not None else None, run_at, clock.now_iso(), job_id))


def run_one(conn, worker_id: str, handlers: dict) -> dict | None:
    """claim + 執行一個 job。回傳最終 job 或 None（沒有可做的）。"""
    job = claim(conn, worker_id)
    if not job:
        return None
    if job["cancel_requested"]:
        _finish(conn, job["id"], "cancelled", error="已取消，未執行")
        return get(conn, job["id"])
    handler = handlers.get(job["type"])
    try:
        if not handler:
            raise TerminalError(f"未知工作類型 {job['type']}")
        result = handler(conn, job["payload"], job)
        _finish(conn, job["id"], "succeeded", result=result)
    except RetryableError as e:
        if job["attempts"] >= job["max_attempts"]:
            _finish(conn, job["id"], "failed", error=f"達最大嘗試次數：{e}")
        else:
            delay = BACKOFF_BASE * (2 ** (job["attempts"] - 1))
            _finish(conn, job["id"], "queued", error=str(e), run_at=clock.iso(clock.now() + timedelta(seconds=delay)))
    except UnknownOutcome as e:
        _finish(conn, job["id"], "unknown", error=str(e))
    except Exception as e:
        _finish(conn, job["id"], "failed", error=f"{type(e).__name__}: {e}")
    return get(conn, job["id"])


def cancel(conn, job_id: str) -> dict:
    """取消：queued 立即 cancelled；running 設旗標（handler 應在安全點檢查）。已完成的副作用不撤回。"""
    j = get(conn, job_id)
    with tx(conn):
        if j["status"] == "queued":
            conn.execute("UPDATE jobs SET status='cancelled', cancel_requested=1, updated_at=? WHERE id=?", (clock.now_iso(), job_id))
        elif j["status"] == "running":
            conn.execute("UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=?", (clock.now_iso(), job_id))
        else:
            raise Conflict(f"狀態為 {j['status']} 的工作無法取消")
    return get(conn, job_id)


def is_cancelled(conn, job_id: str) -> bool:
    r = conn.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
    return bool(r and r["cancel_requested"])


def retry(conn, job_id: str) -> dict:
    """僅允許安全重試：failed 且無副作用。unknown 與有副作用的工作要走 reconcile，不可直接 retry。"""
    j = get(conn, job_id)
    if j["status"] == "unknown":
        raise Conflict("結果不明的工作不可直接重試，請先 reconcile", "needs_reconcile")
    if j["status"] not in ("failed", "cancelled"):
        raise Conflict(f"狀態為 {j['status']} 的工作不需要重試")
    if j["side_effect"]:
        raise Conflict("有外部副作用的工作不可手動重試；由 idempotency/dedup 保護的流程請重新觸發原動作", "unsafe_retry")
    with tx(conn):
        conn.execute("UPDATE jobs SET status='queued', cancel_requested=0, attempts=0, last_error=NULL, run_at=?, updated_at=? WHERE id=?",
                     (clock.now_iso(), clock.now_iso(), job_id))
    return get(conn, job_id)


def stats(conn) -> dict:
    out = {s: 0 for s in ("queued", "running", "succeeded", "failed", "cancelled", "unknown")}
    for r in conn.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status"):
        out[r["status"]] = r["c"]
    return out
