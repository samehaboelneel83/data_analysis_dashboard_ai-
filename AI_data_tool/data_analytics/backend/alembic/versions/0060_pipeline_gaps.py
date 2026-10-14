"""Pipeline gaps (docs/pipeline/PLAN.md, 2026-10-10): deletes reconciled on an
incremental merge, and run metrics (speed, size, slower than usual).

Revision ID: 0060_pipeline_gaps
Revises: 0059_setup_journeys
"""
from alembic import op
import sqlalchemy as sa

revision = "0060_pipeline_gaps"
down_revision = "0059_setup_journeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watermarks", sa.Column("reconcile_deletes", sa.Boolean(), nullable=False,
                                          server_default=sa.false()))
    op.add_column("refresh_runs", sa.Column("metrics", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_runs", "metrics")
    op.drop_column("watermarks", "reconcile_deletes")
