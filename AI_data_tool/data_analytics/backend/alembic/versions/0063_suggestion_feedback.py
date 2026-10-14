"""Suggestions that remember: what a person dismissed or added, per dataset
(docs/suggestions/PLAN.md, phase 4).

Revision ID: 0063_suggestion_feedback
Revises: 0062_meaning_facts
"""
from alembic import op
import sqlalchemy as sa

revision = "0063_suggestion_feedback"
down_revision = "0062_meaning_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suggestion_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signature", sa.String(600), nullable=False),
        sa.Column("widget_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "dataset_id", "signature", name="uq_suggestion_feedback_sig"),
    )
    op.create_index("ix_suggestion_feedback_org_id", "suggestion_feedback", ["org_id"])
    op.create_index("ix_suggestion_feedback_user_id", "suggestion_feedback", ["user_id"])
    op.create_index("ix_suggestion_feedback_dataset_id", "suggestion_feedback", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_suggestion_feedback_dataset_id", table_name="suggestion_feedback")
    op.drop_index("ix_suggestion_feedback_user_id", table_name="suggestion_feedback")
    op.drop_index("ix_suggestion_feedback_org_id", table_name="suggestion_feedback")
    op.drop_table("suggestion_feedback")
