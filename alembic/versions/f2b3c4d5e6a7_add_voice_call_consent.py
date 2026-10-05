"""add voice_call_consent to debtor

Required before any automated SMS/voice reminder can be sent to a
debtor's phone number (TCPA and similar consent-to-call regulations).
Defaults false on existing rows -- phone-based escalation is paused for
all current debtors until each one is explicitly marked as consented.

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6a7'
down_revision: Union[str, Sequence[str], None] = 'e1a2b3c4d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('debtor', sa.Column('voice_call_consent', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('debtor', 'voice_call_consent')
