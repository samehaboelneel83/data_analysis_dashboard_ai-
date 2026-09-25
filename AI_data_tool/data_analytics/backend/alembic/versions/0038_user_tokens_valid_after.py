"""Session revocation: login tokens issued before this instant are refused.

A login JWT lives 7 days and nothing could end it early except deactivating the
user. Resetting a password left every token minted with the OLD password
working -- the one moment a revocation is certainly wanted. NULL = no cut-off,
which is every existing user, so nothing changes until a password is reset.

Revision ID: 0038_user_tokens_valid_after
Revises: 0037_org_review_settings
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_user_tokens_valid_after"
down_revision = "0037_org_review_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("tokens_valid_after")
