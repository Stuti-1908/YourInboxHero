"""Invoice status actions: pause, resume, and mark-paid.

A paused invoice will not receive automated reminders until it is resumed.
A paid invoice stops receiving reminders permanently (every sweep query in
src/scheduler.py and src/services/*.py filters on specific non-paid
statuses, so marking an invoice paid is sufficient on its own to stop all
future email/SMS/voice sends for it).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db import get_db
from src.models.invoice import Invoice, InvoiceStatus
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

router = APIRouter()


def _get_owned_invoice(invoice_id: str, db: Session, current_user: User) -> Invoice:
    inv = (
        db.query(Invoice)
        .join(Debtor)
        .filter(Invoice.id == invoice_id, Debtor.user_id == current_user.id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail='Invoice not found')
    return inv


@router.post('/invoice/{invoice_id}/pause')
def pause_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Pause automated reminders for a specific upcoming invoice."""
    inv = _get_owned_invoice(invoice_id, db, current_user)

    if inv.status == InvoiceStatus.paused:
        raise HTTPException(status_code=400, detail='Invoice is already paused')

    if inv.status in (InvoiceStatus.overdue, InvoiceStatus.paid):
        raise HTTPException(status_code=400, detail=f'Cannot pause invoice with status {inv.status.value}')

    inv.status = InvoiceStatus.paused
    db.commit()

    return {'detail': 'Invoice paused'}


@router.post('/invoice/{invoice_id}/resume')
def resume_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Resume a paused invoice. Re-derives the correct status from its due
    date rather than always going back to 'upcoming', so a paused invoice
    whose due date has already passed resumes as 'overdue', not 'upcoming'."""
    from datetime import date

    inv = _get_owned_invoice(invoice_id, db, current_user)

    if inv.status != InvoiceStatus.paused:
        raise HTTPException(status_code=400, detail=f'Invoice is not paused (status: {inv.status.value})')

    if inv.due_date < date.today():
        inv.status = InvoiceStatus.overdue
    elif inv.due_date == date.today():
        inv.status = InvoiceStatus.due
    else:
        inv.status = InvoiceStatus.upcoming
    db.commit()

    return {'detail': 'Invoice resumed', 'status': inv.status.value}


@router.post('/invoice/{invoice_id}/mark-paid')
def mark_invoice_paid(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Mark an invoice as paid. Stops all future automated reminders (email,
    SMS, voice) for it — every sweep query filters on status, so this alone
    is sufficient, no separate 'stop chasing' flag is needed."""
    inv = _get_owned_invoice(invoice_id, db, current_user)

    if inv.status == InvoiceStatus.paid:
        raise HTTPException(status_code=400, detail='Invoice is already marked paid')

    inv.status = InvoiceStatus.paid
    db.commit()

    return {'detail': 'Invoice marked as paid'}
