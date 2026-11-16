"""搜尋 → 分類 → 草稿 的 domain service。API、worker、agent 全部呼叫這裡，所以規則只有一份。

重點：
* 搜尋（取得資料）與分類（判斷意圖）分開；搜尋結果不代表「有意圖」。
* AI/網路呼叫都在交易之外；每次寫入是短交易。
* 每筆分類與草稿先 reserve 示例 units、成功後 settle、失敗 release。
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from .. import clock
from ..db import jdump, jload, new_id, page, row, rows, tx
from ..errors import Conflict, DomainError, NotFound
from ..providers.social import get_ai, get_social
from . import catalog, ledger, settings


def content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _snippet(text: str, term: str, width: int = 24) -> str:
    i = text.lower().find(term.lower())
    return text[max(0, i - width): i + len(term) + width] if i >= 0 else text[:width * 2]


def search_candidates(conn, project: dict, *, days: int | None = None, extra_exclude: list[str] | None = None,
                      sort: str = "latest", limit: int = 200) -> list[dict]:
    """回傳所有關鍵字命中的貼文，附上 included 與 inclusion/exclusion 原因＋原文證據。
    時間為半開區間 [now-days, now)。"""
    days = days or project["window_days"]
    until = clock.now()
    since = until - timedelta(days=days)
    provider = get_social(conn)
    posts = provider.search_posts(conn, project["keywords"], clock.iso(since), clock.iso(until), sort, limit)
    if provider.name != "demo":
        with tx(conn):
            for p in posts:
                conn.execute("INSERT OR IGNORE INTO source_posts(id,platform,author_handle,text,created_at,likes,replies,is_own,own_account_id,synthetic) "
                             "VALUES(:id,:platform,:author_handle,:text,:created_at,:likes,:replies,0,NULL,0)", p)
    excludes = list(project["exclude_terms"]) + list(extra_exclude or [])
    out = []
    for p in posts:
        text = p["text"]
        hit = next((k for k in project["keywords"] if k.lower() in text.lower()), None)
        missing = [t for t in project["must_terms"] if t.lower() not in text.lower()]
        bad = next((t for t in excludes if t.lower() in text.lower()), None)
        if missing:
            inc, why, ev = False, f"缺少必要條件：{', '.join(missing)}", _snippet(text, hit or "")
        elif bad:
            inc, why, ev = False, f"命中排除條件「{bad}」", _snippet(text, bad)
        else:
            inc, why, ev = True, f"命中關鍵字「{hit}」", _snippet(text, hit or "")
        out.append({**p, "included": inc, "inclusion_reason": why, "evidence": ev})
    return out


def _brand_for(conn, project: dict, version: int | None = None) -> dict:
    return catalog.get_brand(conn, project["brand_id"], version)


def classify_evaluation(conn, eval_id: str, project: dict) -> dict:
    """分類單一 evaluation。AI 呼叫在交易外；失敗只記錄在該筆，不影響其他筆，也不降級成 Demo。"""
    ev = row(conn.execute("SELECT e.*, p.text FROM evaluations e JOIN source_posts p ON p.id=e.post_id WHERE e.id=?", (eval_id,)).fetchone())
    if not ev:
        raise NotFound("找不到評估")
    op = f"classify:{eval_id}"
    with tx(conn):
        ledger.reserve(conn, op, "classify")
    ai = get_ai(conn)
    try:
        c = ai.classify(ev["text"], project)
    except DomainError as e:  # 含 NotConfigured / DependencyError
        with tx(conn):
            conn.execute("UPDATE evaluations SET classify_error=?, classifier=? WHERE id=?", (e.message, ai.name, eval_id))
            ledger.release(conn, op, "分類失敗，釋放")
        return {**ev, "classify_error": e.message}
    with tx(conn):
        conn.execute("UPDATE evaluations SET relevant=?,intent=?,risk=?,reason=?,evidence=?,flags=?,classifier=?,classify_error=NULL WHERE id=?",
                     (int(c.relevant), c.intent, c.risk, c.reason, c.evidence or ev["evidence"], jdump(c.flags), ai.name, eval_id))
        ledger.settle(conn, op)
    return get_evaluation(conn, eval_id)


def get_evaluation(conn, eval_id: str) -> dict:
    r = row(conn.execute("SELECT e.*, p.text post_text, p.author_handle, p.created_at post_created_at, p.platform "
                         "FROM evaluations e JOIN source_posts p ON p.id=e.post_id WHERE e.id=?", (eval_id,)).fetchone())
    if not r:
        raise NotFound("找不到評估")
    r["flags"] = jload(r["flags"], [])
    return r


def create_run(conn, project: dict, trigger: str, params: dict) -> dict:
    rid = new_id("run")
    brand = _brand_for(conn, project)
    with tx(conn):
        conn.execute("INSERT INTO runs(id,project_id,brand_version,params,status,trigger,started_at) VALUES(?,?,?,?,?,?,?)",
                     (rid, project["id"], brand["version"], jdump(params), "running", trigger, clock.now_iso()))
    return rid


def record_candidates(conn, run_id: str, project: dict, candidates: list[dict]) -> list[str]:
    ids = []
    with tx(conn):
        for c in candidates:
            eid = new_id("eval")
            conn.execute("INSERT INTO evaluations(id,run_id,post_id,project_id,included,inclusion_reason,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (eid, run_id, c["id"], project["id"], int(c["included"]), c["inclusion_reason"], c["evidence"], clock.now_iso()))
            if c["included"]:
                ids.append(eid)
        conn.execute("UPDATE runs SET candidates=? WHERE id=?", (len([c for c in candidates if c["included"]]), run_id))
    return ids


def finish_run(conn, run_id: str, status: str, error: str | None = None) -> None:
    with tx(conn):
        conn.execute("UPDATE runs SET status=?, error=?, finished_at=?, "
                     "classified=(SELECT COUNT(*) FROM evaluations WHERE run_id=? AND intent IS NOT NULL), "
                     "drafts=(SELECT COUNT(*) FROM drafts d JOIN evaluations e ON e.id=d.evaluation_id WHERE e.run_id=?) WHERE id=?",
                     (status, error, clock.now_iso(), run_id, run_id, run_id))


def draft_policy_ok(ev: dict) -> bool:
    """哪些評估值得備草稿：明確求助、相關、且不是被標為 prompt injection。"""
    return bool(ev.get("relevant")) and ev.get("intent") == "seeking" and "prompt_injection" not in (ev.get("flags") or [])


def execute_run(conn, project_id: str, trigger: str = "manual", *, days: int | None = None, extra_exclude: list[str] | None = None,
                sort: str = "latest", classify: bool = True, make_drafts: bool = True) -> dict:
    project = catalog.get_project(conn, project_id)
    params = {"days": days or project["window_days"], "extra_exclude": extra_exclude or [], "sort": sort, "keywords": project["keywords"],
              "must_terms": project["must_terms"], "exclude_terms": project["exclude_terms"], "mode": project["mode"]}
    run_id = create_run(conn, project, trigger, params)
    try:
        cands = search_candidates(conn, project, days=days, extra_exclude=extra_exclude, sort=sort)
        eval_ids = record_candidates(conn, run_id, project, cands)
        if classify:
            for eid in eval_ids:
                classify_evaluation(conn, eid, project)
            if make_drafts and project["mode"] != "observe_only":
                from . import drafts as drafts_svc
                for eid in eval_ids:
                    ev = get_evaluation(conn, eid)
                    if draft_policy_ok(ev):
                        drafts_svc.create_draft(conn, project_id, ev["post_id"], evaluation_id=eid, created_by=f"run:{run_id}")
                if project["mode"] == "auto_simulate":
                    from . import drafts as d2
                    d2.auto_simulate_run(conn, project, run_id)
        errors = conn.execute("SELECT COUNT(*) c FROM evaluations WHERE run_id=? AND classify_error IS NOT NULL", (run_id,)).fetchone()["c"]
        finish_run(conn, run_id, "failed" if errors else "succeeded", f"{errors} 筆分類失敗" if errors else None)
    except Exception as e:  # 讓 run 有終局狀態再往外丟
        finish_run(conn, run_id, "failed", f"{type(e).__name__}: {e}")
        raise
    return get_run(conn, run_id)


def get_run(conn, run_id: str) -> dict:
    r = row(conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
    if not r:
        raise NotFound("找不到執行紀錄")
    r["params"] = jload(r["params"], {})
    return r


def list_runs(conn, project_id: str | None, page_no=1, size=20) -> dict:
    where, params = ("WHERE project_id=?", (project_id,)) if project_id else ("", ())
    res = page(conn, f"FROM runs {where}", params, page_no, size, "started_at DESC, rowid DESC")
    for r in res["items"]:
        r["params"] = jload(r["params"], {})
    return res


def run_results(conn, run_id: str, page_no=1, size=50, included: bool | None = None) -> dict:
    get_run(conn, run_id)
    where, params = "WHERE e.run_id=?", [run_id]
    if included is not None:
        where += " AND e.included=?"
        params.append(int(included))
    res = page(conn, f"FROM evaluations e JOIN source_posts p ON p.id=e.post_id {where}", tuple(params), page_no, size,
               "e.included DESC, p.created_at DESC",
               "e.*, p.text post_text, p.author_handle, p.created_at post_created_at, p.platform, p.likes, p.replies")
    for r in res["items"]:
        r["flags"] = jload(r["flags"], [])
        d = conn.execute("SELECT id, status FROM drafts WHERE evaluation_id=? ORDER BY created_at DESC LIMIT 1", (r["id"],)).fetchone()
        r["draft"] = dict(d) if d else None
    return res


def list_evaluations(conn, *, risk=None, intent=None, project_id=None, page_no=1, size=50) -> dict:
    where, params = ["e.intent IS NOT NULL"], []
    for col, v in (("e.risk", risk), ("e.intent", intent), ("e.project_id", project_id)):
        if v:
            where.append(f"{col}=?")
            params.append(v)
    res = page(conn, f"FROM evaluations e JOIN source_posts p ON p.id=e.post_id WHERE {' AND '.join(where)}", tuple(params), page_no, size,
               "e.created_at DESC, e.rowid DESC", "e.*, p.text post_text, p.author_handle, p.created_at post_created_at, p.platform")
    for r in res["items"]:
        r["flags"] = jload(r["flags"], [])
    return res


def list_posts(conn, *, q: str | None = None, page_no=1, size=20, sort="latest") -> dict:
    where, params = "WHERE is_own=0", []
    if q:
        where += " AND text LIKE ?"
        params.append(f"%{q}%")
    order = "(likes+replies*2) DESC, created_at DESC" if sort == "hot" else "created_at DESC"
    return page(conn, f"FROM source_posts {where}", tuple(params), page_no, size, order)
