"""Account-level emails to our own customers (the business owner), distinct
from src/services/email.py which sends invoice reminders to their debtors.

These are branded as YourInboxHero (the vendor), not the customer's own
company -- unlike the reminder emails in email.py, which go out under
the customer's brand to their debtors.
"""
from datetime import datetime, timezone

import structlog
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import update
from sqlalchemy.orm import Session

from src.config.settings import get_settings
from src.models.user import User
from src.services.email import _send_via_resend

logger = structlog.get_logger(__name__)

WARNING_THRESHOLD = 0.8  # fraction of chases_limit that triggers the 80% warning

_jinja_env = Environment(loader=FileSystemLoader('templates'))


def _plan_label(plan: str | None) -> str:
    return (plan or "your").capitalize()


def _as_aware_utc(dt):
    """Treat a naive datetime as UTC rather than crashing on comparison —
    see the identical helper in src/scheduler.py for the full rationale
    (not every DB driver returns an aware datetime back on read even for a
    TIMESTAMP(timezone=True) column)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _next_monthly_anniversary(anchor: datetime, after: datetime) -> datetime:
    """The next occurrence of anchor's day-of-month at or after `after`.

    Calendar-safe for anchors that don't exist in every month (e.g. the
    31st): falls back to the last day of a shorter month rather than
    raising or silently drifting to the 1st of the next month.
    """
    import calendar

    year, month = after.year, after.month
    last_day = calendar.monthrange(year, month)[1]
    day = min(anchor.day, last_day)
    candidate = after.replace(year=year, month=month, day=day, hour=anchor.hour,
                              minute=anchor.minute, second=anchor.second, microsecond=0)
    if candidate < after:
        month += 1
        year += month // 13  # if month rolled past 12
        month = ((month - 1) % 12) + 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(anchor.day, last_day)
        candidate = candidate.replace(year=year, month=month, day=day)
    return candidate


def reset_admin_invite_usage(db: Session) -> int:
    """Monthly chases_used reset for accounts with no Stripe subscription
    to trigger invoice.payment_succeeded (admin-email and invite-code
    grants) — otherwise they permanently cap out at their first month's
    usage. Anchored to the monthly anniversary of subscription_started_at,
    matching how a real billing cycle would behave. Called from the daily
    sweep (src/scheduler.py); safe to call multiple times a day since it
    only resets once the anniversary has actually passed.

    Returns the number of accounts reset, for sweep logging.
    """
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(User)
        .filter(
            User.subscription_status == "active",
            User.stripe_subscription_id.is_(None),
            User.subscription_started_at.isnot(None),
        )
        .all()
    )

    reset_count = 0
    for user in candidates:
        anchor = _as_aware_utc(user.subscription_started_at)
        last_reset = _as_aware_utc(user.usage_reset_at) or anchor
        next_due = _next_monthly_anniversary(anchor, last_reset)
        if now < next_due:
            continue

        user.chases_used = 0
        user.usage_warning_80_sent = False
        user.usage_limit_reached_sent = False
        user.usage_reset_at = now
        reset_count += 1
        logger.info("admin_invite_usage_reset", user_id=user.id)

    if reset_count:
        db.commit()
    return reset_count


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


def _render_usage_warning(
    user: User, used: int, limit: int, banner_text: str, banner_color: str, message_body: str,
) -> str:
    settings = get_settings()
    tmpl = _jinja_env.get_template('usage_warning_email.html')
    return tmpl.render(
        company_name=user.company_name or 'there',
        plan_label=_plan_label(user.subscription_plan),
        used=used,
        limit=limit,
        banner_text=banner_text,
        banner_color=banner_color,
        message_body=message_body,
        settings_url=f"{settings.frontend_url}/dashboard/settings",
        subject=banner_text,
    )


def _send_approaching_limit_email(user: User, used: int, limit: int) -> None:
    remaining = limit - used
    subject = f"You've used {used} of {limit} reminders this month"
    message_body = (
        f"Your {_plan_label(user.subscription_plan)} plan includes {limit} automated "
        f"reminders a month, and you've sent {used} so far — only {remaining} left. "
        "Once you hit the limit, new reminders stop sending until next month or until "
        "you upgrade."
    )
    html = _render_usage_warning(
        user, used, limit,
        banner_text="80% of plan used", banner_color="#d97706",
        message_body=message_body,
    )
    _send_via_resend(to_email=user.username, subject=subject, html_body=html)
    logger.info("usage_warning_80_sent", user_id=user.id, used=used, limit=limit)


def _send_limit_reached_email(user: User) -> None:
    limit = user.chases_limit or 0
    subject = "You've reached your monthly reminder limit"
    message_body = (
        f"You've used all {limit} automated reminders included in your "
        f"{_plan_label(user.subscription_plan)} plan this month. New reminders — email, "
        "SMS, and voice — will stop sending until your plan renews next month, or until "
        "you upgrade for more capacity."
    )
    html = _render_usage_warning(
        user, limit, limit,
        banner_text="Monthly limit reached", banner_color="#dc2626",
        message_body=message_body,
    )
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
    tmpl = _jinja_env.get_template('account_verification_email.html')
    html = tmpl.render(recipient_name=user.company_name or 'there', verify_url=verify_url)
    _send_via_resend(to_email=user.username, subject=subject, html_body=html)
    logger.info("verification_email_sent", user_id=user.id)
