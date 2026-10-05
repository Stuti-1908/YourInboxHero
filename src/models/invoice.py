from sqlalchemy import Column, String, Integer, Numeric, Date, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.types import TIMESTAMP
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
    __table_args__ = (
        # Scoped per-user: two different customers both starting their
        # invoice numbering at "INV-001" must not collide. user_id is
        # denormalized from debtor.user_id (an invoice's debtor can't
        # change owners) so this constraint can be expressed directly,
        # and so every multi-tenant query can filter Invoice by user_id
        # without a join through Debtor.
        UniqueConstraint('user_id', 'invoice_number', name='uq_invoice_user_id_invoice_number'),
    )
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    debtor_id = Column(String, ForeignKey('debtor.id'), nullable=False)
    debtor = relationship('Debtor', back_populates='invoices')
    reminders = relationship('ReminderLog', back_populates='invoice', cascade="all, delete-orphan")
    invoice_number = Column(String, nullable=False)
    amount = Column(Numeric(12,2), nullable=False)
    description = Column(String)
    due_date = Column(Date, nullable=False)
    payment_instructions = Column(String)
    payment_link = Column(String, nullable=True)
    status = Column(Enum(InvoiceStatus), nullable=False)
    last_reminder_sent = Column(TIMESTAMP(timezone=True))
    # Escalation tracking
    escalation_tier = Column(String, nullable=False, default="email")
    escalation_started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    sms_sent_count = Column(Integer, nullable=False, default=0)
    voice_call_count = Column(Integer, nullable=False, default=0)