"""手動匯入貼文：把使用者在社群上自己看到的一則貼文，走一遍既有的「納入 → 分類 → 草稿」流程。

設計重點（為什麼這樣做）：
* 不重寫流程：只負責「把貼文存進 source_posts」，之後呼叫 pipeline 既有的 create_run / record_candidates /
  classify_evaluation / create_draft，所以分類、風險、prompt-injection 防護、不可承諾事項檢查都只有一份。
* 使用者親手貼上就是納入：不用關鍵字把它篩掉；但關鍵字／排除條件命中情形仍寫進 inclusion_reason，方便對照。
* 絕不自動送出：即使專案是 auto_simulate，匯入的真實貼文也只產生草稿，要人工核准。
* 同一則貼文（平台＋內容相同）只存一份；重複匯入回傳既有結果，不重複花費分類額度。
* 公開展示站不在沙盒白名單內，所以 POST /api/posts/import 會被 403，真實貼文不會進展示站。
"""
from __future__ import annotations

import hashlib
import re

from .. import clock
from ..db import new_id, row, tx
from ..schemas import PostImportIn
from . import catalog, drafts, pipeline


def _post_id(platform: str, text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip().lower()
    return "post_imp_" + hashlib.sha256(f"{platform}|{norm}".encode("utf-8")).hexdigest()[:12]


def import_post(conn, body: PostImportIn) -> dict:
    project = catalog.get_project(conn, body.project_id)
    pid = _post_id(body.platform, body.text)
    ts = clock.now_iso()
    with tx(conn):
        created = conn.execute(
            "INSERT OR IGNORE INTO source_posts(id,platform,author_handle,text,created_at,likes,replies,is_own,own_account_id,synthetic,source_url,origin) "
            "VALUES(?,?,?,?,?,0,0,0,NULL,0,?,'manual_import')",
            (pid, body.platform, body.author_handle.strip(), body.text, ts, body.source_url or None)).rowcount == 1

    # 已在此專案分類過 → 直接回傳舊結果（不重複消耗額度）
    prev = conn.execute("SELECT id FROM evaluations WHERE post_id=? AND project_id=? AND intent IS NOT NULL ORDER BY created_at DESC, rowid DESC LIMIT 1",
                        (pid, body.project_id)).fetchone()
    if prev:
        ev = pipeline.get_evaluation(conn, prev["id"])
        d = conn.execute("SELECT id FROM drafts WHERE project_id=? AND post_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (body.project_id, pid)).fetchone()
        return {"post_id": pid, "duplicate": True, "evaluation": ev, "draft": drafts.get_draft(conn, d["id"]) if d else None}

    text_l = body.text.lower()
    hit = next((k for k in project["keywords"] if k.lower() in text_l), None)
    bad = next((t for t in project["exclude_terms"] if t.lower() in text_l), None)
    why = "手動匯入"
    if hit:
        why += f"（命中關鍵字「{hit}」）"
    else:
        why += "（未命中此專案的關鍵字，仍照你的選擇納入）"
    if bad:
        why += f"；注意：含排除字「{bad}」"
    cand = {"id": pid, "included": True, "inclusion_reason": why, "evidence": pipeline._snippet(body.text, hit or bad or "")}

    run_id = pipeline.create_run(conn, project, "manual_import", {"source": "manual_import", "post_id": pid, "mode": project["mode"]})
    try:
        eval_ids = pipeline.record_candidates(conn, run_id, project, [cand])
        ev = pipeline.classify_evaluation(conn, eval_ids[0], project)
        draft = None
        if project["mode"] != "observe_only" and pipeline.draft_policy_ok(ev):
            draft = drafts.create_draft(conn, body.project_id, pid, evaluation_id=eval_ids[0], created_by=f"import:{run_id}")
        err = 1 if ev.get("classify_error") else 0
        pipeline.finish_run(conn, run_id, "failed" if err else "succeeded", ev.get("classify_error") if err else None)
    except Exception as e:
        pipeline.finish_run(conn, run_id, "failed", f"{type(e).__name__}: {e}")
        raise
    return {"post_id": pid, "duplicate": False, "created": created, "run_id": run_id, "evaluation": pipeline.get_evaluation(conn, eval_ids[0]), "draft": draft}
