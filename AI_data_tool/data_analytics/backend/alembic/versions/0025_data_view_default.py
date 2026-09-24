"""A data view an admin can mark as the default for new datasets.

`create_all` never ALTERs a table that already exists, so a column added to the
model reaches fresh databases only -- every already-deployed one would be
missing it and every query naming it would fail. That is what this revision is
for.

Nullable=False with a server default, so existing rows become False rather than
NULL: the application reads this as a plain boolean and a NULL there would make
"is this the default" a three-way question.

Revision ID: 0025_data_view_default
Revises: 0024_boundary_sets
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_data_view_default"
down_revision = "0024_boundary_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_views",
        sa.Column("is_default", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("data_views", "is_default")
