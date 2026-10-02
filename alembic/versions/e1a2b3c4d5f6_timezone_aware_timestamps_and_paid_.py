"""timezone-aware timestamps, add voice to Channel enum

Several TIMESTAMP columns were naive (no timezone), but application code
compares them against datetime.now(timezone.utc) (aware). On Postgres this
raises "can't subtract offset-naive and offset-aware datetimes" -- silently
caught and logged per-step in the daily sweep (src/scheduler.py), meaning
SMS/voice escalation has been crashing on every overdue invoice older than
one day and never actually sending. SQLite (used only in tests/local dev)
doesn't enforce timezone-awareness the same way, which is how this went
unnoticed.

Also adds 'voice' to the Channel enum (reminder_log.channel) -- it was
missing, even though voice calls are a real escalation tier.

Revision ID: e1a2b3c4d5f6
Revises: c5c1d8c4b2bf
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5f6'
down_revision: Union[str, Sequence[str], None] = 'c5c1d8c4b2bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Columns to convert, as (table, column). Existing naive values are assumed
# to already be UTC (every datetime.now() call in the app code uses
# timezone.utc), so Postgres's USING clause just attaches that offset
# rather than shifting the stored instant.
TZ_COLUMNS = [
    ("invoice", "last_reminder_sent"),
    ("invoice", "escalation_started_at"),
    ("document_request", "uploaded_at"),
    ("document_request", "last_reminder_sent"),
    ("document_request", "escalation_started_at"),
    ("document_request", "created_at"),
    ("pending_subscriptions", "created_at"),
    ("reminder_log", "sent_at"),
    ("users", "subscription_started_at"),
]


def upgrade() -> None:
    for table, column in TZ_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE TIMESTAMP WITH TIME ZONE USING "{column}" AT TIME ZONE \'UTC\''
        )

    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on
    # Postgres (even on versions where it's otherwise allowed, Alembic's
    # default transactional DDL wraps the whole migration in one). Commit
    # what's been done so far and run this statement on its own connection
    # outside any open transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE channel ADD VALUE IF NOT EXISTS 'voice'")


def downgrade() -> None:
    # Postgres doesn't support removing an enum value; downgrade leaves
    # 'voice' in place (a harmless superset) and only reverts the
    # timestamp columns.
    for table, column in TZ_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE TIMESTAMP WITHOUT TIME ZONE USING "{column}" AT TIME ZONE \'UTC\''
        )
