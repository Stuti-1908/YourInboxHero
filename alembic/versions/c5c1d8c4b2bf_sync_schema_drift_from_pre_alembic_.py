"""sync schema drift from pre-alembic sqlite bootstrap

Several columns (on users, invoice) existed on the live SQLite database
because it was originally created directly via Base.metadata.create_all()
before these fields were captured in any Alembic migration. This brings
a fresh database (e.g. a new Postgres instance) up to the same schema the
live site has actually been running on.

pending_subscriptions, document_client, email_template, and document_request
are NOT touched here -- they're real, already-correct tables; they only
showed up in the autogenerate diff because the table was created via
create_all() with a narrower model import, not because they need to change.

Revision ID: c5c1d8c4b2bf
Revises: 9c83e5acba41
Create Date: 2026-10-01 13:03:42.007901

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c5c1d8c4b2bf'
down_revision: Union[str, Sequence[str], None] = '9c83e5acba41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('invoice', sa.Column('payment_link', sa.String(), nullable=True))
    op.add_column('invoice', sa.Column('escalation_tier', sa.String(), nullable=False, server_default='email'))
    op.add_column('invoice', sa.Column('escalation_started_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('invoice', sa.Column('sms_sent_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('invoice', sa.Column('voice_call_count', sa.Integer(), nullable=False, server_default='0'))

    op.add_column('users', sa.Column('logo_base64', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_host', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_port', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_password', sa.String(), nullable=True))
    op.add_column('users', sa.Column('smtp_from_email', sa.String(), nullable=True))
    op.add_column('users', sa.Column('webhook_secret', sa.String(), nullable=True))
    op.execute("UPDATE users SET webhook_secret = 'wh_sec_' || md5(random()::text || id) WHERE webhook_secret IS NULL")
    op.alter_column('users', 'webhook_secret', nullable=False)
    op.create_unique_constraint('uq_users_webhook_secret', 'users', ['webhook_secret'])
    op.add_column('users', sa.Column('ghl_webhook_signing_secret', sa.String(), nullable=True))
    op.add_column('users', sa.Column('subscription_plan', sa.String(), nullable=True))
    op.add_column('users', sa.Column('subscription_status', sa.String(), nullable=False, server_default='inactive'))
    op.add_column('users', sa.Column('subscription_started_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('users', sa.Column('chases_limit', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('chases_used', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_webhook_secret', 'users', type_='unique')
    op.drop_column('users', 'chases_used')
    op.drop_column('users', 'chases_limit')
    op.drop_column('users', 'subscription_started_at')
    op.drop_column('users', 'subscription_status')
    op.drop_column('users', 'subscription_plan')
    op.drop_column('users', 'ghl_webhook_signing_secret')
    op.drop_column('users', 'webhook_secret')
    op.drop_column('users', 'smtp_from_email')
    op.drop_column('users', 'smtp_password')
    op.drop_column('users', 'smtp_username')
    op.drop_column('users', 'smtp_port')
    op.drop_column('users', 'smtp_host')
    op.drop_column('users', 'logo_base64')
    op.drop_column('invoice', 'voice_call_count')
    op.drop_column('invoice', 'sms_sent_count')
    op.drop_column('invoice', 'escalation_started_at')
    op.drop_column('invoice', 'escalation_tier')
    op.drop_column('invoice', 'payment_link')
