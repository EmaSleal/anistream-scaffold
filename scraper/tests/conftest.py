import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("INTERNAL_JWT_SECRET", "test-internal-secret-for-tests-only")
os.environ.setdefault("SERVICE_SECRET", "test-service-secret")

import auth
import pytest


@pytest.fixture(autouse=True)
def patch_service_secret(monkeypatch):
    monkeypatch.setattr(auth, "_SERVICE_SECRET", "test-service-secret")
