"""貼文／評估／草稿。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_conn, idem_header, idempotent
from ..schemas import DraftEdit, DraftGenerate
from ..services import drafts, pipeline

r = APIRouter(prefix="/api")


@r.get("/posts")
def posts(q: str | None = None, sort: str = "latest", page: int = 1, page_size: int = 20, conn=Depends(get_conn)):
    return pipeline.list_posts(conn, q=q, page_no=page, size=page_size, sort=sort)


@r.get("/evaluations")
def evaluations(risk: str | None = None, intent: str | None = None, project_id: str | None = None, page: int = 1, page_size: int = 50, conn=Depends(get_conn)):
    return pipeline.list_evaluations(conn, risk=risk, intent=intent, project_id=project_id, page_no=page, size=page_size)


@r.get("/drafts")
def drafts_list(status: str | None = None, project_id: str | None = None, page: int = 1, page_size: int = 30, conn=Depends(get_conn)):
    return drafts.list_drafts(conn, status=status, project_id=project_id, page_no=page, size=page_size)


@r.post("/drafts", status_code=201)
def draft_generate(body: DraftGenerate, conn=Depends(get_conn)):
    return drafts.create_draft(conn, body.project_id, body.post_id)


@r.get("/drafts/{did}")
def draft_get(did: str, conn=Depends(get_conn)):
    return drafts.get_draft(conn, did)


@r.put("/drafts/{did}")
def draft_edit(did: str, body: DraftEdit, conn=Depends(get_conn)):
    return drafts.edit_draft(conn, did, body.body)


@r.post("/drafts/{did}/approve")
def draft_approve(did: str, conn=Depends(get_conn)):
    return drafts.approve(conn, did)


@r.post("/drafts/{did}/reject")
def draft_reject(did: str, conn=Depends(get_conn)):
    return drafts.reject(conn, did)


@r.post("/drafts/{did}/regenerate", status_code=201)
def draft_regenerate(did: str, conn=Depends(get_conn)):
    return drafts.regenerate(conn, did)


@r.post("/drafts/{did}/simulate-send")
def draft_send(did: str, idem: str | None = Depends(idem_header), conn=Depends(get_conn)):
    return idempotent(conn, idem, f"simulate-send:{did}", lambda: drafts.simulate_send(conn, did))
