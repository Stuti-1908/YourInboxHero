from sqlalchemy import Column, String, JSON, TIMESTAMP, Enum, ForeignKey
from sqlalchemy.types import UUID
import uuid
from sqlalchemy.orm import relationship
import enum
from .base import Base

class Channel(str, enum.Enum):
    email = "email"
    sms = "sms"

class ReminderStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"

class ReminderLog(Base):
    __tablename__ = "reminder_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey('invoice.id'), nullable=False)
    sent_at = Column(TIMESTAMP, nullable=False, server_default='now()')
    channel = Column(Enum(Channel), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(ReminderStatus), nullable=False)