"""A06–A10, A21：事件、去重、失敗注入、unknown、worker lease、取消、排程。"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import clock, worker
from app.services import jobs
from tests.conftest import run_worker


def event(client, eid, text="請給我清單", post="own_toeic_1"):
    return client.post("/api/simulator/events", json={"event_id": eid, "post_id": post, "author_handle": "demo_tester", "text": text})


def attempts(conn, cid):
    return {r["kind"]: dict(r) for r in conn.execute("SELECT * FROM delivery_attempts WHERE comment_id=?", (cid,))}


def test_preview_sends_nothing(client, conn):
    p = client.post("/api/automations/rule_toeic_list/preview").json()
    assert p["matching"] > 0 and p["note"].startswith("預覽")
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0] == 0


def test_duplicate_event_accepted_once(client, conn):
    a, b = event(client, "ev-1").json(), event(client, "ev-1").json()
    assert a["duplicate"] is False and b["duplicate"] is True and a["accepted"] and b["accepted"]
    run_worker(conn)
    assert conn.execute("SELECT COUNT(*) FROM events WHERE event_id='ev-1'").fetchone()[0] == 1
    cid = "cmt_ev-1"
    at = attempts(conn, cid)
    assert at["public_reply"]["status"] == "simulated_sent" and at["dm"]["status"] == "simulated_sent"
    assert at["dm"]["read_status"] == "not_reported"  # 沒有假已讀
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts WHERE comment_id=?", (cid,)).fetchone()[0] == 2
    assert conn.execute("SELECT status FROM events WHERE event_id='ev-1'").fetchone()[0] == "processed"
    # 事件進名單
    assert conn.execute("SELECT COUNT(*) FROM leads WHERE handle='demo_tester'").fetchone()[0] == 1


def test_non_matching_comment_does_nothing(client, conn):
    event(client, "ev-2", text="路過看看")
    run_worker(conn)
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0] == 0


def test_keyword_match_case_insensitive_or(client):
    rule = client.get("/api/automations").json()["items"][0]
    body = {k: rule[k] for k in ("name", "post_id", "keywords", "reply_template", "send_dm", "links", "enabled")} | {"dm_template": "x", "keywords": ["Hello", "世界"]}
    client.put(f"/api/automations/{rule['id']}", json=body)
    from app.services import automations
    r = {"keywords": ["Hello", "世界"]}
    assert automations.matches(r, "say HELLO") and automations.matches(r, "你好世界") and not automations.matches(r, "nothing")


def test_workflow_version_change_does_not_resend(client, conn):
    event(client, "ev-3")
    run_worker(conn)
    rule = client.get("/api/automations").json()["items"][0]
    body = {k: rule[k] for k in ("name", "post_id", "keywords", "reply_template", "send_dm", "links", "enabled")} | {"dm_template": rule["dm_template"] or "dm"}
    v2 = client.put(f"/api/automations/{rule['id']}", json=body).json()
    assert v2["version"] == rule["version"] + 1
    client.post(f"/api/automations/{rule['id']}/process-existing")  # 重新處理既有留言（含 ev-3 的留言）
    run_worker(conn)
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts WHERE comment_id='cmt_ev-3'").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM delivery_dedup WHERE dedup_key LIKE 'comment:cmt_ev-3:%'").fetchone()[0] == 2


def test_process_existing_is_idempotent(client, conn):
    n1 = client.post("/api/automations/rule_toeic_list/process-existing").json()["matched_comments"]
    run_worker(conn, n=500)
    sent1 = conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0]
    client.post("/api/automations/rule_toeic_list/process-existing")
    run_worker(conn, n=500)
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0] == sent1 == n1 * 2


def test_public_ok_dm_terminal_failure_independent(client, conn):
    client.post("/api/simulator/inject", json={"channel": "dm", "outcome": "permission_revoked"})
    event(client, "ev-4")
    run_worker(conn)
    at = attempts(conn, "cmt_ev-4")
    assert at["public_reply"]["status"] == "simulated_sent"
    assert at["dm"]["status"] == "failed_terminal" and at["dm"]["attempts"] == 1  # 終局失敗不盲目 retry
    j = conn.execute("SELECT status, attempts FROM jobs WHERE idempotency_key='comment:cmt_ev-4:dm'").fetchone()
    assert j["status"] == "failed" and j["attempts"] == 1
    # 終局失敗釋放額度
    led = conn.execute("SELECT entry_type FROM usage_ledger WHERE operation_id='comment:cmt_ev-4:dm'").fetchall()
    assert {r[0] for r in led} == {"reserve", "release"}


def test_rate_limit_retries_with_backoff_then_succeeds(client, conn):
    client.post("/api/simulator/inject", json={"channel": "public_reply", "outcome": "rate_limit"})
    event(client, "ev-5")
    run_worker(conn)
    j = dict(conn.execute("SELECT * FROM jobs WHERE idempotency_key='comment:cmt_ev-5:public_reply'").fetchone())
    assert j["status"] == "queued" and j["attempts"] == 1 and j["run_at"] > clock.now_iso()
    client.post("/api/simulator/inject", json={"channel": "public_reply", "outcome": "success"})
    clock.advance(seconds=6)
    run_worker(conn)
    j = dict(conn.execute("SELECT * FROM jobs WHERE idempotency_key='comment:cmt_ev-5:public_reply'").fetchone())
    assert j["status"] == "succeeded" and j["attempts"] == 2
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts WHERE comment_id='cmt_ev-5' AND kind='public_reply'").fetchone()[0] == 1


def test_rate_limit_gives_up_after_max_attempts(client, conn):
    client.post("/api/simulator/inject", json={"channel": "public_reply", "outcome": "rate_limit"})
    event(client, "ev-6")
    for _ in range(8):
        run_worker(conn)
        clock.advance(seconds=120)
    j = dict(conn.execute("SELECT * FROM jobs WHERE idempotency_key='comment:cmt_ev-6:public_reply'").fetchone())
    assert j["status"] == "failed" and j["attempts"] == 4


def test_unknown_outcome_stops_and_reconciles(client, conn):
    client.post("/api/simulator/inject", json={"channel": "public_reply", "outcome": "unknown"})
    event(client, "ev-7")
    run_worker(conn)
    j = dict(conn.execute("SELECT * FROM jobs WHERE idempotency_key='comment:cmt_ev-7:public_reply'").fetchone())
    assert j["status"] == "unknown" and j["attempts"] == 1
    # 不可直接 retry
    assert client.post(f"/api/jobs/{j['id']}/retry").status_code == 409
    clock.advance(seconds=3600)
    run_worker(conn)  # 不會被再次執行
    assert conn.execute("SELECT attempts FROM jobs WHERE id=?", (j["id"],)).fetchone()[0] == 1
    att = attempts(conn, "cmt_ev-7")["public_reply"]
    assert att["status"] == "unknown"
    bal = client.get("/api/usage").json()["balance"]
    assert bal["in_flight"] >= 2  # unknown 保持 reserved
    r = client.post(f"/api/deliveries/{att['id']}/reconcile?resolution=sent").json()
    assert r["status"] == "simulated_sent"
    assert client.get("/api/usage").json()["balance"]["in_flight"] < bal["in_flight"]


def test_worker_crash_lease_recovery(conn):
    safe = jobs.enqueue(conn, "run_project", {"project_id": "proj_notes"})
    risky = jobs.enqueue(conn, "send_draft", {"draft_id": "x"}, side_effect=True)
    jobs.claim(conn, "w1")
    jobs.claim(conn, "w1")   # 兩個都被 w1 claim 後 w1「當掉」
    assert conn.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0] == 2
    assert jobs.claim(conn, "w2") is None  # lease 未過期，別人不能搶
    clock.advance(seconds=jobs.LEASE_SECONDS + 1)
    jobs.recover_expired(conn)
    assert jobs.get(conn, safe["id"])["status"] == "queued"      # 無副作用 → 重排
    assert jobs.get(conn, risky["id"])["status"] == "unknown"    # 有副作用 → 不盲目重跑


def test_claim_is_atomic_single_winner(conn):
    jobs.enqueue(conn, "run_project", {"project_id": "proj_toeic"})
    a = jobs.claim(conn, "w1")
    b = jobs.claim(conn, "w2")
    assert a and b is None


def test_cancel_partial_keeps_results(client, conn):
    n = client.post("/api/automations/rule_toeic_list/process-existing").json()["matched_comments"]
    assert n >= 3
    run_worker(conn, n=2)  # 只做兩個工作
    done = conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0]
    queued = conn.execute("SELECT id FROM jobs WHERE status='queued'").fetchall()
    for q in queued:
        assert client.post(f"/api/jobs/{q[0]}/cancel").status_code == 200
    run_worker(conn, n=500)
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0] == done  # 既有保留、沒有新副作用
    assert conn.execute("SELECT COUNT(*) FROM jobs WHERE status='cancelled'").fetchone()[0] == len(queued)
    assert client.post(f"/api/jobs/{queued[0][0]}/cancel").status_code == 409


def test_schedule_tick_enqueues_once_and_run_now_independent(client, conn):
    p = client.get("/api/projects/proj_notes").json()
    body = {k: p[k] for k in ("name", "brand_id", "account_id", "purpose", "keywords", "must_terms", "exclude_terms", "window_days", "mode", "daily_limit", "interval_seconds", "enabled")}
    client.put("/api/projects/proj_notes", json={**body, "schedule_enabled": True, "interval_seconds": 600})
    assert worker.schedule_tick(conn) == 0
    clock.advance(seconds=601)
    assert worker.schedule_tick(conn) == 1
    assert worker.schedule_tick(conn) == 0  # next_run_at 已前移，不會雙重 enqueue
    assert conn.execute("SELECT COUNT(*) FROM jobs WHERE type='run_project'").fetchone()[0] == 1
    # 改排程（同 interval）不會 enqueue，也不重置 next_run_at
    nxt = conn.execute("SELECT next_run_at FROM projects WHERE id='proj_notes'").fetchone()[0]
    client.put("/api/projects/proj_notes", json={**body, "schedule_enabled": True, "interval_seconds": 600, "name": "改名"})
    assert conn.execute("SELECT next_run_at FROM projects WHERE id='proj_notes'").fetchone()[0] == nxt
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    # Run Now 不需等排程；Idempotency-Key 去重
    h = {"Idempotency-Key": "rn-1"}
    a = client.post("/api/projects/proj_notes/run-now", headers=h).json()
    b = client.post("/api/projects/proj_notes/run-now", headers=h).json()
    assert a["job"]["id"] == b["job"]["id"]
    run_worker(conn)
    assert conn.execute("SELECT COUNT(*) FROM runs WHERE project_id='proj_notes'").fetchone()[0] == 2  # 一次排程 + 一次 run-now


def test_worker_singleton_heartbeat(conn):
    worker.heartbeat(conn, 4242)
    st = worker.worker_status(conn)
    assert st["alive"] and st["pid"] == 4242
    clock.advance(seconds=worker.HEARTBEAT_TTL + 1)
    assert not worker.worker_status(conn)["alive"]
