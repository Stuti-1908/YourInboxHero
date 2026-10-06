"""Authentication endpoints with rate limiting."""
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from src.db import get_db
from src.models.user import User, generate_email_verification_token
from src.models.pending_subscription import PendingSubscription
from src.config.settings import get_settings
from src.auth import (
    verify_password,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    revoke_token,
    oauth2_scheme,
    get_password_hash
)
from src.rate_limit import limiter
from src.services.account_notifications import send_verification_email
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/token", response_model=Token)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in. Check your inbox for the verification link.",
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "company_name": user.company_name}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    revoke_token(token)
    return {"msg": "Successfully logged out"}

# Debug endpoint to create a test user easily in dev
class UserCreate(BaseModel):
    username: str
    password: str
    company_name: str
    invite_code: Optional[str] = None

@router.post("/users/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register_user(
    request: Request,
    user: UserCreate,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    settings = get_settings()
    is_admin = settings.is_admin_email(user.username)
    has_valid_invite = settings.is_valid_invite_code(user.invite_code)

    # A Stripe payment landing for this email (via webhook, before the
    # customer ever registers) is the only path to a paid plan — see
    # stripe_payments.py's PendingSubscription handling. Without one (or an
    # admin-email or shared test-invite-code bypass), there's nothing to
    # grant an account access to, so we refuse the signup rather than
    # create a free/inactive account that looks legitimate but can't
    # actually do anything.
    pending = db.query(PendingSubscription).filter(PendingSubscription.email == user.username).first()
    if not pending and not is_admin and not has_valid_invite:
        raise HTTPException(
            status_code=402,
            detail="No active plan found for this email. Choose a plan and complete checkout before creating an account.",
        )

    db_user = User(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        company_name=user.company_name
    )
    db.add(db_user)
    db.flush()  # assign db_user.id before we may reference it below

    if pending:
        db_user.subscription_plan = pending.plan
        db_user.subscription_status = "active"
        db_user.subscription_started_at = datetime.now(timezone.utc)
        db_user.stripe_customer_id = pending.stripe_customer_id
        db_user.stripe_subscription_id = pending.stripe_subscription_id
        db_user.chases_limit = pending.chases_limit
        db_user.chases_used = 0
        db.delete(pending)
    elif is_admin or has_valid_invite:
        db_user.subscription_plan = "scale"
        db_user.subscription_status = "active"
        db_user.subscription_started_at = datetime.now(timezone.utc)
        db_user.chases_limit = 750
        db_user.chases_used = 0

    db.commit()
    db.refresh(db_user)

    try:
        send_verification_email(db_user)
    except Exception as exc:
        # The account exists either way (dropping it here would also lose
        # the plan/pending-subscription linkage just applied above). Log
        # loudly -- Sentry will surface this -- but still tell the caller
        # plainly, since the user otherwise has no way to know verification
        # never went out and will be stuck unable to log in.
        logger.error("verification_email_send_failed", user_id=db_user.id, error=str(exc))
        return {
            "id": db_user.id,
            "username": db_user.username,
            "company_name": db_user.company_name,
            "subscription_plan": db_user.subscription_plan,
            "subscription_status": db_user.subscription_status,
            "verification_email_sent": False,
        }

    return {
        "id": db_user.id,
        "username": db_user.username,
        "company_name": db_user.company_name,
        "subscription_plan": db_user.subscription_plan,
        "subscription_status": db_user.subscription_status,
        "verification_email_sent": True,
    }


@router.post("/users/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    """Public — the link clicked from the verification email. Query-param
    (not a path segment) to match how the frontend route reads it, and
    because it's a one-time bearer token, not a resource identifier."""
    user = db.query(User).filter(User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if user.email_verified:
        return {"msg": "Email already verified. You can log in."}

    user.email_verified = True
    user.email_verification_token = None  # single-use
    db.commit()
    return {"msg": "Email verified successfully. You can now log in."}


class ResendVerificationRequest(BaseModel):
    username: str


@router.post("/users/resend-verification")
@limiter.limit("3/minute")
def resend_verification(request: Request, data: ResendVerificationRequest, db: Session = Depends(get_db)):
    """Public — lets a user request a fresh verification email if the
    first one was lost, expired from their inbox view, or never arrived.
    Always returns the same response regardless of whether the email
    exists, so this can't be used to enumerate registered accounts."""
    user = db.query(User).filter(User.username == data.username).first()
    if user and not user.email_verified:
        if not user.email_verification_token:
            user.email_verification_token = generate_email_verification_token()
            db.commit()
        try:
            send_verification_email(user)
        except Exception as exc:
            logger.error("resend_verification_email_failed", user_id=user.id, error=str(exc))
    return {"msg": "If that email is registered and unverified, a new verification link has been sent."}


from src.auth import get_current_user

class UserSettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    logo_base64: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    ghl_webhook_signing_secret: Optional[str] = None

@router.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "company_name": current_user.company_name,
        "logo_base64": current_user.logo_base64,
        "smtp_host": current_user.smtp_host,
        "smtp_port": current_user.smtp_port,
        "smtp_username": current_user.smtp_username,
        "smtp_password": current_user.smtp_password,
        "smtp_from_email": current_user.smtp_from_email,
        "webhook_secret": current_user.webhook_secret,
        "subscription_plan": current_user.subscription_plan,
        "subscription_status": current_user.subscription_status,
        "chases_limit": current_user.chases_limit or 0,
        "chases_used": current_user.chases_used or 0
    }

@router.put("/users/me")
def update_me(
    settings: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if settings.company_name is not None:
        current_user.company_name = settings.company_name
    if settings.logo_base64 is not None:
        current_user.logo_base64 = settings.logo_base64
    if settings.smtp_host is not None:
        current_user.smtp_host = settings.smtp_host
    if settings.smtp_port is not None:
        current_user.smtp_port = settings.smtp_port
    if settings.smtp_username is not None:
        current_user.smtp_username = settings.smtp_username
    if settings.smtp_password is not None:
        current_user.smtp_password = settings.smtp_password
    if settings.smtp_from_email is not None:
        current_user.smtp_from_email = settings.smtp_from_email
        
    db.commit()
    db.refresh(current_user)
    return {"msg": "Settings updated successfully"}