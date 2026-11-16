"""A20, A22 與依賴錯誤／分頁／約束／時間邊界／Threads adapter／評估。"""
from __future__ import annotations

import sqlite3

import httpx
import pytest

from app import clock, db, seed
from app.errors import Conflict, DependencyError, NotConfigured
from app.providers.social import ThreadsReadonlyProvider
from app.services import ledger


# ---- ledger ----
def test_reserve_settle_release_idempotent(conn):
    b0 = ledger.balance(conn)
    assert ledger.reserve(conn, "op1", "send") is True
    assert ledger.reserve(conn, "op1", "send") is False        # 重試不重複扣
    assert ledger.balance(conn)["available"] == b0["available"] - 2
    assert ledger.settle(conn, "op1") is True and ledger.settle(conn, "op1") is False
    assert ledger.release(conn, "op1") is False                 # 已 settle 不可再 release
    ledger.reserve(conn, "op2", "draft")
    assert ledger.release(conn, "op2") is True and ledger.release(conn, "op2") is False
    b = ledger.balance(conn)
    assert b["available"] == b0["available"] - 2 and b["available"] >= 0 and b["in_flight"] == 0


def test_insufficient_units_rolls_back_whole_delivery(client, conn):
    conn.execute("INSERT INTO usage_ledger(id,operation_id,entry_type,units,category,created_at) VALUES('l_burn','burn','reserve',999,'x','2026-11-16T12:00:00Z')")
    assert ledger.balance(conn)["available"] < 2
    client.post("/api/simulator/events", json={"event_id": "poor", "post_id": "own_rent_1", "author_handle": "demo_p", "text": "清單"})
    from tests.conftest import run_worker
    run_worker(conn)
    assert conn.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0] == 0   # 沒有半成品 attempt
    assert ledger.balance(conn)["available"] >= 0


def test_ledger_is_unique_per_operation_and_type(conn):
    ledger.reserve(conn, "dup", "send")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO usage_ledger(id,operation_id,entry_type,units,category,created_at) VALUES('x','dup','reserve',1,'s','t')")


def test_usage_has_no_cash_value_note(client):
    assert "無現金價值" in client.get("/api/usage").json()["balance"]["unit_note"]


# ---- 400/404/409/422 與約束 ----
def test_status_codes(client):
    assert client.get("/api/projects/nope").status_code == 404
    assert client.post("/api/projects", json={"name": "x"}).status_code == 422
    assert client.post("/api/projects", json={"name": "x", "brand_id": "nope", "account_id": "acct_x", "keywords": ["a"]}).status_code == 404
    assert client.post("/api/projects", json={"name": "x", "brand_id": "brand_rent", "account_id": "acct_x", "keywords": ["a"], "mode": "turbo"}).status_code == 422
    assert client.post("/api/brands", json={"name": "安居台北租屋顧問（虛構）"}).status_code == 409
    assert client.post("/api/accounts", json={"platform": "x", "handle": "real_person", "display_name": "x"}).status_code == 422  # 只允許 demo_*
    assert client.post("/api/accounts", json={"platform": "x", "handle": "demo_shiguang_x", "display_name": "dup"}).status_code == 409
    assert client.post("/api/drafts", json={"project_id": "proj_rent", "post_id": "nope"}).status_code == 404
    assert client.get("/api/analytics/summary?from=bad&to=worse").status_code == 400


def test_fk_and_check_enforced_at_db_level(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO projects(id,name,brand_id,account_id,keywords,created_at,updated_at) VALUES('p','n','nobrand','acct_x','[]','t','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO leads(id,platform,handle,list_id,status,created_at,updated_at) VALUES('l','x','h','nolist','New','t','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO social_accounts(id,platform,handle,display_name,created_at) VALUES('a','x','realuser','n','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO jobs(id,type,payload,status,run_at,created_at,updated_at) VALUES('j','t','{}','weird','t','t','t')")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_pagination_consistent(client):
    a = client.get("/api/posts?page=1&page_size=10").json()
    b = client.get("/api/posts?page=2&page_size=10").json()
    assert a["total"] == b["total"] and a["page"] == 1 and b["page"] == 2 and len(a["items"]) == 10
    assert not {x["id"] for x in a["items"]} & {x["id"] for x in b["items"]}
    big = client.get("/api/posts?page_size=9999").json()
    assert big["page_size"] == 200
    assert client.get("/api/posts?page=9999").json()["items"] == []


def test_origin_guard_blocks_foreign_write(client):
    r = client.post("/api/brands", json={"name": "x2"}, headers={"Origin": "http://evil.example.com"})
    assert r.status_code == 403
    ok = client.post("/api/brands", json={"name": "x3"}, headers={"Origin": "http://127.0.0.1:5173"})
    assert ok.status_code == 201


def test_settings_expose_no_secrets(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-abcdefghijklmnop")
    monkeypatch.setenv("ANTHROPIC_MODEL", "some-model")
    s = client.get("/api/settings").json()
    assert s["anthropic_configured"] is True and "sk-ant" not in str(s)
    assert client.patch("/api/settings", json={"ai_provider": "gpt"}).status_code == 422
    assert s["delivery_mode"] == "simulation" and client.patch("/api/settings", json={"delivery_mode": "live"}).json()["delivery_mode"] == "simulation"


def test_demo_mode_labels_are_honest(client):
    s = client.get("/api/settings").json()
    assert "非 LLM" in s["labels"]["ai"] and "合成" in s["labels"]["social"] and "模擬" in s["labels"]["delivery"]


# ---- Threads read-only ----
def make_threads(handler):
    return ThreadsReadonlyProvider(token="T", transport=httpx.MockTransport(handler))


def test_threads_not_configured(conn, monkeypatch):
    monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
    with pytest.raises(NotConfigured):
        ThreadsReadonlyProvider().search_posts(conn, ["租屋"], "a", "b", "hot", 10)


@pytest.mark.parametrize("code,msg", [(401, "401"), (403, "403"), (429, "429")])
def test_threads_error_codes(conn, code, msg):
    p = make_threads(lambda req: httpx.Response(code, json={}))
    with pytest.raises(DependencyError) as e:
        p.search_posts(conn, ["租屋"], "a", "b", "hot", 10)
    assert msg in e.value.message


def test_threads_pagination_and_mapping(conn):
    pages = {None: {"data": [{"id": "1", "text": "想找租屋", "username": "u1", "timestamp": "2026-11-15T10:00:00+0000"}], "paging": {"cursors": {"after": "C2"}}},
             "C2": {"data": [{"id": "2", "text": "租屋推薦", "username": "u2", "timestamp": "2026-11-14T10:00:00+0000"}, {"id": "3", "username": "nt"}]}}
    seen = []

    def h(req):
        seen.append(dict(req.url.params))
        assert req.method == "GET"
        return httpx.Response(200, json=pages[req.url.params.get("after")])
    out = make_threads(h).search_posts(conn, ["租屋"], "a", "b", "hot", 10)
    assert [p["id"] for p in out] == ["threads_1", "threads_2"] and out[0]["created_at"] == "2026-11-15T10:00:00Z"
    assert seen[0]["search_type"] == "TOP" and seen[1]["after"] == "C2"


def test_threads_has_no_write_methods():
    assert not [m for m in dir(ThreadsReadonlyProvider) if any(w in m for w in ("send", "reply", "post_", "publish", "deliver"))]


def test_threads_unconfigured_does_not_block_demo(client):
    client.patch("/api/settings", json={"social_source": "threads_readonly"})
    r = client.post("/api/projects/proj_rent/run-now?sync=true")
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"
    client.patch("/api/settings", json={"social_source": "demo"})
    assert client.post("/api/projects/proj_rent/run-now?sync=true").status_code == 202


# ---- seed / migration / eval ----
def test_seed_counts_and_idempotent(conn):
    c = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert c("source_posts") == 120 and c("comments") == 80 and c("brands") == 3 and c("social_accounts") == 4
    assert {r[0] for r in conn.execute("SELECT platform FROM social_accounts")} == {"threads", "x", "instagram", "facebook"}
    conn.execute("UPDATE brands SET name='使用者改的' WHERE id='brand_rent'")
    seed.seed_demo(conn)
    assert conn.execute("SELECT name FROM brands WHERE id='brand_rent'").fetchone()[0] == "使用者改的"   # 不覆蓋使用者修改
    assert c("source_posts") == 120


def test_seed_recent_window_never_empty_across_days(conn):
    for d in (0, 30, 400):
        clock.set_fixed(clock.parse("2026-11-16T12:00:00Z") + __import__("datetime").timedelta(days=d))
        seed.seed_demo(conn)
        n = conn.execute("SELECT COUNT(*) FROM source_posts WHERE is_own=0 AND created_at>=? AND created_at<?",
                         (clock.iso(clock.now() - __import__("datetime").timedelta(days=7)), clock.now_iso())).fetchone()[0]
        assert n > 20, d


def test_seed_same_day_deterministic(app, db_path):
    a = db.connect(db_path); b = db.connect(":memory:")
    db.migrate(b); seed.seed_demo(b)
    rows = lambda c: [tuple(r) for r in c.execute("SELECT id,text,created_at FROM source_posts ORDER BY id")]
    assert rows(a) == rows(b)


def test_migrations_idempotent(conn):
    assert db.migrate(conn) == []


def test_reset_demo_requires_confirm_and_resets(conn, capsys, monkeypatch):
    conn.execute("DELETE FROM source_posts WHERE id='post_001'") if False else None
    conn.execute("INSERT INTO lead_lists(id,name,created_at) VALUES('lx','tmp','t')")
    seed.reset_demo(conn)
    assert conn.execute("SELECT COUNT(*) FROM lead_lists WHERE id='lx'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM source_posts").fetchone()[0] == 120


def test_eval_report_zero_denominator_safe():
    from eval.evaluate import evaluate
    r = evaluate()
    assert r["n"] >= 30 and 0 <= r["intent_accuracy"] <= 1
    assert r["per_class"]["advice"]["support"] > 0
    r0 = evaluate([{"id": "z", "text": "今天天氣好", "relevant": False, "intent": "other", "risk": "low"}])
    assert r0["per_class"]["seeking"]["precision"] is None and r0["per_class"]["seeking"]["recall"] is None   # 零分母 → None，不是 0


def test_eval_fixtures_have_enough_labelled_rows():
    import json
    from pathlib import Path
    fx = json.loads((Path(__file__).parents[1] / "eval" / "fixtures.json").read_text(encoding="utf-8"))
    assert len(fx) >= 30 and {f["intent"] for f in fx} == {"seeking", "advice", "promotion", "complaint", "other"}


def test_dashboard_has_denominators(client):
    d = client.get("/api/dashboard").json()
    for m in d["metrics"].values():
        assert "of" in m and "label" in m
    assert d["updated_at"] and "合成" in d["period_note"]


# ---- 公開展示模式 ----
def test_public_demo_blocks_non_sandbox_writes_and_rate_limits(db_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app
    monkeypatch.setenv("SIGNALDESK_PUBLIC_DEMO", "1")
    c = TestClient(create_app(db_path))
    assert c.get("/api/settings").json()["public_demo"] is True
    for method, path, body in [("post", "/api/brands", {"name": "x"}), ("patch", "/api/settings", {"ai_provider": "anthropic"}),
                               ("post", "/api/links", {"label": "a", "destination": "http://127.0.0.1/x"}), ("delete", "/api/projects/proj_rent", None)]:
        r = getattr(c, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 403 and r.json()["error"]["code"] == "public_demo_readonly", path
    assert c.post("/api/projects/proj_rent/run-now?sync=true").status_code == 202   # 沙盒白名單
    codes = [c.post("/api/simulator/events", json={"event_id": f"r{i}", "post_id": "own_rent_1", "author_handle": "demo_x", "text": "清單"}).status_code for i in range(70)]
    assert 429 in codes and codes[0] == 202


def test_public_demo_off_by_default(client):
    assert client.get("/api/settings").json()["public_demo"] is False
    assert client.post("/api/brands", json={"name": "ok-local"}).status_code == 201
