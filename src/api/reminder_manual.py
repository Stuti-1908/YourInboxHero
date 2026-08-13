from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import date, datetime

from src.db import get_db
from src.models.invoice import Invoice, InvoiceStatus
from src.models.reminder import ReminderLog, Channel, ReminderStatus
from src.models.debtor import Debtor
from src.services.email import send_reminder_email
from src.auth import get_current_user
from src.models.user import User

router = APIRouter()

@router.post('/reminders/{invoice_id}/send-now', status_code=200)
def send_manual_reminder(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Manually trigger a reminder for a specific invoice."""
    invoice = (
        db.query(Invoice)
        .join(Debtor)
        .filter(Invoice.id == invoice_id, Debtor.user_id == current_user.id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.debtor.debtor_type != 'business':
        raise HTTPException(status_code=400, detail='Only business debtors allowed')
    if invoice.due_date < date.today():
        raise HTTPException(status_code=400, detail='Invoice past due – automation forbidden')
    # Send email (mockable)
    send_reminder_email(invoice)
    invoice.last_reminder_sent = datetime.utcnow()
    db.commit()
    return {'detail': 'Reminder sent'}