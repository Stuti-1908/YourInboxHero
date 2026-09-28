from sqlalchemy import Column, String, Integer, Numeric, Date, ForeignKey, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from .base import Base
import enum
import uuid

class InvoiceStatus(str, enum.Enum):
    upcoming = "upcoming"
    due = "due"
    overdue = "overdue"
    paid = "paid"
    manual = "manual"
    paused = "paused"

class EscalationTier(str, enum.Enum):
    email = "email"
    sms = "sms"
    voice = "voice"

class Invoice(Base):
    __tablename__ = "invoice"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    debtor_id = Column(String, ForeignKey('debtor.id'), nullable=False)
    debtor = relationship('Debtor', back_populates='invoices')
    reminders = relationship('ReminderLog', back_populates='invoice', cascade="all, delete-orphan")
    invoice_number = Column(String, nullable=False, unique=True)
    amount = Column(Numeric(12,2), nullable=False)
    description = Column(String)
    due_date = Column(Date, nullable=False)
    payment_instructions = Column(String)
    payment_link = Column(String, nullable=True)
    status = Column(Enum(InvoiceStatus), nullable=False)
    last_reminder_sent = Column(TIMESTAMP)
    # Escalation tracking
    escalation_tier = Column(String, nullable=False, default="email")
    escalation_started_at = Column(TIMESTAMP, nullable=True)
    sms_sent_count = Column(Integer, nullable=False, default=0)
    voice_call_count = Column(Integer, nullable=False, default=0)