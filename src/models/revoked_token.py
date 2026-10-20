"""Signed-out (or rotated-on-refresh) access tokens.

Stored in the database rather than in process memory so a sign-out still
holds after a restart or deploy. Only a SHA-256 of the token is kept, and
rows are useless once the token itself expires, so they are pruned then.
"""
from sqlalchemy import Column, String
from sqlalchemy.types import TIMESTAMP
from .base import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    token_hash = Column(String(64), primary_key=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
