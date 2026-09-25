"""Aggregate datasets: a scheduled GROUP BY over a DirectQuery source.

Revision ID: 0029_aggregate_datasets
Revises: 0028_query_run_shape
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_aggregate_datasets"
down_revision = "0028_query_run_shape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table, exactly as 0020_dataset_ownership: SQLite cannot ALTER
    # TABLE ADD COLUMN with a foreign-key constraint outside its copy-and-move
    # "batch mode", and `alembic upgrade head` is run on SQLite by
    # tests/test_alembic_migrations.py. Postgres, where this actually deploys,
    # executes the same statements either way. The constraint is NAMED so batch
    # mode can drop it again on downgrade.
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.add_column(sa.Column(
            "aggregate_of_dataset_id", sa.Integer(),
            sa.ForeignKey("datasets.id", ondelete="CASCADE",
                          name="fk_datasets_aggregate_of_dataset_id_datasets"),
            nullable=True))
        batch_op.create_index("ix_datasets_aggregate_of_dataset_id",
                              ["aggregate_of_dataset_id"])
        batch_op.add_column(sa.Column("aggregate_spec", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch_op:
        batch_op.drop_column("aggregate_spec")
        batch_op.drop_index("ix_datasets_aggregate_of_dataset_id")
        batch_op.drop_column("aggregate_of_dataset_id")
