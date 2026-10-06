"""add email verification fields to users

Closes an account-takeover window: registration never confirmed the
registrant actually controls the email address they signed up with, so
anyone who knew an ADMIN_EMAILS address, or a customer's already-paid
email (parked as a PendingSubscription before that customer registers),
could register it themselves and steal that access.

Existing users are backfilled as already verified -- they've been
actively using the product, which is a stronger signal than a fresh
email click, and retroactively locking out real customers over this
would be a worse outcome than the gap it closes.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('email_verification_token', sa.String(), nullable=True))
    op.execute("UPDATE users SET email_verified = true")


def downgrade() -> None:
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'email_verified')
