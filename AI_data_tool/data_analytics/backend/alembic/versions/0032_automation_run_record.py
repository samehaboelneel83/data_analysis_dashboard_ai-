"""The automation run's structured record: what it produced, in typed columns.

WHY THIS EXISTS
---------------
`discard_run_artifacts` removes a run's directory the moment it reaches `done`.
So the instant a run succeeds, scan.json / propose.json / review.json are gone
-- and with them the path that produced the proposal, what the gate accepted
and rejected, and the proposals themselves. The first real run of the chain
composed a report with a meaningless lead KPI, and by the time that was noticed
the 17 proposals it was chosen from no longer existed anywhere. The gate fix
could not be verified against them.

Model output is not reproducible: same dataset, same prompt, materially
different proposals on the next run. A proposal set that is not captured is
gone for good, and it is the only material that makes a quality claim
checkable afterwards. So `raw_proposals` is stored whole -- it is a small JSON.

TYPED COLUMNS ARE THE SOURCE OF TRUTH
-------------------------------------
Every field here is something a surface has to FILTER or ORDER by: runs the
model produced, runs with the most rejections, runs waiting on a person. A
stored sentence supports none of that. `describe_run` derives the sentence from
these columns at render time; nothing parses it back.

`error` was being assigned in three places and persisted in none -- the model
had no such column, Python allowed the attribute, SQLAlchemy dropped it on
commit, and the test that checked it read the in-memory value in the same
session. Every needs_review reason and every rejection reason was lost.

Revision ID: 0032_automation_run_record
Revises: 0031_report_origin
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_automation_run_record"
down_revision = "0031_report_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── the run's result, queryable ──
    op.add_column("automation_runs", sa.Column("result_report_name", sa.String(255), nullable=True))
    op.add_column("automation_runs", sa.Column("proposal_path", sa.String(20), nullable=True))
    op.add_column("automation_runs", sa.Column("widgets_accepted", sa.Integer(), nullable=True))
    op.add_column("automation_runs", sa.Column("widgets_rejected", sa.Integer(), nullable=True))
    op.add_column("automation_runs", sa.Column("rejection_reasons", sa.JSON(), nullable=True))
    op.add_column("automation_runs", sa.Column("raw_proposals", sa.JSON(), nullable=True))
    # The column three assignments believed already existed.
    op.add_column("automation_runs", sa.Column("error", sa.Text(), nullable=True))
    # Home filters on these: "what did the model produce", "what needs a look".
    op.create_index("ix_automation_runs_proposal_path", "automation_runs", ["proposal_path"])

    # ── an analysis result knows what produced it, and with what ──
    # `AnalysisResult` stored a result and its type, and nothing else. A saved
    # regression without its predictors recorded is uninterpretable, and a
    # result with no run cannot be reached from the run that made it. Both are
    # nullable: results a person ran by hand have neither.
    #
    # batch_alter_table, because two of these carry a foreign key: SQLite
    # cannot ALTER a constraint in place (the fresh-database tests run on
    # SQLite), so alembic rebuilds the table there; on PostgreSQL the same
    # call is a plain ALTER. 0030 created its tables outright and needed
    # none of this; 0031 added a column with no constraint.
    # The keys are NAMED: batch mode has to spell the rebuilt table out, and
    # this metadata carries no naming convention to invent a name from.
    with op.batch_alter_table("analysis_results") as batch:
        batch.add_column(sa.Column("run_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("params", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_analysis_results_run_id_automation_runs", "automation_runs",
            ["run_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key(
            "fk_analysis_results_created_by_users", "users",
            ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_analysis_results_run_id", "analysis_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_results_run_id", table_name="analysis_results")
    # SQLite also refuses to DROP a column that is part of a foreign key;
    # batch mode rebuilds the table without them.
    with op.batch_alter_table("analysis_results") as batch:
        batch.drop_constraint("fk_analysis_results_created_by_users", type_="foreignkey")
        batch.drop_constraint("fk_analysis_results_run_id_automation_runs", type_="foreignkey")
        batch.drop_column("created_by")
        batch.drop_column("params")
        batch.drop_column("run_id")
    op.drop_index("ix_automation_runs_proposal_path", table_name="automation_runs")
    for col in ("error", "raw_proposals", "rejection_reasons", "widgets_rejected",
                "widgets_accepted", "proposal_path", "result_report_name"):
        op.drop_column("automation_runs", col)
