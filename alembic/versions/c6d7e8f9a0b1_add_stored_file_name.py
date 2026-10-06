"""add stored_file_name to document_request

Document upload (H5) previously just marked a request "submitted" without
actually accepting a file. Now a real multipart upload is stored on disk
and this column tracks the generated on-disk filename, kept separate from
uploaded_file_name (the original, user-supplied filename shown in the UI)
so a crafted filename from a client can never influence the actual
storage path.

On production, document_request already existed at this point (created
by src/app.py's old, unguarded create_all() call, before a225ef8d6e70/M1
made that dev-only and gave it a real migration far later in this
chain). A genuinely fresh database -- CI's, or a disaster-recovery
rebuild per docs/runbook.md -- runs every migration in order from
scratch and hits this one BEFORE a225ef8d6e70 creates the table, so the
unconditional ADD COLUMN below fails with UndefinedTable. Guarded with
a to_regclass existence check so this is a no-op on a fresh DB (where
a225ef8d6e70 creates document_request with stored_file_name already
included), while still adding the column on production (where the
table already exists here).

Revision ID: c6d7e8f9a0b1
Revises: b4c5d6e7f8a9
Create Date: 2026-10-05 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF to_regclass('public.document_request') IS NOT NULL THEN "
        "ALTER TABLE document_request ADD COLUMN IF NOT EXISTS stored_file_name VARCHAR; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF to_regclass('public.document_request') IS NOT NULL THEN "
        "ALTER TABLE document_request DROP COLUMN IF EXISTS stored_file_name; "
        "END IF; END $$;"
    )
