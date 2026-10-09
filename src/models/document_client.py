import uuid
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class DocumentClient(Base):
    __tablename__ = "document_client"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    # Required before any automated SMS/voice reminder can be sent to this
    # client's phone number (TCPA and similar consent-to-call regulations)
    # -- same gate Debtor.voice_call_consent enforces for invoices.
    voice_call_consent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
    requests = relationship("DocumentRequest", back_populates="client")
