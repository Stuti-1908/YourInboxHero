"""add sweep_run table

Tracks when the daily sweep last completed, so a startup catch-up check
can tell whether today's scheduled run was missed (container was down at
08:00 UTC) and run it immediately rather than silently waiting until
tomorrow.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-10-05 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sweep_run',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('last_run_date', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('sweep_run')
