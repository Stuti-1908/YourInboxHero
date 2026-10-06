"""Tests for the authentication endpoints."""
from fastapi.testclient import TestClient
from unittest.mock import patch
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


@pytest.fixture(autouse=True)
def _mock_verification_email():
    """Every registration now sends a verification email — mock it across
    this whole file so tests that aren't specifically about verification
    don't depend on a real Resend API key or spam error logs on failure."""
    with patch("src.api.auth.send_verification_email") as mock:
        yield mock

def test_login_success():
    session = SessionLocal()
    try:
        # Create a test user
        test_username = f"user_{uuid.uuid4().hex[:6]}"
        test_password = "test123"

        db_user = User(
            username=test_username,
            hashed_password=get_password_hash(test_password),
            email_verified=True,
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


def test_login_blocked_until_email_verified():
    session = SessionLocal()
    try:
        test_username = f"unverified_{uuid.uuid4().hex[:6]}@example.com"
        test_password = "test123"
        db_user = User(
            username=test_username,
            hashed_password=get_password_hash(test_password),
            email_verified=False,
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(
        "/token",
        data={"username": test_username, "password": test_password}
    )
    assert response.status_code == 403

def test_login_failure():
    client = TestClient(app)
    response = client.post(
        "/token",
        data={"username": "wrong", "password": "wrong"}
    )
    assert response.status_code == 401


def test_refresh_issues_new_token_and_revokes_old_one():
    """M8: an active session can slide its 30-minute expiry forward."""
    session = SessionLocal()
    try:
        test_username = f"refresh_{uuid.uuid4().hex[:6]}"
        test_password = "test123"
        db_user = User(
            username=test_username,
            hashed_password=get_password_hash(test_password),
            email_verified=True,
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    login = client.post("/token", data={"username": test_username, "password": test_password})
    old_token = login.json()["access_token"]

    refresh = client.post("/refresh", headers={"Authorization": f"Bearer {old_token}"})
    assert refresh.status_code == 200
    new_token = refresh.json()["access_token"]
    assert new_token != old_token

    # The old token is now revoked...
    old_check = client.get("/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_check.status_code == 401

    # ...but the new one works.
    new_check = client.get("/users/me", headers={"Authorization": f"Bearer {new_token}"})
    assert new_check.status_code == 200


def test_refresh_rejects_already_revoked_token():
    session = SessionLocal()
    try:
        test_username = f"refresh2_{uuid.uuid4().hex[:6]}"
        test_password = "test123"
        db_user = User(
            username=test_username,
            hashed_password=get_password_hash(test_password),
            email_verified=True,
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    login = client.post("/token", data={"username": test_username, "password": test_password})
    token = login.json()["access_token"]

    client.post("/logout", headers={"Authorization": f"Bearer {token}"})
    refresh = client.post("/refresh", headers={"Authorization": f"Bearer {token}"})
    assert refresh.status_code == 401


def test_refresh_rejects_missing_token():
    client = TestClient(app)
    response = client.post("/refresh")
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


def test_verify_email_with_valid_token_activates_account():
    session = SessionLocal()
    try:
        username = f"verify_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=False, email_verification_token="valid-token-123",
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    resp = client.post("/users/verify-email", params={"token": "valid-token-123"})
    assert resp.status_code == 200

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username=username).first()
        assert user.email_verified is True
        assert user.email_verification_token is None  # single-use
    finally:
        session.close()


def test_verify_email_with_invalid_token_rejected():
    client = TestClient(app)
    resp = client.post("/users/verify-email", params={"token": "nonexistent-token"})
    assert resp.status_code == 400


def test_verify_email_token_cannot_be_reused():
    session = SessionLocal()
    try:
        username = f"reuse_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=False, email_verification_token="one-time-token",
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    first = client.post("/users/verify-email", params={"token": "one-time-token"})
    assert first.status_code == 200

    second = client.post("/users/verify-email", params={"token": "one-time-token"})
    assert second.status_code == 400


def test_newly_registered_user_cannot_login_until_verified():
    """End-to-end: register (with a paid pending plan) -> login blocked ->
    verify -> login succeeds."""
    from src.models.pending_subscription import PendingSubscription

    client = TestClient(app)
    username = f"e2e_{uuid.uuid4().hex[:8]}@example.com"

    session = SessionLocal()
    try:
        session.add(PendingSubscription(
            email=username, plan="starter", chases_limit=100,
            stripe_customer_id="cus_e2e", stripe_subscription_id="sub_e2e",
        ))
        session.commit()
    finally:
        session.close()

    reg_resp = client.post(
        "/users/register",
        json={"username": username, "password": "test123", "company_name": "E2E Co"},
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["verification_email_sent"] is True

    login_blocked = client.post("/token", data={"username": username, "password": "test123"})
    assert login_blocked.status_code == 403

    session = SessionLocal()
    try:
        token = session.query(User).filter_by(username=username).first().email_verification_token
    finally:
        session.close()
    assert token is not None

    verify_resp = client.post("/users/verify-email", params={"token": token})
    assert verify_resp.status_code == 200

    login_ok = client.post("/token", data={"username": username, "password": "test123"})
    assert login_ok.status_code == 200


def test_resend_verification_does_not_reveal_whether_account_exists():
    client = TestClient(app)
    resp_unknown = client.post("/users/resend-verification", json={"username": "nobody@example.com"})
    assert resp_unknown.status_code == 200

    session = SessionLocal()
    try:
        username = f"resend_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=False, email_verification_token="existing-token",
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    resp_known = client.post("/users/resend-verification", json={"username": username})
    assert resp_known.status_code == 200
    # Same response shape either way -- no enumeration signal.
    assert resp_known.json() == resp_unknown.json()


def test_resend_verification_does_nothing_for_already_verified_account(_mock_verification_email):
    session = SessionLocal()
    try:
        username = f"alreadyverified_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=True,
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    client.post("/users/resend-verification", json={"username": username})
    _mock_verification_email.assert_not_called()


def test_users_me_never_returns_smtp_password():
    """GET /users/me must never include smtp_password, encrypted or not —
    there's no legitimate UI need to display it, and returning it would
    let a stolen JWT round-trip it back through PUT /users/me."""
    from src.auth import get_current_user
    from src.services.secrets import encrypt_secret

    session = SessionLocal()
    try:
        username = f"smtpuser_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=True, smtp_host="smtp.gmail.com", smtp_port="587",
            smtp_username=username, smtp_password=encrypt_secret("real-app-password"),
            subscription_status="active",
        )
        session.add(db_user)
        session.commit()
        user_id = db_user.id
    finally:
        session.close()

    # get_me reads straight off current_user (no re-fetch), so the override
    # needs the real DB-persisted row — including smtp_host — the same way
    # the real get_current_user would return it, not a hand-built stand-in
    # missing those fields.
    def _load_current_user():
        session = SessionLocal()
        return session.query(User).filter_by(id=user_id).first()

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = _load_current_user
        client = TestClient(app)
        resp = client.get("/users/me")
        assert resp.status_code == 200
        body = resp.json()
        assert "smtp_password" not in body
        assert body["smtp_host"] == "smtp.gmail.com"  # non-secret SMTP fields still returned
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)


def test_update_me_encrypts_smtp_password_at_rest():
    from src.auth import get_current_user

    session = SessionLocal()
    try:
        username = f"smtpupdate_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=True, subscription_status="active",
        )
        session.add(db_user)
        session.commit()
        user_id = db_user.id
    finally:
        session.close()

    # update_me re-fetches the user within its own db session by ID, so the
    # override here can safely be a detached object — it's only used for
    # its .id (and route auth), not mutated/refreshed directly.
    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=username, email_verified=True,
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
        client = TestClient(app)
        resp = client.put("/users/me", json={
            "smtp_host": "smtp.gmail.com", "smtp_port": "587",
            "smtp_username": username, "smtp_password": "plaintext-app-password",
        })
        assert resp.status_code == 200
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        # Stored value must not be the plaintext the client sent.
        assert user.smtp_password != "plaintext-app-password"
        assert user.smtp_password is not None
    finally:
        session.close()


def test_update_me_disconnect_smtp_stores_empty_not_encrypted_empty():
    from src.auth import get_current_user
    from src.services.secrets import encrypt_secret

    session = SessionLocal()
    try:
        username = f"smtpdisconnect_{uuid.uuid4().hex[:8]}@example.com"
        db_user = User(
            username=username, hashed_password=get_password_hash("pw"),
            email_verified=True, subscription_status="active",
            smtp_host="smtp.gmail.com", smtp_password=encrypt_secret("old-password"),
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
        client = TestClient(app)
        resp = client.put("/users/me", json={
            "smtp_host": "", "smtp_port": "", "smtp_username": "", "smtp_password": "",
        })
        assert resp.status_code == 200
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        assert user.smtp_password == ""
    finally:
        session.close()
