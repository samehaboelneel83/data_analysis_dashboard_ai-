"""Refresh run history: one row per dataset refresh or dataflow run.

Pipeline plan, phase 1 (2026-10-03): a scheduled refresh that failed was only
logged, and nothing kept a history of runs, durations or row counts.

Revision ID: 0054_refresh_runs
Revises: 0053_delivery_details
"""
from alembic import op
import sqlalchemy as sa

revision = "0054_refresh_runs"
down_revision = "0053_delivery_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
    )
    for col in ("org_id", "item_id", "started_at"):
        op.create_index(f"ix_refresh_runs_{col}", "refresh_runs", [col])


def downgrade() -> None:
    for col in ("org_id", "item_id", "started_at"):
        op.drop_index(f"ix_refresh_runs_{col}", table_name="refresh_runs")
    op.drop_table("refresh_runs")
