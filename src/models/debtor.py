from sqlalchemy import Column, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .base import Base
import uuid

class Debtor(Base):
    __tablename__ = "debtor"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    user = relationship('User')
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone = Column(String)
    # Required before any automated SMS/voice reminder may be sent to this
    # debtor's phone number (TCPA and similar consent-to-call regulations).
    # Defaults False: a debtor added without explicit opt-in only ever gets
    # email reminders until this is set true.
    voice_call_consent = Column(Boolean, nullable=False, default=False)
    debtor_type = Column(String, nullable=False)  # 'business'
    invoices = relationship('Invoice', back_populates='debtor', cascade="all, delete-orphan")