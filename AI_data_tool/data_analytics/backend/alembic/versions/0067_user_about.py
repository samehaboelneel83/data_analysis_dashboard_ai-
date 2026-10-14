"""What a person wrote about themselves, for the designers that tailor a
dashboard to them (services/ai_context.py).

Revision ID: 0067_user_about
Revises: 0066_dashboard_templates
"""
from alembic import op
import sqlalchemy as sa

revision = "0067_user_about"
down_revision = "0066_dashboard_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("about", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "about")
