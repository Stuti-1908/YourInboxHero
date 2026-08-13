from sqlalchemy import Column, String, Numeric, Date, ForeignKey, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from .base import Base
import enum

class InvoiceStatus(str, enum.Enum):
    upcoming = "upcoming"
    due = "due"
    overdue = "overdue"
    paid = "paid"
    manual = "manual"
    paused = "paused"

class Invoice(Base):
    __tablename__ = "invoice"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    debtor_id = Column(String, ForeignKey('debtor.id'), nullable=False)
    debtor = relationship('Debtor')
    invoice_number = Column(String, nullable=False, unique=True)
    amount = Column(Numeric(12,2), nullable=False)
    description = Column(String)
    due_date = Column(Date, nullable=False)
    payment_instructions = Column(String)
    status = Column(Enum(InvoiceStatus), nullable=False)
    last_reminder_sent = Column(TIMESTAMP)