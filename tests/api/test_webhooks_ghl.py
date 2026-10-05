"""Tests for the GHL inbound webhook — POST /api/webhooks/ghl/{webhook_secret}."""
import uuid
from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.user import User
from src.auth import get_password_hash

client = TestClient(app)


def _make_user(subscription_status="active"):
    session = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"), company_name="GHL Test Co",
            subscription_status=subscription_status, subscription_plan="scale",
            chases_limit=750, chases_used=0,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.webhook_secret
    finally:
        session.close()


def test_ghl_webhook_rejects_inactive_subscription():
    """A cancelled/past_due account must not be able to keep creating new
    invoices (and therefore new chases) via the GHL integration."""
    webhook_secret = _make_user(subscription_status="cancelled")

    resp = client.post(
        f"/api/webhooks/ghl/{webhook_secret}",
        json={"email": "debtor@example.com", "amount": 100.0, "due_date": "2026-12-01"},
    )
    assert resp.status_code == 402


def test_ghl_webhook_accepts_active_subscription():
    webhook_secret = _make_user(subscription_status="active")

    resp = client.post(
        f"/api/webhooks/ghl/{webhook_secret}",
        json={"email": "debtor2@example.com", "amount": 250.0, "due_date": "2026-12-01"},
    )
    assert resp.status_code == 200


def test_ghl_webhook_rejects_unknown_secret():
    resp = client.post(
        f"/api/webhooks/ghl/{uuid.uuid4().hex}",
        json={"email": "debtor@example.com"},
    )
    assert resp.status_code == 401
