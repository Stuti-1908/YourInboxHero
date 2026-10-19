"""reminder_log supports document requests too

ReminderLog was invoice-only (invoice_id NOT NULL FK) -- SMS and voice
sends for invoices, and ALL sends (email/SMS/voice) for document
requests, never got logged, so there was no audit trail for them
despite the History page (and the landing page's "every send is
logged" promise) implying one exists. Relaxes invoice_id to nullable
and adds document_request_id, with a check constraint enforcing exactly
one of the two is set on every row.

Revision ID: 1341e72d2578
Revises: 05278e4c6725
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1341e72d2578'
down_revision: Union[str, Sequence[str], None] = '05278e4c6725'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('reminder_log', 'invoice_id', nullable=True)
    op.add_column('reminder_log', sa.Column('document_request_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_reminder_log_document_request_id',
        'reminder_log', 'document_request',
        ['document_request_id'], ['id'],
    )
    op.create_check_constraint(
        'ck_reminder_log_exactly_one_target',
        'reminder_log',
        '(invoice_id IS NOT NULL AND document_request_id IS NULL) OR '
        '(invoice_id IS NULL AND document_request_id IS NOT NULL)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_reminder_log_exactly_one_target', 'reminder_log', type_='check')
    op.drop_constraint('fk_reminder_log_document_request_id', 'reminder_log', type_='foreignkey')
    op.drop_column('reminder_log', 'document_request_id')
    op.alter_column('reminder_log', 'invoice_id', nullable=False)
