"""任務 4：記錄「已貼到平台／略過」。這是人工紀錄，不是投遞：不送出任何東西、不改既有的模擬投遞狀態。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

SEEK = "微積分期末快到了，積分技巧看不懂，求推薦整理好的微積分筆記。"


def _draft(c):
    j = c.post("/api/posts/import", json={"project_id": "proj_notes_calculus", "text": SEEK}).json()
    return j["draft"]["id"]


def _outcome(c, did, outcome, note=""):
    return c.post(f"/api/drafts/{did}/manual-outcome", json={"outcome": outcome, "note": note})


def test_posted_requires_valid_approval(client):
    did = _draft(client)
    r = _outcome(client, did, "posted")
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_required"
    client.post(f"/api/drafts/{did}/approve")
    d = _outcome(client, did, "posted", "貼在 Threads").json()
    assert d["manual_outcome"]["outcome"] == "posted" and d["manual_outcome"]["note"] == "貼在 Threads"
    assert d["manual_outcome"]["body"] == d["body"]       # 留下當時文字的快照
    assert d["status"] == "approved"                       # 不動既有狀態機；也沒有任何模擬投遞
    assert d["delivery"] is None


def test_posted_draft_is_locked_until_undone(client):
    did = _draft(client)
    client.post(f"/api/drafts/{did}/approve")
    _outcome(client, did, "posted")
    for call in (lambda: client.put(f"/api/drafts/{did}", json={"body": "改一下"}), lambda: client.post(f"/api/drafts/{did}/reject"),
                 lambda: client.post(f"/api/drafts/{did}/regenerate")):
        r = call()
        assert r.status_code == 409 and r.json()["error"]["code"] == "already_posted"
    d = client.delete(f"/api/drafts/{did}/manual-outcome").json()   # 復原後又可以修改
    assert d["manual_outcome"] is None
    assert client.put(f"/api/drafts/{did}", json={"body": "改一下"}).status_code == 200


def test_skip_anytime_and_new_outcome_supersedes_old(client, conn):
    did = _draft(client)
    d = _outcome(client, did, "skipped", "已經有人回了").json()          # 沒核准也可以略過
    assert d["manual_outcome"]["outcome"] == "skipped"
    client.post(f"/api/drafts/{did}/approve")
    d = _outcome(client, did, "posted").json()
    assert d["manual_outcome"]["outcome"] == "posted"
    rows = conn.execute("SELECT outcome, undone_at IS NOT NULL FROM manual_outcomes WHERE draft_id=? ORDER BY rowid", (did,)).fetchall()
    assert [tuple(r) for r in rows] == [("skipped", 1), ("posted", 0)]   # 歷史保留：舊的標為已取代


def test_edit_after_approval_invalidates_posted_gate(client):
    did = _draft(client)
    client.post(f"/api/drafts/{did}/approve")
    client.put(f"/api/drafts/{did}", json={"body": "我改過了"})
    assert _outcome(client, did, "posted").status_code == 409          # 修改後核准失效，要重新核准


def test_handling_filter_and_pending_excludes_handled_and_rejected(client):
    a = _draft(client)
    b = client.post("/api/posts/import", json={"project_id": "proj_notes_calculus", "text": "想找微積分筆記，期末求推薦好讀的"}).json()["draft"]["id"]
    c3 = client.post("/api/posts/import", json={"project_id": "proj_notes_calculus", "text": "微積分的偏微分看不懂，求推薦筆記"}).json()["draft"]["id"]
    client.post(f"/api/drafts/{a}/approve"); _outcome(client, a, "posted")
    _outcome(client, b, "skipped")
    ids = lambda h: {d["id"] for d in client.get(f"/api/drafts?handling={h}").json()["items"]}
    assert ids("posted") == {a} and ids("skipped") == {b} and ids("pending") == {c3}
    client.post(f"/api/drafts/{c3}/reject")
    assert ids("pending") == set()
    assert client.get("/api/drafts?handling=bogus").status_code == 400


def test_outcome_validation_and_not_found(client):
    did = _draft(client)
    assert _outcome(client, did, "sent").status_code == 422
    assert client.post(f"/api/drafts/{did}/manual-outcome", json={"outcome": "skipped", "note": "x" * 301}).status_code == 422
    assert _outcome(client, "nope", "skipped").status_code == 404


def test_draft_exposes_post_url_and_synthetic_flag(client):
    j = client.post("/api/posts/import", json={"project_id": "proj_notes_calculus", "text": SEEK, "source_url": "https://example.com/p/1"}).json()
    d = client.get(f"/api/drafts/{j['draft']['id']}").json()
    assert d["post_url"] == "https://example.com/p/1" and d["post_synthetic"] == 0
    client.post("/api/projects/proj_toeic/run-now?sync=true")   # 合成貼文產生的草稿要標示為合成
    synth = [x for x in client.get("/api/drafts?page_size=100").json()["items"] if x["id"] != j["draft"]["id"]]
    assert synth and all(x["post_synthetic"] == 1 for x in synth)


def test_outcome_endpoints_blocked_on_public_demo(db_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_PUBLIC_DEMO", "1")
    c = TestClient(create_app(db_path))
    for method in ("post", "delete"):
        r = getattr(c, method)("/api/drafts/x/manual-outcome", **({"json": {"outcome": "skipped"}} if method == "post" else {}))
        assert r.status_code == 403 and r.json()["error"]["code"] == "public_demo_readonly"


def test_capabilities_expose_synthetic_flag(client, db_path, monkeypatch):
    assert client.get("/api/settings").json()["synthetic"] is True
    monkeypatch.setenv("SIGNALDESK_SYNTHETIC", "0")
    assert TestClient(create_app(str(db_path) + "2")).get("/api/settings").json()["synthetic"] is False
