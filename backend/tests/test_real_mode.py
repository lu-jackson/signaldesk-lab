"""任務 2、3：真實使用模式（不灌合成資料）與品牌升級（預覽 → 確認 → 新版本，舊版保留）。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import clock, db, seed
from app.main import create_app


def _real_client(db_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_SYNTHETIC", "0")
    return TestClient(create_app(db_path))


def test_real_mode_seeds_only_brands_accounts_projects(db_path, monkeypatch):
    c = _real_client(db_path, monkeypatch)
    conn = db.connect(db_path)
    n = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    assert n("brands") == 2 and n("projects") >= 9
    assert n("source_posts") == 0 and n("comments") == 0 and n("click_events") == 0 and n("engagement_snapshots") == 0
    assert n("automation_rules") == 0
    # 重啟（再次 seed）也不會冒出合成資料
    create_app(db_path)
    assert n("source_posts") == 0
    # 標示清楚：不是「合成 Demo 資料」
    s = c.get("/api/settings").json()
    assert "合成" not in s["labels"]["social"] and "匯入" in s["labels"]["social"]
    assert "合成" not in c.get("/api/dashboard").json()["period_note"]


def test_real_mode_import_works_and_only_real_data_exists(db_path, monkeypatch):
    c = _real_client(db_path, monkeypatch)
    r = c.post("/api/posts/import", json={"project_id": "proj_notes_calculus", "text": "微積分期末快到了，求推薦好讀的微積分筆記"})
    assert r.status_code == 201 and r.json()["draft"]
    conn = db.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM source_posts WHERE synthetic=1").fetchone()[0] == 0
    # Run Now 只會搜到自己匯入的真實貼文（搜尋是半開區間 [now-N天, now)，時鐘凍結時要先前進一點）
    clock.advance(seconds=1)
    run = c.post("/api/projects/proj_notes_calculus/run-now?sync=true").json()["run"]
    assert run["candidates"] == 1


def test_default_mode_still_seeds_synthetic(client, conn):
    assert conn.execute("SELECT COUNT(*) FROM source_posts WHERE synthetic=1").fetchone()[0] == 120


def test_brand_upgrade_preview_does_not_change_data_and_apply_keeps_old_version(db_path):
    create_app(db_path)
    conn = db.connect(db_path)
    # 模擬「舊資料庫」：把電子筆記品牌改回只有一筆舊事實的 v1
    old = '{"intro":"舊","products":["總體經濟筆記"],"audience":"","service_area":"","tone":"","faq":[],"facts":["舊事實"],"forbidden":[],"cta":""}'
    conn.execute("UPDATE brand_versions SET data=? WHERE brand_id='brand_notes' AND version=1", (old,))
    conn.commit()
    rep = {r["brand_id"]: r for r in seed.brand_upgrade_report(conn)}
    assert rep["brand_notes"]["status"] == "changed" and rep["brand_toeic"]["status"] == "up_to_date"
    facts = next(c for c in rep["brand_notes"]["changes"] if c["field"] == "facts")
    assert facts["added"] == 10 and facts["removed"] == 1
    # 預覽不改資料
    assert conn.execute("SELECT current_version FROM brands WHERE id='brand_notes'").fetchone()[0] == 1
    # 套用：新增 v2，v1 原封不動；再跑一次就是最新（冪等）
    assert seed.upgrade_brands(conn) == ["MoreTi 電子筆記：v1 → v2"]
    assert conn.execute("SELECT current_version FROM brands WHERE id='brand_notes'").fetchone()[0] == 2
    assert conn.execute("SELECT data FROM brand_versions WHERE brand_id='brand_notes' AND version=1").fetchone()[0] == old
    assert seed.upgrade_brands(conn) == []
    assert all(r["status"] == "up_to_date" for r in seed.brand_upgrade_report(conn))
