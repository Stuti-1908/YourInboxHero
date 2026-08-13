from sqlalchemy import Column, String
from .base import Base

class Debtor(Base):
    __tablename__ = "debtor"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone = Column(String)
    debtor_type = Column(String, nullable=False)  # 'business'