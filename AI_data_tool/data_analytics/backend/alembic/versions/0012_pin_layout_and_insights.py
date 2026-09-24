"""Pin layout + Dynamic Insight Pins: position, size, and finding references.

Extends `pinned_tiles` (0011) rather than adding a second table, because both
pin kinds share ONE dashboard grid and one ordering -- two tables would mean
two position sequences and an interleaving problem no reader benefits from.

* `position` / `size`: dashboard order (dense, 1-based; renumbered by the
  client, TabOrderPane-style) and a discrete size token ('s'|'m'|'l') -- no
  freeform pixel sizes, matching the decision to keep the grid a flow layout.
* `dataset_id` / `finding_key`: an INSIGHT pin references a finding by the
  same identity `apply_novelty` uses (`kind|col|col`, columns sorted), and is
  re-evaluated live per viewer -- never a stored copy of figures or prose.
* `widget_id` becomes NULLABLE: an insight pin has no widget. Postgres treats
  NULLs as distinct in unique constraints, so the existing
  `uq_pin_user_widget` keeps deduping widget pins and the new
  `uq_pin_user_finding` dedupes insight pins without cross-talk.

The same DDL also ships as `main.py` inline `ALTER IF NOT EXISTS` statements,
per the 0009/0010 lesson: create_all never ALTERs the live table it already
created, so columns must be patched onto running installs explicitly.

Chained on 0011_pinned_tiles.

Revision ID: 0012_pin_layout_and_insights
Revises: 0011_pinned_tiles
Create Date: 2026-09-01 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0012_pin_layout_and_insights'
down_revision: Union[str, None] = '0011_pinned_tiles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table, not bare op.alter_column: the migration suite runs
    # these revisions against SQLite, which cannot ALTER a column's
    # nullability or add a table constraint in place -- batch mode rebuilds
    # the table there and emits ordinary ALTERs on Postgres.
    with op.batch_alter_table('pinned_tiles') as batch:
        batch.add_column(sa.Column('position', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('size', sa.String(length=1),
                                   nullable=False, server_default='m'))
        batch.add_column(sa.Column('dataset_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('finding_key', sa.Text(), nullable=True))
        batch.alter_column('widget_id', existing_type=sa.Integer(),
                           nullable=True)
        batch.create_foreign_key('fk_pin_dataset', 'datasets',
                                 ['dataset_id'], ['id'], ondelete='CASCADE')
        batch.create_unique_constraint('uq_pin_user_finding',
                                       ['user_id', 'dataset_id', 'finding_key'])


def downgrade() -> None:
    with op.batch_alter_table('pinned_tiles') as batch:
        batch.drop_constraint('uq_pin_user_finding', type_='unique')
        batch.drop_constraint('fk_pin_dataset', type_='foreignkey')
        batch.alter_column('widget_id', existing_type=sa.Integer(),
                           nullable=False)
        batch.drop_column('finding_key')
        batch.drop_column('dataset_id')
        batch.drop_column('size')
        batch.drop_column('position')
