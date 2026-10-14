"""Guided setup: several flows (steps 2-4) per person and connection
(docs/guided-setup/PLAN_V2.md, part 1).

A journey's own step 2-4 columns stay where they are: the first visit after
this revision copies them into the journey's first flow
(routers/guided_setup.py `_adopt_legacy`), so nothing in progress is lost.

Revision ID: 0061_setup_flows
Revises: 0060_pipeline_gaps
"""
from alembic import op
import sqlalchemy as sa

revision = "0061_setup_flows"
down_revision = "0060_pipeline_gaps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "setup_flows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("journey_id", sa.Integer(), sa.ForeignKey("setup_journeys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("step", sa.String(20), nullable=False, server_default="data"),
        sa.Column("brief", sa.JSON(), nullable=True),
        sa.Column("demand", sa.JSON(), nullable=True),
        sa.Column("dataset_ids", sa.JSON(), nullable=True),
        sa.Column("created_ids", sa.JSON(), nullable=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("proposals", sa.JSON(), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=True),
        sa.Column("cleaning", sa.JSON(), nullable=True),
        sa.Column("designs", sa.JSON(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_setup_flows_org_id", "setup_flows", ["org_id"])
    op.create_index("ix_setup_flows_user_id", "setup_flows", ["user_id"])
    op.create_index("ix_setup_flows_journey_id", "setup_flows", ["journey_id"])
    op.create_index("ix_setup_flows_data_source_id", "setup_flows", ["data_source_id"])


def downgrade() -> None:
    op.drop_index("ix_setup_flows_data_source_id", table_name="setup_flows")
    op.drop_index("ix_setup_flows_journey_id", table_name="setup_flows")
    op.drop_index("ix_setup_flows_user_id", table_name="setup_flows")
    op.drop_index("ix_setup_flows_org_id", table_name="setup_flows")
    op.drop_table("setup_flows")
