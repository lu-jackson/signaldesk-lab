"""留言 → 公開回覆＋私訊 模擬。

兩條入口，明確分開：
  1. process_existing(rule)：「既有留言一次處理」— 對目前已存在的符合留言各建立工作。
  2. ingest_event(event)：「新事件觸發」— webhook simulator 先落地 event_id 去重，再排工作。
兩條入口最後都走同一個 job `comment_channel`（一個 comment × 一個 channel），
job 的 idempotency_key 與 delivery_dedup 都是 comment:{id}:{channel}（不含 workflow version）。
"""
from __future__ import annotations

from urllib.parse import urlparse

from .. import clock
from ..db import jdump, jload, new_id, page, row, rows, tx
from ..errors import Conflict, DomainError, NotFound
from ..schemas import CommentEventIn, RuleIn
from . import delivery, jobs, leads


def _rule_out(r: dict) -> dict:
    r["keywords"] = jload(r["keywords"], [])
    r["links"] = jload(r["links"], [])
    r["send_dm"] = bool(r["send_dm"])
    r["enabled"] = bool(r["enabled"])
    return r


def _check(conn, body: RuleIn) -> None:
    p = conn.execute("SELECT is_own FROM source_posts WHERE id=?", (body.post_id,)).fetchone()
    if not p:
        raise NotFound("找不到貼文")
    if not p["is_own"]:
        raise Conflict("自動化只能設定在 Demo 自有貼文上")
    for u in body.links:
        pr = urlparse(u)
        if pr.scheme not in ("http", "https") or not pr.hostname:
            raise DomainError(f"連結不合法（只接受 http/https）：{u}", "invalid_link")
    if any(not k.strip() for k in body.keywords):
        raise DomainError("關鍵字不可為空白")


def list_rules(conn) -> list[dict]:
    return [_rule_out(r) for r in rows(conn.execute("SELECT * FROM automation_rules ORDER BY created_at, rowid"))]


def get_rule(conn, rid: str) -> dict:
    r = row(conn.execute("SELECT * FROM automation_rules WHERE id=?", (rid,)).fetchone())
    if not r:
        raise NotFound("找不到自動化規則")
    return _rule_out(r)


def create_rule(conn, body: RuleIn) -> dict:
    _check(conn, body)
    rid, ts = new_id("rule"), clock.now_iso()
    with tx(conn):
        conn.execute("INSERT INTO automation_rules(id,name,post_id,keywords,reply_template,dm_template,send_dm,links,version,enabled,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,1,?,?,?)",
                     (rid, body.name, body.post_id, jdump([k.strip() for k in body.keywords]), body.reply_template, body.dm_template,
                      int(body.send_dm), jdump(body.links), int(body.enabled), ts, ts))
    return get_rule(conn, rid)


def update_rule(conn, rid: str, body: RuleIn) -> dict:
    get_rule(conn, rid)
    _check(conn, body)
    with tx(conn):
        conn.execute("UPDATE automation_rules SET name=?,post_id=?,keywords=?,reply_template=?,dm_template=?,send_dm=?,links=?,enabled=?,"
                     "version=version+1,updated_at=? WHERE id=?",
                     (body.name, body.post_id, jdump([k.strip() for k in body.keywords]), body.reply_template, body.dm_template,
                      int(body.send_dm), jdump(body.links), int(body.enabled), clock.now_iso(), rid))
    return get_rule(conn, rid)


def matches(rule: dict, text: str) -> str | None:
    low = text.lower()
    return next((k for k in rule["keywords"] if k.lower() in low), None)  # contains、大小寫不敏感、OR


def render(rule: dict, template: str) -> str:
    return template + ("\n" + "\n".join(rule["links"]) if rule["links"] else "")


def preview(conn, rid: str) -> dict:
    """預覽：只計算，不寫任何投遞或工作。"""
    rule = get_rule(conn, rid)
    cs = rows(conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY created_at", (rule["post_id"],)))
    hits = []
    for c in cs:
        kw = matches(rule, c["text"])
        if kw:
            done = {ch: bool(conn.execute("SELECT 1 FROM delivery_dedup WHERE dedup_key=?", (f"comment:{c['id']}:{ch}",)).fetchone())
                    for ch in ("public_reply", "dm")}
            hits.append({"comment_id": c["id"], "author": c["author_handle"], "text": c["text"], "matched_keyword": kw, "already_handled": done})
    return {"rule": rule, "total_comments": len(cs), "matching": len(hits), "matches": hits,
            "public_reply_preview": render(rule, rule["reply_template"]),
            "dm_preview": render(rule, rule["dm_template"]) if rule["send_dm"] else None,
            "note": "預覽不會送出任何內容"}


def _channels(rule: dict) -> list[str]:
    return ["public_reply"] + (["dm"] if rule["send_dm"] else [])


def enqueue_comment(conn, rule: dict, comment: dict) -> list[dict]:
    out = []
    for ch in _channels(rule):
        out.append(jobs.enqueue(conn, "comment_channel", {"rule_id": rule["id"], "comment_id": comment["id"], "channel": ch},
                                idempotency_key=f"comment:{comment['id']}:{ch}", side_effect=True))
    return out


def process_existing(conn, rid: str) -> dict:
    rule = get_rule(conn, rid)
    if not rule["enabled"]:
        raise Conflict("規則已停用")
    n = 0
    queued = []
    for c in rows(conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY created_at", (rule["post_id"],))):
        if matches(rule, c["text"]):
            queued += enqueue_comment(conn, rule, c)
            n += 1
    return {"mode": "existing_comments", "matched_comments": n, "jobs": [j["id"] for j in queued]}


def ingest_event(conn, body: CommentEventIn) -> dict:
    """webhook simulator：先落地 event_id（UNIQUE）去重，再排工作。重複事件回相同接受結果。"""
    if not conn.execute("SELECT 1 FROM source_posts WHERE id=?", (body.post_id,)).fetchone():
        raise NotFound("找不到貼文")
    ts = clock.now_iso()
    with tx(conn):
        ex = conn.execute("SELECT * FROM events WHERE event_id=?", (body.event_id,)).fetchone()
        if ex:
            return {"accepted": True, "duplicate": True, "event_id": body.event_id, "event_status": ex["status"]}
        cid = f"cmt_{body.event_id}"[:60]
        conn.execute("INSERT INTO events(id,event_id,type,payload,received_at) VALUES(?,?,?,?,?)",
                     (new_id("evt"), body.event_id, "comment.created", jdump(body.model_dump()), ts))
        conn.execute("INSERT OR IGNORE INTO comments(id,post_id,author_handle,text,created_at,synthetic) VALUES(?,?,?,?,?,1)",
                     (cid, body.post_id, body.author_handle, body.text, ts))
    jobs.enqueue(conn, "process_event", {"event_id": body.event_id, "comment_id": cid}, idempotency_key=f"event:{body.event_id}")
    return {"accepted": True, "duplicate": False, "event_id": body.event_id, "event_status": "received"}


def handle_event(conn, payload: dict) -> dict:
    """worker：處理 comment.created — 找出該貼文的啟用規則，對符合者排 channel 工作。"""
    c = row(conn.execute("SELECT * FROM comments WHERE id=?", (payload["comment_id"],)).fetchone())
    n = 0
    if c:
        for rule in list_rules(conn):
            if rule["enabled"] and rule["post_id"] == c["post_id"] and matches(rule, c["text"]):
                enqueue_comment(conn, rule, c)
                n += 1
    with tx(conn):
        conn.execute("UPDATE events SET status='processed', processed_at=? WHERE event_id=?", (clock.now_iso(), payload["event_id"]))
    return {"rules_matched": n}


def handle_channel(conn, payload: dict, job: dict) -> dict:
    """worker：一個 comment × 一個 channel 的模擬投遞。"""
    rule = get_rule(conn, payload["rule_id"])
    c = row(conn.execute("SELECT * FROM comments WHERE id=?", (payload["comment_id"],)).fetchone())
    if not c:
        raise jobs.TerminalError("留言不存在")
    if jobs.is_cancelled(conn, job["id"]):
        return {"skipped": "cancelled"}
    ch = payload["channel"]
    tpl = rule["reply_template"] if ch == "public_reply" else rule["dm_template"]
    att, replayed = delivery.deliver(conn, dedup_key=f"comment:{c['id']}:{ch}", kind=ch,
                                     fields={"comment_id": c["id"], "rule_id": rule["id"], "rule_version": rule["version"],
                                             "recipient": c["author_handle"], "body": render(rule, tpl)})
    if att["status"] == "simulated_sent" and not replayed and ch == "public_reply":
        leads.upsert_lead(conn, "threads", c["author_handle"], c["post_id"], f"留言命中關鍵字「{matches(rule, c['text'])}」",
                          activity=f"自動化 {rule['name']} v{rule['version']} 公開回覆已模擬送出")
    if att["status"] == "failed_retryable":
        raise jobs.RetryableError(att["error"] or "可重試錯誤")
    if att["status"] == "unknown":
        raise jobs.UnknownOutcome(att["error"] or "結果不明")
    if att["status"] == "failed_terminal":
        raise jobs.TerminalError(att["error"] or "終局失敗")
    return {"attempt_id": att["id"], "status": att["status"], "replayed": replayed}
