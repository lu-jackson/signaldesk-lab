"""名單：以 platform+handle 去重，保留多來源與歷史；匯出分頁走完所有資料。"""
from __future__ import annotations

import csv
import io

from .. import clock
from ..db import new_id, page, row, rows, tx
from ..errors import Conflict, NotFound
from ..schemas import LeadPatch

DEFAULT_LIST = "預設名單"
CSV_COLUMNS = [
    ("lead_id", "名單 ID"), ("platform", "平台"), ("handle", "帳號（合成）"), ("status", "狀態（Converted 為人工分類，不代表訂單）"),
    ("note", "備註"), ("source_count", "來源數"), ("sources", "來源（貼文ID: 理由；以 | 分隔）"), ("created_at", "建立時間 UTC"), ("updated_at", "更新時間 UTC"),
]


def default_list_id(conn) -> str:
    r = conn.execute("SELECT id FROM lead_lists WHERE name=?", (DEFAULT_LIST,)).fetchone()
    if r:
        return r["id"]
    lid = new_id("list")
    conn.execute("INSERT OR IGNORE INTO lead_lists(id,name,created_at) VALUES(?,?,?)", (lid, DEFAULT_LIST, clock.now_iso()))
    return conn.execute("SELECT id FROM lead_lists WHERE name=?", (DEFAULT_LIST,)).fetchone()["id"]


def _activity(conn, lead_id: str, kind: str, detail: str) -> None:
    conn.execute("INSERT INTO lead_activity(id,lead_id,kind,detail,created_at) VALUES(?,?,?,?,?)", (new_id("act"), lead_id, kind, detail, clock.now_iso()))


def upsert_lead(conn, platform: str, handle: str, post_id: str | None, reason: str, activity: str | None = None) -> dict:
    handle = handle.strip().lstrip("@")
    if post_id and not conn.execute("SELECT 1 FROM source_posts WHERE id=?", (post_id,)).fetchone():
        raise NotFound("找不到來源貼文")
    ts = clock.now_iso()
    with tx(conn):
        ex = conn.execute("SELECT id FROM leads WHERE platform=? AND handle=?", (platform, handle)).fetchone()
        if ex:
            lid, created = ex["id"], False
        else:
            lid, created = new_id("lead"), True
            conn.execute("INSERT INTO leads(id,platform,handle,list_id,status,created_at,updated_at) VALUES(?,?,?,?,'New',?,?)",
                         (lid, platform, handle, default_list_id(conn), ts, ts))
            _activity(conn, lid, "created", f"建立名單：{reason}")
        added = conn.execute("INSERT OR IGNORE INTO lead_sources(id,lead_id,post_id,reason,created_at) VALUES(?,?,?,?,?)",
                             (new_id("src"), lid, post_id, reason, ts)).rowcount
        if added and not created:
            _activity(conn, lid, "source_added", f"新增來源：{reason}")
        if activity:
            _activity(conn, lid, "event", activity)
        conn.execute("UPDATE leads SET updated_at=? WHERE id=?", (ts, lid))
    return get_lead(conn, lid)


def get_lead(conn, lid: str) -> dict:
    r = row(conn.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone())
    if not r:
        raise NotFound("找不到名單")
    r["sources"] = rows(conn.execute("SELECT s.*, p.text post_text FROM lead_sources s LEFT JOIN source_posts p ON p.id=s.post_id WHERE lead_id=? ORDER BY s.created_at, s.rowid", (lid,)))
    r["activity"] = rows(conn.execute("SELECT * FROM lead_activity WHERE lead_id=? ORDER BY created_at, rowid", (lid,)))
    return r


def patch_lead(conn, lid: str, body: LeadPatch) -> dict:
    cur = get_lead(conn, lid)
    ts = clock.now_iso()
    with tx(conn):
        if body.status and body.status != cur["status"]:
            conn.execute("UPDATE leads SET status=?, updated_at=? WHERE id=?", (body.status, ts, lid))
            _activity(conn, lid, "status", f"{cur['status']} → {body.status}" + ("（人工分類，不代表訂單）" if body.status == "Converted" else ""))
        if body.note is not None and body.note != cur["note"]:
            conn.execute("UPDATE leads SET note=?, updated_at=? WHERE id=?", (body.note, ts, lid))
            _activity(conn, lid, "note", "更新備註")
    return get_lead(conn, lid)


def _filters(status: str | None, q: str | None) -> tuple[str, tuple]:
    where, params = [], []
    if status:
        where.append("l.status=?")
        params.append(status)
    if q:
        where.append("l.handle LIKE ?")
        params.append(f"%{q}%")
    return ("WHERE " + " AND ".join(where)) if where else "", tuple(params)


def list_leads(conn, status=None, q=None, page_no=1, size=30) -> dict:
    w, p = _filters(status, q)
    res = page(conn, f"FROM leads l {w}", p, page_no, size, "l.updated_at DESC, l.rowid DESC",
               "l.*, (SELECT COUNT(*) FROM lead_sources s WHERE s.lead_id=l.id) source_count")
    return res


def _iter_all(conn, status, q, chunk: int):
    """逐頁走完所有符合資料（不是只匯出畫面已載入的那一頁）。"""
    w, p = _filters(status, q)
    last_rowid = 0
    while True:
        batch = rows(conn.execute(f"SELECT l.*, l.rowid rid FROM leads l {w + (' AND ' if w else 'WHERE ')} l.rowid>? ORDER BY l.rowid LIMIT ?", (*p, last_rowid, chunk)))
        if not batch:
            return
        for b in batch:
            yield b
        last_rowid = batch[-1]["rid"]


def csv_safe(v) -> str:
    """CSV formula injection：以 = + - @ Tab CR 開頭的儲存格前綴單引號。"""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_csv(conn, status=None, q=None, chunk: int = 200) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"{k}（{label}）" for k, label in CSV_COLUMNS])
    for l in _iter_all(conn, status, q, chunk):
        srcs = rows(conn.execute("SELECT post_id, reason FROM lead_sources WHERE lead_id=? ORDER BY created_at, rowid", (l["id"],)))
        w.writerow([csv_safe(x) for x in (l["id"], l["platform"], l["handle"], l["status"], l["note"], len(srcs),
                                          " | ".join(f"{s['post_id']}: {s['reason']}" for s in srcs), l["created_at"], l["updated_at"])])
    return out.getvalue()


def export_json(conn, status=None, q=None, chunk: int = 200) -> dict:
    items = [get_lead(conn, l["id"]) for l in _iter_all(conn, status, q, chunk)]
    return {"exported_at": clock.now_iso(), "count": len(items), "note": "Converted 為人工分類，不代表訂單；資料皆為合成。", "leads": items}
