"""Tests for record_chase_used — the single shared increment point used by
every send path, including its integration with usage-warning emails."""
import uuid
from unittest.mock import patch
from src.db import SessionLocal
from src.models.user import User
from src.services.usage_limits import record_chase_used, has_chase_capacity


def _make_user(session, chases_limit=100, chases_used=0):
    u = User(
        id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="pwd", company_name="Test Co",
        subscription_plan="growth", subscription_status="active",
        chases_limit=chases_limit, chases_used=chases_used,
    )
    session.add(u)
    session.flush()
    return u


def test_record_chase_used_increments_count():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=10)
        session.commit()
        user_id = user.id

        with patch('src.services.account_notifications.maybe_send_usage_warnings'):
            record_chase_used(user, session, channel='email', invoice_id='fake-inv')
        session.commit()
    finally:
        session = SessionLocal()
        refreshed = session.query(User).filter_by(id=user_id).first()
        assert refreshed.chases_used == 11
        session.close()


def test_record_chase_used_triggers_warning_check_with_fresh_data():
    """The warning check must see the post-increment count, confirmed by
    crossing the 80% threshold exactly on the triggering call."""
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=79)
        session.commit()

        with patch('src.services.account_notifications.maybe_send_usage_warnings') as mock_warn:
            record_chase_used(user, session, channel='email', invoice_id='fake-inv')
            mock_warn.assert_called_once()
            called_user = mock_warn.call_args.args[0]
            assert called_user.chases_used == 80  # post-increment, not the stale 79
    finally:
        session.close()


def test_warning_check_failure_does_not_raise_or_block_chase_recording():
    """record_chase_used must never raise because of the follow-up
    warning-email check -- the chase has already been sent and counted by
    that point, so a bug there must not look like the send itself failed."""
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=79)
        session.commit()
        user_id = user.id

        with patch(
            'src.services.account_notifications.maybe_send_usage_warnings',
            side_effect=Exception('boom'),
        ):
            record_chase_used(user, session, channel='email', invoice_id='fake-inv')  # must not raise
        session.commit()
    finally:
        session.close()

    session = SessionLocal()
    refreshed = session.query(User).filter_by(id=user_id).first()
    assert refreshed.chases_used == 80
    session.close()


def test_has_chase_capacity_respects_limit():
    session = SessionLocal()
    try:
        under = _make_user(session, chases_limit=100, chases_used=99)
        at = _make_user(session, chases_limit=100, chases_used=100)
        over = _make_user(session, chases_limit=100, chases_used=101)
        session.commit()

        assert has_chase_capacity(under) is True
        assert has_chase_capacity(at) is False
        assert has_chase_capacity(over) is False
    finally:
        session.close()
