"""Packed vs free page layout, plus the last layout recipe id.

Existing pages stay NULL so the builder can auto-pack them once into Executive.
New pages are created packed/executive from the API defaults.

Revision ID: 0035_page_layout_mode
Revises: 0034_source_column_target
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_page_layout_mode"
down_revision = "0034_source_column_target"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("report_pages") as batch_op:
        batch_op.add_column(sa.Column("layout_mode", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("layout_template", sa.String(40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("report_pages") as batch_op:
        batch_op.drop_column("layout_template")
        batch_op.drop_column("layout_mode")
