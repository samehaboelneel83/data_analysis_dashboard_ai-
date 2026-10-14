""""Allow AI" per dataset, so an uploaded file has the switch a connection has
(docs/discovery/PLAN.md, phase 0).

Revision ID: 0064_dataset_allow_ai
Revises: 0063_suggestion_feedback
"""
from alembic import op
import sqlalchemy as sa

revision = "0064_dataset_allow_ai"
down_revision = "0063_suggestion_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("allow_ai", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("datasets", "allow_ai")
