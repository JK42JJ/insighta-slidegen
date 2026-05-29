"""
Trivial passing test for the FastAPI CV service health endpoint.
Uses TestClient so no real server or network is required.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_returns_ok():
    """GET /health should return 200 with status='ok'."""
    # Import here to avoid app-level side effects at collection time
    from app import app  # noqa: PLC0415

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mode"] in ("dev", "prod")


def test_health_mode_default_is_dev(monkeypatch):
    """SLIDEGEN_MODE defaults to 'dev' when env var is unset."""
    monkeypatch.delenv("SLIDEGEN_MODE", raising=False)

    import importlib
    import app as app_module  # noqa: PLC0415

    importlib.reload(app_module)
    client = TestClient(app_module.app)
    response = client.get("/health")
    assert response.json()["mode"] == "dev"
