"""Change the data behind an existing dataset (owner request, 2026-10-08).

A dealer looking at "Pricing & Inventory Health" wanted each car's link; the
connection has `item_url`, the dataset left it out, and nothing short of
writing SQL and rebuilding the dashboard could add it. This lets a person:

* tick columns of the dataset's source table that are not in it yet (no
  model: the query's projection is extended), or
* ask in plain words ("add the listing link and the city") -- the model edits
  the query, checked and run as the person like every other setup query;

see exactly what is added and removed and a preview, then confirm. The
dataset is re-imported IN PLACE (same id), so every dashboard on it keeps
working. A column something uses (a chart, a filter, an alert...) can never
be removed this way (`services/dependencies.find_dependents`).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.models import DataSource, Dataset, SourceColumn, SourceObject, User


def _parse(sql: str, family: str):
    import sqlglot
    from .datasets import _dialect
    try:
        return sqlglot.parse_one(sql, dialect=_dialect(family))
    except Exception:                                               # noqa: BLE001
        return None


def simple_table(sql: str, family: str) -> tuple[str, str | None] | None:
    """(table, alias) when the query is a plain read of ONE table -- the shape
    whose column list can be extended by ticking. None for joins, unions,
    CTEs, grouping or DISTINCT (those go through the plain-words path)."""
    from sqlglot import exp
    tree = _parse(sql, family)
    if not isinstance(tree, exp.Select) or tree.find(exp.Join) or tree.find(exp.With) \
            or tree.args.get("group") or tree.args.get("distinct") or tree.find(exp.AggFunc):
        return None
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1:
        return None
    return tables[0].name, (tables[0].alias or None)


def output_columns(sql: str, family: str) -> list[str] | None:
    """The column names a query returns, or None when it says `*`."""
    from sqlglot import exp
    tree = _parse(sql, family)
    if tree is None or not isinstance(tree, exp.Select):
        return None
    if any(isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star))
           for e in tree.expressions):
        return None
    return [e.alias_or_name for e in tree.expressions]


def add_columns(sql: str, columns: list[str], family: str) -> str:
    """`sql` with `columns` appended to its projection (plain one-table reads)."""
    from sqlglot import exp
    from .datasets import _dialect
    tree = _parse(sql, family)
    found = simple_table(sql, family)
    if tree is None or found is None:
        raise ValueError("This dataset's query cannot be extended by ticking columns")
    _table, alias = found
    have = set(output_columns(sql, family) or [])
    for c in columns:
        if c in have:
            continue
        tree = tree.select(exp.column(c, table=alias, quoted=True), copy=False)
    return tree.sql(dialect=_dialect(family))


async def addable(db: AsyncSession, source: DataSource, ds: Dataset) -> list[dict]:
    """Columns of the dataset's source table it does not have yet."""
    from .access import _family
    sql = ds.source_query or (f'SELECT * FROM "{ds.source_table}"' if ds.source_table else "")
    found = simple_table(sql, _family(source)) if sql else None
    if found is None:
        return []
    table, _alias = found
    obj = (await db.execute(select(SourceObject).where(
        SourceObject.data_source_id == source.id, SourceObject.name == table))).scalars().first()
    if obj is None:
        return []
    have = set(output_columns(sql, _family(source)) or [c.name for c in ds.columns])
    cols = (await db.execute(select(SourceColumn).where(SourceColumn.source_object_id == obj.id)
                             .order_by(SourceColumn.position))).scalars().all()
    return [{"name": c.name, "table": table, "dtype": c.dtype, "semantic_type": c.semantic_type,
             "description": c.description or c.comment}
            for c in cols if c.name not in have]


async def blocked_removals(db: AsyncSession, ds: Dataset, removed: list[str]) -> list[dict]:
    """Removed columns something still uses: {column, used_by: [...]}."""
    from ..dependencies import find_dependents
    out = []
    for name in removed:
        deps = await find_dependents(db, ds, name)
        if deps:
            out.append({"column": name, "used_by": deps})
    return out


async def preview(db: AsyncSession, user: User, source: DataSource, ds: Dataset, *,
                  add: list[str] | None, message: str | None, lang: str, client) -> dict:
    """The changed query, what it adds and removes, and a run of it as `user`.

    {"sql", "adds", "removes", "blocked", "test", "reply", "error"}"""
    from . import datasets, understand
    from .access import _family

    family = _family(source)
    current = ds.source_query or (f'SELECT * FROM "{ds.source_table}"' if ds.source_table else "")
    before = [c.name for c in ds.columns]
    reply, sql = None, None
    if add:
        try:
            sql = add_columns(current, add, family)
        except ValueError as e:
            return {"error": str(e)}
    elif message:
        revised, reply = await datasets.refine(
            db, user, source, None, None,
            {"id": "change", "name": ds.name, "purpose": "", "sql": current, "includes": [],
             "leaves_out": [], "why": "", "history": []},
            message, lang, client)
        if revised is None:
            return {"error": reply}
        sql = revised["sql"]
    else:
        return {"error": "Nothing to change"}
    facts = await understand.load_facts(db, source)
    clean, why = datasets.check_sql(sql, family, datasets.catalog_of(facts))
    if clean is None:
        return {"error": why}
    test = await datasets.test_run(db, user, source, clean)
    if test["error"]:
        return {"error": test["error"]}
    after = test["columns"]
    removes = [c for c in before if c not in after]
    return {"sql": clean, "adds": [c for c in after if c not in before], "removes": removes,
            "blocked": await blocked_removals(db, ds, removes), "test": test,
            "reply": reply if reply and reply not in ("off", "failed", "unusable") else None,
            "error": None}
