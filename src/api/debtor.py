"""Debtor CRUD endpoints with pagination."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db import get_db
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

router = APIRouter()

class DebtorCreateRequest(BaseModel):
    name: str
    email: str
    phone: str = None
    debtor_type: str = "business"

class DebtorResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    debtor_type: str


class PaginatedDebtorResponse(BaseModel):
    items: List[DebtorResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.post('/debtor', response_model=DebtorResponse)
def create_debtor(
    request: DebtorCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new debtor for the authenticated client."""
    # Check if email is already in use
    if db.query(Debtor).filter(Debtor.email == request.email).first():
        raise HTTPException(status_code=400, detail="Debtor with this email already exists")

    new_debtor = Debtor(
        user_id=current_user.id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        debtor_type=request.debtor_type
    )
    db.add(new_debtor)
    db.commit()
    db.refresh(new_debtor)

    return {
        "id": new_debtor.id,
        "name": new_debtor.name,
        "email": new_debtor.email,
        "phone": new_debtor.phone,
        "debtor_type": new_debtor.debtor_type
    }


@router.get('/debtor', response_model=PaginatedDebtorResponse)
def get_debtors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)"),
    search: Optional[str] = Query(None, description="Search by name or email"),
):
    """Retrieve paginated debtors for the authenticated client."""
    query = db.query(Debtor).filter(Debtor.user_id == current_user.id)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Debtor.name.ilike(search_term)) | (Debtor.email.ilike(search_term))
        )
    
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    debtors = (
        query.order_by(Debtor.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    
    return PaginatedDebtorResponse(
        items=[
            {
                "id": d.id,
                "name": d.name,
                "email": d.email,
                "phone": d.phone,
                "debtor_type": d.debtor_type
            } for d in debtors
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.delete('/debtor/{debtor_id}', status_code=200)
def delete_debtor(
    debtor_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a debtor and cascade delete all their invoices and reminders."""
    debtor = db.query(Debtor).filter(Debtor.id == debtor_id, Debtor.user_id == current_user.id).first()
    if not debtor:
        raise HTTPException(status_code=404, detail="Debtor not found or unauthorized")
    
    db.delete(debtor)
    db.commit()
    return {"detail": "Debtor and all associated data deleted successfully"}