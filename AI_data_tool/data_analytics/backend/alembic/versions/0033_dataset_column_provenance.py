"""Where a dataset column came from, so its MEANING can be found again.

WHY THIS EXISTS
---------------
Two pipelines write what the platform knows about data, and neither writes to
the other's store. `run_catalog_sync` describes a live connection into
`source_objects` / `source_columns` -- comments the DBA wrote, descriptions the
model inferred, semantic types, and `enum_labels` saying that status 2 means
"paid". `run_sync` describes an uploaded file into `dataset_columns`.

Every site that creates a dataset column writes `name, dtype, missing_pct,
stats={}` and nothing else. So a dataset imported from a richly described table
is born blind -- and the dataset side is the side every chart, every dashboard
proposal and the dataset-mode agent read. The knowledge sat one table away and
nothing could reach it.

This column is the bridge. NOT a copy of the description: copying at import time
manufactures exactly the drift that already exists between `relationships` and
`source_relationships`, where the same fact is stored twice and the two disagree
the moment either is edited. A pointer resolves at read time, so describing
`patient_id` once improves every dataset ever built from that table.

NULL is meaningful and common: an uploaded file has no source column, and a
hand-written SQL dataset whose output name matches nothing is left unlinked on
purpose. A wrong link is worse than no link -- it would put another column's
sentence next to this one's numbers.

SET NULL rather than CASCADE: losing the provenance of a column must never
delete the column. A table dropped upstream leaves datasets that still hold
their rows and still render; they simply stop knowing what the values mean.

Revision ID: 0033_dataset_column_provenance
Revises: 0032_automation_run_record
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_dataset_column_provenance"
down_revision = "0032_automation_run_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table, exactly as 0029_aggregate_datasets: SQLite cannot ALTER
    # TABLE ADD COLUMN with a foreign key outside its copy-and-move "batch
    # mode", and tests/test_alembic_migrations.py runs `upgrade head` on SQLite.
    # Postgres, where this deploys, executes the same statements either way. The
    # constraint is NAMED so batch mode can drop it again on downgrade.
    with op.batch_alter_table("dataset_columns") as batch_op:
        batch_op.add_column(sa.Column(
            "source_column_id", sa.Integer(),
            sa.ForeignKey("source_columns.id", ondelete="SET NULL",
                          name="fk_dataset_columns_source_column_id_source_columns"),
            nullable=True))
        batch_op.create_index("ix_dataset_columns_source_column_id",
                              ["source_column_id"])


def downgrade() -> None:
    with op.batch_alter_table("dataset_columns") as batch_op:
        batch_op.drop_index("ix_dataset_columns_source_column_id")
        batch_op.drop_column("source_column_id")
