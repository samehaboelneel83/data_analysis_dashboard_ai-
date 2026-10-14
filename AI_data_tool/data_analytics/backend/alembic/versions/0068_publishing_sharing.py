"""Publishing and sharing (docs/publishing/PLAN.md): publication details and
approval on a dashboard; a grant may name a role or a team and carries an
expiry and what its holder may do; favourites.

Revision ID: 0068_publishing_sharing
Revises: 0067_user_about
"""
from alembic import op
import sqlalchemy as sa

revision = "0068_publishing_sharing"
down_revision = "0067_user_about"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("tags", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_reports_published_by"), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("viewers_may_export", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        batch_op.add_column(sa.Column("review_state", sa.String(12), nullable=False, server_default="none"))
        batch_op.add_column(sa.Column("review_revision", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("review_requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_reports_review_requested_by"), nullable=True))
        batch_op.add_column(sa.Column("review_decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_reports_review_decided_by"), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.String(500), nullable=True))
    op.create_index("ix_reports_category", "reports", ["category"])
    op.create_index("ix_reports_archived_at", "reports", ["archived_at"])
    op.create_index("ix_reports_org_published", "reports", ["org_id", "published"])

    # Batch mode: SQLite (the migration tests) cannot alter a column or add a foreign key in place.
    with op.batch_alter_table("report_user_grants") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE", name="fk_report_user_grants_role_id"), nullable=True))
        batch_op.add_column(sa.Column("org_unit_id", sa.Integer(), sa.ForeignKey("org_units.id", ondelete="CASCADE", name="fk_report_user_grants_org_unit_id"), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("can_export", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        batch_op.add_column(sa.Column("can_share", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch_op.add_column(sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_report_user_grants_created_by"), nullable=True))
    op.create_index("ix_report_user_grants_role_id", "report_user_grants", ["role_id"])
    op.create_index("ix_report_user_grants_org_unit_id", "report_user_grants", ["org_unit_id"])

    op.add_column("org_review_settings", sa.Column("require_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.create_table(
        "report_favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "report_id", name="uq_report_favorite"),
    )
    op.create_index("ix_report_favorites_user_id", "report_favorites", ["user_id"])
    op.create_index("ix_report_favorites_report_id", "report_favorites", ["report_id"])


def downgrade() -> None:
    op.drop_table("report_favorites")
    with op.batch_alter_table("org_review_settings") as batch_op:
        batch_op.drop_column("require_approval")
    # A share that names a role or a team has no person; the older shape cannot hold it.
    op.execute("DELETE FROM report_user_grants WHERE user_id IS NULL")
    for ix in ("ix_report_user_grants_org_unit_id", "ix_report_user_grants_role_id"):
        op.drop_index(ix, table_name="report_user_grants")
    with op.batch_alter_table("report_user_grants") as batch_op:
        for col in ("created_by", "can_share", "can_export", "expires_at", "org_unit_id", "role_id"):
            batch_op.drop_column(col)
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
    for ix in ("ix_reports_org_published", "ix_reports_archived_at", "ix_reports_category"):
        op.drop_index(ix, table_name="reports")
    with op.batch_alter_table("reports") as batch_op:
        for col in ("review_note", "review_decided_by", "review_requested_by", "review_revision", "review_state",
                    "viewers_may_export", "archived_at", "published_by", "published_at", "tags", "category"):
            batch_op.drop_column(col)
