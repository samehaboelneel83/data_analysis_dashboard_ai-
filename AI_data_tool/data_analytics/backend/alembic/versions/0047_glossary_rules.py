"""Business rules on glossary terms: `glossary_terms.rule`, `.always`.

HR evaluation (2026-10-01), blocker 3: Ask AI did not know the company rule
"current = to_date 9999-01-01" and answered from every historical row. A term
can now carry the rule the AI must follow, and `always` applies it to every
question on the source.

Revision ID: 0047_glossary_rules
Revises: 0046_app_settings
"""
from alembic import op
import sqlalchemy as sa

revision = "0047_glossary_rules"
down_revision = "0046_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("glossary_terms", sa.Column("rule", sa.Text(), nullable=True))
    op.add_column("glossary_terms", sa.Column("always", sa.Boolean(), nullable=False,
                                              server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("glossary_terms", "always")
    op.drop_column("glossary_terms", "rule")
