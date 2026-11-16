"""AI 助手：會話、訊息、trace、提案確認。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_conn, idem_header, idempotent
from ..schemas import AgentMessageIn, SessionIn
from ..services import agent

r = APIRouter(prefix="/api/agent")


@r.get("/tools")
def tools():
    return {"items": agent.TOOLS, "limits": {"max_model_turns": agent.MAX_MODEL_TURNS, "max_tool_calls": agent.MAX_TOOL_CALLS, "timeout_seconds": agent.TIMEOUT_SECONDS}}


@r.get("/sessions")
def sessions(conn=Depends(get_conn)):
    return {"items": agent.list_sessions(conn)}


@r.post("/sessions", status_code=201)
def session_create(body: SessionIn, conn=Depends(get_conn)):
    return agent.create_session(conn, body.title)


@r.get("/sessions/{sid}")
def session_get(sid: str, conn=Depends(get_conn)):
    return agent.trace(conn, sid)


@r.post("/sessions/{sid}/messages")
def session_message(sid: str, body: AgentMessageIn, idem: str | None = Depends(idem_header), conn=Depends(get_conn)):
    return idempotent(conn, idem, f"agent-msg:{sid}", lambda: agent.send_message(conn, sid, body.content))


@r.post("/sessions/{sid}/cancel")
def session_cancel(sid: str, conn=Depends(get_conn)):
    return agent.cancel_session(conn, sid)


@r.get("/proposals")
def proposals(status: str | None = None, conn=Depends(get_conn)):
    return {"items": agent.list_proposals(conn, status)}


@r.post("/proposals/{pid}/confirm")
def proposal_confirm(pid: str, conn=Depends(get_conn)):
    return agent.confirm_proposal(conn, pid)


@r.post("/proposals/{pid}/reject")
def proposal_reject(pid: str, conn=Depends(get_conn)):
    return agent.reject_proposal(conn, pid)
