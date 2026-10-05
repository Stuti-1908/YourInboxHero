"""add stored_file_name to document_request

Document upload (H5) previously just marked a request "submitted" without
actually accepting a file. Now a real multipart upload is stored on disk
and this column tracks the generated on-disk filename, kept separate from
uploaded_file_name (the original, user-supplied filename shown in the UI)
so a crafted filename from a client can never influence the actual
storage path.

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
    op.add_column('document_request', sa.Column('stored_file_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('document_request', 'stored_file_name')
