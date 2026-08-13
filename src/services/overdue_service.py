"""Overdue transition service — marks past-due invoices as 'overdue'.

Business rule: Any invoice with status 'upcoming' or 'due' whose due_date
is strictly before today must transition to 'overdue'. Once overdue, no
automated reminders are sent (legal guardrail).
"""
from datetime import date

from src.models.invoice import Invoice, InvoiceStatus


def transition_overdue(session):
    """Find all upcoming/due invoices past their due date and mark them overdue.

    Args:
        session: SQLAlchemy session (caller is responsible for commit).

    Returns:
        int: Number of invoices transitioned.
    """
    today = date.today()
    overdue_invoices = (
        session.query(Invoice)
        .filter(
            Invoice.due_date < today,
            Invoice.status.in_([InvoiceStatus.upcoming, InvoiceStatus.due]),
        )
        .all()
    )
    for inv in overdue_invoices:
        inv.status = InvoiceStatus.overdue
    session.commit()
    return len(overdue_invoices)
