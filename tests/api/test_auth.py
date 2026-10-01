"""Tests for the authentication endpoints."""
from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.user import User
from src.auth import get_password_hash
import uuid
import pytest

# Disable rate limiting for tests
app.state.limiter.enabled = False

@pytest.fixture(autouse=True)
def clear_overrides():
    old_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides = old_overrides

def test_login_success():
    session = SessionLocal()
    try:
        # Create a test user
        test_username = f"user_{uuid.uuid4().hex[:6]}"
        test_password = "test123"
        
        db_user = User(
            username=test_username,
            hashed_password=get_password_hash(test_password)
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    
    # Try to login
    response = client.post(
        "/token",
        data={"username": test_username, "password": test_password}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_failure():
    client = TestClient(app)
    response = client.post(
        "/token",
        data={"username": "wrong", "password": "wrong"}
    )
    assert response.status_code == 401


def test_register_without_paid_plan_is_rejected():
    """A signup with no completed Stripe payment and no admin bypass must be
    refused — there is nothing for the account to have paid access to."""
    client = TestClient(app)
    username = f"nopay_{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/users/register",
        json={"username": username, "password": "test123", "company_name": "No Pay Co"},
    )

    assert response.status_code == 402
    session = SessionLocal()
    try:
        assert session.query(User).filter_by(username=username).first() is None
    finally:
        session.close()


def test_register_with_pending_subscription_succeeds():
    """A signup whose email matches a Stripe-confirmed PendingSubscription
    (webhook landed before registration) is allowed and activates the plan."""
    from src.models.pending_subscription import PendingSubscription

    client = TestClient(app)
    username = f"paid_{uuid.uuid4().hex[:8]}@example.com"

    session = SessionLocal()
    try:
        session.add(PendingSubscription(
            email=username, plan="growth", chases_limit=300,
            stripe_customer_id="cus_test", stripe_subscription_id="sub_test",
        ))
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/users/register",
        json={"username": username, "password": "test123", "company_name": "Paid Co"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["subscription_plan"] == "growth"
    assert data["subscription_status"] == "active"


def test_register_with_admin_email_bypasses_payment_gate(monkeypatch):
    """ADMIN_EMAILS is the deliberate bypass for internal/test accounts."""
    from src.api import auth as auth_module

    admin_username = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    settings = auth_module.get_settings()
    monkeypatch.setattr(settings, "admin_emails", admin_username)

    client = TestClient(app)
    response = client.post(
        "/users/register",
        json={"username": admin_username, "password": "test123", "company_name": "Admin Co"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["subscription_status"] == "active"
    assert data["subscription_plan"] == "scale"


def test_register_with_valid_invite_code_bypasses_payment_gate(monkeypatch):
    """A correct shared TEST_INVITE_CODE grants the same Scale-tier bypass
    as an admin email, without maintaining a per-person allowlist."""
    from src.api import auth as auth_module

    username = f"tester_{uuid.uuid4().hex[:8]}@example.com"
    settings = auth_module.get_settings()
    monkeypatch.setattr(settings, "test_invite_code", "letmein-2026")

    client = TestClient(app)
    response = client.post(
        "/users/register",
        json={"username": username, "password": "test123", "company_name": "Tester Co", "invite_code": "letmein-2026"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["subscription_status"] == "active"
    assert data["subscription_plan"] == "scale"


def test_register_with_wrong_invite_code_is_rejected(monkeypatch):
    from src.api import auth as auth_module

    username = f"tester_{uuid.uuid4().hex[:8]}@example.com"
    settings = auth_module.get_settings()
    monkeypatch.setattr(settings, "test_invite_code", "letmein-2026")

    client = TestClient(app)
    response = client.post(
        "/users/register",
        json={"username": username, "password": "test123", "company_name": "Tester Co", "invite_code": "wrong-code"},
    )

    assert response.status_code == 402


def test_register_with_invite_code_but_none_configured_is_rejected(monkeypatch):
    """If TEST_INVITE_CODE is unset on the server, no submitted code -- not
    even an empty string -- should be able to bypass the payment gate."""
    from src.api import auth as auth_module

    username = f"tester_{uuid.uuid4().hex[:8]}@example.com"
    settings = auth_module.get_settings()
    monkeypatch.setattr(settings, "test_invite_code", "")

    client = TestClient(app)
    response = client.post(
        "/users/register",
        json={"username": username, "password": "test123", "company_name": "Tester Co", "invite_code": ""},
    )

    assert response.status_code == 402
