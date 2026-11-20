"""草稿、核准與模擬送出。

核准綁定 content_hash：approvals 存核准當下的 hash；送出時重算目前內容 hash，不符 = 核准失效。
編輯草稿會同時撤銷既有核准並把狀態退回 draft（雙重保險）。
"""
from __future__ import annotations

from .. import clock
from ..db import new_id, page, row, rows, tx
from ..errors import Conflict, DomainError, NotFound
from ..providers.social import get_ai
from . import catalog, delivery, jobs, ledger, pipeline


def _out(conn, d: dict) -> dict:
    d["requires_human"] = bool(d["requires_human"])
    brand = conn.execute("SELECT current_version FROM brands WHERE id=?", (d["brand_id"],)).fetchone()
    d["brand_outdated"] = bool(brand and brand["current_version"] > d["brand_version"])
    if d["brand_outdated"]:
        d["notice"] = "品牌設定已更新：請重新生成，或確認內容後再次核准"
    ap = conn.execute("SELECT id, content_hash FROM approvals WHERE draft_id=? AND revoked_at IS NULL ORDER BY rowid DESC LIMIT 1", (d["id"],)).fetchone()
    d["approval_valid"] = bool(ap and ap["content_hash"] == d["content_hash"] and d["status"] in ("approved", "sent"))
    att = conn.execute("SELECT id,status,error FROM delivery_attempts WHERE draft_id=? ORDER BY rowid DESC LIMIT 1", (d["id"],)).fetchone()
    d["delivery"] = dict(att) if att else None
    d["manual_outcome"] = active_outcome(conn, d["id"])
    return d


def active_outcome(conn, draft_id: str) -> dict | None:
    o = conn.execute("SELECT id,outcome,note,body,created_at FROM manual_outcomes WHERE draft_id=? AND undone_at IS NULL ORDER BY rowid DESC LIMIT 1", (draft_id,)).fetchone()
    return dict(o) if o else None


def _assert_not_posted(conn, draft_id: str, what: str) -> None:
    o = active_outcome(conn, draft_id)
    if o and o["outcome"] == "posted":
        raise Conflict(f"這則草稿已記錄為「已貼到平台」，不可{what}；若記錄錯了請先復原", "already_posted")


def record_outcome(conn, draft_id: str, outcome: str, note: str = "") -> dict:
    """記錄人工處理結果。posted 需要「核准有效」的草稿（和送出一樣的人工把關）；skipped 隨時可記。"""
    d = get_draft(conn, draft_id)
    if outcome == "posted" and not (d["approval_valid"] and d["status"] in ("approved", "sent")):
        raise Conflict("草稿未核准，或核准已因修改／品牌更新而失效；請先核准再記錄「已貼到平台」", "approval_required")
    ts = clock.now_iso()
    with tx(conn):
        conn.execute("UPDATE manual_outcomes SET undone_at=? WHERE draft_id=? AND undone_at IS NULL", (ts, draft_id))
        conn.execute("INSERT INTO manual_outcomes(id,draft_id,outcome,note,body,content_hash,created_at) VALUES(?,?,?,?,?,?,?)",
                     (new_id("mo"), draft_id, outcome, note.strip(), d["body"], d["content_hash"], ts))
    return get_draft(conn, draft_id)


def undo_outcome(conn, draft_id: str) -> dict:
    get_draft(conn, draft_id)
    with tx(conn):
        conn.execute("UPDATE manual_outcomes SET undone_at=? WHERE draft_id=? AND undone_at IS NULL", (clock.now_iso(), draft_id))
    return get_draft(conn, draft_id)


def get_draft(conn, draft_id: str) -> dict:
    r = row(conn.execute("SELECT d.*, p.text post_text, p.author_handle post_author, p.source_url post_url, p.synthetic post_synthetic "
                         "FROM drafts d JOIN source_posts p ON p.id=d.post_id WHERE d.id=?", (draft_id,)).fetchone())
    if not r:
        raise NotFound("找不到草稿")
    return _out(conn, r)


def list_drafts(conn, *, status: str | None = None, project_id: str | None = None, handling: str | None = None, page_no=1, size=30) -> dict:
    where, params = [], []
    act = "EXISTS(SELECT 1 FROM manual_outcomes m WHERE m.draft_id=d.id AND m.undone_at IS NULL{})"
    if handling == "pending":      # 還沒處理：沒有人工紀錄，且不是已拒絕
        where.append("NOT " + act.format("") + " AND d.status<>'rejected'")
    elif handling in ("posted", "skipped"):
        where.append(act.format(f" AND m.outcome='{handling}'"))
    elif handling:
        raise DomainError("handling 只接受 pending、posted、skipped", "invalid_filter")
    if status:
        where.append("d.status=?")
        params.append(status)
    if project_id:
        where.append("d.project_id=?")
        params.append(project_id)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    res = page(conn, f"FROM drafts d JOIN source_posts p ON p.id=d.post_id {w}", tuple(params), page_no, size, "d.created_at DESC, d.rowid DESC",
               "d.*, p.text post_text, p.author_handle post_author, p.source_url post_url, p.synthetic post_synthetic")
    res["items"] = [_out(conn, d) for d in res["items"]]
    return res


def create_draft(conn, project_id: str, post_id: str, *, evaluation_id: str | None = None, created_by: str = "user") -> dict:
    project = catalog.get_project(conn, project_id)
    post = row(conn.execute("SELECT * FROM source_posts WHERE id=?", (post_id,)).fetchone())
    if not post:
        raise NotFound("找不到貼文")
    if evaluation_id is None:
        e = conn.execute("SELECT id FROM evaluations WHERE post_id=? AND project_id=? AND intent IS NOT NULL ORDER BY created_at DESC, rowid DESC LIMIT 1",
                         (post_id, project_id)).fetchone()
        if not e:
            raise Conflict("此貼文尚未在該專案分類，請先執行分類再準備草稿", "not_classified")
        evaluation_id = e["id"]
    ev = pipeline.get_evaluation(conn, evaluation_id)
    if "prompt_injection" in ev["flags"]:
        raise Conflict("此貼文被標為 prompt injection，不產生草稿", "unsafe_post")
    if ev["intent"] is None:
        raise Conflict("此評估尚未分類", "not_classified")
    existing = conn.execute("SELECT id FROM drafts WHERE project_id=? AND post_id=? AND status IN ('draft','approved')", (project_id, post_id)).fetchone()
    if existing:
        return get_draft(conn, existing["id"])  # 同一專案同一貼文只留一份有效草稿（也是 unique index）
    brand = catalog.get_brand(conn, project["brand_id"])
    did = new_id("draft")
    op = f"draft:{did}"
    with tx(conn):
        ledger.reserve(conn, op, "draft")
    ai = get_ai(conn)
    try:
        body = ai.draft(post, brand, ev)
    except DomainError:
        with tx(conn):
            ledger.release(conn, op, "草稿生成失敗")
        raise
    for bad in brand["data"].get("forbidden", []):
        if bad and bad in body:
            with tx(conn):
                ledger.release(conn, op, "草稿違反不可承諾事項")
            raise Conflict(f"草稿含不可承諾內容「{bad}」，已拒絕")
    ts = clock.now_iso()
    with tx(conn):
        conn.execute(
            "INSERT INTO drafts(id,project_id,post_id,evaluation_id,brand_id,brand_version,body,content_hash,status,requires_human,source,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, project_id, post_id, evaluation_id, brand["id"], brand["version"], body, pipeline.content_hash(body), "draft",
             int(ev["risk"] in ("high", "medium")), ai.name, created_by, ts, ts))
        ledger.settle(conn, op)
    return get_draft(conn, did)


def edit_draft(conn, draft_id: str, body: str) -> dict:
    d = get_draft(conn, draft_id)
    if d["status"] == "sent":
        raise Conflict("已送出的草稿不可修改")
    _assert_not_posted(conn, draft_id, "修改")
    ts = clock.now_iso()
    with tx(conn):
        conn.execute("UPDATE drafts SET body=?, content_hash=?, revision=revision+1, status='draft', updated_at=? WHERE id=?",
                     (body, pipeline.content_hash(body), ts, draft_id))
        conn.execute("UPDATE approvals SET revoked_at=? WHERE draft_id=? AND revoked_at IS NULL", (ts, draft_id))
    return get_draft(conn, draft_id)


def approve(conn, draft_id: str, approved_by: str = "user") -> dict:
    d = get_draft(conn, draft_id)
    if d["status"] in ("sent", "rejected"):
        raise Conflict(f"狀態為 {d['status']} 的草稿不可核准")
    ts = clock.now_iso()
    with tx(conn):
        conn.execute("UPDATE approvals SET revoked_at=? WHERE draft_id=? AND revoked_at IS NULL", (ts, draft_id))
        conn.execute("INSERT INTO approvals(id,draft_id,content_hash,approved_by,approved_at) VALUES(?,?,?,?,?)",
                     (new_id("appr"), draft_id, d["content_hash"], approved_by, ts))
        conn.execute("UPDATE drafts SET status='approved', updated_at=? WHERE id=?", (ts, draft_id))
    return get_draft(conn, draft_id)


def reject(conn, draft_id: str) -> dict:
    d = get_draft(conn, draft_id)
    if d["status"] == "sent":
        raise Conflict("已送出的草稿不可拒絕")
    _assert_not_posted(conn, draft_id, "拒絕")
    ts = clock.now_iso()
    with tx(conn):
        conn.execute("UPDATE drafts SET status='rejected', updated_at=? WHERE id=?", (ts, draft_id))
        conn.execute("UPDATE approvals SET revoked_at=? WHERE draft_id=? AND revoked_at IS NULL", (ts, draft_id))
    return get_draft(conn, draft_id)


def on_brand_updated(conn, brand_id: str) -> None:
    """品牌改版：未送出的草稿保留原 brand_version，但核准撤銷（需重新核准）。"""
    ts = clock.now_iso()
    with tx(conn):
        conn.execute("UPDATE approvals SET revoked_at=? WHERE revoked_at IS NULL AND draft_id IN "
                     "(SELECT id FROM drafts WHERE brand_id=? AND status='approved')", (ts, brand_id))
        conn.execute("UPDATE drafts SET status='draft', updated_at=? WHERE brand_id=? AND status='approved'", (ts, brand_id))


def regenerate(conn, draft_id: str) -> dict:
    d = get_draft(conn, draft_id)
    if d["status"] == "sent":
        raise Conflict("已送出的草稿不可重新生成")
    _assert_not_posted(conn, draft_id, "重新生成")
    with tx(conn):
        conn.execute("UPDATE drafts SET status='rejected', updated_at=? WHERE id=?", (clock.now_iso(), draft_id))
        conn.execute("UPDATE approvals SET revoked_at=? WHERE draft_id=? AND revoked_at IS NULL", (clock.now_iso(), draft_id))
    return create_draft(conn, d["project_id"], d["post_id"], evaluation_id=d["evaluation_id"], created_by="regenerate")


def simulate_send(conn, draft_id: str) -> dict:
    d = get_draft(conn, draft_id)
    if d["status"] == "sent" and d["delivery"]:
        att, replayed = delivery.get_attempt(conn, d["delivery"]["id"]), True
        return {"attempt": att, "replayed": replayed, "draft": d}
    if d["status"] != "approved" or not d["approval_valid"]:
        raise Conflict("草稿未核准，或核准已因修改／品牌更新而失效；不可送出", "approval_required")
    if d["requires_human"]:
        ap = conn.execute("SELECT approved_by FROM approvals WHERE draft_id=? AND revoked_at IS NULL ORDER BY rowid DESC LIMIT 1", (draft_id,)).fetchone()
        if ap and ap["approved_by"].startswith("policy:"):
            raise Conflict("高／中風險草稿需要人工核准，不接受政策自動核准", "human_required")
    att, replayed = delivery.deliver(conn, dedup_key=f"draft:{draft_id}:public_reply", kind="draft_reply",
                                     fields={"draft_id": draft_id, "recipient": d["post_author"], "body": d["body"]})
    if att["status"] == "simulated_sent":
        with tx(conn):
            conn.execute("UPDATE drafts SET status='sent', updated_at=? WHERE id=?", (clock.now_iso(), draft_id))
    return {"attempt": att, "replayed": replayed, "draft": get_draft(conn, draft_id)}


def auto_simulate_run(conn, project: dict, run_id: str) -> int:
    """Auto Simulate：低風險草稿由政策核准並排入送出工作；受每日上限限制；高／中風險一律留給人工。"""
    today = clock.now().strftime("%Y-%m-%d")
    used = conn.execute("SELECT COUNT(*) c FROM approvals a JOIN drafts d ON d.id=a.draft_id WHERE a.approved_by='policy:auto_simulate' "
                        "AND d.project_id=? AND substr(a.approved_at,1,10)=?", (project["id"], today)).fetchone()["c"]
    n = 0
    for d in rows(conn.execute("SELECT d.id FROM drafts d JOIN evaluations e ON e.id=d.evaluation_id WHERE e.run_id=? AND d.status='draft' "
                               "AND d.requires_human=0 ORDER BY d.created_at", (run_id,))):
        if used + n >= project["daily_limit"]:
            break
        approve(conn, d["id"], approved_by="policy:auto_simulate")
        jobs.enqueue(conn, "send_draft", {"draft_id": d["id"]}, idempotency_key=f"send_draft:{d['id']}", side_effect=True)
        n += 1
    return n
