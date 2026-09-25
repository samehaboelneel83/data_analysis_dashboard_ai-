"""Dataflows: dataflows + dataflow_capabilities tables

A transformation as a first-class object (models.py Dataflow, DataflowCapability,
routers/dataflows.py) rather than a recipe buried in one dataset's column_meta:
it owns the steps, produces SEVERAL output datasets, carries its own schedule,
and has its own authoring permissions instead of inheriting whatever the reports
using its output happen to allow.

New tables rather than columns on `datasets`, matching the reason
0009_workspace_nodes states: create_all never ALTERs a live table, so a column
would exist on fresh installs and be missing on every database that already has
data.

Outputs need no table of their own. A produced dataset records `dataflow_id`
inside its existing `__derived_from__` JSON, so no schema change is needed to
link one, and every derived dataset that exists today keeps working untouched --
it simply has no dataflow_id, which reads as "not owned by a dataflow".

NO DATA MIGRATION. Existing derived datasets are deliberately not adopted into
synthesised dataflows: their recipes keep running exactly as before, and inventing
an owner for them would change who may author them.

`dataflow_capabilities` ships EMPTY on purpose. No rows for a dataflow means every
role has full access, the same default ReportCapability and WorkspaceFolderRole
take -- a deny-by-default switch would break every existing workflow on the day it
ships.

Chained on 0009_workspace_nodes.

Revision ID: 0010_dataflows
Revises: 0009_workspace_nodes
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010_dataflows'
down_revision: Union[str, None] = '0009_workspace_nodes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dataflows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('source_dataset_id', sa.Integer(), nullable=True),
        sa.Column('join_dataset_ids', sa.JSON(), nullable=False),
        sa.Column('refresh_interval_minutes', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_status', sa.String(length=20), nullable=True),
        sa.Column('last_run_rows', sa.Integer(), nullable=True),
        sa.Column('last_run_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        # SET NULL, not CASCADE: deleting a source dataset must not silently
        # delete the recipe that reads it. The run then fails loudly and the
        # owner can repoint it, which is recoverable; a vanished dataflow is not.
        sa.ForeignKeyConstraint(['source_dataset_id'], ['datasets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dataflows_org_id'), 'dataflows', ['org_id'], unique=False)

    op.create_table(
        'dataflow_capabilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataflow_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(['dataflow_id'], ['dataflows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dataflow_id', 'role_id', name='uq_dataflow_capability'),
    )
    op.create_index(op.f('ix_dataflow_capabilities_dataflow_id'),
                    'dataflow_capabilities', ['dataflow_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dataflow_capabilities_dataflow_id'),
                  table_name='dataflow_capabilities')
    op.drop_table('dataflow_capabilities')
    op.drop_index(op.f('ix_dataflows_org_id'), table_name='dataflows')
    op.drop_table('dataflows')
