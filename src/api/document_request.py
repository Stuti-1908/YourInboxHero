"""Document Request API — CRUD for document/form collection requests."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, datetime, timezone

from src.db import get_db
from src.auth import get_current_user, require_active_subscription
from src.models.user import User
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest
from src.services.document_storage import save_uploaded_document, get_document_path

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
    current_user: User = Depends(require_active_subscription)
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
    current_user: User = Depends(require_active_subscription)
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


class PublicDocumentRequestInfo(BaseModel):
    title: str
    description: Optional[str]
    due_date: date
    status: str
    business_name: str
    already_uploaded_file_name: Optional[str]


@router.get("/documents/upload/{upload_token}", response_model=PublicDocumentRequestInfo)
def get_upload_request_info(upload_token: str, db: Session = Depends(get_db)):
    """Public endpoint — lets the upload page show what's being requested
    (and by whom) before the client picks a file, without requiring login."""
    doc = db.query(DocumentRequest).filter(DocumentRequest.upload_token == upload_token).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid upload link")

    return PublicDocumentRequestInfo(
        title=doc.title,
        description=doc.description,
        due_date=doc.due_date,
        status=doc.status,
        business_name=doc.user.company_name or "the business that requested this",
        already_uploaded_file_name=doc.uploaded_file_name,
    )


@router.post("/documents/upload/{upload_token}")
async def upload_document(
    upload_token: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Public endpoint — clients use their unique upload_token (no login
    required) to submit the requested file. Accepts PDF/PNG/JPEG/DOC/DOCX
    up to settings.max_upload_size_mb."""
    doc = db.query(DocumentRequest).filter(
        DocumentRequest.upload_token == upload_token
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Invalid upload link")

    stored_filename, original_filename = await save_uploaded_document(doc.id, file)

    doc.status = "submitted"
    doc.uploaded_at = datetime.now(timezone.utc)
    doc.uploaded_file_name = original_filename
    doc.stored_file_name = stored_filename
    db.commit()

    return {"msg": "Document received successfully. Thank you!"}


@router.get("/documents/{doc_id}/download")
def download_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Authenticated — the business owner downloads what their client
    uploaded."""
    doc = db.query(DocumentRequest).filter(
        DocumentRequest.id == doc_id,
        DocumentRequest.user_id == current_user.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document request not found")
    if not doc.stored_file_name:
        raise HTTPException(status_code=404, detail="No file has been uploaded for this request yet")

    path = get_document_path(doc.stored_file_name)
    return FileResponse(
        path=path,
        filename=doc.uploaded_file_name or path.name,
    )