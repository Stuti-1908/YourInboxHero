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
    voice_call_consent: bool = False


class DocumentClientResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str]
    voice_call_consent: bool


class DocumentClientUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    voice_call_consent: Optional[bool] = None


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
        phone=client_in.phone,
        voice_call_consent=client_in.voice_call_consent,
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return {
        "id": db_client.id,
        "name": db_client.name,
        "email": db_client.email,
        "phone": db_client.phone,
        "voice_call_consent": db_client.voice_call_consent,
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
            "phone": c.phone,
            "voice_call_consent": c.voice_call_consent,
        }
        for c in clients
    ]


@router.put("/{client_id}", response_model=DocumentClientResponse)
def update_document_client(
    client_id: str,
    request: DocumentClientUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a document client's editable fields — notably
    voice_call_consent, which is usually granted after the client was
    first added (mirrors PUT /debtor/{id})."""
    client = db.query(DocumentClient).filter(
        DocumentClient.id == client_id, DocumentClient.user_id == current_user.id
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Document client not found or unauthorized")

    if request.name is not None:
        client.name = request.name
    if request.phone is not None:
        client.phone = request.phone
    if request.voice_call_consent is not None:
        client.voice_call_consent = request.voice_call_consent

    db.commit()
    db.refresh(client)

    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "voice_call_consent": client.voice_call_consent,
    }
