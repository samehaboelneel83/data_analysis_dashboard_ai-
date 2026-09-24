"""Tier 2 retrieval: entities table

New `entities` table (services/agent/context.py, spec section 5, Task R3):
named business objects a source models ("customer", "order"), each with a
stated grain ("one row per..."), drafted by the sync's LLM pass and
confirmed/edited on the metadata review surface. Unique per
(data_source_id, name) so a resync updates rather than duplicates a row.

Revision ID: 0005_entities
Revises: 0004_retrieval_embeddings
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_entities'
down_revision: Union[str, None] = '0004_retrieval_embeddings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('entities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('data_source_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('business_name', sa.String(length=255), nullable=True),
    sa.Column('grain', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('primary_object', sa.String(length=500), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False, server_default='inferred'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('data_source_id', 'name', name='uq_entity_name')
    )
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_entities_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_entities_data_source_id'), ['data_source_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_entities_data_source_id'))
        batch_op.drop_index(batch_op.f('ix_entities_org_id'))

    op.drop_table('entities')
