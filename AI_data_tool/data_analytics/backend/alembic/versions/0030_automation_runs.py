"""Power Pi automation runs: an orchestrated profile-to-dashboard chain.

Revision ID: 0030_automation_runs
Revises: 0029_aggregate_datasets
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_automation_runs"
down_revision = "0029_aggregate_datasets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Two NEW tables, so no batch_alter_table: that exists for SQLite's
    # inability to ALTER an existing table (see 0029), and CREATE TABLE has
    # no such limitation. Every foreign key is NAMED so downgrade can drop
    # them on any dialect, same convention as 0029.
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), nullable=False),
        # Nullable + SET NULL, matching reports.created_by: a person's work
        # outlives their account. The runner refuses to execute a step whose
        # creator cannot be resolved -- RLS is per-user, and a headless step
        # would compose a dashboard from rows the creator may not see.
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(length=30), nullable=False,
                  server_default="manual"),
        sa.Column("subject_type", sa.String(length=30), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("result_report_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"],
                                ondelete="CASCADE",
                                name="fk_automation_runs_org_id_organizations"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"],
                                ondelete="SET NULL",
                                name="fk_automation_runs_created_by_users"),
        sa.ForeignKeyConstraint(["result_report_id"], ["reports.id"],
                                ondelete="SET NULL",
                                name="fk_automation_runs_result_report_id_reports"),
    )
    op.create_index("ix_automation_runs_org_id", "automation_runs", ["org_id"])
    op.create_index("ix_automation_runs_created_by", "automation_runs", ["created_by"])
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"])
    op.create_index("ix_automation_runs_created_at", "automation_runs", ["created_at"])
    op.create_index("ix_automation_runs_result_report_id", "automation_runs",
                    ["result_report_id"])

    op.create_table(
        "automation_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        # "order" is a reserved word on every dialect this ships on;
        # SQLAlchemy and Alembic quote it, and the chain's vocabulary is
        # spelled the way the design states it.
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        # Presence of output_ref -- not status -- is what marks a step done.
        # A worker killed between writing the ref and committing the status
        # must not redo the work on resume.
        sa.Column("output_ref", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["automation_runs.id"],
                                ondelete="CASCADE",
                                name="fk_automation_steps_run_id_automation_runs"),
        # Without this, creating a run twice silently doubles its steps and
        # "skip the step that already has an output_ref" has no single row to
        # key on.
        sa.UniqueConstraint("run_id", "name", name="uq_automation_step_run_name"),
    )
    op.create_index("ix_automation_steps_run_id", "automation_steps", ["run_id"])
    op.create_index("ix_automation_steps_status", "automation_steps", ["status"])
    op.create_index("ix_automation_steps_next_attempt_at", "automation_steps",
                    ["next_attempt_at"])


def downgrade() -> None:
    # Children first: automation_steps.run_id references automation_runs.
    op.drop_index("ix_automation_steps_next_attempt_at", "automation_steps")
    op.drop_index("ix_automation_steps_status", "automation_steps")
    op.drop_index("ix_automation_steps_run_id", "automation_steps")
    op.drop_table("automation_steps")

    op.drop_index("ix_automation_runs_result_report_id", "automation_runs")
    op.drop_index("ix_automation_runs_created_at", "automation_runs")
    op.drop_index("ix_automation_runs_status", "automation_runs")
    op.drop_index("ix_automation_runs_created_by", "automation_runs")
    op.drop_index("ix_automation_runs_org_id", "automation_runs")
    op.drop_table("automation_runs")
