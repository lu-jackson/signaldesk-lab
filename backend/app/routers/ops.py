"""自動化／模擬器／工作／投遞／名單／追蹤／分析。"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from ..db import page as db_page
from ..deps import get_conn
from ..schemas import CommentEventIn, InjectIn, LeadIn, LeadPatch, LinkIn, RuleIn
from ..services import automations, delivery, jobs, leads, settings, tracking

r = APIRouter(prefix="/api")
public = APIRouter()


# ---- automations ----
@r.get("/automations")
def rules(conn=Depends(get_conn)):
    return {"items": automations.list_rules(conn)}


@r.post("/automations", status_code=201)
def rule_create(body: RuleIn, conn=Depends(get_conn)):
    return automations.create_rule(conn, body)


@r.put("/automations/{rid}")
def rule_update(rid: str, body: RuleIn, conn=Depends(get_conn)):
    return automations.update_rule(conn, rid, body)


@r.post("/automations/{rid}/preview")
def rule_preview(rid: str, conn=Depends(get_conn)):
    return automations.preview(conn, rid)


@r.post("/automations/{rid}/process-existing", status_code=202)
def rule_process_existing(rid: str, conn=Depends(get_conn)):
    return automations.process_existing(conn, rid)


@r.get("/posts/own")
def own_posts(conn=Depends(get_conn)):
    from ..db import rows
    out = rows(conn.execute("SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) comment_count FROM source_posts p WHERE is_own=1 ORDER BY id"))
    return {"items": out}


@r.get("/posts/{post_id}/comments")
def post_comments(post_id: str, page: int = 1, page_size: int = 50, conn=Depends(get_conn)):
    return db_page(conn, "FROM comments WHERE post_id=?", (post_id,), page, page_size, "created_at DESC, rowid DESC")


# ---- simulator ----
@r.post("/simulator/events", status_code=202)
def sim_event(body: CommentEventIn, conn=Depends(get_conn)):
    return automations.ingest_event(conn, body)


@r.post("/simulator/inject")
def sim_inject(body: InjectIn, conn=Depends(get_conn)):
    settings.set_value(conn, f"inject_{body.channel}", body.outcome)
    return settings.capabilities(conn)["injection"]


@r.get("/events")
def events(page: int = 1, page_size: int = 30, conn=Depends(get_conn)):
    return db_page(conn, "FROM events", (), page, page_size, "received_at DESC, rowid DESC")


# ---- deliveries ----
@r.get("/deliveries")
def deliveries(limit: int = 100, conn=Depends(get_conn)):
    return {"items": delivery.list_attempts(conn, min(limit, 500))}


@r.post("/deliveries/{aid}/reconcile")
def reconcile(aid: str, resolution: str, conn=Depends(get_conn)):
    return delivery.reconcile(conn, aid, resolution)


# ---- jobs ----
@r.get("/jobs")
def jobs_list(status: str | None = None, page: int = 1, page_size: int = 30, conn=Depends(get_conn)):
    return {**jobs.list_jobs(conn, status, page, page_size), "stats": jobs.stats(conn)}


@r.post("/jobs/{jid}/cancel")
def job_cancel(jid: str, conn=Depends(get_conn)):
    return jobs.cancel(conn, jid)


@r.post("/jobs/{jid}/retry")
def job_retry(jid: str, conn=Depends(get_conn)):
    return jobs.retry(conn, jid)


# ---- leads ----
@r.get("/leads")
def leads_list(status: str | None = None, q: str | None = None, page: int = 1, page_size: int = 30, conn=Depends(get_conn)):
    return leads.list_leads(conn, status, q, page, page_size)


@r.post("/leads", status_code=201)
def lead_add(body: LeadIn, conn=Depends(get_conn)):
    return leads.upsert_lead(conn, body.platform, body.handle, body.post_id, body.reason, activity="手動加入／新增來源")


@r.get("/leads/export.csv")
def leads_csv(status: str | None = None, q: str | None = None, conn=Depends(get_conn)):
    return Response(leads.export_csv(conn, status, q), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=leads.csv"})


@r.get("/leads/export.json")
def leads_json(status: str | None = None, q: str | None = None, conn=Depends(get_conn)):
    return leads.export_json(conn, status, q)


@r.get("/leads/{lid}")
def lead_get(lid: str, conn=Depends(get_conn)):
    return leads.get_lead(conn, lid)


@r.patch("/leads/{lid}")
def lead_patch(lid: str, body: LeadPatch, conn=Depends(get_conn)):
    return leads.patch_lead(conn, lid, body)


@r.get("/lists")
def lists(conn=Depends(get_conn)):
    from ..db import rows
    return {"items": rows(conn.execute("SELECT l.*, (SELECT COUNT(*) FROM leads x WHERE x.list_id=l.id) lead_count FROM lead_lists l ORDER BY name"))}


# ---- tracking / analytics ----
@r.get("/links")
def links(conn=Depends(get_conn)):
    return {"items": tracking.list_links(conn)}


@r.post("/links", status_code=201)
def link_create(body: LinkIn, conn=Depends(get_conn)):
    return tracking.create_link(conn, body)


@r.get("/analytics/summary")
def analytics(frm: str | None = Query(None, alias="from"), to: str | None = None, link_id: str | None = None, conn=Depends(get_conn)):
    return tracking.summary(conn, frm, to, link_id)


@r.get("/analytics/engagement")
def engagement(frm: str | None = Query(None, alias="from"), to: str | None = None, conn=Depends(get_conn)):
    return tracking.engagement(conn, frm, to)


@public.get("/t/{token}")
def track(token: str, request: Request, sd_sid: str | None = Cookie(default=None), conn=Depends(get_conn)):
    dest, sid = tracking.record_click(conn, token, request.headers.get("user-agent", ""), sd_sid)
    resp = RedirectResponse(dest, status_code=302)
    resp.set_cookie("sd_sid", sid, max_age=30 * 86400, httponly=True, samesite="lax")
    return resp


@public.get("/demo-landing", response_class=PlainTextResponse)
def landing():
    return PlainTextResponse("SignalDesk Lab Demo Landing Page（本機測試頁，無真實內容）", media_type="text/plain; charset=utf-8")
