"""Platform settings changed from the app: `app_settings`.

Every install-wide setting (LLM endpoint, mail server, limits, timeouts) could
only be changed by editing environment variables and restarting. A row here
overrides one setting's environment value; deleting the row returns it to the
environment. See services/app_settings.py.

A new table: create_all also provisions it, so there is no inline ALTER.

Revision ID: 0046_app_settings
Revises: 0045_migration_items
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_app_settings"
down_revision = "0045_migration_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
