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


def handle_invoice_reminder(invoice_id: str) -> None:
    """Send a reminder for a single invoice and log the result.

    Args:
        invoice_id: The invoice primary key (string UUID).

    Raises:
        ValueError: If the invoice is not found in the database.
    """
    with get_session() as sess:
        inv = sess.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not inv:
            raise ValueError(f'Invoice {invoice_id} not found')

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
        sess.commit()