"""Task E2: quotas table

New `quotas` table (models.py Quota, services/quotas.py, routers/platform.py):
per-tenant usage ceilings, one row per org, unique on org_id. All four
limits nullable -- NULL means unlimited, the byte-preserved default for
every org that never gets a row here. Chained on E1's 0006_embed_configs.

Revision ID: 0007_quotas
Revises: 0006_embed_configs
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_quotas'
down_revision: Union[str, None] = '0006_embed_configs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('quotas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('max_queries_per_day', sa.Integer(), nullable=True),
    sa.Column('max_agent_asks_per_day', sa.Integer(), nullable=True),
    sa.Column('max_storage_mb', sa.Integer(), nullable=True),
    sa.Column('max_concurrent_asks', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('org_id', name='uq_quotas_org_id'),
    )


def downgrade() -> None:
    op.drop_table('quotas')
