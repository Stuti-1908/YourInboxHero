"""DocumentRequest model — tracks documents/forms that need to be collected from clients.

Similar to Invoice but instead of chasing money, it chases paperwork.
The same 3-tier escalation engine (email → SMS → voice) applies.
"""
from sqlalchemy import Column, String, Text, Date, Integer, ForeignKey
from sqlalchemy.types import TIMESTAMP
from sqlalchemy.orm import relationship
from .base import Base
from datetime import datetime, timezone
import uuid


class DocumentRequest(Base):
    __tablename__ = "document_request"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    user = relationship('User')
    client_id = Column(String, ForeignKey('document_client.id'), nullable=False)
    client = relationship('DocumentClient')
    
    # Document details
    title = Column(String, nullable=False)  # e.g. "W-9 Tax Form", "Signed Contract"
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=False)
    
    # Status tracking
    status = Column(String, nullable=False, default="pending")  # pending, submitted, approved, overdue
    
    # Upload tracking
    upload_token = Column(String, unique=True, nullable=False, default=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    uploaded_file_name = Column(String, nullable=True)
    uploaded_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Reminder tracking (same as Invoice)
    last_reminder_sent = Column(TIMESTAMP(timezone=True), nullable=True)
    escalation_tier = Column(String, nullable=False, default="email")
    escalation_started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    sms_sent_count = Column(Integer, nullable=False, default=0)
    voice_call_count = Column(Integer, nullable=False, default=0)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
