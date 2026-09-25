"""Report version history (R2): a restorable content snapshot per revision.

Captured by `reports._bump_revision` before every mutating commit, so any
edit — GUI or page-copilot — can be walked back. A NEW table, so `create_all`
builds it on running installs and no inline `main.py` ALTER is needed.

Chained on 0017_agent_results.

Revision ID: 0018_report_versions
Revises: 0017_agent_results
Create Date: 2026-09-05 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0018_report_versions'
down_revision: Union[str, None] = '0017_agent_results'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('report_id', sa.Integer(),
                  sa.ForeignKey('reports.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('report_versions')
