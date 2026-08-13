from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from src.db import get_db
from src.models.debtor import Debtor
from src.auth import get_current_user
from src.models.user import User

router = APIRouter()

class DebtorResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    debtor_type: str

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
