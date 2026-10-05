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
    voice_call_consent: bool = False

class DebtorResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    debtor_type: str
    voice_call_consent: bool


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
    # Uniqueness is scoped to this user — another customer may legitimately
    # have their own debtor record for the same email address.
    if db.query(Debtor).filter(Debtor.email == request.email, Debtor.user_id == current_user.id).first():
        raise HTTPException(status_code=400, detail="Debtor with this email already exists")

    new_debtor = Debtor(
        user_id=current_user.id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        debtor_type=request.debtor_type,
        voice_call_consent=request.voice_call_consent
    )
    db.add(new_debtor)
    db.commit()
    db.refresh(new_debtor)

    return {
        "id": new_debtor.id,
        "name": new_debtor.name,
        "email": new_debtor.email,
        "phone": new_debtor.phone,
        "debtor_type": new_debtor.debtor_type,
        "voice_call_consent": new_debtor.voice_call_consent
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
                "debtor_type": d.debtor_type,
                "voice_call_consent": d.voice_call_consent
            } for d in debtors
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


class DebtorUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    voice_call_consent: Optional[bool] = None


@router.put('/debtor/{debtor_id}', response_model=DebtorResponse)
def update_debtor(
    debtor_id: str,
    request: DebtorUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a debtor's editable fields — notably voice_call_consent,
    which is usually granted after the debtor was first added (e.g. once
    a signed consent form comes back), not at creation time."""
    debtor = db.query(Debtor).filter(Debtor.id == debtor_id, Debtor.user_id == current_user.id).first()
    if not debtor:
        raise HTTPException(status_code=404, detail="Debtor not found or unauthorized")

    if request.name is not None:
        debtor.name = request.name
    if request.phone is not None:
        debtor.phone = request.phone
    if request.voice_call_consent is not None:
        debtor.voice_call_consent = request.voice_call_consent

    db.commit()
    db.refresh(debtor)

    return {
        "id": debtor.id,
        "name": debtor.name,
        "email": debtor.email,
        "phone": debtor.phone,
        "debtor_type": debtor.debtor_type,
        "voice_call_consent": debtor.voice_call_consent
    }


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