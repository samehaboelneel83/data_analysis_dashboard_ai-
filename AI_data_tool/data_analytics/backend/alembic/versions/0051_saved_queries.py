"""Saved queries and run history for a connection's Browse dialog.

HR evaluation (2026-10-01), item 4.2: the workforce SQL had to be retyped on
every visit. One table holds both named queries and the last runs (name NULL).

Revision ID: 0051_saved_queries
Revises: 0050_alert_changes
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_saved_queries"
down_revision = "0050_alert_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("org_id", "user_id", "data_source_id"):
        op.create_index(f"ix_saved_queries_{col}", "saved_queries", [col])


def downgrade() -> None:
    for col in ("org_id", "user_id", "data_source_id"):
        op.drop_index(f"ix_saved_queries_{col}", table_name="saved_queries")
    op.drop_table("saved_queries")
