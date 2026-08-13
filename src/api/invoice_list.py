"""Endpoint for listing invoices for the frontend table."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.db import get_db
from src.models.invoice import Invoice
from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import List, Optional

class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    amount: float
    due_date: date
    status: str
    
    model_config = ConfigDict(from_attributes=True)

router = APIRouter()

@router.get('/invoice', response_model=List[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db)):
    """Return all invoices."""
    invoices = db.query(Invoice).all()
    return invoices
