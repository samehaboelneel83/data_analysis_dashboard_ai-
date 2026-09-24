"""What the data in scope IS, read from the catalog rather than guessed.

"descripe this dataset" was answered, live, with four COUNT(*)s over four
Moodle tables the model picked out of a catalog of seventeen. The numbers were
right and the answer looked complete -- and nothing in it said that four
tables had been chosen, or that thirteen others existed. A description that
silently narrows its own scope is the failure this module exists to prevent:
the catalog knows every object and what each one holds, so the description
comes from there, and the model's query stays what it is -- an answer to a
question, sitting BESIDE the description rather than standing in for one.

Nothing here is inferred at answer time. Every name, kind and sentence was
written by the metadata sync (or by a DBA, in `comment`) long before the
question was asked, which is what makes these rows safe to show as a result
when no SQL produced them.
"""
from __future__ import annotations

from sqlalchemy import select as sa_select

from ...models.models import SourceObject
from .results import RESULT_ROW_CAP

#: A description is a sentence, not a page: enough to say what a table holds.
_DESCRIPTION_CHARS = 160


def _clip(text: str | None) -> str:
    s = (text or "").strip().replace("\n", " ")
    return s[:_DESCRIPTION_CHARS - 1] + "…" if len(s) > _DESCRIPTION_CHARS else s


async def catalog_overview(db, context, *, source_id: int | None = None,
                           org_id: int | None = None,
                           frames: dict | None = None) -> dict | None:
    """`{columns, rows, total, truncated}` describing what is in scope.

    Two shapes, because "describe this" means different things at different
    scopes and a person asking means the one they can see:

    * ONE object in scope (a single dataset, or a one-table connection) ->
      its COLUMNS, with their types. Describing a table is listing what is in
      it.
    * Several -> one row per TABLE: kind, how many columns, how many rows
      where that is known, and what it holds.

    Row counts come from `SourceObject.row_count_estimate` (whatever the sync
    recorded) or, in dataset mode, from the frame that is already loaded.
    Neither costs a query. A `COUNT(*)` per table would: on the connection
    that prompted this, one of the seventeen is a log table.

    None when there is no catalog to read -- the caller then answers as it
    always did.
    """
    objects = list((context.objects or {}).items())
    if not objects:
        return None

    frames = frames or {}
    estimates: dict[str, int] = {}
    if source_id is not None and org_id is not None:
        rows = (await db.execute(sa_select(
            SourceObject.name, SourceObject.row_count_estimate).where(
                SourceObject.data_source_id == source_id,
                SourceObject.org_id == org_id))).all()
        estimates = {name: count for name, count in rows if count is not None}

    if len(objects) == 1:
        name, info = objects[0]
        body = [[col, dtype] for col, dtype in (info.columns or {}).items()]
        return _snapshot(["column", "type"], body)

    body = []
    for name, info in objects:
        frame = frames.get(name)
        count = len(frame) if frame is not None else estimates.get(name)
        body.append([
            name,
            info.kind or "table",
            len(info.columns or {}),
            count if count is not None else "",
            _clip(info.description),
        ])
    # "description", not "what it holds": the header becomes a column name the
    # chat may offer back as an axis ("Chart columns by what it holds"), and a
    # column named like a question was read AS a question -- the click was
    # routed to describe_data and re-listed the tables instead of drawing.
    return _snapshot(["table", "kind", "columns", "rows", "description"], body)


def _snapshot(columns: list[str], rows: list[list]) -> dict:
    kept = rows[:RESULT_ROW_CAP]
    return {"columns": columns, "rows": kept, "total": len(rows),
            "truncated": len(rows) > RESULT_ROW_CAP}
