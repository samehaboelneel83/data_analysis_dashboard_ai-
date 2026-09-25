"""Custom calculated-column functions: `datasets.custom_functions`.

Chained on 0021_schedule_failures.

Revision ID: 0022_dataset_custom_functions
Revises: 0021_schedule_failures
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0022_dataset_custom_functions'
down_revision: Union[str, None] = '0021_schedule_failures'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('datasets') as batch_op:
        batch_op.add_column(sa.Column('custom_functions', sa.JSON(), nullable=True))
    op.execute(sa.text("UPDATE datasets SET custom_functions = '[]' WHERE custom_functions IS NULL"))


def downgrade() -> None:
    with op.batch_alter_table('datasets') as batch_op:
        batch_op.drop_column('custom_functions')
