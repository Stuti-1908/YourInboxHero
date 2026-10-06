"""add usage_reset_at to users

Admin/invite-granted accounts have no Stripe subscription, so they never
receive the invoice.payment_succeeded webhook that resets chases_used for
paying customers -- without tracking, they'd permanently cap out at their
first month's usage. usage_reset_at records the last time this account's
usage was reset (either via Stripe renewal or the new admin/invite
monthly sweep step), so that step only fires once per monthly cycle.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-10-06 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, Sequence[str], None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('usage_reset_at', sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'usage_reset_at')
