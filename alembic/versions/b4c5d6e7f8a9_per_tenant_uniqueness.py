"""per-tenant uniqueness for debtor.email and invoice.invoice_number

debtor.email and invoice.invoice_number were globally unique across all
customers, not per-customer. Any second real customer starting their
invoice numbering at "INV-001" (which almost everyone does) would be
blocked outright the moment another customer already had that number,
and two customers couldn't each have their own debtor record for the
same email address (e.g. two agencies both billing the same client).

This adds a user_id column directly on invoice (denormalized from
debtor.user_id, backfilled below) and replaces both global unique
constraints with composite (user_id, <field>) ones.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-05 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add invoice.user_id as nullable first so the backfill can run.
    op.add_column('invoice', sa.Column('user_id', sa.String(), nullable=True))

    # 2. Backfill from debtor.user_id for every existing invoice.
    op.execute("""
        UPDATE invoice
        SET user_id = debtor.user_id
        FROM debtor
        WHERE invoice.debtor_id = debtor.id
    """)

    # 3. Now that every row has a value, enforce NOT NULL + FK.
    op.alter_column('invoice', 'user_id', nullable=False)
    op.create_foreign_key('fk_invoice_user_id_users', 'invoice', 'users', ['user_id'], ['id'])

    # 4. Drop the old global unique constraints.
    op.drop_constraint('debtor_email_key', 'debtor', type_='unique')
    op.drop_constraint('invoice_invoice_number_key', 'invoice', type_='unique')

    # 5. Add the new per-tenant composite unique constraints.
    op.create_unique_constraint('uq_debtor_user_id_email', 'debtor', ['user_id', 'email'])
    op.create_unique_constraint('uq_invoice_user_id_invoice_number', 'invoice', ['user_id', 'invoice_number'])


def downgrade() -> None:
    op.drop_constraint('uq_invoice_user_id_invoice_number', 'invoice', type_='unique')
    op.drop_constraint('uq_debtor_user_id_email', 'debtor', type_='unique')
    op.create_unique_constraint('invoice_invoice_number_key', 'invoice', ['invoice_number'])
    op.create_unique_constraint('debtor_email_key', 'debtor', ['email'])
    op.drop_constraint('fk_invoice_user_id_users', 'invoice', type_='foreignkey')
    op.drop_column('invoice', 'user_id')
