"""品牌（版本化）、Demo 帳號、專案 CRUD。"""
from __future__ import annotations

from datetime import timedelta

from .. import clock
from ..db import jdump, jload, new_id, row, rows, tx
from ..errors import Conflict, NotFound
from ..schemas import AccountIn, BrandIn, ProjectIn


# ---------- brands ----------
def _brand_out(conn, b: dict) -> dict:
    v = conn.execute("SELECT data FROM brand_versions WHERE brand_id=? AND version=?", (b["id"], b["current_version"])).fetchone()
    return {**b, "data": jload(v["data"], {})}


def list_brands(conn) -> list[dict]:
    return [_brand_out(conn, b) for b in rows(conn.execute("SELECT * FROM brands ORDER BY created_at, name"))]


def get_brand(conn, brand_id: str, version: int | None = None) -> dict:
    b = row(conn.execute("SELECT * FROM brands WHERE id=?", (brand_id,)).fetchone())
    if not b:
        raise NotFound("找不到品牌")
    if version is not None:
        v = conn.execute("SELECT data FROM brand_versions WHERE brand_id=? AND version=?", (brand_id, version)).fetchone()
        if not v:
            raise NotFound("找不到品牌版本")
        return {**b, "version": version, "data": jload(v["data"], {})}
    out = _brand_out(conn, b)
    out["version"] = b["current_version"]
    return out


def create_brand(conn, body: BrandIn) -> dict:
    ts = clock.now_iso()
    bid = new_id("brand")
    with tx(conn):
        if conn.execute("SELECT 1 FROM brands WHERE name=?", (body.name,)).fetchone():
            raise Conflict("品牌名稱已存在")
        conn.execute("INSERT INTO brands(id,name,current_version,created_at,updated_at) VALUES(?,?,?,?,?)", (bid, body.name, 1, ts, ts))
        conn.execute("INSERT INTO brand_versions(id,brand_id,version,data,created_at) VALUES(?,?,?,?,?)",
                     (new_id("bv"), bid, 1, jdump(body.data.model_dump()), ts))
    return get_brand(conn, bid)


def update_brand(conn, brand_id: str, body: BrandIn) -> dict:
    """每次更新新增一個 version；舊版本與引用它的草稿保持不變。"""
    ts = clock.now_iso()
    with tx(conn):
        b = conn.execute("SELECT * FROM brands WHERE id=?", (brand_id,)).fetchone()
        if not b:
            raise NotFound("找不到品牌")
        dup = conn.execute("SELECT 1 FROM brands WHERE name=? AND id<>?", (body.name, brand_id)).fetchone()
        if dup:
            raise Conflict("品牌名稱已存在")
        nv = b["current_version"] + 1
        conn.execute("INSERT INTO brand_versions(id,brand_id,version,data,created_at) VALUES(?,?,?,?,?)",
                     (new_id("bv"), brand_id, nv, jdump(body.data.model_dump()), ts))
        conn.execute("UPDATE brands SET name=?, current_version=?, updated_at=? WHERE id=?", (body.name, nv, ts, brand_id))
    return get_brand(conn, brand_id)


# ---------- accounts ----------
def list_accounts(conn) -> list[dict]:
    return rows(conn.execute("SELECT * FROM social_accounts ORDER BY platform, handle"))


def create_account(conn, body: AccountIn) -> dict:
    if body.brand_id and not conn.execute("SELECT 1 FROM brands WHERE id=?", (body.brand_id,)).fetchone():
        raise NotFound("找不到品牌")
    aid = new_id("acct")
    with tx(conn):
        if conn.execute("SELECT 1 FROM social_accounts WHERE platform=? AND handle=?", (body.platform, body.handle)).fetchone():
            raise Conflict("此平台帳號已存在")
        conn.execute("INSERT INTO social_accounts(id,platform,handle,display_name,brand_id,created_at) VALUES(?,?,?,?,?,?)",
                     (aid, body.platform, body.handle, body.display_name, body.brand_id, clock.now_iso()))
    return row(conn.execute("SELECT * FROM social_accounts WHERE id=?", (aid,)).fetchone())


def update_account(conn, account_id: str, body: AccountIn) -> dict:
    if not conn.execute("SELECT 1 FROM social_accounts WHERE id=?", (account_id,)).fetchone():
        raise NotFound("找不到帳號")
    if body.brand_id and not conn.execute("SELECT 1 FROM brands WHERE id=?", (body.brand_id,)).fetchone():
        raise NotFound("找不到品牌")
    with tx(conn):
        conn.execute("UPDATE social_accounts SET platform=?, handle=?, display_name=?, brand_id=? WHERE id=?",
                     (body.platform, body.handle, body.display_name, body.brand_id, account_id))
    return row(conn.execute("SELECT * FROM social_accounts WHERE id=?", (account_id,)).fetchone())


# ---------- projects ----------
def _proj_out(p: dict) -> dict:
    for k in ("keywords", "must_terms", "exclude_terms"):
        p[k] = jload(p[k], [])
    for k in ("schedule_enabled", "enabled"):
        p[k] = bool(p[k])
    return p


def list_projects(conn) -> list[dict]:
    return [_proj_out(p) for p in rows(conn.execute("SELECT * FROM projects ORDER BY created_at, name"))]


def get_project(conn, pid: str) -> dict:
    p = row(conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
    if not p:
        raise NotFound("找不到專案")
    return _proj_out(p)


def _check_refs(conn, body: ProjectIn) -> None:
    if not conn.execute("SELECT 1 FROM brands WHERE id=?", (body.brand_id,)).fetchone():
        raise NotFound("找不到品牌")
    if not conn.execute("SELECT 1 FROM social_accounts WHERE id=?", (body.account_id,)).fetchone():
        raise NotFound("找不到帳號")


def _next_run(body: ProjectIn, current: str | None = None) -> str | None:
    if not body.schedule_enabled:
        return None
    return current or clock.iso(clock.now() + timedelta(seconds=body.interval_seconds))


def create_project(conn, body: ProjectIn) -> dict:
    _check_refs(conn, body)
    pid, ts = new_id("proj"), clock.now_iso()
    with tx(conn):
        conn.execute(
            "INSERT INTO projects(id,name,brand_id,account_id,purpose,keywords,must_terms,exclude_terms,window_days,mode,daily_limit,"
            "schedule_enabled,interval_seconds,next_run_at,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, body.name, body.brand_id, body.account_id, body.purpose, jdump(body.keywords), jdump(body.must_terms),
             jdump(body.exclude_terms), body.window_days, body.mode, body.daily_limit, int(body.schedule_enabled),
             body.interval_seconds, _next_run(body), int(body.enabled), ts, ts))
    return get_project(conn, pid)


def update_project(conn, pid: str, body: ProjectIn) -> dict:
    """修改排程只更新 next_run_at 欄位（單一來源），不會額外 enqueue，所以不會雙重排程。"""
    old = get_project(conn, pid)
    _check_refs(conn, body)
    keep = old["next_run_at"] if (old["schedule_enabled"] and body.schedule_enabled and old["interval_seconds"] == body.interval_seconds) else None
    with tx(conn):
        conn.execute(
            "UPDATE projects SET name=?,brand_id=?,account_id=?,purpose=?,keywords=?,must_terms=?,exclude_terms=?,window_days=?,mode=?,"
            "daily_limit=?,schedule_enabled=?,interval_seconds=?,next_run_at=?,enabled=?,updated_at=? WHERE id=?",
            (body.name, body.brand_id, body.account_id, body.purpose, jdump(body.keywords), jdump(body.must_terms),
             jdump(body.exclude_terms), body.window_days, body.mode, body.daily_limit, int(body.schedule_enabled),
             body.interval_seconds, _next_run(body, keep), int(body.enabled), clock.now_iso(), pid))
    return get_project(conn, pid)


def delete_project(conn, pid: str) -> None:
    get_project(conn, pid)
    with tx(conn):
        used = conn.execute("SELECT 1 FROM runs WHERE project_id=? LIMIT 1", (pid,)).fetchone()
        if used:
            raise Conflict("專案已有執行紀錄，請改為停用而不是刪除")
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
