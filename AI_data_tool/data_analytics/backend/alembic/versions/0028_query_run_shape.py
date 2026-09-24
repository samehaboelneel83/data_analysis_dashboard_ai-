"""query_runs: the shape of the query, so index advice has something to read.

Revision ID: 0028_query_run_shape
Revises: 0027_prediction_models
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_query_run_shape"
down_revision = "0027_prediction_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Column NAMES only -- never a value, never SQL. `sql_hash` next to these
    # is still the only trace of the statement, and it is a hash.
    op.add_column("query_runs", sa.Column("source_table", sa.String(length=255), nullable=True))
    op.add_column("query_runs", sa.Column("filter_columns", sa.JSON(), nullable=True))
    op.add_column("query_runs", sa.Column("group_column", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("query_runs", "group_column")
    op.drop_column("query_runs", "filter_columns")
    op.drop_column("query_runs", "source_table")
