"""A11–A14：名單去重／匯出、追蹤連結、分析、分頁與約束。"""
from __future__ import annotations

import csv
import io

import pytest

from app import clock
from app.services import leads as leads_svc


def test_same_handle_multi_sources_one_lead(client, conn):
    a = client.post("/api/leads", json={"platform": "threads", "handle": "demo_multi", "post_id": "post_001", "reason": "原因A"}).json()
    b = client.post("/api/leads", json={"platform": "threads", "handle": "@demo_multi", "post_id": "post_002", "reason": "原因B"}).json()
    assert a["id"] == b["id"] and len(b["sources"]) == 2
    assert [x["kind"] for x in b["activity"]] == ["created", "source_added", "event", "event"][:len(b["activity"])] or len(b["activity"]) >= 2
    # 同平台不同 handle / 不同平台同 handle 是不同 lead
    c = client.post("/api/leads", json={"platform": "x", "handle": "demo_multi", "reason": "x"}).json()
    assert c["id"] != a["id"]
    # 同來源同理由重複不新增來源
    d = client.post("/api/leads", json={"platform": "threads", "handle": "demo_multi", "post_id": "post_001", "reason": "原因A"}).json()
    assert len(d["sources"]) == 2


def test_lead_status_history_and_enum(client):
    l = client.post("/api/leads", json={"platform": "threads", "handle": "demo_s", "reason": "r"}).json()
    r = client.patch(f"/api/leads/{l['id']}", json={"status": "Converted", "note": "電話確認"}).json()
    assert r["status"] == "Converted"
    assert any("人工分類，不代表訂單" in a["detail"] for a in r["activity"])
    assert client.patch(f"/api/leads/{l['id']}", json={"status": "Won"}).status_code == 422


def test_export_covers_all_pages_and_history(client, conn):
    for i in range(55):
        leads_svc.upsert_lead(conn, "threads", f"demo_bulk{i:03d}", "post_001", f"理由{i}")
    csv_txt = leads_svc.export_csv(conn, chunk=10)  # 小 chunk 強迫多頁
    rows = list(csv.reader(io.StringIO(csv_txt)))
    assert len(rows) - 1 == 55
    js = leads_svc.export_json(conn, chunk=10)
    assert js["count"] == 55 and all(l["activity"] and l["sources"] for l in js["leads"])
    # API 的列表分頁與匯出總數一致
    api = client.get("/api/leads?page_size=20").json()
    assert api["total"] == 55 and len(api["items"]) == 20
    assert len(client.get("/api/leads/export.json").json()["leads"]) == 55
    assert client.get("/api/leads/export.csv").text.count("\n") >= 56


@pytest.mark.parametrize("v", ["=1+1", "+SUM(A1)", "-2", "@cmd", "\tTAB"])
def test_csv_formula_injection_neutralised(v):
    assert leads_svc.csv_safe(v).startswith("'")


def test_csv_export_neutralises_malicious_note(client, conn):
    l = leads_svc.upsert_lead(conn, "threads", "demo_f", None, "=HYPERLINK(\"http://x\")")
    from app.schemas import LeadPatch
    leads_svc.patch_lead(conn, l["id"], LeadPatch(note="=cmd|' /C calc'!A0"))
    txt = leads_svc.export_csv(conn)
    cells = [c for row in csv.reader(io.StringIO(txt)) for c in row]
    assert not any(c.startswith("=") for c in cells)


# ---- tracking ----
@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ftp://127.0.0.1/x", "http://user:pw@127.0.0.1/x",
                                 "https://evil.example.com/x", "http:///nohost"])
def test_dangerous_destinations_rejected(client, url):
    r = client.post("/api/links", json={"label": "bad", "destination": url})
    assert r.status_code == 400, url


def test_click_redirect_only_to_stored_destination(client):
    link = client.post("/api/links", json={"label": "ok", "destination": "http://127.0.0.1:8000/demo-landing"}).json()
    # 無法經由 query 指定 redirect 目標
    r = client.get(f"/t/{link['token']}?url=http://evil.example.com&next=http://evil.example.com", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://127.0.0.1:8000/demo-landing"
    assert client.get("/t/nope", follow_redirects=False).status_code == 404


def test_click_vs_unique_vs_bot(client):
    link = client.post("/api/links", json={"label": "u", "destination": "http://127.0.0.1:8000/demo-landing"}).json()
    from fastapi.testclient import TestClient
    a = TestClient(client.app)   # 獨立 cookie jar = 不同訪客
    b = TestClient(client.app)
    for _ in range(3):
        a.get(f"/t/{link['token']}", follow_redirects=False)
    b.get(f"/t/{link['token']}", follow_redirects=False, headers={"user-agent": "Mozilla/5.0 (iPhone) Mobile"})
    b2 = TestClient(client.app)
    b2.get(f"/t/{link['token']}", follow_redirects=False, headers={"user-agent": "Googlebot/2.1"})
    s = client.get(f"/api/analytics/summary?link_id={link['id']}&from=2026-11-16T00:00:00Z&to=2026-11-17T00:00:00Z").json()
    assert s["clicks"] == 4 and s["estimated_unique"] == 2 and s["bot_clicks"] == 1


def test_analytics_empty_not_faked_and_halfopen(client, conn):
    s = client.get("/api/analytics/summary?from=2026-01-01T00:00:00Z&to=2026-01-08T00:00:00Z").json()
    assert s["has_data"] is False and s["click_per_simulated_send"] is None and s["denominators"]["click_per_simulated_send"] == 0
    assert len(s["series"]) == 7
    # 半開區間：恰好等於 to 的點擊不計入，等於 from 的計入
    conn.execute("INSERT INTO click_events(id,link_id,session_id,is_bot,device,synthetic,clicked_at) VALUES('c_a','lnk_demo','s1',0,'desktop',0,'2026-02-01T00:00:00Z')")
    conn.execute("INSERT INTO click_events(id,link_id,session_id,is_bot,device,synthetic,clicked_at) VALUES('c_b','lnk_demo','s2',0,'desktop',0,'2026-02-02T00:00:00Z')")
    s = client.get("/api/analytics/summary?from=2026-02-01T00:00:00Z&to=2026-02-02T00:00:00Z").json()
    assert s["clicks"] == 1
    assert client.get("/api/analytics/summary?from=2026-02-02T00:00:00Z&to=2026-02-01T00:00:00Z").status_code == 400


def test_card_and_chart_consistent(client):
    s = client.get("/api/analytics/summary").json()
    assert s["clicks"] == sum(d["clicks"] for d in s["series"])
    s2 = client.get("/api/analytics/summary?from=2026-11-14T00:00:00Z&to=2026-11-16T00:00:00Z").json()
    assert s2["clicks"] == sum(d["clicks"] for d in s2["series"])


def test_engagement_labelled_synthetic(client):
    e = client.get("/api/analytics/engagement").json()
    assert e["synthetic"] is True and "合成" in e["note"]
