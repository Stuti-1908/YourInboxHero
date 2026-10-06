from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base
import uuid


class EmailTemplate(Base):
    __tablename__ = "email_template"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    user = relationship('User')
    template_type = Column(String, nullable=False)  # 'upcoming', 'due', 'overdue'
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
