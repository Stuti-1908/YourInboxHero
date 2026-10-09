"""add created_at (issue date) to invoice

Real invoices show an issue date distinct from the due date -- the
invoice.py model and PDF generator only ever had due_date. Adds
created_at, backfilled for existing rows with their own due_date (the
closest honest value available; we have no real record of when these
were actually created) so every invoice -- old and new -- has a sane,
non-null issue date for the redesigned PDF/email to display.

Revision ID: a1b2c3d4e5f6
Revises: a225ef8d6e70
Create Date: 2026-10-09 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'a225ef8d6e70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoice', sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=True))
    # Backfill: due_date is a DATE, cast to a UTC midnight TIMESTAMP --
    # the closest honest value available for rows that predate this column.
    op.execute("UPDATE invoice SET created_at = due_date::timestamptz AT TIME ZONE 'UTC' WHERE created_at IS NULL")
    op.alter_column('invoice', 'created_at', nullable=False, server_default=sa.text('now()'))


def downgrade() -> None:
    op.drop_column('invoice', 'created_at')
