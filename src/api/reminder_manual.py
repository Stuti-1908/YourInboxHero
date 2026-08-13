from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from src.db import get_db
from src.models.invoice import Invoice, InvoiceStatus
from datetime import date, datetime
from src.services.email import send_reminder_email
from pydantic import BaseModel

class ManualReminderRequest(BaseModel):
    invoice_id: str

router = APIRouter()

@router.post('/reminder/manual', status_code=200)
def manual_reminder(request: ManualReminderRequest, db: Session = Depends(get_db)):
    invoice_id = request.invoice_id
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail='Invoice not found')
    if invoice.debtor.debtor_type != 'business':
        raise HTTPException(status_code=400, detail='Only business debtors allowed')
    if invoice.due_date < date.today():
        raise HTTPException(status_code=400, detail='Invoice past due – automation forbidden')
    # Send email (mockable)
    send_reminder_email(invoice)
    invoice.last_reminder_sent = datetime.utcnow()
    db.commit()
    return {'detail': 'Reminder sent'}