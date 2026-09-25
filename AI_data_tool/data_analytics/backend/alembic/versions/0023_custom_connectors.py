"""Custom connector presets: `custom_connectors` table and
`data_sources.custom_connector_id`.

Chained on 0022_dataset_custom_functions.

Revision ID: 0023_custom_connectors
Revises: 0022_dataset_custom_functions
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0023_custom_connectors'
down_revision: Union[str, None] = '0022_dataset_custom_functions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custom_connectors',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE', name='fk_custom_connectors_org_id_organizations'),
                  nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('base_type', sa.String(50), nullable=False),
        sa.Column('base_config', sa.JSON(), nullable=True),
        sa.Column('locked_fields', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_custom_connectors_created_by_users'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('org_id', 'key', name='uq_custom_connectors_org_key'),
    )
    op.create_index('ix_custom_connectors_org_id', 'custom_connectors', ['org_id'])
    op.create_index('ix_custom_connectors_created_by', 'custom_connectors', ['created_by'])

    with op.batch_alter_table('data_sources') as batch_op:
        batch_op.add_column(sa.Column(
            'custom_connector_id', sa.Integer(),
            sa.ForeignKey('custom_connectors.id', ondelete='RESTRICT',
                           name='fk_data_sources_custom_connector_id_custom_connectors'),
            nullable=True))
        batch_op.create_index('ix_data_sources_custom_connector_id', ['custom_connector_id'])


def downgrade() -> None:
    with op.batch_alter_table('data_sources') as batch_op:
        batch_op.drop_index('ix_data_sources_custom_connector_id')
        batch_op.drop_column('custom_connector_id')
    op.drop_index('ix_custom_connectors_created_by', table_name='custom_connectors')
    op.drop_index('ix_custom_connectors_org_id', table_name='custom_connectors')
    op.drop_table('custom_connectors')
