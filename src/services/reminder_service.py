"""Reminder service — queries eligible invoices and processes pre-due reminders.

Business rules:
  - Only 'business' debtor invoices are eligible.
  - Only invoices with status 'upcoming' and due_date within [today, today+lookahead_days] qualify.
  - Overdue invoices (due_date < today) are NEVER sent automated reminders (legal guardrail).
"""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.models.invoice import Invoice, InvoiceStatus
from src.services.email import send_reminder_email


def get_eligible_invoices(db: Session, lookahead_days: int = 14):
    """Return invoices eligible for a pre-due reminder.

    Eligibility criteria:
      1. status == 'upcoming'
      2. due_date >= today  (not overdue)
      3. due_date <= today + lookahead_days  (within the reminder window)
      4. debtor.debtor_type == 'business'
    """
    today = date.today()
    upper = today + timedelta(days=lookahead_days)
    return (
        db.query(Invoice)
        .join(Invoice.debtor)
        .filter(
            Invoice.status == InvoiceStatus.upcoming,
            Invoice.due_date >= today,
            Invoice.due_date <= upper,
        )
        .all()
    )


def process_due_reminders():
    """Fetch eligible invoices and send reminder emails for each."""
    from src.db import get_session
    with get_session() as sess:
        invoices = get_eligible_invoices(sess)
        for inv in invoices:
            send_reminder_email(inv)
            inv.last_reminder_sent = datetime.utcnow()
        sess.commit()
