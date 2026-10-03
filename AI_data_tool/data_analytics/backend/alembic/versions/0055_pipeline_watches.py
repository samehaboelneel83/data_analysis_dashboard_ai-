"""Pipeline watches: who hears about a refresh failure, and the freshness target.

Pipeline plan, phase 2 (2026-10-03).

Revision ID: 0055_pipeline_watches
Revises: 0054_refresh_runs
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_pipeline_watches"
down_revision = "0054_refresh_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_watches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("freshness_hours", sa.Integer(), nullable=True),
        sa.Column("recipients", sa.JSON(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("state_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("kind", "item_id", name="uq_pipeline_watch_item"),
    )
    op.create_index("ix_pipeline_watches_org_id", "pipeline_watches", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_watches_org_id", table_name="pipeline_watches")
    op.drop_table("pipeline_watches")
