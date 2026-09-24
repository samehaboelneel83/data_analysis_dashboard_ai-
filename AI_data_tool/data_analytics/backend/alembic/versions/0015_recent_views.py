"""Per-user recents: the `recent_views` table.

Home's "Recents" ordered by `reports.updated_at`, which answers "what changed"
rather than "what did I open". Two consequences a user actually notices: a
dashboard somebody ELSE edited jumps to the top of your recents, and one you
read every morning without editing never appears at all.

One row per (user, report), upserted on open -- not an append-only event log.
The read is only ever "most recently viewed first", so a history of every open
would grow without bound to answer a question a single timestamp already
answers, and would need a retention policy nobody wrote. The audit log remains
the append-only, admin-facing account of what happened; this is a personal
convenience and is deliberately not that.

New TABLE, so `create_all` builds it on running installs and no inline
`main.py` ALTER is needed -- unlike 0013/0014, which added columns to live
tables.

Chained on 0014_publish_and_user_grants.

Revision ID: 0015_recent_views
Revises: 0014_publish_and_user_grants
Create Date: 2026-09-02 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0015_recent_views'
down_revision: Union[str, None] = '0014_publish_and_user_grants'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recent_views',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('report_id', sa.Integer(),
                  sa.ForeignKey('reports.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'report_id', name='uq_recent_user_report'),
    )


def downgrade() -> None:
    op.drop_table('recent_views')
