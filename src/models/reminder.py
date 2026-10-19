from sqlalchemy import Column, String, JSON, Enum, ForeignKey
from sqlalchemy.types import TIMESTAMP
import uuid
from sqlalchemy.orm import relationship
import enum
from .base import Base


class Channel(str, enum.Enum):
    email = "email"
    sms = "sms"
    voice = "voice"


class ReminderStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"


class ReminderLog(Base):
    """A sent (or failed) reminder, for either an Invoice or a
    DocumentRequest -- exactly one of invoice_id/document_request_id is
    set, never both and never neither. Originally invoice-only (invoice_id
    NOT NULL); invoice_id was relaxed to nullable and document_request_id
    added so document-request sends (email/SMS/voice) can be logged here
    too instead of having no audit trail at all."""
    __tablename__ = "reminder_log"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id = Column(String, ForeignKey('invoice.id'), nullable=True)
    invoice = relationship('Invoice', back_populates='reminders')
    document_request_id = Column(String, ForeignKey('document_request.id'), nullable=True)
    document_request = relationship('DocumentRequest', back_populates='reminders')
    sent_at = Column(TIMESTAMP(timezone=True), nullable=False)
    channel = Column(Enum(Channel), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(ReminderStatus), nullable=False)
