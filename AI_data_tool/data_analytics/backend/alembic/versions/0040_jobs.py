"""Durable jobs: the `jobs` table.

E07 / E12. Long work -- a database import that can run for the whole statement
timeout -- ran inside the HTTP request: closing the tab lost the outcome, a
restart lost the work, and there was nothing to cancel or retry. A job row is
the plan's `Job` contract (§8): state, owner/org, immutable inputs, idempotency
key, progress, attempt/lease, cancellation, output refs and a sanitized error.

A brand-new table, so `create_all` also provisions it on a running install; no
inline ALTER is needed in `main.py`.

Revision ID: 0040_jobs
Revises: 0039_dataset_content_sha256
"""
from alembic import op
import sqlalchemy as sa

revision = "0040_jobs"
down_revision = "0039_dataset_content_sha256"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retry_of", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_job_org_idempotency_key"),
    )
    op.create_index("ix_jobs_org_id", "jobs", ["org_id"])
    op.create_index("ix_jobs_created_by", "jobs", ["created_by"])
    op.create_index("ix_jobs_state", "jobs", ["state"])
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    op.drop_index("ix_jobs_state", table_name="jobs")
    op.drop_index("ix_jobs_created_by", table_name="jobs")
    op.drop_index("ix_jobs_org_id", table_name="jobs")
    op.drop_table("jobs")
