"""90% usage warning, welcome email, and the next-reset date shown in Settings."""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app import app
from src.db import SessionLocal
from src.models.user import User
from src.services.account_notifications import maybe_send_usage_warnings, next_usage_reset, send_welcome_email

SEND = 'src.services.account_notifications._send_via_resend'


def _user(session, used, limit=100, **flags):
    u = User(id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
             company_name="Usage Co", subscription_plan="growth", subscription_status="active",
             chases_limit=limit, chases_used=used, **flags)
    session.add(u)
    session.flush()
    return u


def _subjects(mock_send):
    return [c.kwargs['subject'] for c in mock_send.call_args_list]


def test_90_percent_warning_sends_once_after_80():
    session = SessionLocal()
    try:
        u = _user(session, used=90, usage_warning_80_sent=True)
        session.commit()
        with patch(SEND) as mock_send:
            maybe_send_usage_warnings(u, session)
            session.refresh(u)
            maybe_send_usage_warnings(u, session)
        assert _subjects(mock_send) == ["You've used 90 of 100 reminders this month"]
        assert "90% of plan used" in mock_send.call_args.kwargs['html_body']
        assert u.usage_warning_90_sent is True
    finally:
        session.close()


def test_jump_past_both_thresholds_sends_only_the_90_warning():
    session = SessionLocal()
    try:
        u = _user(session, used=95)
        session.commit()
        with patch(SEND) as mock_send:
            maybe_send_usage_warnings(u, session)
        assert len(mock_send.call_args_list) == 1
        session.refresh(u)
        assert u.usage_warning_80_sent and u.usage_warning_90_sent
    finally:
        session.close()


def test_80_warning_still_sends_first():
    session = SessionLocal()
    try:
        u = _user(session, used=80)
        session.commit()
        with patch(SEND) as mock_send:
            maybe_send_usage_warnings(u, session)
        assert "80% of plan used" in mock_send.call_args.kwargs['html_body']
    finally:
        session.close()


def test_next_usage_reset_is_next_monthly_anniversary():
    u = User(subscription_started_at=datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc))
    assert next_usage_reset(u, now=datetime(2026, 2, 10, tzinfo=timezone.utc)) == datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc)
    assert next_usage_reset(u, now=datetime(2026, 3, 1, tzinfo=timezone.utc)) == datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc)
    assert next_usage_reset(User(subscription_started_at=None)) is None


def test_welcome_email_lists_plan_limit_and_features():
    u = User(id="w1", username="owner@example.com", company_name="Acme", subscription_plan="growth",
             subscription_status="active", chases_limit=300,
             subscription_started_at=datetime.now(timezone.utc))
    with patch(SEND) as mock_send:
        send_welcome_email(u)
    kw = mock_send.call_args.kwargs
    assert kw['to_email'] == "owner@example.com"
    assert kw['subject'] == "Welcome to YourInboxHero: your Growth plan is active"
    assert "300" in kw['html_body'] and "AI voice call" in kw['html_body'] and "Gmail or Yahoo" in kw['html_body']


def test_welcome_email_skipped_without_active_plan():
    with patch(SEND) as mock_send:
        send_welcome_email(User(id="w2", username="x@example.com", subscription_plan=None, subscription_status="inactive"))
    mock_send.assert_not_called()


def test_verifying_email_sends_welcome():
    token = uuid.uuid4().hex
    session = SessionLocal()
    try:
        session.add(User(id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
                         subscription_plan="starter", subscription_status="active", chases_limit=100,
                         email_verified=False, email_verification_token=token,
                         subscription_started_at=datetime.now(timezone.utc)))
        session.commit()
    finally:
        session.close()
    with patch(SEND) as mock_send:
        resp = TestClient(app).post(f"/users/verify-email?token={token}")
    assert resp.status_code == 200
    assert _subjects(mock_send) == ["Welcome to YourInboxHero: your Starter plan is active"]


def test_users_me_returns_usage_and_reset_date():
    from src.auth import get_current_user
    session = SessionLocal()
    try:
        u = User(id=str(uuid.uuid4()), username=f"me_{uuid.uuid4().hex[:6]}", hashed_password="x", email_verified=True,
                 subscription_plan="growth", subscription_status="active", chases_limit=300, chases_used=45,
                 subscription_started_at=datetime.now(timezone.utc) - timedelta(days=3))
        session.add(u)
        session.commit()
        session.refresh(u)
        session.expunge(u)
    finally:
        session.close()
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        me = TestClient(app).get("/users/me").json()
    finally:
        app.dependency_overrides[get_current_user] = previous
    assert (me["chases_used"], me["chases_limit"]) == (45, 300)
    resets = datetime.fromisoformat(me["usage_resets_at"])
    assert timedelta(days=24) < resets - datetime.now(timezone.utc) < timedelta(days=29)
