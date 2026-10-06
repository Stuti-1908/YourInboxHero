from sqlalchemy import Column, String, Boolean, Integer
from sqlalchemy.types import TIMESTAMP
import uuid
import secrets
from .base import Base

def generate_webhook_secret():
    return f"wh_sec_{secrets.token_hex(16)}"

def generate_email_verification_token():
    return secrets.token_urlsafe(32)

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    company_name = Column(String, nullable=True)
    # Closes a real account-takeover window: without this, anyone who knows
    # an ADMIN_EMAILS address or a customer's already-paid email (via a
    # parked PendingSubscription) could register it themselves before its
    # real owner does, since registration never previously confirmed the
    # registrant actually controls that inbox.
    email_verified = Column(Boolean, nullable=False, default=False)
    email_verification_token = Column(String, nullable=True, default=generate_email_verification_token)
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
    subscription_started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    chases_limit = Column(Integer, nullable=False, default=0)  # 100, 300, 750
    chases_used = Column(Integer, nullable=False, default=0)
    # Tracks whether each usage-limit warning email has already gone out
    # this billing cycle, so a customer sitting above a threshold doesn't
    # get the same warning on every single send. Both reset to False
    # whenever chases_used resets (registration, and monthly renewal via
    # the invoice.payment_succeeded webhook).
    usage_warning_80_sent = Column(Boolean, nullable=False, default=False)
    usage_limit_reached_sent = Column(Boolean, nullable=False, default=False)
