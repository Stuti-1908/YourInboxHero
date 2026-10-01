from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from src.db import get_db
from src.auth import get_current_user, require_active_subscription
from src.models.user import User
from src.models.document_client import DocumentClient

router = APIRouter(prefix="/document-clients", tags=["document_clients"])

class DocumentClientCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None

class DocumentClientResponse(DocumentClientCreate):
    id: str

@router.post("", response_model=DocumentClientResponse)
def create_document_client(
    client_in: DocumentClientCreate,
    current_user: User = Depends(require_active_subscription),
    db: Session = Depends(get_db)
):
    db_client = DocumentClient(
        user_id=current_user.id,
        name=client_in.name,
        email=client_in.email,
        phone=client_in.phone
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return {
        "id": db_client.id,
        "name": db_client.name,
        "email": db_client.email,
        "phone": db_client.phone
    }

@router.get("", response_model=List[DocumentClientResponse])
def get_document_clients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    clients = db.query(DocumentClient).filter(DocumentClient.user_id == current_user.id).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone
        }
        for c in clients
    ]
