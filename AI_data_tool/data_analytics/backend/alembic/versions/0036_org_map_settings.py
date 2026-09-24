"""The org's basemap tile server (MASTER_PLAN Phase 4 item 4).

Revision ID: 0036_org_map_settings
Revises: 0035_page_layout_mode
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_org_map_settings"
down_revision = "0035_page_layout_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_map_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, unique=True, index=True),
        sa.Column("tile_url", sa.String(length=500), nullable=True),
        sa.Column("attribution", sa.String(length=300), nullable=True),
        sa.Column("contrast_tile_url", sa.String(length=500), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("org_map_settings")
