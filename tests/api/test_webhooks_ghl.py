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


def test_ghl_webhook_accepts_valid_signature_when_secret_configured():
    """The real-world flow: a signing secret saved via PUT /users/me
    (encrypted at rest) must be correctly decrypted and used to validate
    an incoming webhook's signature."""
    import hmac
    import hashlib
    import json
    from src.services.secrets import encrypt_secret

    raw_secret = "my-ghl-signing-secret-123"
    session = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"), company_name="GHL Sig Test Co",
            subscription_status="active", subscription_plan="scale",
            chases_limit=750, chases_used=0,
            ghl_webhook_signing_secret=encrypt_secret(raw_secret),
        )
        session.add(user)
        session.commit()
        webhook_secret = user.webhook_secret
    finally:
        session.close()

    body = json.dumps({"email": "sigdebtor@example.com"}).encode()
    signature = "sha256=" + hmac.new(raw_secret.encode(), body, hashlib.sha256).hexdigest()

    resp = client.post(
        f"/api/webhooks/ghl/{webhook_secret}",
        content=body,
        headers={"Content-Type": "application/json", "X-GHL-Signature": signature},
    )
    assert resp.status_code == 200


def test_ghl_webhook_rejects_invalid_signature_when_secret_configured():
    from src.services.secrets import encrypt_secret

    session = SessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"), company_name="GHL Bad Sig Co",
            subscription_status="active", subscription_plan="scale",
            chases_limit=750, chases_used=0,
            ghl_webhook_signing_secret=encrypt_secret("correct-secret"),
        )
        session.add(user)
        session.commit()
        webhook_secret = user.webhook_secret
    finally:
        session.close()

    resp = client.post(
        f"/api/webhooks/ghl/{webhook_secret}",
        json={"email": "baddebtor@example.com"},
        headers={"X-GHL-Signature": "sha256=wrongsignature"},
    )
    assert resp.status_code == 401


def test_update_me_actually_persists_ghl_signing_secret():
    """Regression test for the bug this fixes: the field was accepted by
    the request model but silently never assigned to the user row."""
    from src.auth import get_current_user
    from src.services.secrets import decrypt_secret

    session = SessionLocal()
    try:
        username = f"ghlsave_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=True, subscription_status="active",
        )
        session.add(db_user)
        session.commit()
        user_id = db_user.id
    finally:
        session.close()

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=username, email_verified=True,
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
        resp = client.put("/users/me", json={"ghl_webhook_signing_secret": "a-real-secret-value"})
        assert resp.status_code == 200
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        assert user.ghl_webhook_signing_secret is not None
        assert user.ghl_webhook_signing_secret != "a-real-secret-value"  # encrypted, not plaintext
        assert decrypt_secret(user.ghl_webhook_signing_secret) == "a-real-secret-value"
    finally:
        session.close()
