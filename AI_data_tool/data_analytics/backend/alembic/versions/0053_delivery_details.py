"""What a delivery row is about: subject, recipients, file name.

HR evaluation (2026-10-01), item 5.18: the Deliveries log showed "—" for
every alert row and never said who a send went to or what it attached.

Revision ID: 0053_delivery_details
Revises: 0052_dataflow_snapshot
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_delivery_details"
down_revision = "0052_dataflow_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("subject", sa.String(255), nullable=True))
    op.add_column("deliveries", sa.Column("recipients", sa.Text(), nullable=True))
    op.add_column("deliveries", sa.Column("file_name", sa.String(255), nullable=True))


def downgrade() -> None:
    for c in ("file_name", "recipients", "subject"):
        op.drop_column("deliveries", c)
