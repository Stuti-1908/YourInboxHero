"""Endpoint for listing invoices for the frontend table."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.db import get_db
from src.models.invoice import Invoice
from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import List
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    amount: float
    due_date: date
    status: str
    
    model_config = ConfigDict(from_attributes=True)

router = APIRouter()

@router.get('/invoice', response_model=List[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return all invoices in the system for the current user."""
    invoices = (
        db.query(Invoice)
        .join(Debtor)
        .filter(Debtor.user_id == current_user.id)
        .order_by(Invoice.due_date.asc())
        .all()
    )
    return invoices
