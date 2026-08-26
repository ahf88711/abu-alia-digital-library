from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from abu_alia.config import reset_settings
from abu_alia.db.session import init_db, reset_engine, session_scope
from abu_alia.seed import seed_all


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    db = tmp_path / "library.db"
    monkeypatch.setenv("ABU_ALIA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ABU_ALIA_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("ABU_ALIA_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("ABU_ALIA_TMP_ROOT", str(tmp_path / "tmp"))
    monkeypatch.setenv("ABU_ALIA_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("ABU_ALIA_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ABU_ALIA_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("ABU_ALIA_ADMIN_PASSWORD", "test-admin-pass")
    monkeypatch.setenv("ABU_ALIA_ENV", "test")
    reset_engine()
    settings = reset_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.tmp_root.mkdir(parents=True, exist_ok=True)
    init_db(settings)
    with session_scope() as session:
        seed_all(session)
    yield settings
    reset_engine()


@pytest.fixture()
def client(tmp_env):
    from abu_alia.web.app import app

    with TestClient(app) as c:
        yield c
