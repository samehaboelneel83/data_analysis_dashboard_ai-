"""Pipeline watches gain followers: editors who asked for the in-app notices.

Loose ends after the pipeline plan (2026-10-03): a dataset whose creator
account nobody reads sent its failure notices nowhere useful. "Notify me" adds
the caller to `followers`, a JSON list of user ids.

Revision ID: 0058_pipeline_followers
Revises: 0057_incremental_merge
"""
from alembic import op
import sqlalchemy as sa

revision = "0058_pipeline_followers"
down_revision = "0057_incremental_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_watches", sa.Column("followers", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_watches", "followers")
