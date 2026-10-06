"""Tests for the GET /healthz endpoint."""
from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)


def test_healthz_returns_200():
    resp = client.get('/healthz')
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime" in data
