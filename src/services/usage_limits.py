"""Per-plan monthly reminder ("chase") usage enforcement.

A "chase" is one outbound reminder attempt — an email, SMS, or voice call —
sent on an invoice. Every send path (manual trigger, the automated pre-due
worker, scheduled SMS/voice escalation) must check the limit before sending
and record the usage after, using these two functions so the counting logic
lives in exactly one place.
"""
import logging
from sqlalchemy import update
from sqlalchemy.orm import Session

from src.models.user import User

logger = logging.getLogger(__name__)


def has_chase_capacity(user: User) -> bool:
    """Return True if this user can send one more chase this billing cycle."""
    limit = user.chases_limit or 0
    used = user.chases_used or 0
    return used < limit


def can_send_chase(user: User) -> bool:
    """Single gate every automated send path must check before reaching out
    to a debtor: the user must both have remaining quota AND an active
    subscription. A cancelled or past-due account must stop generating
    outbound email/SMS/voice immediately, not just once its last paid
    month's chases run out -- that's unpaid service and can mean reminders
    going out after a customer believes they've cancelled.
    """
    return user.subscription_status == "active" and has_chase_capacity(user)


def record_chase_used(user: User, db: Session, channel: str, invoice_id: str) -> None:
    """Increment usage after a chase is actually sent (or attempted —
    callers should call this regardless of send success/failure, matching
    the existing reminder_log behavior of logging failed sends too, since a
    failed send still consumed a real provider call).

    Issues a direct UPDATE keyed by user_id rather than mutating `user` and
    relying on the ORM session to know it's an existing row. This matters
    because `user` is not always the same object the caller's session
    originally loaded (e.g. request-scoped auth dependencies, or any
    detached/transient instance) — attempting an ORM-level save on such an
    object can misfire as an INSERT instead of an UPDATE. A keyed UPDATE is
    correct regardless of the object's attachment state, and also avoids a
    lost-update race if two sends for the same user commit concurrently.
    """
    db.execute(
        update(User).where(User.id == user.id).values(chases_used=User.chases_used + 1)
    )
    db.flush()
    # Best-effort: if `user` happens to be attached to this session, refresh
    # it so callers that read user.chases_used afterwards see the new value.
    # Harmless no-op for detached/transient instances.
    try:
        db.refresh(user)
    except Exception:
        pass
    logger.info(
        f'chase_recorded user_id={user.id} channel={channel} invoice_id={invoice_id}'
    )

    # Re-fetch fresh from the DB rather than trusting `user` (which may be
    # a detached/transient object the refresh above couldn't update) --
    # the warning-threshold check needs the real post-increment count, not
    # a possibly-stale in-memory value, or it could miss the exact moment
    # a threshold is crossed.
    #
    # This is deliberately isolated with its own try/except: the chase has
    # already been sent and counted by this point, so nothing here may ever
    # cause record_chase_used to raise. A caller that saw an exception here
    # could wrongly mark an already-successful send as failed.
    try:
        from src.services.account_notifications import maybe_send_usage_warnings
        fresh_user = db.query(User).filter(User.id == user.id).first()
        if fresh_user:
            maybe_send_usage_warnings(fresh_user, db)
    except Exception as exc:
        logger.error(f'usage_warning_check_failed user_id={user.id} error={exc}')
