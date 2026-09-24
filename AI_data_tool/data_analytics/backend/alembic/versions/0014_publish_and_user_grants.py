"""Publish/grant model: `reports.published`, `workspace_nodes.published`,
and the `report_user_grants` table.

The regime this enables (authored dashboards only -- created_by NULL rows are
grandfathered into the old default-open world):

  draft      invisible to everyone but the author, admins, and per-user grants
  published  org members may OPEN it, capability 'view' -- layout locked
  granted    a named user gets 'view'/'edit'/'data' regardless of publication

Publishing and granting are deliberately different acts on different axes:
publish (report-level here, folder-level via workspace_nodes.published for a
whole workspace) controls AUDIENCE at view strength; a grant controls
CAPABILITY for one person. Neither column is consulted for unowned reports.

Booleans with a server_default of 0, so every existing row wakes up as an
unpublished draft -- which changes nothing, because every existing row is also
unowned and therefore grandfathered.

Same DDL ships as `main.py` inline `ALTER IF NOT EXISTS` (create_all builds
the new TABLE on running installs but never ALTERs the live ones).

Chained on 0013_report_created_by.

Revision ID: 0014_publish_and_user_grants
Revises: 0013_report_created_by
Create Date: 2026-09-01 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0014_publish_and_user_grants'
down_revision: Union[str, None] = '0013_report_created_by'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reports', sa.Column('published', sa.Boolean(),
                                       nullable=False, server_default='0'))
    op.add_column('workspace_nodes', sa.Column('published', sa.Boolean(),
                                               nullable=False, server_default='0'))
    op.create_table(
        'report_user_grants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('report_id', sa.Integer(),
                  sa.ForeignKey('reports.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('level', sa.String(length=5), nullable=False,
                  server_default='edit'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('report_id', 'user_id', name='uq_report_user_grant'),
    )


def downgrade() -> None:
    op.drop_table('report_user_grants')
    op.drop_column('workspace_nodes', 'published')
    op.drop_column('reports', 'published')
