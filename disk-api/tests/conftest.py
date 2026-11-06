import os
import sys
from pathlib import Path

os.environ["DISK_API_KEY"] = "test-key"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app.models import db
from app.routers import files as files_mod


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Isolated DB + storage + media roots (never touches the live metadata.db)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    storage = tmp_path / "storage"
    media = tmp_path / "media"
    monkeypatch.setattr(files_mod, "STORAGE_ROOT", storage)
    monkeypatch.setattr(files_mod, "MEDIA_ROOT", media)
    return storage, media


@pytest.fixture
def client(roots):
    from app.main import app
    c = TestClient(app, headers={"X-API-Key": "test-key"})
    return c
