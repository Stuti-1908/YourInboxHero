"""remove per-user GHL webhook columns

All GHL automation (SMS/voice escalation) runs through a single shared
GHL sub-account configured globally via GHL_API_KEY/GHL_LOCATION_ID
(src/services/ghl_service.py). The per-user inbound webhook feature
(each customer connecting their own GHL workflow via a personal
webhook_secret + optional HMAC signing secret) has been removed along
with its route (src/api/webhooks.py) and Settings UI -- customers must
not be able to bring their own GHL account.

Revision ID: 66911c4b9010
Revises: b2c3d4e5f6a7
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '66911c4b9010'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'ghl_webhook_signing_secret')
    op.drop_constraint('uq_users_webhook_secret', 'users', type_='unique')
    op.drop_column('users', 'webhook_secret')


def downgrade() -> None:
    op.add_column('users', sa.Column('webhook_secret', sa.String(), nullable=True))
    op.execute("UPDATE users SET webhook_secret = 'wh_sec_' || md5(random()::text || id) WHERE webhook_secret IS NULL")
    op.alter_column('users', 'webhook_secret', nullable=False)
    op.create_unique_constraint('uq_users_webhook_secret', 'users', ['webhook_secret'])
    op.add_column('users', sa.Column('ghl_webhook_signing_secret', sa.String(), nullable=True))
