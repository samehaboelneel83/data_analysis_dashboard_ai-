"""Hierarchical RLS: `org_units` and `user_org_units`.

An organization's own chart -- Country → Region → Branch → Department → Team,
to whatever depth that org uses -- plus which unit(s) each user sits at. Row
access then flows DOWNWARD: a rule written once as `branch in MYSCOPE()` gives
the Alexandria/Engineering user every team beneath them, and gives their Cairo
colleague a different set, with no second rule and no role-per-branch.

Deliberately NOT an extension of `hierarchy_nodes`: that table is a drill-down
path over a DATASET's columns (with aggregation and format) for charting. This
is the org chart itself. Sharing one table would mean a NULL-heavy row that is
sometimes a chart axis and sometimes a place of work.

Placement is per USER rather than per role, because two people can share the
"Regional manager" role while sitting at different branches -- a role-scoped
rule cannot express that without one role per branch, which is exactly the
explosion this replaces.

Both are NEW tables, so `create_all` builds them on running installs and no
inline `main.py` ALTER is needed.

Chained on 0015_recent_views.

Revision ID: 0016_org_units
Revises: 0015_recent_views
Create Date: 2026-09-02 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0016_org_units'
down_revision: Union[str, None] = '0015_recent_views'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'org_units',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('parent_id', sa.Integer(),
                  sa.ForeignKey('org_units.id', ondelete='CASCADE'),
                  nullable=True, index=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('level_name', sa.String(length=60), nullable=True),
        sa.Column('match_value', sa.String(length=255), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('org_id', 'parent_id', 'name',
                            name='uq_org_unit_sibling_name'),
    )
    op.create_table(
        'user_org_units',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('org_unit_id', sa.Integer(),
                  sa.ForeignKey('org_units.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('user_id', 'org_unit_id', name='uq_user_org_unit'),
    )


def downgrade() -> None:
    op.drop_table('user_org_units')
    op.drop_table('org_units')
