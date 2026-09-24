"""Task E1: embed_configs table

New `embed_configs` table (models.py EmbedConfig, routers/embed.py):
host-signed embed credentials for reports. Each row holds an enc:v2
encrypted secret (shown once at creation), an optional Origin allowlist,
an enabled flag used for revocation, and `created_by` -- the embed's data
path resolves row-level security and denied columns as THIS user, the
same creator-scoping ShareLink guests get (see routers/shared.py
`_resolve_identity`), so an embed can never expose more than its
creator's own slice. Unique per (report_id, name) so re-creating a
config under the same name updates rather than duplicates.

Revision ID: 0006_embed_configs
Revises: 0005_entities
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_embed_configs'
down_revision: Union[str, None] = '0005_entities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('embed_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('secret_encrypted', sa.Text(), nullable=False),
    sa.Column('allowed_origins', sa.JSON(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('report_id', 'name', name='uq_embed_config_name'),
    )
    with op.batch_alter_table('embed_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_embed_configs_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_embed_configs_report_id'), ['report_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('embed_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_embed_configs_report_id'))
        batch_op.drop_index(batch_op.f('ix_embed_configs_org_id'))

    op.drop_table('embed_configs')
