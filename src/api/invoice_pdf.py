from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from src.db import get_db
from src.auth import get_current_user
from src.models.invoice import Invoice
from src.models.debtor import Debtor
from src.models.user import User
from src.services.pdf_service import generate_invoice_pdf

router = APIRouter()

@router.get("/api/invoice/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoice = db.query(Invoice).join(Debtor).filter(
        Invoice.id == invoice_id,
        Debtor.user_id == current_user.id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    debtor = db.query(Debtor).filter(Debtor.id == invoice.debtor_id).first()
    
    pdf_buffer = generate_invoice_pdf(invoice, debtor, current_user.username)
    
    headers = {
        "Content-Disposition": f"attachment; filename=invoice_{invoice.invoice_number}.pdf"
    }
    
    return StreamingResponse(
        iter([pdf_buffer.getvalue()]),
        media_type="application/pdf",
        headers=headers
    )
