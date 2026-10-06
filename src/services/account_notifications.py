"""Account-level emails to our own customers (the business owner), distinct
from src/services/email.py which sends invoice reminders to their debtors.
"""
import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.user import User
from src.services.email import _send_via_resend

logger = structlog.get_logger(__name__)

WARNING_THRESHOLD = 0.8  # fraction of chases_limit that triggers the 80% warning


def _plan_label(plan: str | None) -> str:
    return (plan or "your").capitalize()


def maybe_send_usage_warnings(user: User, db: Session) -> None:
    """Check the user's current usage against both thresholds and send
    whichever warning email(s) newly apply, exactly once per billing cycle.

    Called after record_chase_used() increments usage, so `user` reflects
    post-increment counts. Failures to send are logged, not raised --
    a warning email failing must never block or roll back the chase that
    was already sent to a debtor.
    """
    limit = user.chases_limit or 0
    used = user.chases_used or 0
    if limit <= 0:
        return

    try:
        if used >= limit and not user.usage_limit_reached_sent:
            _send_limit_reached_email(user)
            db.execute(update(User).where(User.id == user.id).values(usage_limit_reached_sent=True))
            db.flush()
        elif used >= limit * WARNING_THRESHOLD and not user.usage_warning_80_sent:
            _send_approaching_limit_email(user, used, limit)
            db.execute(update(User).where(User.id == user.id).values(usage_warning_80_sent=True))
            db.flush()
    except Exception as exc:
        logger.error("usage_warning_email_failed", user_id=user.id, error=str(exc))


def _send_approaching_limit_email(user: User, used: int, limit: int) -> None:
    settings = get_settings()
    remaining = limit - used
    subject = f"You've used {used} of {limit} reminders this month"
    html = f"""
    <p>Hi {user.company_name or 'there'},</p>
    <p>Your {_plan_label(user.subscription_plan)} plan includes <strong>{limit} automated
    reminders</strong> a month, and you've sent <strong>{used}</strong> so far —
    only <strong>{remaining}</strong> left.</p>
    <p>Once you hit the limit, new reminders stop sending until next month or
    until you upgrade. If you'd like more headroom, you can upgrade your plan
    any time from Settings.</p>
    <p>— {settings.resend_from_email.split('@')[0] if settings.resend_from_email else 'YourInboxHero'}</p>
    """
    _send_via_resend(to_email=user.username, subject=subject, html_body=html)
    logger.info("usage_warning_80_sent", user_id=user.id, used=used, limit=limit)


def _send_limit_reached_email(user: User) -> None:
    settings = get_settings()
    limit = user.chases_limit or 0
    subject = "You've reached your monthly reminder limit"
    html = f"""
    <p>Hi {user.company_name or 'there'},</p>
    <p>You've used all <strong>{limit}</strong> automated reminders included in your
    {_plan_label(user.subscription_plan)} plan this month. New reminders —
    email, SMS, and voice — will stop sending until your plan renews next
    month, or until you upgrade for more capacity.</p>
    <p>You can upgrade any time from Settings to keep reminders going without
    interruption.</p>
    <p>— {settings.resend_from_email.split('@')[0] if settings.resend_from_email else 'YourInboxHero'}</p>
    """
    _send_via_resend(to_email=user.username, subject=subject, html_body=html)
    logger.warning("usage_limit_reached_email_sent", user_id=user.id, limit=limit)


def send_verification_email(user: User) -> None:
    """Sent right after registration. The account exists but can't log in
    (see require_active_subscription's sibling check in src/api/auth.py's
    /token handler) until this link is clicked -- this is what actually
    confirms the registrant controls the email address they signed up
    with, closing the account-takeover window where someone could
    register an ADMIN_EMAILS address or another customer's already-paid
    email before its real owner does.

    Raises on failure rather than swallowing the exception (unlike the
    usage-warning emails above) -- if this can't be sent, the user has no
    other way to verify their account, so the caller needs to know.
    """
    settings = get_settings()
    verify_url = f"{settings.frontend_url}/verify-email?token={user.email_verification_token}"
    subject = "Verify your email to activate your YourInboxHero account"
    html = f"""
    <p>Hi {user.company_name or 'there'},</p>
    <p>Click below to verify your email address and activate your account:</p>
    <p><a href="{verify_url}">Verify my email</a></p>
    <p>If you didn't create this account, you can safely ignore this email.</p>
    """
    _send_via_resend(to_email=user.username, subject=subject, html_body=html)
    logger.info("verification_email_sent", user_id=user.id)
