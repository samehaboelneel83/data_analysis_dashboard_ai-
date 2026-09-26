"""AI budgets: `quotas.max_ai_tokens_per_day/month` and the `ai_usage` table (E11).

An org's use of the model was bounded only by how many questions it asked a
day. A question costs anything from a few hundred tokens to tens of thousands
(a long history, a wide catalog, retries), and suggestions, insight
narratives and connection descriptions used the model with no bound at all.
`ai_usage` records what each unit of work spent; the two new limits cap an
org's tokens per UTC day and per calendar month. NULL, the default, is
unlimited, so nothing changes for an org until a platform admin sets one.

`ai_usage` is a new table (create_all also provisions it); the two columns
also ship as `main.py` inline `ALTER ... IF NOT EXISTS`.

Revision ID: 0042_ai_budget
Revises: 0041_report_releases
"""
from alembic import op
import sqlalchemy as sa

revision = "0042_ai_budget"
down_revision = "0041_report_releases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quotas") as batch_op:
        batch_op.add_column(sa.Column("max_ai_tokens_per_day", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("max_ai_tokens_per_month", sa.Integer(), nullable=True))
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refused", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_usage_org_id", "ai_usage", ["org_id"])
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_created_at", table_name="ai_usage")
    op.drop_index("ix_ai_usage_org_id", table_name="ai_usage")
    op.drop_table("ai_usage")
    with op.batch_alter_table("quotas") as batch_op:
        batch_op.drop_column("max_ai_tokens_per_month")
        batch_op.drop_column("max_ai_tokens_per_day")
