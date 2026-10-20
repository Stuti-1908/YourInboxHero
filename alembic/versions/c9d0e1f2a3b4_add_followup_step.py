"""add followup_step to invoice and document_request

Replaces the old tier/time-based chasing with a fixed follow-up schedule
(see src/services/followup.py). followup_step records how far each item has
got through that schedule.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-20 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoice', sa.Column('followup_step', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('document_request', sa.Column('followup_step', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('document_request', 'followup_step')
    op.drop_column('invoice', 'followup_step')
