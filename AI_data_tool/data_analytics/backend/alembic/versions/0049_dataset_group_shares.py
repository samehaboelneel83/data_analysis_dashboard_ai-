"""Dataset shares by role / org unit, and a level on every share.

HR evaluation (2026-10-01), item 2.5: a dataset could only be shared one user
at a time, and every share could re-model the data. `dataset_shares.level`
('view' | 'edit', existing rows 'edit' -- what they meant until now) and a new
`dataset_group_shares` table (role or org unit).

Revision ID: 0049_dataset_group_shares
Revises: 0048_source_sensitivity
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_dataset_group_shares"
down_revision = "0048_source_sensitivity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_shares", sa.Column("level", sa.String(10), nullable=False,
                                              server_default="edit"))
    op.create_table(
        "dataset_group_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=True),
        sa.Column("org_unit_id", sa.Integer(), sa.ForeignKey("org_units.id", ondelete="CASCADE"), nullable=True),
        sa.Column("level", sa.String(10), nullable=False, server_default="view"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dataset_group_shares_org_id", "dataset_group_shares", ["org_id"])
    op.create_index("ix_dataset_group_shares_dataset_id", "dataset_group_shares", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_dataset_group_shares_dataset_id", table_name="dataset_group_shares")
    op.drop_index("ix_dataset_group_shares_org_id", table_name="dataset_group_shares")
    op.drop_table("dataset_group_shares")
    op.drop_column("dataset_shares", "level")
