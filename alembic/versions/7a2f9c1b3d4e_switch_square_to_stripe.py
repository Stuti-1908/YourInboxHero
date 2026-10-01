"""Switch payment provider from Square to Stripe

Revision ID: 7a2f9c1b3d4e
Revises: 4e1004a142f2
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a2f9c1b3d4e'
down_revision: Union[str, Sequence[str], None] = '4e1004a142f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('stripe_subscription_id', sa.String(), nullable=True))
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col['name'] for col in inspector.get_columns('users')}
    if 'square_payment_id' in existing_columns:
        op.drop_column('users', 'square_payment_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('square_payment_id', sa.String(), nullable=True))
    op.drop_column('users', 'stripe_subscription_id')
    op.drop_column('users', 'stripe_customer_id')
