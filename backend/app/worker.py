"""背景 worker：獨立 process，輪詢 SQLite jobs 表。

啟動方式：python -m app.worker  （dev 腳本只啟動一次；API 啟動不會產生 worker）
單例保護：worker_heartbeat（settings 表）在 15 秒內仍有別的 pid 活著時，拒絕啟動第二個。
"""
from __future__ import annotations

import os
import time
from datetime import timedelta

from . import clock, config, db
from .db import jdump, jload, tx
from .errors import DomainError
from .services import automations, catalog, drafts, jobs, pipeline

HEARTBEAT_KEY = "worker_heartbeat"
HEARTBEAT_TTL = 15


def h_run_project(conn, payload, job):
    run = pipeline.execute_run(conn, payload["project_id"], payload.get("trigger", "job"))
    return {"run_id": run["id"], "status": run["status"], "candidates": run["candidates"], "drafts": run["drafts"]}


def h_send_draft(conn, payload, job):
    res = drafts.simulate_send(conn, payload["draft_id"])
    st = res["attempt"]["status"]
    if st == "failed_retryable":
        raise jobs.RetryableError(res["attempt"]["error"] or "可重試")
    if st == "unknown":
        raise jobs.UnknownOutcome(res["attempt"]["error"] or "結果不明")
    if st == "failed_terminal":
        raise jobs.TerminalError(res["attempt"]["error"] or "終局失敗")
    return {"attempt_id": res["attempt"]["id"], "status": st, "replayed": res["replayed"]}


HANDLERS = {
    "run_project": h_run_project,
    "send_draft": h_send_draft,
    "process_event": lambda conn, p, j: automations.handle_event(conn, p),
    "comment_channel": automations.handle_channel,
}


def schedule_tick(conn) -> int:
    """到期的排程專案各 enqueue 一次。以 (project, 本次 next_run_at) 作 idempotency key，
    即使 tick 被重複呼叫或兩個 process 同時呼叫也只會有一個 job。"""
    now = clock.now_iso()
    n = 0
    due = [dict(r) for r in conn.execute("SELECT id, next_run_at, interval_seconds FROM projects WHERE enabled=1 AND schedule_enabled=1 AND next_run_at<=?", (now,))]
    for p in due:
        jobs.enqueue(conn, "run_project", {"project_id": p["id"], "trigger": "schedule"}, idempotency_key=f"sched:{p['id']}:{p['next_run_at']}")
        nxt = clock.iso(clock.now() + timedelta(seconds=p["interval_seconds"]))
        with tx(conn):
            conn.execute("UPDATE projects SET next_run_at=? WHERE id=? AND next_run_at=?", (nxt, p["id"], p["next_run_at"]))
        n += 1
    return n


def tick(conn, worker_id: str) -> dict | None:
    schedule_tick(conn)
    return jobs.run_one(conn, worker_id, HANDLERS)


def heartbeat(conn, pid: int) -> None:
    with tx(conn):
        conn.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                     (HEARTBEAT_KEY, jdump({"pid": pid, "at": clock.now_iso()}), clock.now_iso()))


def worker_status(conn) -> dict:
    r = conn.execute("SELECT value FROM settings WHERE key=?", (HEARTBEAT_KEY,)).fetchone()
    if not r:
        return {"alive": False, "last_seen": None}
    v = jload(r["value"], {})
    alive = bool(v.get("at")) and (clock.now() - clock.parse(v["at"])).total_seconds() <= HEARTBEAT_TTL
    return {"alive": alive, "last_seen": v.get("at"), "pid": v.get("pid")}


def main() -> None:
    conn = db.connect(config.db_path())
    db.migrate(conn)
    pid = os.getpid()
    st = worker_status(conn)
    if st["alive"] and st.get("pid") != pid:
        raise SystemExit(f"已有 worker 在執行（pid={st.get('pid')}），不再啟動第二個。")
    print(f"[worker] pid={pid} db={config.db_path()}", flush=True)
    wid = f"worker-{pid}"
    while True:
        try:
            heartbeat(conn, pid)
            job = tick(conn, wid)
            if job:
                print(f"[worker] {job['type']} {job['id']} → {job['status']}", flush=True)
                continue
        except DomainError as e:
            print("[worker] domain error:", e.message, flush=True)
        except Exception as e:  # 不讓單一錯誤殺掉 worker
            print("[worker] error:", type(e).__name__, e, flush=True)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
