"""Workspaces: workspace_nodes table

New `workspace_nodes` table (models.py WorkspaceNode, routers/workspace.py): the
per-org report navigation tree. One row per folder or filed report; folders and
reports share a single sibling `position` so they interleave. Pages are NOT rows
here -- the tree endpoint joins ReportPage in at serialize time.

A new table rather than a `folder_id` column on `reports`, matching the reason
org_parents states: create_all never ALTERs a live table, so a column would exist
on fresh installs and be missing on every database that already has data.

No data migration: reports with no node render at root, which is the same rule
that applies to a report created after this ships.

Chained on 0008_materializations.

Revision ID: 0009_workspace_nodes
Revises: 0008_materializations
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009_workspace_nodes'
down_revision: Union[str, None] = '0008_materializations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('workspace_nodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('node_type', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('report_id', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    # Self-referential: a NULL parent is a root node. CASCADE here is why the
    # router re-parents children BEFORE deleting a folder -- letting the cascade
    # run would take the whole subtree, and with it somebody's filed reports.
    sa.ForeignKeyConstraint(['parent_id'], ['workspace_nodes.id'], ondelete='CASCADE'),
    # Deleting a report drops its node; the node never drops the report.
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
    # SET NULL, not CASCADE: a folder must outlive the person who made it.
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_workspace_nodes_org_id', 'workspace_nodes', ['org_id'])
    op.create_index('ix_workspace_nodes_created_by', 'workspace_nodes', ['created_by'])
    op.create_index('ix_workspace_nodes_parent_id', 'workspace_nodes', ['parent_id'])
    # Unique: a report is filed in at most one place in the tree.
    op.create_index('ix_workspace_nodes_report_id', 'workspace_nodes', ['report_id'],
                    unique=True)

    # Folder visibility grants. No rows for a folder = everyone in the org sees
    # it; rows RESTRICT it to those roles (plus admins and the creator). Same
    # shape and same default as page_role_visibility.
    op.create_table('workspace_folder_roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('node_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['node_id'], ['workspace_nodes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('node_id', 'role_id', name='uq_workspace_folder_role'),
    )
    op.create_index('ix_workspace_folder_roles_node_id', 'workspace_folder_roles', ['node_id'])


def downgrade() -> None:
    op.drop_index('ix_workspace_folder_roles_node_id', table_name='workspace_folder_roles')
    op.drop_table('workspace_folder_roles')
    op.drop_index('ix_workspace_nodes_report_id', table_name='workspace_nodes')
    op.drop_index('ix_workspace_nodes_parent_id', table_name='workspace_nodes')
    op.drop_index('ix_workspace_nodes_created_by', table_name='workspace_nodes')
    op.drop_index('ix_workspace_nodes_org_id', table_name='workspace_nodes')
    op.drop_table('workspace_nodes')
