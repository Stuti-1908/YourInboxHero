"""add voice_call_consent to document_client

Document Collection's escalation engine (added in this change) reuses
the exact same email->SMS->voice tier pattern as invoices, which
requires the same consent gate (f2b3c4d5e6a7's rationale: TCPA and
similar consent-to-call regulations) before any automated phone call.
document_client never had this field -- defaults false on existing
rows, same as the debtor migration.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_client', sa.Column('voice_call_consent', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('document_client', 'voice_call_consent')
