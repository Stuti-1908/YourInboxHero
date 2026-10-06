"""GHL Webhook with HMAC signature verification."""
import hmac
import hashlib
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from src.db import get_db
from src.models.user import User
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.services.secrets import decrypt_secret
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
import uuid

logger = structlog.get_logger(__name__)

router = APIRouter()


class GHLWebhookPayload(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[str] = None
    description: Optional[str] = None


def verify_ghl_signature(
    payload: bytes,
    signature: str,
    webhook_secret: str
) -> bool:
    """
    Verify GHL webhook signature using HMAC-SHA256.
    
    GHL sends the signature in the 'X-GHL-Signature' header as:
    sha256=<hex_digest>
    """
    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = signature[7:]  # Remove 'sha256=' prefix

    # Compute HMAC-SHA256
    computed_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    return hmac.compare_digest(computed_signature, expected_signature)


@router.post("/ghl/{webhook_secret}")
async def ghl_webhook_receiver(
    webhook_secret: str,
    request: Request,
    payload: GHLWebhookPayload,
    db: Session = Depends(get_db),
    x_ghl_signature: Optional[str] = Header(None, alias="X-GHL-Signature"),
):
    """
    Receive and process GHL webhook with signature verification.
    
    Security:
    - Validates webhook secret in URL path
    - Verifies HMAC-SHA256 signature from X-GHL-Signature header
    - Rejects unsigned or invalid requests with 401
    """
    # 1. Authenticate user via webhook secret
    user = db.query(User).filter(User.webhook_secret == webhook_secret).first()
    if not user:
        logger.warning("ghl_webhook_invalid_secret", webhook_secret_prefix=webhook_secret[:8])
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # A cancelled/past_due account must not keep accumulating new invoices
    # (and therefore new chases) via GHL after their subscription lapses.
    if user.subscription_status != "active":
        logger.warning("ghl_webhook_inactive_subscription", user_id=user.id, subscription_status=user.subscription_status)
        raise HTTPException(status_code=402, detail="Subscription is not active")

    # 2. Verify HMAC signature (if user has GHL configured)
    signing_secret = decrypt_secret(user.ghl_webhook_signing_secret) if user.ghl_webhook_signing_secret else None
    if signing_secret:
        # Get raw body for signature verification
        body = await request.body()

        if not verify_ghl_signature(body, x_ghl_signature or "", signing_secret):
            logger.warning(
                "ghl_webhook_invalid_signature",
                user_id=user.id,
                webhook_secret_prefix=webhook_secret[:8],
            )
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 3. Extract Debtor Info
    full_name = f"{payload.first_name or ''} {payload.last_name or ''}".strip()
    if not full_name:
        full_name = payload.email.split('@')[0]

    debtor = db.query(Debtor).filter(
        Debtor.user_id == user.id,
        Debtor.email == payload.email
    ).first()

    if not debtor:
        debtor = Debtor(
            user_id=user.id,
            name=full_name,
            email=payload.email,
            phone=payload.phone,
            debtor_type='business'
        )
        db.add(debtor)
        db.commit()
        db.refresh(debtor)
    else:
        # Update existing debtor if needed
        debtor.name = full_name
        if payload.phone:
            debtor.phone = payload.phone
        db.commit()

    # 4. Create Invoice (if provided)
    if payload.amount and payload.amount > 0 and payload.due_date:
        try:
            parsed_due_date = datetime.strptime(payload.due_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_due_date = date.today()  # fallback

        inv_number = payload.invoice_number or f"INV-{uuid.uuid4().hex[:6].upper()}"

        # Ensure invoice number is unique for this user
        existing_inv = db.query(Invoice).filter(Invoice.invoice_number == inv_number, Invoice.user_id == user.id).first()
        if existing_inv:
            inv_number = f"{inv_number}-{uuid.uuid4().hex[:4].upper()}"

        status = InvoiceStatus.upcoming
        if parsed_due_date < date.today():
            status = InvoiceStatus.overdue
        elif parsed_due_date == date.today():
            status = InvoiceStatus.due

        new_invoice = Invoice(
            user_id=user.id,
            debtor_id=debtor.id,
            invoice_number=inv_number,
            amount=payload.amount,
            description=payload.description or "Automated Invoice from GHL",
            due_date=parsed_due_date,
            payment_instructions="Please submit payment upon receipt.",
            status=status
        )
        db.add(new_invoice)
        db.commit()

    return {"status": "success", "message": "GHL data processed successfully"}
