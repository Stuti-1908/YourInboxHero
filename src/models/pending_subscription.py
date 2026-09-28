"""Holds a Stripe subscription that was activated (via webhook) for an email
that hasn't registered a User account yet — since Stripe Checkout collects
payment before this app has ever seen the customer. Consumed and deleted the
moment that email registers, so the plan is never lost."""
from sqlalchemy import Column, String, Integer, TIMESTAMP
import uuid
from datetime import datetime, timezone
from .base import Base


class PendingSubscription(Base):
    __tablename__ = "pending_subscriptions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    plan = Column(String, nullable=False)
    chases_limit = Column(Integer, nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
