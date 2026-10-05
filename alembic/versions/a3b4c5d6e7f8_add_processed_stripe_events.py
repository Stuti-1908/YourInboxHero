"""add processed_stripe_events table

Deduplicates Stripe webhook deliveries by event ID. Stripe retries
undelivered/timed-out webhooks and events can also be manually replayed
from the dashboard; without this, a replayed invoice.payment_succeeded
with billing_reason=subscription_cycle would reset chases_used a second
time mid-month.

Revision ID: a3b4c5d6e7f8
Revises: f2b3c4d5e6a7
Create Date: 2026-10-05 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2b3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'processed_stripe_events',
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('processed_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )


def downgrade() -> None:
    op.drop_table('processed_stripe_events')
