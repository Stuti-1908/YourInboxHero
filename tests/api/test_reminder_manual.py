"""Tests for the manual reminder endpoint — POST /reminder/manual."""
from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)


def test_manual_reminder_404():
    # Use a valid UUID format that does not exist in the DB
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post('/reminder/manual', json={'invoice_id': fake_id})
    assert resp.status_code == 404