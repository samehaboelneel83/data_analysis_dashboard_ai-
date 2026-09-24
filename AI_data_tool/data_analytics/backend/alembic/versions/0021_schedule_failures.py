"""Scheduler backoff: remember failures instead of retrying blindly.

`schedule_failures` holds one row per FAILING scheduled item (dataset
refresh, dataflow run, report schedule, data alert) with a consecutive
attempt count, the next time it may run, and the last error. Success deletes
the row, so the table stays empty on a healthy install.

A new table, so `create_all` provisions it on running installs and no inline
`main.py` ALTER is needed. This revision exists for completeness.

Chained on 0020_dataset_ownership.

Revision ID: 0021_schedule_failures
Revises: 0020_dataset_ownership
Create Date: 2026-09-07 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0021_schedule_failures'
down_revision: Union[str, None] = '0020_dataset_ownership'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'schedule_failures',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True,
                  index=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('first_failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('kind', 'item_id', name='uq_schedule_failure_item'),
    )


def downgrade() -> None:
    op.drop_table('schedule_failures')
