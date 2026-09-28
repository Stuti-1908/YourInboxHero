from sqlalchemy import Column, String, Boolean, Integer, TIMESTAMP
import uuid
import secrets
from .base import Base

def generate_webhook_secret():
    return f"wh_sec_{secrets.token_hex(16)}"

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    logo_base64 = Column(String, nullable=True)
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(String, nullable=True)
    smtp_username = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)
    smtp_from_email = Column(String, nullable=True)
    webhook_secret = Column(String, unique=True, nullable=False, default=generate_webhook_secret)
    ghl_webhook_signing_secret = Column(String, nullable=True)  # For GHL webhook HMAC verification
    is_active = Column(Boolean, default=True)
    # Subscription tracking
    subscription_plan = Column(String, nullable=True)  # 'starter', 'growth', 'scale'
    subscription_status = Column(String, nullable=False, default="inactive")  # 'inactive', 'active', 'cancelled'
    subscription_started_at = Column(TIMESTAMP, nullable=True)
    square_payment_id = Column(String, nullable=True)
    chases_limit = Column(Integer, nullable=False, default=0)  # 100, 300, 750
    chases_used = Column(Integer, nullable=False, default=0)
