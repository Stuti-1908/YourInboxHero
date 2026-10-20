"""Authentication utilities with timezone-aware datetimes."""
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import jwt

from src.db import SessionLocal, get_db
from src.models.revoked_token import RevokedToken
from src.models.user import User
from src.config.settings import get_settings

# Single source of truth for the signing secret — validate_production_settings()
# (called at app startup) already refuses to boot in production/staging if this
# is missing or still the dev default, so there is no separate fallback here.
SECRET_KEY = get_settings().secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")



def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def revoke_token(token: str) -> None:
    """Persist a sign-out so it survives restarts. Expired revocations are
    pruned on the way, since an expired token is rejected anyway."""
    try:
        exp = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})["exp"]
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    except (jwt.PyJWTError, KeyError, TypeError):
        return  # not one of our tokens: nothing it could unlock
    db = SessionLocal()
    try:
        db.query(RevokedToken).filter(RevokedToken.expires_at < datetime.now(timezone.utc)).delete(synchronize_session=False)
        db.merge(RevokedToken(token_hash=_token_hash(token), expires_at=expires_at))
        db.commit()
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if db.query(RevokedToken).filter(RevokedToken.token_hash == _token_hash(token)).first():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def require_active_subscription(request: Request, current_user: User = Depends(get_current_user)) -> User:
    """Gate write actions behind an active subscription.

    A lapsed subscription (past_due after a failed renewal, or cancelled)
    still allows login and viewing existing data — losing access to your own
    invoice history on a billing hiccup would be needlessly punishing — but
    every mutating request (create/update/delete, sending a reminder, etc.)
    is blocked until the plan is reactivated. GET requests always pass
    through untouched regardless of subscription state.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return current_user
    if current_user.subscription_status != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your subscription is inactive. Reactivate your plan to continue.",
        )
    return current_user
