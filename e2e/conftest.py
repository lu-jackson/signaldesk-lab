"""E2E：啟動獨立的臨時 DB + uvicorn + worker（不碰使用者的 data/signaldesk.db），用真的瀏覽器操作。"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PY = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        pytest.fail("請先 npm run build（frontend/dist 不存在）")
    port = free_port()
    db = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {**os.environ, "SIGNALDESK_DB": str(db), "PYTHONUTF8": "1",
           "SIGNALDESK_ORIGINS": f"http://127.0.0.1:{port}", "SIGNALDESK_BASE_URL": f"http://127.0.0.1:{port}"}
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "THREADS_ACCESS_TOKEN"):
        env.pop(k, None)
    api = subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", str(port)], cwd=BACKEND, env=env)
    worker = subprocess.Popen([str(PY), "-m", "app.worker"], cwd=BACKEND, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        api.kill(); worker.kill()
        pytest.fail("server 沒有啟動")
    yield base
    for p in (worker, api):
        p.terminate()
    for p in (worker, api):
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()


@pytest.fixture(scope="session")
def browser_ctx():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = None
        errors = []
        for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
            try:
                browser = pw.chromium.launch(headless=True, **kw)
                break
            except Exception as e:  # 沒有該瀏覽器就試下一個
                errors.append(f"{kw}: {str(e)[:120]}")
        if browser is None:
            pytest.fail("找不到可用瀏覽器（msedge/chrome/chromium）：" + " | ".join(errors))
        yield browser
        browser.close()


@pytest.fixture
def page(browser_ctx, server):
    ctx = browser_ctx.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.set_default_timeout(15000)
    pg.base = server
    yield pg
    ctx.close()
