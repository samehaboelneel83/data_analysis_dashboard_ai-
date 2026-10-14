"""What is remembered about a dataset, in a table no payload returns
(docs/discovery/PLAN.md, phase 1; services/discovery/profile.py).

Revision ID: 0065_dataset_profiles
Revises: 0064_dataset_allow_ai
"""
from alembic import op
import sqlalchemy as sa

revision = "0065_dataset_profiles"
down_revision = "0064_dataset_allow_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_profiles",
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.String(120), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("dataset_profiles")
