"""The org's optional publish gate on open review errors (MASTER_PLAN Phase 7.4).

Revision ID: 0037_org_review_settings
Revises: 0036_org_map_settings
"""
import sqlalchemy as sa
from alembic import op

revision = "0037_org_review_settings"
down_revision = "0036_org_map_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_review_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, unique=True, index=True),
        sa.Column("publish_gate", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("org_review_settings")
