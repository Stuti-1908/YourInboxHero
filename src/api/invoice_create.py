from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from src.db import get_db
from src.models.invoice import Invoice, InvoiceStatus
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

router = APIRouter()

class InvoiceCreateRequest(BaseModel):
    debtor_id: str
    invoice_number: str
    amount: float
    description: str = None
    due_date: date
    payment_instructions: str = None

class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    amount: float
    due_date: date
    status: str

@router.post('/invoice', response_model=InvoiceResponse)
def create_invoice(request: InvoiceCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a new invoice for a debtor belonging to the authenticated client."""
    # Verify the debtor belongs to the user
    debtor = db.query(Debtor).filter(Debtor.id == request.debtor_id, Debtor.user_id == current_user.id).first()
    if not debtor:
        raise HTTPException(status_code=404, detail="Debtor not found")

    # Verify invoice number is unique
    if db.query(Invoice).filter(Invoice.invoice_number == request.invoice_number).first():
        raise HTTPException(status_code=400, detail="Invoice number already exists")

    status = InvoiceStatus.upcoming
    if request.due_date < date.today():
        status = InvoiceStatus.overdue
    elif request.due_date == date.today():
        status = InvoiceStatus.due

    new_invoice = Invoice(
        debtor_id=request.debtor_id,
        invoice_number=request.invoice_number,
        amount=request.amount,
        description=request.description,
        due_date=request.due_date,
        payment_instructions=request.payment_instructions,
        status=status
    )
    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)

    return {
        "id": new_invoice.id,
        "invoice_number": new_invoice.invoice_number,
        "amount": float(new_invoice.amount),
        "due_date": new_invoice.due_date,
        "status": new_invoice.status.value
    }
