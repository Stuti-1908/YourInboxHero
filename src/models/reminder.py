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
    __tablename__ = "reminder_log"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invoice_id = Column(String, ForeignKey('invoice.id'), nullable=False)
    invoice = relationship('Invoice', back_populates='reminders')
    sent_at = Column(TIMESTAMP(timezone=True), nullable=False)
    channel = Column(Enum(Channel), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(ReminderStatus), nullable=False)
