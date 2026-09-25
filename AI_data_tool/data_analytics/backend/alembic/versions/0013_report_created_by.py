"""Report authorship: `reports.created_by`.

Reports never had an owner -- by design for ACCESS (capability is role-scoped
and default-open), but the workspace tree's "My workspaces / Granted" split
needs to know who AUTHORED a report, and the folder node that files it is not
an answer: unfiled reports have no node, and the filer need not be the author.

NULL means "unowned" (every pre-existing row) and is never "mine" for anyone,
mirroring `workspace_nodes.created_by` exactly -- including ON DELETE SET NULL,
because a departed author must not take the report's listing with them.

Grouping only, never access control: visibility and mutation stay governed by
org scoping + ReportCapability, and `test_workspace.py`'s
TestVisibilityIsNotAccessControl continues to hold.

The same DDL also ships as a `main.py` inline `ALTER IF NOT EXISTS`, per the
0009/0010 lesson: create_all never ALTERs a live table it already created.

Chained on 0012_pin_layout_and_insights.

Revision ID: 0013_report_created_by
Revises: 0012_pin_layout_and_insights
Create Date: 2026-09-01 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0013_report_created_by'
down_revision: Union[str, None] = '0012_pin_layout_and_insights'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table: the migration suite replays these against SQLite,
    # which cannot add a foreign key in place.
    with op.batch_alter_table('reports') as batch:
        batch.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_report_created_by', 'users',
                                 ['created_by'], ['id'], ondelete='SET NULL')
    op.create_index('ix_reports_created_by', 'reports', ['created_by'])


def downgrade() -> None:
    op.drop_index('ix_reports_created_by', table_name='reports')
    with op.batch_alter_table('reports') as batch:
        batch.drop_constraint('fk_report_created_by', type_='foreignkey')
        batch.drop_column('created_by')
