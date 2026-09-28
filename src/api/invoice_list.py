"""Endpoint for listing invoices with pagination."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.db import get_db
from src.models.invoice import Invoice
from pydantic import BaseModel, ConfigDict
from datetime import date
from typing import List, Optional
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


class PaginatedResponse(BaseModel):
    items: List[InvoiceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

router = APIRouter()


@router.get('/invoice', response_model=PaginatedResponse)
def list_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    debtor_id: Optional[str] = Query(None, description="Filter by debtor"),
):
    """Return paginated invoices for the current user."""
    query = (
        db.query(Invoice)
        .join(Debtor)
        .filter(Debtor.user_id == current_user.id)
    )
    
    if status:
        query = query.filter(Invoice.status == status)
    if debtor_id:
        query = query.filter(Invoice.debtor_id == debtor_id)
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    invoices = (
        query.order_by(Invoice.due_date.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    
    return PaginatedResponse(
        items=invoices,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )