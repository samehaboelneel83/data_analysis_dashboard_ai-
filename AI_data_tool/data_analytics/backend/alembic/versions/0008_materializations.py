"""Task O3: materializations table

New `materializations` table (models.py Materialization, services/dataset_refresh.py
write_materialization, frame_cache.py sidecar reuse): one manifest row per dataset,
recording which refresh (full|incremental) produced the dataset's parquet
sidecar, its row count, column list and watermark cursor value at write time.
Chained on 0007_quotas.

Revision ID: 0008_materializations
Revises: 0007_quotas
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_materializations'
down_revision: Union[str, None] = '0007_quotas'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('materializations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('path', sa.String(length=1000), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('columns', sa.JSON(), nullable=False),
    sa.Column('watermark_value', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_materializations_dataset_id', 'materializations', ['dataset_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_materializations_dataset_id', table_name='materializations')
    op.drop_table('materializations')
