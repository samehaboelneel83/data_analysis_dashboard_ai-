"""Customer-supplied map boundaries: the `boundary_sets` table.

Sub-national geometry (governorates, states, districts) is tens of megabytes
per country, so it cannot be bundled with the app. This is where an org stores
a GeoJSON file it already has, once, for every map in the org to draw against.

No change to any existing table: a map widget names its boundary set in its own
`config`, which is already a JSON column. That deliberately avoids the three
closed role vocabularies and the two `column_meta` whitelists a column-level
geography role would have to pass through — see the design note in
services/boundary_sets.py.

Chained on 0023_custom_connectors.

Revision ID: 0024_boundary_sets
Revises: 0023_custom_connectors
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0024_boundary_sets'
down_revision: Union[str, None] = '0023_custom_connectors'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'boundary_sets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE', name='fk_boundary_sets_org_id_organizations'),
                  nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        # The FeatureCollection verbatim. A JSON column rather than a file on
        # disk: this is reference data read as one document by the browser, not
        # something the query engine ever scans.
        sa.Column('geometry', sa.JSON(), nullable=False),
        sa.Column('key_properties', sa.JSON(), nullable=True),
        sa.Column('feature_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_boundary_sets_created_by_users'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('org_id', 'name', name='uq_boundary_sets_org_name'),
    )
    op.create_index('ix_boundary_sets_org_id', 'boundary_sets', ['org_id'])
    op.create_index('ix_boundary_sets_created_by', 'boundary_sets', ['created_by'])


def downgrade() -> None:
    op.drop_index('ix_boundary_sets_created_by', table_name='boundary_sets')
    op.drop_index('ix_boundary_sets_org_id', table_name='boundary_sets')
    op.drop_table('boundary_sets')
