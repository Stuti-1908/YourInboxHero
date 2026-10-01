"""Add usage warning flags and fix monthly chase reset

Revision ID: 9c83e5acba41
Revises: 7a2f9c1b3d4e
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c83e5acba41'
down_revision: Union[str, Sequence[str], None] = '7a2f9c1b3d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('usage_warning_80_sent', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('usage_limit_reached_sent', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'usage_limit_reached_sent')
    op.drop_column('users', 'usage_warning_80_sent')
