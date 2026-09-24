"""Ask AI results travel with the answer.

Three nullable JSON columns, all additive:

- `agent_steps.result_rows` -- a capped snapshot of a SINK step's rows
  (`{columns, rows, total, truncated}`), so the chat can draw the result as
  a grid or chart and reload it with the conversation. Intermediate steps
  stay NULL: their rows exist only to feed a later step's SQL.
- `agent_runs.context_objects` -- the retrieval-ranked object names the
  schema context put first for the question ("tables considered").
- `agent_runs.presentation` -- `{format, limit}` when a run only re-shows an
  earlier result ("as a table", "as a bar chart"); NULL for a data run.

`main._migrate` carries the matching `ADD COLUMN IF NOT EXISTS` lines for
running installs, since `create_all` never ALTERs an existing table.

Chained on 0016_org_units.

Revision ID: 0017_agent_results
Revises: 0016_org_units
Create Date: 2026-09-03 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0017_agent_results'
down_revision: Union[str, None] = '0016_org_units'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_steps', sa.Column('result_rows', sa.JSON(), nullable=True))
    op.add_column('agent_runs', sa.Column('context_objects', sa.JSON(), nullable=True))
    op.add_column('agent_runs', sa.Column('presentation', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_runs', 'presentation')
    op.drop_column('agent_runs', 'context_objects')
    op.drop_column('agent_steps', 'result_rows')
