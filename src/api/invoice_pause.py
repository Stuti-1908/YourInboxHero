"""Pause endpoint — allows clients to pause upcoming/due invoices.

A paused invoice will not receive automated reminders until it is resumed.
Only invoices with status 'upcoming' or 'due' can be paused.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db import get_db
from src.models.invoice import Invoice, InvoiceStatus
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

router = APIRouter()


@router.post('/invoice/{invoice_id}/pause')
def pause_invoice(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Pause automated reminders for a specific upcoming invoice."""
    inv = (
        db.query(Invoice)
        .join(Debtor)
        .filter(Invoice.id == invoice_id, Debtor.user_id == current_user.id)
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail='Invoice not found')

    if inv.status == InvoiceStatus.paused:
        raise HTTPException(status_code=400, detail='Invoice is already paused')

    if inv.status in (InvoiceStatus.overdue, InvoiceStatus.paid):
        raise HTTPException(status_code=400, detail=f'Cannot pause invoice with status {inv.status.value}')

    inv.status = InvoiceStatus.paused
    db.commit()

    return {'detail': 'Invoice paused'}
