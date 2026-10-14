"""Change alerts and webhook delivery on data alerts.

HR evaluation (2026-10-01), items 3.1 and 4.8: "tell me when leavers jump by
20% against last month" could not be said, and alerts reached e-mail only.

Revision ID: 0050_alert_changes
Revises: 0049_dataset_group_shares
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_alert_changes"
down_revision = "0049_dataset_group_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_alerts", sa.Column("last_value", sa.Float(), nullable=True))
    op.add_column("data_alerts", sa.Column("change_pct", sa.Float(), nullable=True))
    op.add_column("data_alerts", sa.Column("change_direction", sa.String(5), nullable=True))
    op.add_column("data_alerts", sa.Column("webhook_url", sa.String(500), nullable=True))


def downgrade() -> None:
    for c in ("webhook_url", "change_direction", "change_pct", "last_value"):
        op.drop_column("data_alerts", c)
