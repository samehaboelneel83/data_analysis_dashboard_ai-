"""A background image on a report page.

`create_all` never ALTERs a table that already exists, so a column added to the
model reaches fresh databases only. Nullable, because a page without a backdrop
is the norm and NULL is what "no image" means here.

Revision ID: 0026_page_background
Revises: 0025_data_view_default
"""
import sqlalchemy as sa
from alembic import op

revision = "0026_page_background"
down_revision = "0025_data_view_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_pages",
                  sa.Column("background_url", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("report_pages", "background_url")
