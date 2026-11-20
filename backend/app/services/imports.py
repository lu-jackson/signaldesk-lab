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

import csv
import hashlib
import io
import re

from .. import clock
from ..db import new_id, row, tx
from pydantic import ValidationError

from ..errors import DomainError
from ..schemas import CsvImportIn, PostImportIn
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


# ---- CSV 批次匯入 -------------------------------------------------------------------------
MAX_CSV_ROWS = 50  # 每次最多 50 列：每列都會分類（用 LLM 時會花錢），一次量小才好檢查
# 欄位名稱容許中英文別名；比對時忽略大小寫與空白
HEADER_ALIASES = {
    "text": {"text", "內容", "貼文", "貼文內容", "content", "post"},
    "platform": {"platform", "平台"},
    "author_handle": {"author_handle", "author", "handle", "作者", "作者帳號"},
    "source_url": {"source_url", "url", "link", "網址", "連結", "來源網址"},
}


def parse_csv(csv_text: str) -> tuple[list[tuple[int, dict]], list[dict]]:
    """回傳 (有效列[(列號, 欄位 dict)], 錯誤列[{row, reason}])。第 1 列必須是標題列，且至少要有「內容」欄。
    列號是試算表上看到的行號（標題列＝1），方便使用者回頭對照。"""
    reader = csv.reader(io.StringIO(csv_text.lstrip("\ufeff"), newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise DomainError("CSV 是空的", "csv_empty")
    cols: dict[str, int] = {}
    for i, name in enumerate(header):
        key = re.sub(r"\s+", "", name).lower()
        for field, aliases in HEADER_ALIASES.items():
            if key in {a.lower() for a in aliases} and field not in cols:
                cols[field] = i
    if "text" not in cols:
        raise DomainError("第 1 列必須是標題列，且要有「內容」欄（可寫 text、內容、貼文）", "csv_no_text_column")
    rows: list[tuple[int, dict]] = []
    errors: list[dict] = []
    for n, rec in enumerate(reader, start=2):
        if not any(c.strip() for c in rec):
            continue  # 空白列直接略過
        if len(rows) + len(errors) >= MAX_CSV_ROWS:
            errors.append({"row": n, "reason": f"超過每次 {MAX_CSV_ROWS} 列的上限，這一列起都沒有處理，請分批匯入"})
            break
        rows.append((n, {f: (rec[i].strip() if i < len(rec) else "") for f, i in cols.items()}))
    return rows, errors


def _friendly(e: ValidationError) -> str:
    """把 pydantic 的英文驗證訊息換成使用者看得懂的中文（單列匯入走 422，不需要；CSV 要逐列回報所以要翻）。"""
    out = []
    for x in e.errors():
        field = x["loc"][0] if x["loc"] else ""
        if field == "platform":
            out.append("平台必須是 threads、x、instagram 或 facebook")
        elif field == "text":
            out.append("貼文內容不可為空，也不能超過 1500 字")
        elif field == "author_handle":
            out.append("作者帳號最多 40 字")
        elif field == "source_url":
            out.append(x["msg"].removeprefix("Value error, ") if x["type"] == "value_error" else "來源網址最多 500 字")
        else:
            out.append(x["msg"])
    return "；".join(out)


def import_csv(conn, body: CsvImportIn) -> dict:
    catalog.get_project(conn, body.project_id)  # 專案不存在就整批 404，不要一列一列失敗
    rows, errors = parse_csv(body.csv_text)
    results: list[dict] = []
    stopped = False
    for n, rec in rows:
        if stopped:
            errors.append({"row": n, "reason": "額度不足，之後的列都沒有處理"})
            continue
        try:
            item = PostImportIn(project_id=body.project_id, text=rec.get("text", ""), platform=(rec.get("platform") or body.platform).lower(),
                                author_handle=rec.get("author_handle", ""), source_url=rec.get("source_url", ""))
        except ValidationError as e:
            errors.append({"row": n, "reason": _friendly(e)})
            continue
        try:
            r = import_post(conn, item)
        except DomainError as e:
            errors.append({"row": n, "reason": e.message})
            stopped = e.code == "insufficient_units"
            continue
        ev, d = r["evaluation"], r["draft"]
        results.append({"row": n, "post_id": r["post_id"], "duplicate": r["duplicate"], "intent": ev["intent"], "risk": ev["risk"],
                        "flags": ev["flags"], "draft_id": d["id"] if d else None, "text": item.text[:60]})
    errors.sort(key=lambda x: x["row"])
    return {"rows_processed": len(rows), "imported": len([r for r in results if not r["duplicate"]]),
            "duplicates": len([r for r in results if r["duplicate"]]), "drafts": len([r for r in results if r["draft_id"]]),
            "errors": errors, "results": results}
