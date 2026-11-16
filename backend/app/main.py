"""FastAPI app 工廠。build 後的前端由同一個 app 供應，完成版只需一個 localhost 網址。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, seed
from .errors import DomainError
from .routers import agent, content, core, ops


def create_app(db_path: str | None = None, *, do_seed: bool = True) -> FastAPI:
    app = FastAPI(title="SignalDesk Lab API", version="1.0.0",
                  description="個人學習用本機工作台。所有資料為合成／模擬，不連任何真實社群平台。")
    app.state.db_path = db_path or config.db_path()
    conn = db.connect(app.state.db_path)
    db.migrate(conn)
    if do_seed:
        seed.seed_demo(conn)
    conn.close()

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        """本機單使用者：寫入類請求若帶了不認得的 Origin（例如別的網站上的惡意頁面）一律拒絕。"""
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and origin not in config.allowed_origins():
                return JSONResponse({"error": {"code": "origin_forbidden", "message": f"不允許的 Origin：{origin}"}}, status_code=403)
        return await call_next(request)

    # ---- 公開展示模式：沙盒白名單 + 每 IP 限流（本機模式不啟用）----
    import re
    import threading
    import time
    from collections import defaultdict, deque

    SANDBOX = [("POST", r"^/api/projects/[\w-]+/run-now$"), ("POST", r"^/api/drafts/[\w-]+/(approve|reject|simulate-send|regenerate)$"),
               ("PUT", r"^/api/drafts/[\w-]+$"), ("POST", r"^/api/agent/sessions$"), ("POST", r"^/api/agent/sessions/[\w-]+/(messages|cancel)$"),
               ("POST", r"^/api/agent/proposals/[\w-]+/(confirm|reject)$"), ("POST", r"^/api/simulator/events$"),
               ("POST", r"^/api/automations/[\w-]+/(preview|process-existing)$"), ("PATCH", r"^/api/leads/[\w-]+$"), ("POST", r"^/api/leads$"),
               ("POST", r"^/api/jobs/[\w-]+/(cancel|retry)$"), ("POST", r"^/api/deliveries/[\w-]+/reconcile$")]
    hits: dict[str, deque] = defaultdict(deque)
    lock = threading.Lock()

    @app.middleware("http")
    async def public_guard(request: Request, call_next):
        if config.public_demo() and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not any(m == request.method and re.match(p, request.url.path) for m, p in SANDBOX):
                return JSONResponse({"error": {"code": "public_demo_readonly", "message": "公開展示站為唯讀沙盒：此操作僅限本機執行（見 GitHub README）"}}, status_code=403)
            ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?"))
            now = time.monotonic()
            with lock:
                q = hits[ip]
                while q and now - q[0] > 600:
                    q.popleft()
                if len(q) >= 60:
                    return JSONResponse({"error": {"code": "rate_limited", "message": "公開展示站限流：每 10 分鐘最多 60 次寫入"}}, status_code=429)
                q.append(now)
        return await call_next(request)

    interval = config.reset_interval_hours()
    if config.public_demo() and interval > 0:
        def _reset_loop():
            while True:
                time.sleep(interval * 3600)
                try:
                    c = db.connect(app.state.db_path)
                    seed.reset_demo(c)
                    c.close()
                except Exception as e:  # 重置失敗不影響服務
                    print("[reset] failed:", e, flush=True)
        threading.Thread(target=_reset_loop, daemon=True).start()

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errs = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": "validation_error", "message": "請求格式不正確", "details": errs}}, status_code=422)

    import sqlite3

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(_: Request, exc: sqlite3.IntegrityError):
        return JSONResponse({"error": {"code": "constraint_violation", "message": f"資料約束衝突：{exc}"}}, status_code=409)

    for rt in (core.r, content.r, ops.r, ops.public, agent.r):
        app.include_router(rt)

    dist = config.static_dir()
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"error": {"code": "not_found", "message": "沒有這個 API"}}, status_code=404)
            f = dist / path
            return FileResponse(f if path and f.is_file() else dist / "index.html")
    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.main:app_factory
    return create_app()
