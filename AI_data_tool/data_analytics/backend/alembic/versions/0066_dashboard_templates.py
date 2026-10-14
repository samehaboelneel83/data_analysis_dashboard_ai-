"""Dashboard templates, their versions and favourites; a dashboard's style
(docs/templates/PLAN.md; services/dashboard_templates).

Revision ID: 0066_dashboard_templates
Revises: 0065_dataset_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = "0066_dashboard_templates"
down_revision = "0065_dataset_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboard_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dashboard_templates_org_id", "dashboard_templates", ["org_id"])
    op.create_index("ix_dashboard_templates_created_by", "dashboard_templates", ["created_by"])
    op.create_table(
        "dashboard_template_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("dashboard_templates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dashboard_template_versions_template_id", "dashboard_template_versions", ["template_id"])
    op.create_table(
        "template_favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_ref", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "template_ref", name="uq_template_favorite"),
    )
    op.create_index("ix_template_favorites_user_id", "template_favorites", ["user_id"])
    op.add_column("reports", sa.Column("style", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "style")
    op.drop_index("ix_template_favorites_user_id", table_name="template_favorites")
    op.drop_table("template_favorites")
    op.drop_index("ix_dashboard_template_versions_template_id", table_name="dashboard_template_versions")
    op.drop_table("dashboard_template_versions")
    op.drop_index("ix_dashboard_templates_created_by", table_name="dashboard_templates")
    op.drop_index("ix_dashboard_templates_org_id", table_name="dashboard_templates")
    op.drop_table("dashboard_templates")
