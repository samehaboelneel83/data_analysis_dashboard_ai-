"""Which columns are OUTCOMES worth explaining, recorded on the catalog.

WHY THIS EXISTS
---------------
`key_influencers`, `decision_tree` and `automated_prediction` all answer "what
drives X" and all need somebody to say what X is. Until now the only way to
choose was a heuristic over flag-shaped columns -- and a heuristic cannot know
that `readmitted_30d` is the question this hospital actually cares about while
`is_active` is a housekeeping bit nobody has ever asked about.

So a person says it once, and the platform stops guessing.

WHY ON THE SOURCE COLUMN
------------------------
Same reason descriptions live here (see 0033): a column that came from a
connected table means the same thing in every dataset built from it. Recording
`patient_outcome` as a target on the catalog makes it a target for every dataset
anyone ever imports from that table, and `services/knowledge.py` resolves it
through the same provenance ladder. A per-dataset override still exists in
`datasets.column_meta` for the case where one dataset genuinely has a different
question in mind.

Higher runs first. NULL means "not a target", which is the overwhelming majority
of columns and the right default -- a platform that treats every column as an
outcome worth explaining produces a great deal of confident noise.

Revision ID: 0034_source_column_target
Revises: 0033_dataset_column_provenance
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_source_column_target"
down_revision = "0033_dataset_column_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table for the same reason as 0033 and 0029: SQLite executes
    # `alembic upgrade head` in tests/test_alembic_migrations.py and cannot ADD
    # COLUMN outside its copy-and-move batch mode for several alteration kinds.
    # No foreign key here, so no constraint name is needed.
    with op.batch_alter_table("source_columns") as batch_op:
        batch_op.add_column(sa.Column("target_candidate_priority", sa.Integer(),
                                      nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("source_columns") as batch_op:
        batch_op.drop_column("target_candidate_priority")
