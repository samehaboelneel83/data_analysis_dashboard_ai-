"""The migration inventory: `migration_items` (E17).

Moving off SAS is a list of things (reports, programs, stored processes,
jobs) each of which is either replaced by a Datalytics report, checked
against the old output and signed off by its owner, or retired. Until now
that list lived in a spreadsheet beside the app; reconciliation results were
audited but attached to nothing. `migration_items` is that list, with the
evidence and the sign-off on the row.

A new table: create_all also provisions it, so there is no inline ALTER.

Revision ID: 0045_migration_items
Revises: 0044_fiscal_year
"""
from alembic import op
import sqlalchemy as sa

revision = "0045_migration_items"
down_revision = "0044_fiscal_year"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "migration_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False, server_default="SAS"),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False, server_default="report"),
        sa.Column("source_path", sa.String(1000), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False, server_default="migrate"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("features", sa.JSON(), nullable=True),
        sa.Column("reconciles", sa.JSON(), nullable=True),
        sa.Column("sign_off", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_migration_items_org_id", "migration_items", ["org_id"])
    op.create_index("ix_migration_items_owner_id", "migration_items", ["owner_id"])
    op.create_index("ix_migration_items_report_id", "migration_items", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_migration_items_report_id", table_name="migration_items")
    op.drop_index("ix_migration_items_owner_id", table_name="migration_items")
    op.drop_index("ix_migration_items_org_id", table_name="migration_items")
    op.drop_table("migration_items")
