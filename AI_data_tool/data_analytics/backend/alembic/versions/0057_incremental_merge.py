"""Incremental merge by key, and items that run after their source.

Pipeline plan, phase 4 (2026-10-03): watermarks gain a key column, a look-back
window, a periodic full reload and the time of the last full load; pipeline
watches gain run-after-source and its pending flag.

Revision ID: 0057_incremental_merge
Revises: 0056_data_checks
"""
from alembic import op
import sqlalchemy as sa

revision = "0057_incremental_merge"
down_revision = "0056_data_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watermarks", sa.Column("key_column", sa.String(255), nullable=True))
    op.add_column("watermarks", sa.Column("lookback_hours", sa.Integer(), nullable=True))
    op.add_column("watermarks", sa.Column("full_reload_days", sa.Integer(), nullable=True))
    op.add_column("watermarks", sa.Column("last_full_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pipeline_watches", sa.Column("run_after_source", sa.Boolean(), nullable=False,
                                                server_default=sa.false()))
    op.add_column("pipeline_watches", sa.Column("trigger_pending", sa.Boolean(), nullable=False,
                                                server_default=sa.false()))


def downgrade() -> None:
    for c in ("trigger_pending", "run_after_source"):
        op.drop_column("pipeline_watches", c)
    for c in ("last_full_at", "full_reload_days", "lookback_hours", "key_column"):
        op.drop_column("watermarks", c)
