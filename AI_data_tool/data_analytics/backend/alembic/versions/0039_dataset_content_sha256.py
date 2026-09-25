"""Duplicate uploads: `datasets.content_sha256`.

E07. The same file uploaded twice made two datasets with nothing to say they
were the same data, and a dashboard could end up on the stale copy. The hash is
of the bytes as uploaded (before a CSV is rewritten into the canonical dialect),
so the same file hashes the same however often it arrives. NULL for every
dataset that did not come from an upload, and for every pre-existing row.

Advisory only: a match is reported to the uploader, never refused -- loading
the same file again on purpose is legitimate.

The same DDL also ships as a `main.py` inline `ALTER IF NOT EXISTS`.

Revision ID: 0039_dataset_content_sha256
Revises: 0038_user_tokens_valid_after
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_dataset_content_sha256"
down_revision = "0038_user_tokens_valid_after"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.add_column(sa.Column("content_sha256", sa.String(64), nullable=True))
        batch_op.create_index("ix_datasets_content_sha256", ["content_sha256"])


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_index("ix_datasets_content_sha256")
        batch_op.drop_column("content_sha256")
