"""A sensitivity label on a connection: `data_sources.sensitivity`.

HR evaluation (2026-10-01), item 2.2: a dataset imported from the HR database
was Unlabelled while the live dataset over the same salaries was Confidential.
The connection's label is now a floor for every dataset read from it.

Revision ID: 0048_source_sensitivity
Revises: 0047_glossary_rules
"""
from alembic import op
import sqlalchemy as sa

revision = "0048_source_sensitivity"
down_revision = "0047_glossary_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_sources", sa.Column("sensitivity", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("data_sources", "sensitivity")
