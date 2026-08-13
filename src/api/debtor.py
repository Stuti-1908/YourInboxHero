from typing import List
from fastapi import APIRouter, Depends, HTTPException
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

@router.post('/debtor', response_model=DebtorResponse)
def create_debtor(request: DebtorCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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

@router.get('/debtor', response_model=List[DebtorResponse])
def get_debtors(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retrieve all debtors for the authenticated client."""
    debtors = db.query(Debtor).filter(Debtor.user_id == current_user.id).order_by(Debtor.name.asc()).all()
    
    return [
        {
            "id": d.id,
            "name": d.name,
            "email": d.email,
            "phone": d.phone,
            "debtor_type": d.debtor_type
        } for d in debtors
    ]
