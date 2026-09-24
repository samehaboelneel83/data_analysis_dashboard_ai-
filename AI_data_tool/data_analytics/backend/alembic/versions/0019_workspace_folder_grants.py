"""Workspace sharing: live folder grants to people, roles, and teams.

`workspace_folder_grants` OPENS access (the counterpart of
`workspace_folder_roles`, which only trims the menu): a grant on any ancestor
folder resolves into report capability in `core.capability`, so sharing a
workspace publishes its subtree — interactively, never as a snapshot — to the
named user, role, or org unit at 'view' or 'edit'. A NEW table, so
`create_all` builds it on running installs and no inline `main.py` ALTER is
needed.

Chained on 0018_report_versions.

Revision ID: 0019_workspace_folder_grants
Revises: 0018_report_versions
Create Date: 2026-09-05 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0019_workspace_folder_grants'
down_revision: Union[str, None] = '0018_report_versions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workspace_folder_grants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('node_id', sa.Integer(),
                  sa.ForeignKey('workspace_nodes.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=True, index=True),
        sa.Column('role_id', sa.Integer(),
                  sa.ForeignKey('roles.id', ondelete='CASCADE'), nullable=True),
        sa.Column('org_unit_id', sa.Integer(),
                  sa.ForeignKey('org_units.id', ondelete='CASCADE'),
                  nullable=True),
        sa.Column('level', sa.String(10), nullable=False,
                  server_default='view'),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('workspace_folder_grants')
