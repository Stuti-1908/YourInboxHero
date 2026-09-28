"""Document Request API — CRUD for document/form collection requests."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, datetime, timezone
import os
import shutil

from src.db import get_db
from src.auth import get_current_user
from src.models.user import User
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest

router = APIRouter(prefix="", tags=["document_requests"])

class DocumentRequestCreate(BaseModel):
    client_id: str
    title: str
    description: Optional[str] = None
    due_date: date

class DocumentClientOut(BaseModel):
    id: str
    name: str
    email: str

class DocumentRequestResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    due_date: date
    status: str
    upload_token: str
    uploaded_file_name: Optional[str]
    escalation_tier: str
    sms_sent_count: int
    voice_call_count: int
    client: DocumentClientOut


@router.get("/documents", response_model=List[DocumentRequestResponse])
def list_document_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all document requests for the authenticated user."""
    docs = db.query(DocumentRequest).filter(
        DocumentRequest.user_id == current_user.id
    ).order_by(DocumentRequest.due_date.desc()).all()
    
    results = []
    for doc in docs:
        results.append({
            "id": doc.id,
            "title": doc.title,
            "description": doc.description,
            "due_date": doc.due_date,
            "status": doc.status,
            "upload_token": doc.upload_token,
            "uploaded_file_name": doc.uploaded_file_name,
            "escalation_tier": str(doc.escalation_tier) if doc.escalation_tier else "none",
            "sms_sent_count": doc.sms_sent_count or 0,
            "voice_call_count": doc.voice_call_count or 0,
            "client": {
                "id": doc.client.id,
                "name": doc.client.name,
                "email": doc.client.email
            }
        })
    return results


@router.post("/documents", response_model=DocumentRequestResponse)
def create_document_request(
    data: DocumentRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new document request."""
    client = db.query(DocumentClient).filter(
        DocumentClient.id == data.client_id,
        DocumentClient.user_id == current_user.id
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Document client not found")
    
    doc = DocumentRequest(
        user_id=current_user.id,
        client_id=data.client_id,
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        status="pending"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    return {
        "id": doc.id,
        "title": doc.title,
        "description": doc.description,
        "due_date": doc.due_date,
        "status": doc.status,
        "upload_token": doc.upload_token,
        "uploaded_file_name": None,
        "escalation_tier": "email",
        "sms_sent_count": 0,
        "voice_call_count": 0,
        "client": {
            "id": client.id,
            "name": client.name,
            "email": client.email
        }
    }


@router.delete("/documents/{doc_id}")
def delete_document_request(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(DocumentRequest).filter(
        DocumentRequest.id == doc_id,
        DocumentRequest.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document request not found")
    db.delete(doc)
    db.commit()
    return {"msg": "Document request deleted"}


@router.post("/documents/upload/{upload_token}")
def upload_document(
    upload_token: str,
    db: Session = Depends(get_db)
):
    """Public endpoint — clients use their unique upload_token to mark document as submitted.
    In production, this would accept a file upload. For now it marks the request as submitted."""
    doc = db.query(DocumentRequest).filter(
        DocumentRequest.upload_token == upload_token
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid upload link")
    
    doc.status = "submitted"
    doc.uploaded_at = datetime.now(timezone.utc)
    doc.uploaded_file_name = "document_submitted"
    db.commit()
    
    return {"msg": "Document received successfully. Thank you!"}