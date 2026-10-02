"""Snapshot dataflows: append a row per period instead of replacing.

HR evaluation (2026-10-01), item 4.6: a live source only shows today, so a
month-by-month headcount trend needed SQL. `dataflows.snapshot` holds the spec.

Revision ID: 0052_dataflow_snapshot
Revises: 0051_saved_queries
"""
from alembic import op
import sqlalchemy as sa

revision = "0052_dataflow_snapshot"
down_revision = "0051_saved_queries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataflows", sa.Column("snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("dataflows", "snapshot")
