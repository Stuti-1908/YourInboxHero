"""Tests for usage-limit warning emails — must fire exactly once per
threshold per billing cycle, never block the chase that triggered them."""
from unittest.mock import patch, MagicMock
from src.services.account_notifications import maybe_send_usage_warnings
from src.db import SessionLocal
from src.models.user import User
import uuid


def _make_user(session, chases_limit=100, chases_used=0, warning_sent=False, limit_sent=False):
    u = User(
        id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="pwd", company_name="Test Co",
        subscription_plan="growth", subscription_status="active",
        chases_limit=chases_limit, chases_used=chases_used,
        usage_warning_80_sent=warning_sent, usage_limit_reached_sent=limit_sent,
    )
    session.add(u)
    session.flush()
    return u


def test_no_email_below_80_percent():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=50)
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            mock_send.assert_not_called()
    finally:
        session.close()


def test_warning_email_sent_at_80_percent():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=80)
        session.commit()
        user_id = user.id
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert "80" in call_kwargs['subject'] or "100" in call_kwargs['subject']
        session.commit()
    finally:
        session = SessionLocal()
        refreshed = session.query(User).filter_by(id=user_id).first()
        assert refreshed.usage_warning_80_sent is True
        session.close()


def test_warning_email_not_resent_once_flag_set():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=85, warning_sent=True)
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            mock_send.assert_not_called()
    finally:
        session.close()


def test_limit_reached_email_sent_at_100_percent():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=100, warning_sent=True)
        session.commit()
        user_id = user.id
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            mock_send.assert_called_once()
        session.commit()
    finally:
        session = SessionLocal()
        refreshed = session.query(User).filter_by(id=user_id).first()
        assert refreshed.usage_limit_reached_sent is True
        session.close()


def test_limit_reached_email_not_resent_once_flag_set():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=100, warning_sent=True, limit_sent=True)
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            mock_send.assert_not_called()
    finally:
        session.close()


def test_skips_both_when_limit_is_zero():
    """A user with no plan (chases_limit=0) must never divide-by-zero or
    send a nonsensical '0 of 0 used' warning."""
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=0, chases_used=0)
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            mock_send.assert_not_called()
    finally:
        session.close()


def test_send_failure_is_logged_not_raised():
    """A Resend outage while sending a warning email must never bubble up
    and fail the chase send that triggered it."""
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=80)
        session.commit()
        with patch('src.services.account_notifications._send_via_resend', side_effect=Exception('Resend down')):
            maybe_send_usage_warnings(user, session)  # must not raise
    finally:
        session.close()
