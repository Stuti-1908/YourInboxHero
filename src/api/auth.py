"""Authentication endpoints with rate limiting."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from slowapi.util import get_remote_address

from src.db import get_db
from src.models.user import User
from src.auth import (
    verify_password,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    revoke_token,
    oauth2_scheme,
    get_password_hash
)
from pydantic import BaseModel

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str

@router.post("/token", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # Rate limiting handled by app-level limiter
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
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

@router.post("/users/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    request: Request,
    user: UserCreate,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user = User(
        username=user.username,
        hashed_password=get_password_hash(user.password),
        company_name=user.company_name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"id": db_user.id, "username": db_user.username, "company_name": db_user.company_name}

from typing import Optional
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