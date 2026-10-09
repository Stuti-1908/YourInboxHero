"""Tests for usage-limit warning emails — must fire exactly once per
threshold per billing cycle, never block the chase that triggered them."""
from unittest.mock import patch
from src.services.account_notifications import maybe_send_usage_warnings
from src.db import SessionLocal
from src.models.user import User
import uuid


def _make_user(session, chases_limit=100, chases_used=0, warning_sent=False, limit_sent=False, company_name="Test Co"):
    u = User(
        id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="pwd", company_name=company_name,
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


def test_warning_email_is_branded_as_yourinboxhero():
    """These emails go to our own customers (the business owner), not
    their debtors -- they must be branded as YourInboxHero, not the
    customer's own company (unlike the reminder emails in email.py)."""
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=100, chases_used=80, company_name="Acme Co")
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            html = mock_send.call_args.kwargs['html_body']
            assert 'YourInboxHero' in html
            assert '<html' in html  # a real HTML document, not a bare string
            assert 'Upgrade Plan' in html
            assert '80' in html and '100' in html  # used / limit shown
    finally:
        session.close()


def test_limit_reached_email_is_branded_and_shows_usage():
    session = SessionLocal()
    try:
        user = _make_user(session, chases_limit=50, chases_used=50, warning_sent=True, company_name="Acme Co")
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            maybe_send_usage_warnings(user, session)
            html = mock_send.call_args.kwargs['html_body']
            assert 'YourInboxHero' in html
            assert 'Monthly limit reached' in html
            assert '50 / 50' in html
    finally:
        session.close()


def test_verification_email_is_branded_and_includes_link():
    from src.services.account_notifications import send_verification_email

    session = SessionLocal()
    try:
        user = _make_user(session, company_name="Acme Co")
        user.email_verification_token = "test-token-xyz"
        session.commit()
        with patch('src.services.account_notifications._send_via_resend') as mock_send:
            send_verification_email(user)
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs['to_email'] == user.username
            html = call_kwargs['html_body']
            assert 'YourInboxHero' in html
            assert 'test-token-xyz' in html
            assert '<html' in html
    finally:
        session.close()


class TestResetAdminInviteUsage:
    """Tests for reset_admin_invite_usage — the monthly usage reset for
    accounts with no Stripe subscription (admin-email/invite-code grants),
    which never receive the invoice.payment_succeeded webhook that resets
    paying customers' usage."""

    def _make_admin_user(self, session, started_days_ago, chases_used=500,
                         usage_reset_at=None, stripe_subscription_id=None):
        from datetime import datetime, timezone, timedelta
        started = datetime.now(timezone.utc) - timedelta(days=started_days_ago)
        u = User(
            id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="pwd", company_name="Admin Test Co",
            subscription_plan="scale", subscription_status="active",
            chases_limit=750, chases_used=chases_used,
            subscription_started_at=started,
            usage_reset_at=usage_reset_at,
            stripe_subscription_id=stripe_subscription_id,
            usage_warning_80_sent=True, usage_limit_reached_sent=True,
        )
        session.add(u)
        session.flush()
        return u

    def test_resets_account_past_its_monthly_anniversary(self):
        from src.services.account_notifications import reset_admin_invite_usage
        session = SessionLocal()
        try:
            # Started 35 days ago, never reset -- anniversary has passed.
            user = self._make_admin_user(session, started_days_ago=35)
            session.commit()
            user_id = user.id

            count = reset_admin_invite_usage(session)
            assert count == 1
        finally:
            session.close()

        session = SessionLocal()
        try:
            refreshed = session.query(User).filter_by(id=user_id).first()
            assert refreshed.chases_used == 0
            assert refreshed.usage_warning_80_sent is False
            assert refreshed.usage_limit_reached_sent is False
            assert refreshed.usage_reset_at is not None
        finally:
            session.close()

    def test_does_not_reset_before_anniversary(self):
        from src.services.account_notifications import reset_admin_invite_usage
        session = SessionLocal()
        try:
            # Started 10 days ago -- anniversary is ~20 days out.
            user = self._make_admin_user(session, started_days_ago=10)
            session.commit()
            user_id = user.id

            count = reset_admin_invite_usage(session)
            assert count == 0
        finally:
            session.close()

        session = SessionLocal()
        try:
            refreshed = session.query(User).filter_by(id=user_id).first()
            assert refreshed.chases_used == 500  # untouched
        finally:
            session.close()

    def test_does_not_reset_twice_in_the_same_cycle(self):
        from datetime import datetime, timezone, timedelta
        from src.services.account_notifications import reset_admin_invite_usage
        session = SessionLocal()
        try:
            # Started 35 days ago, already reset 3 days ago (within this
            # cycle) -- must not reset again just because it's past the
            # original anniversary; next reset is due ~27 days from the
            # last reset, not from subscription_started_at.
            recently_reset = datetime.now(timezone.utc) - timedelta(days=3)
            user = self._make_admin_user(
                session, started_days_ago=35, chases_used=10,
                usage_reset_at=recently_reset,
            )
            session.commit()
            user_id = user.id

            count = reset_admin_invite_usage(session)
            assert count == 0
        finally:
            session.close()

        session = SessionLocal()
        try:
            refreshed = session.query(User).filter_by(id=user_id).first()
            assert refreshed.chases_used == 10  # untouched
        finally:
            session.close()

    def test_ignores_accounts_with_a_stripe_subscription(self):
        """Paying customers are reset via the Stripe webhook, not this
        sweep step -- including one must not double-reset them."""
        from src.services.account_notifications import reset_admin_invite_usage
        session = SessionLocal()
        try:
            self._make_admin_user(
                session, started_days_ago=35, chases_used=500,
                stripe_subscription_id="sub_real_customer",
            )
            session.commit()

            count = reset_admin_invite_usage(session)
            assert count == 0
        finally:
            session.close()

    def test_ignores_inactive_accounts(self):
        from src.services.account_notifications import reset_admin_invite_usage
        session = SessionLocal()
        try:
            user = self._make_admin_user(session, started_days_ago=35)
            user.subscription_status = "cancelled"
            session.commit()

            count = reset_admin_invite_usage(session)
            assert count == 0
        finally:
            session.close()
