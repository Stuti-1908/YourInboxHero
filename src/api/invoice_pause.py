"""Pause endpoint — allows clients to pause upcoming/due invoices.

A paused invoice will not receive automated reminders until it is resumed.
Only invoices with status 'upcoming' or 'due' can be paused.
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.db import get_db
from src.models.invoice import Invoice, InvoiceStatus

router = APIRouter()


@router.post('/invoice/{invoice_id}/pause', status_code=200)
def pause_invoice(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail='Invoice not found')
    if inv.status not in (InvoiceStatus.upcoming, InvoiceStatus.due):
        raise HTTPException(
            status_code=400,
            detail='Only upcoming/due invoices can be paused',
        )
    inv.status = InvoiceStatus.paused
    db.commit()
    return {'detail': 'Invoice paused'}
