"""Meaning map: what a connection's data means -- grains, bases, outcomes,
number kinds (docs/meaning-map/PLAN.md).

Revision ID: 0062_meaning_facts
Revises: 0061_setup_flows
"""
from alembic import op
import sqlalchemy as sa

revision = "0062_meaning_facts"
down_revision = "0061_setup_flows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meaning_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(600), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="measured"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("data_source_id", "kind", "subject", name="uq_meaning_facts_subject"),
    )
    op.create_index("ix_meaning_facts_org_id", "meaning_facts", ["org_id"])
    op.create_index("ix_meaning_facts_data_source_id", "meaning_facts", ["data_source_id"])


def downgrade() -> None:
    op.drop_index("ix_meaning_facts_data_source_id", table_name="meaning_facts")
    op.drop_index("ix_meaning_facts_org_id", table_name="meaning_facts")
    op.drop_table("meaning_facts")
