"""品牌／帳號／專案／設定／健康／儀表板。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from .. import clock, config, worker
from ..db import rows
from ..deps import get_conn, idem_header, idempotent
from ..schemas import AccountIn, BrandIn, CsvImportIn, PostImportIn, ProjectIn, SettingsPatch
from ..services import catalog, drafts, imports, jobs, ledger, pipeline, settings, tracking

r = APIRouter(prefix="/api")


@r.get("/health")
def health(conn=Depends(get_conn)):
    conn.execute("SELECT 1")
    return {"status": "ok", "time": clock.now_iso(), "worker": worker.worker_status(conn)}


@r.get("/settings")
def get_settings(conn=Depends(get_conn)):
    return settings.capabilities(conn)


@r.patch("/settings")
def patch_settings(body: SettingsPatch, conn=Depends(get_conn)):
    for k, v in body.model_dump(exclude_none=True).items():
        settings.set_value(conn, k, v)
    return settings.capabilities(conn)


@r.get("/brands")
def brands(conn=Depends(get_conn)):
    return {"items": catalog.list_brands(conn)}


@r.post("/brands", status_code=201)
def brand_create(body: BrandIn, conn=Depends(get_conn)):
    return catalog.create_brand(conn, body)


@r.get("/brands/{brand_id}")
def brand_get(brand_id: str, version: int | None = None, conn=Depends(get_conn)):
    return catalog.get_brand(conn, brand_id, version)


@r.put("/brands/{brand_id}")
def brand_update(brand_id: str, body: BrandIn, conn=Depends(get_conn)):
    b = catalog.update_brand(conn, brand_id, body)
    drafts.on_brand_updated(conn, brand_id)
    return b


@r.get("/accounts")
def accounts(conn=Depends(get_conn)):
    return {"items": catalog.list_accounts(conn)}


@r.post("/accounts", status_code=201)
def account_create(body: AccountIn, conn=Depends(get_conn)):
    return catalog.create_account(conn, body)


@r.put("/accounts/{account_id}")
def account_update(account_id: str, body: AccountIn, conn=Depends(get_conn)):
    return catalog.update_account(conn, account_id, body)


@r.get("/projects")
def projects(conn=Depends(get_conn)):
    return {"items": catalog.list_projects(conn)}


@r.post("/projects", status_code=201)
def project_create(body: ProjectIn, conn=Depends(get_conn)):
    return catalog.create_project(conn, body)


@r.get("/projects/{pid}")
def project_get(pid: str, conn=Depends(get_conn)):
    return catalog.get_project(conn, pid)


@r.put("/projects/{pid}")
def project_update(pid: str, body: ProjectIn, conn=Depends(get_conn)):
    return catalog.update_project(conn, pid, body)


@r.delete("/projects/{pid}", status_code=204)
def project_delete(pid: str, conn=Depends(get_conn)):
    catalog.delete_project(conn, pid)


@r.post("/projects/{pid}/enable")
def project_enable(pid: str, enabled: bool = True, conn=Depends(get_conn)):
    p = catalog.get_project(conn, pid)
    body = ProjectIn(**{k: p[k] for k in ProjectIn.model_fields} | {"enabled": enabled})
    return catalog.update_project(conn, pid, body)


@r.post("/projects/{pid}/run-now", status_code=202)
def project_run_now(pid: str, sync: bool = False, idem: str | None = Depends(idem_header), conn=Depends(get_conn)):
    """Run Now：排入 run_project 工作（預設）；sync=true 則在本 request 直接執行（測試／E2E 方便用，走同一個 service）。"""
    catalog.get_project(conn, pid)

    def go():
        if sync:
            run = pipeline.execute_run(conn, pid, "run_now")
            return {"mode": "sync", "run": run}
        j = jobs.enqueue(conn, "run_project", {"project_id": pid, "trigger": "run_now"}, idempotency_key=f"run_now:{idem}" if idem else None)
        return {"mode": "queued", "job": j}
    return idempotent(conn, idem, f"run-now:{pid}:{sync}", go)


@r.post("/posts/import", status_code=201)
def post_import(body: PostImportIn, conn=Depends(get_conn)):
    """手動貼上一則貼文並走完 納入→分類→草稿。不會自動送出；公開展示站會被沙盒規則擋下（403）。"""
    return imports.import_post(conn, body)


@r.post("/posts/import-csv", status_code=201)
def post_import_csv(body: CsvImportIn, conn=Depends(get_conn)):
    """CSV 批次匯入（每次最多 50 列）：每列各自走 納入→分類→草稿，壞列回報不中斷。不自動送出；公開展示站 403。"""
    return imports.import_csv(conn, body)


@r.get("/projects/{pid}/runs")
def project_runs(pid: str, page: int = 1, page_size: int = 20, conn=Depends(get_conn)):
    catalog.get_project(conn, pid)
    return pipeline.list_runs(conn, pid, page, page_size)


@r.get("/runs/{run_id}")
def run_get(run_id: str, conn=Depends(get_conn)):
    return pipeline.get_run(conn, run_id)


@r.get("/runs/{run_id}/results")
def run_results(run_id: str, page: int = 1, page_size: int = 50, included: bool | None = None, conn=Depends(get_conn)):
    return pipeline.run_results(conn, run_id, page, page_size, included)


@r.get("/dashboard")
def dashboard(conn=Depends(get_conn)):
    now = clock.now()
    since = clock.iso(now.replace(microsecond=0) - __import__("datetime").timedelta(days=7))
    q = lambda sql, p=(): conn.execute(sql, p).fetchone()[0]
    drafts_total = q("SELECT COUNT(*) FROM drafts")
    leads_total = q("SELECT COUNT(*) FROM leads")
    evals_7d = q("SELECT COUNT(*) FROM evaluations WHERE intent IS NOT NULL AND created_at>=?", (since,))
    sent_7d = q("SELECT COUNT(*) FROM delivery_attempts WHERE created_at>=?", (since,))
    return {
        "updated_at": clock.now_iso(),
        "period_note": ("近 7 天 [now-7d, now)；所有資料皆為合成或本機模擬" if config.synthetic_enabled()
                        else "近 7 天 [now-7d, now)；資料為你手動／CSV 匯入的貼文，投遞皆為本機模擬（不會送到任何平台）"),
        "mode": settings.capabilities(conn),
        "worker": worker.worker_status(conn),
        "jobs": jobs.stats(conn),
        "metrics": {
            "pending_drafts": {"value": q("SELECT COUNT(*) FROM drafts WHERE status='draft'"), "of": drafts_total, "label": "待審草稿", "link": "/drafts?status=draft"},
            "active_leads": {"value": q("SELECT COUNT(*) FROM leads WHERE status IN ('New','Qualified')"), "of": leads_total, "label": "有效商機（New/Qualified）", "link": "/leads"},
            "risk_alerts": {"value": q("SELECT COUNT(*) FROM evaluations WHERE risk='high' AND created_at>=?", (since,)), "of": evals_7d, "label": "高風險警報（近 7 天）", "link": "/pr"},
            "simulated_deliveries": {"value": q("SELECT COUNT(*) FROM delivery_attempts WHERE status='simulated_sent' AND created_at>=?", (since,)), "of": sent_7d, "label": "模擬投遞成功（近 7 天）", "link": "/automations"},
            "running_jobs": {"value": q("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"), "of": q("SELECT COUNT(*) FROM jobs"), "label": "進行中工作", "link": "/jobs"},
        },
        "recent_runs": rows(conn.execute("SELECT r.*, p.name project_name FROM runs r JOIN projects p ON p.id=r.project_id ORDER BY r.started_at DESC, r.rowid DESC LIMIT 5")),
        "usage": ledger.balance(conn),
    }


@r.get("/usage")
def usage(conn=Depends(get_conn)):
    return {"balance": ledger.balance(conn), "rates": ledger.RATES, "entries": ledger.entries(conn)}
