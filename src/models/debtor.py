from sqlalchemy import Column, String, ForeignKey
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
    debtor_type = Column(String, nullable=False)  # 'business'
    invoices = relationship('Invoice', back_populates='debtor', cascade="all, delete-orphan")