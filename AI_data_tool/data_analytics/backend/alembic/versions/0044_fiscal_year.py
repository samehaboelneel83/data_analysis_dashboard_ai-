"""The org's fiscal year: `organizations.fiscal_year_start_month` (E10).

Charts can group dates by fiscal year and fiscal quarter; the month the
fiscal year starts in is the org's (Admin -> Calendar), 1 = January, which
makes the fiscal year the calendar year. Existing orgs get 1. The column also
ships as a `main.py` inline ALTER for installs provisioned by create_all.

Revision ID: 0044_fiscal_year
Revises: 0043_model_versions
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_fiscal_year"
down_revision = "0043_model_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.add_column(sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False,
                                      server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_column("fiscal_year_start_month")
