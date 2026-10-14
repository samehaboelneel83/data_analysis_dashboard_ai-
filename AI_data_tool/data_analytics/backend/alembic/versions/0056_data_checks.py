"""Saved data quality checks, and each refresh run's check results.

Pipeline plan, phase 3 (2026-10-03): checks run on new data before it replaces
the old; a failing blocking check keeps yesterday's data live.

Revision ID: 0056_data_checks
Revises: 0055_pipeline_watches
"""
from alembic import op
import sqlalchemy as sa

revision = "0056_data_checks"
down_revision = "0055_pipeline_watches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("column", sa.String(255), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_data_checks_org_id", "data_checks", ["org_id"])
    op.create_index("ix_data_checks_dataset_id", "data_checks", ["dataset_id"])
    op.add_column("refresh_runs", sa.Column("checks", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_runs", "checks")
    op.drop_index("ix_data_checks_dataset_id", table_name="data_checks")
    op.drop_index("ix_data_checks_org_id", table_name="data_checks")
    op.drop_table("data_checks")
