"""Tier 2 retrieval: retrieval_embeddings cache table

New `retrieval_embeddings` table (services/retrieval.py, spec §1B): caches a
Backend-B (OpenAI-compatible embeddings endpoint) vector for one piece of
retrievable text, keyed by a hash of that text plus the model, so an
unchanged document is never re-embedded.

Revision ID: 0004_retrieval_embeddings
Revises: 0003_feedback_evals
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_retrieval_embeddings'
down_revision: Union[str, None] = '0003_feedback_evals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('retrieval_embeddings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('ref', sa.String(length=500), nullable=False),
    sa.Column('text_hash', sa.String(length=64), nullable=False),
    sa.Column('vector', sa.JSON(), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('text_hash', 'model', name='uq_retrieval_embedding_text_model')
    )
    with op.batch_alter_table('retrieval_embeddings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_retrieval_embeddings_text_hash'), ['text_hash'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('retrieval_embeddings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_retrieval_embeddings_text_hash'))

    op.drop_table('retrieval_embeddings')
