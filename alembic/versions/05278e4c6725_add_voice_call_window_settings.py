"""add per-user voice call window settings

Each customer can restrict which days/hours (in their own timezone) our
automated voice escalation is allowed to call their debtors/clients.
Defaults to Mon-Fri 9am-5pm America/New_York for every existing and new
user; narrower is allowed, wider than Mon-Sun 00-24 is not meaningful
since that's already "no restriction".

Revision ID: 05278e4c6725
Revises: 66911c4b9010
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '05278e4c6725'
down_revision: Union[str, Sequence[str], None] = '66911c4b9010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('voice_call_days', sa.String(), nullable=False, server_default='mon,tue,wed,thu,fri'))
    op.add_column('users', sa.Column('voice_call_start_hour', sa.Integer(), nullable=False, server_default='9'))
    op.add_column('users', sa.Column('voice_call_end_hour', sa.Integer(), nullable=False, server_default='17'))
    op.add_column('users', sa.Column('voice_call_timezone', sa.String(), nullable=False, server_default='America/New_York'))


def downgrade() -> None:
    op.drop_column('users', 'voice_call_timezone')
    op.drop_column('users', 'voice_call_end_hour')
    op.drop_column('users', 'voice_call_start_hour')
    op.drop_column('users', 'voice_call_days')
