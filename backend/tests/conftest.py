"""測試用臨時 DB + 凍結時鐘；絕不碰使用者的 Demo DB。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_MODEL", None)
os.environ.pop("THREADS_ACCESS_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import clock, db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.providers import social  # noqa: E402

NOW = "2026-11-16T12:00:00Z"


@pytest.fixture(autouse=True)
def frozen_clock():
    clock.set_fixed(NOW)
    social._ai_override = None
    yield
    clock.set_fixed(None)
    social._ai_override = None


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def app(db_path):
    return create_app(db_path)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def conn(db_path, app):
    c = db.connect(db_path)
    yield c
    c.close()


def run_worker(conn, n=50, advance_seconds=0):
    """同步地跑 worker tick 直到沒有可執行工作。"""
    from app import worker
    done = []
    for _ in range(n):
        j = worker.tick(conn, "test-worker")
        if not j:
            break
        done.append(j)
    return done


def first_seeking_draft(client, project="proj_toeic"):
    """跑一次專案並回傳第一份草稿。"""
    run = client.post(f"/api/projects/{project}/run-now?sync=true").json()["run"]
    ds = client.get(f"/api/drafts?project_id={project}").json()["items"]
    assert ds, f"沒有草稿：{run}"
    return ds[0]
