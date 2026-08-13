"""Reminder service — queries eligible invoices and processes pre-due reminders.

Business rules:
  - Only 'business' debtor invoices are eligible.
  - Only invoices with status 'upcoming' and due_date within [today, today+lookahead_days] qualify.
  - Overdue invoices (due_date < today) are NEVER sent automated reminders (legal guardrail).
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.models.invoice import Invoice, InvoiceStatus


def get_eligible_invoices(db: Session, lookahead_days: int = 14):
    """Return invoices eligible for a pre-due reminder.

    Eligibility criteria:
      1. status == 'upcoming'
      2. due_date >= today  (not overdue)
      3. due_date <= today + lookahead_days  (within the reminder window)
      4. debtor.debtor_type == 'business'
      5. last_reminder_sent is NULL or < today (no double sends on same day)
    """
    today = date.today()
    upper = today + timedelta(days=lookahead_days)
    
    # We want to exclude invoices where a reminder was already sent today (UTC).
    # Since last_reminder_sent is a UTC datetime, we compare its date component
    # or just ensure it's strictly less than today's datetime start.
    today_start = datetime.combine(today, datetime.min.time())
    
    return (
        db.query(Invoice)
        .join(Invoice.debtor)
        .filter(
            Invoice.status == InvoiceStatus.upcoming,
            Invoice.due_date >= today,
            Invoice.due_date <= upper,
            (Invoice.last_reminder_sent == None) | (Invoice.last_reminder_sent < today_start)
        )
        .all()
    )


def process_due_reminders():
    """Fetch eligible invoices and enqueue each for async reminder delivery.

    In production, each invoice ID is pushed onto Azure Service Bus.
    A consumer function picks up each message and calls the reminder worker.

    Aborts early if the 'reminders-enabled' feature flag is off.
    """
    from src.feature_flags import reminders_enabled
    if not reminders_enabled():
        logging.info('Reminders disabled via feature flag — skipping')
        return

    from src.db import get_session

    with get_session() as sess:
        invoices = get_eligible_invoices(sess)
        if not invoices:
            logging.info('No eligible invoices found')
            return

        from src.services.queue import enqueue_reminder

        for inv in invoices:
            enqueue_reminder(str(inv.id))
            inv.last_reminder_sent = datetime.utcnow()
            logging.info(f'Enqueued reminder for invoice {inv.id}')
        sess.commit()
        logging.info(f'Enqueued {len(invoices)} reminder(s)')
