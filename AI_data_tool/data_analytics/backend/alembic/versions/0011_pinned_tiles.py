"""Pinned tiles: any chart, pinned to a personal live dashboard.

One table (models.py PinnedTile, routers/pins.py). A pin is a REFERENCE to a
report widget, never a copy of its config or data: the tile renders by
re-reading the live widget and re-querying widget-data as the viewer, so it
shows exactly what that person would see inside the report -- same RLS, same
column mask. A snapshot would drift from the report and freeze one identity's
row visibility into a picture shown to nobody-in-particular.

Per user, not per org: a home dashboard is the set of numbers ONE person
checks daily. `ON DELETE CASCADE` everywhere -- a tile pointing at a deleted
widget, user or org is not worth a tombstone.

New table rather than columns on `report_widgets`, for the reason 0009 and
0010 state: create_all never ALTERs a live table, so a column would exist on
fresh installs and be missing on every database that already has data.

Chained on 0010_dataflows.

Revision ID: 0011_pinned_tiles
Revises: 0010_dataflows
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0011_pinned_tiles'
down_revision: Union[str, None] = '0010_dataflows'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pinned_tiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('org_id', sa.Integer(),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('widget_id', sa.Integer(),
                  sa.ForeignKey('report_widgets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('user_id', 'widget_id', name='uq_pin_user_widget'),
    )


def downgrade() -> None:
    op.drop_table('pinned_tiles')
