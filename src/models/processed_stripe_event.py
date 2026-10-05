"""Tracks Stripe webhook event IDs already processed, so a retried/replayed
delivery of the same event (Stripe resends on timeout, and can also be
manually replayed from the Stripe dashboard) doesn't reapply side effects
like resetting chases_used a second time mid-month.
"""
from sqlalchemy import Column, String
from sqlalchemy.types import TIMESTAMP
from datetime import datetime, timezone
from .base import Base


class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"
    event_id = Column(String, primary_key=True)  # Stripe's event["id"], globally unique
    event_type = Column(String, nullable=False)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
