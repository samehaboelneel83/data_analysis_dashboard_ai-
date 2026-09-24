"""Report.origin: who made this report.

Recents could not tell a finished automated report from a draft somebody
started and walked away from -- both are just rows with a name and a date. The
automation chain's step 6 now marks what it composes, and step 7 and the Home
page both read that difference.

A string rather than a boolean: the next origin (a template, an import) is a
value in this column rather than a second one beside it.

Backfill is `user`, which is true of every report that existed before this
column did -- the automation chain had never composed one.

Revision ID: 0031_report_origin
Revises: 0030_automation_runs
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_report_origin"
down_revision = "0030_automation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("origin", sa.String(length=20), nullable=False,
                  server_default="user"),
    )
    # Indexed because the surfaces that read it FILTER on it -- Recents showing
    # only what a person made, Home showing only what ran overnight.
    op.create_index("ix_reports_origin", "reports", ["origin"])


def downgrade() -> None:
    op.drop_index("ix_reports_origin", table_name="reports")
    op.drop_column("reports", "origin")
