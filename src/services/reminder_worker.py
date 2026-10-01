"""Reminder worker — processes individual invoice reminders from the queue.

Called by the Service Bus consumer function (consume_queue.py). Loads the
invoice from the database, sends the reminder email, and logs the result
to the reminder_log table.
"""
import logging
from datetime import datetime, timezone

from src.db import get_session
from src.models.invoice import Invoice
from src.models.reminder import ReminderLog, Channel, ReminderStatus
from src.services.email import send_reminder_email
from src.services.usage_limits import has_chase_capacity, record_chase_used


class ChaseLimitReached(Exception):
    """Raised when the owning user has exhausted their plan's monthly chase
    allowance. Callers (manual trigger, the automated worker) decide how to
    surface this — e.g. a 402 to the UI, or just skip-and-log in a batch."""
    pass


def handle_invoice_reminder(invoice_id: str) -> None:
    """Send a reminder for a single invoice and log the result.

    Args:
        invoice_id: The invoice primary key (string UUID).

    Raises:
        ValueError: If the invoice is not found in the database.
        ChaseLimitReached: If the owning user has no chases left this cycle.
            The invoice is left untouched — no partial log entry, no usage
            increment — so a retry next cycle (or after a plan upgrade)
            behaves exactly as if this attempt never happened.
    """
    with get_session() as sess:
        inv = sess.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise ValueError(f'Invoice {invoice_id} not found')

        user = inv.debtor.user
        if not has_chase_capacity(user):
            raise ChaseLimitReached(
                f'User {user.id} has used {user.chases_used}/{user.chases_limit} chases this cycle'
            )

        try:
            send_reminder_email(inv)
            status = ReminderStatus.sent
        except Exception as exc:
            logging.error(f'Failed to send reminder for invoice {invoice_id}: {exc}')
            status = ReminderStatus.failed

        log_entry = ReminderLog(
            invoice_id=invoice_id,
            sent_at=datetime.now(timezone.utc),
            channel=Channel.email,
            payload={'invoice_number': inv.invoice_number, 'debtor_email': inv.debtor.email},
            status=status,
        )
        sess.add(log_entry)
        inv.last_reminder_sent = datetime.now(timezone.utc)
        record_chase_used(user, sess, channel='email', invoice_id=invoice_id)
        sess.commit()