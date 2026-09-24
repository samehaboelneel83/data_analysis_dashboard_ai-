"""Dataset and connection ownership: `created_by`, backfilled to an org admin.

Until now every member of an org could list, query and export EVERY dataset in
it, and could delete any connection. `core.capability.readable_dataset_ids`
turns that into owner / explicitly-shared / reachable-through-a-dashboard-you-
can-see, and these two columns are what it resolves against.

THE BACKFILL IS THE POINT. A NULL owner reads as "unowned" and stays open --
that keeps fixtures and pre-existing installs working -- so leaving live rows
NULL would ship the new rules with nothing to apply them to. Every existing
dataset and connection is therefore assigned to its org's first admin: admins
see everything anyway, and members drop to the new rules immediately.

Existing installs that skip alembic get the same two columns and the same
backfill from `main.py`'s startup statements.

Chained on 0019_workspace_folder_grants.

Revision ID: 0020_dataset_ownership
Revises: 0019_workspace_folder_grants
Create Date: 2026-09-05 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0020_dataset_ownership'
down_revision: Union[str, None] = '0019_workspace_folder_grants'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: The org's lowest-numbered admin -- deterministic, and always somebody who
#: could read the row anyway, so the backfill grants nothing new.
_BACKFILL = """
UPDATE {table} SET created_by = (
    SELECT u.id FROM users u
    JOIN roles r ON r.id = u.role_id
    WHERE u.org_id = {table}.org_id AND r.is_org_admin = true
    ORDER BY u.id LIMIT 1
)
WHERE created_by IS NULL AND org_id IS NOT NULL
"""


def upgrade() -> None:
    # batch_alter_table: SQLite can't ALTER TABLE ADD COLUMN with a foreign-key
    # constraint outside its copy-and-move "batch mode" (Postgres, where this
    # actually deploys, executes the same statements directly either way --
    # batch mode only changes strategy on dialects that need it).
    for table in ("datasets", "data_sources"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(
                'created_by', sa.Integer(),
                sa.ForeignKey('users.id', ondelete='SET NULL',
                               name=f'fk_{table}_created_by_users'), nullable=True))
            batch_op.create_index(f'ix_{table}_created_by', ['created_by'])
        op.execute(sa.text(_BACKFILL.format(table=table)))


def downgrade() -> None:
    for table in ("datasets", "data_sources"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(f'ix_{table}_created_by')
            batch_op.drop_column('created_by')
