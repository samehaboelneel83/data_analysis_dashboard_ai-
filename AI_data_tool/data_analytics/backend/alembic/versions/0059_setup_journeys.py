"""Guided setup: one row per person and connection (docs/guided-setup/PLAN.md, 0c).

Revision ID: 0059_setup_journeys
Revises: 0058_pipeline_followers
"""
from alembic import op
import sqlalchemy as sa

revision = "0059_setup_journeys"
down_revision = "0058_pipeline_followers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "setup_journeys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(20), nullable=False, server_default="understand"),
        sa.Column("brief", sa.JSON(), nullable=True),
        sa.Column("dataset_ids", sa.JSON(), nullable=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("proposals", sa.JSON(), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=True),
        sa.Column("designs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "data_source_id", name="uq_setup_journeys_user_source"),
    )
    op.create_index("ix_setup_journeys_org_id", "setup_journeys", ["org_id"])
    op.create_index("ix_setup_journeys_user_id", "setup_journeys", ["user_id"])
    op.create_index("ix_setup_journeys_data_source_id", "setup_journeys", ["data_source_id"])


def downgrade() -> None:
    op.drop_index("ix_setup_journeys_data_source_id", table_name="setup_journeys")
    op.drop_index("ix_setup_journeys_user_id", table_name="setup_journeys")
    op.drop_index("ix_setup_journeys_org_id", table_name="setup_journeys")
    op.drop_table("setup_journeys")
