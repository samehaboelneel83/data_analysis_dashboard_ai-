"""V4 — row policies injected into the parsed AST.

Never concatenated: the predicate is itself PARSED, and a predicate that does
not parse fails the query (PolicyError) rather than being pasted in as text.
Never post-filtered: injection happens inside every SELECT that references
the table, so WHERE applies before GROUP BY and the aggregate is computed
over only the permitted rows. The import path's `apply_rls_filter`
post-filters a DataFrame; the agent path must never import it (spec F4).
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from .validate import _dialect


#: The policy key that applies to every table of the source.
ANY_TABLE = "*"


class PolicyError(Exception):
    """A policy could not be applied safely. The query is refused — failing
    open is the vulnerability this module exists to prevent."""


def apply_policies(sql: str, policies: dict[str, str], family: str) -> str:
    if not policies:
        return sql
    dialect = _dialect(family)
    tree = sqlglot.parse_one(sql, dialect=dialect)

    parsed_predicates: dict[str, exp.Expression] = {}
    for table, predicate in policies.items():
        try:
            parsed_predicates[table] = sqlglot.parse_one(
                predicate, dialect=dialect, into=exp.Condition)
        except Exception as exc:
            raise PolicyError(
                f"policy predicate for {table!r} does not parse: {exc}") from exc

    # "*" applies to every table (see load_policies: a rule that cannot be
    # tied to particular tables closes them all).
    everywhere = parsed_predicates.pop(ANY_TABLE, None)

    def predicate_for(name: str):
        own = parsed_predicates.get(name)
        if own is not None and everywhere is not None:
            return exp.and_(own.copy(), everywhere.copy())
        return own if own is not None else everywhere

    applied: set[int] = set()
    # Walk every SELECT (subqueries included) and AND the predicate into the
    # WHERE of each one that references a policied table.
    for select in tree.find_all(exp.Select):
        for table in select.find_all(exp.Table):
            pred = predicate_for(table.name)
            if pred is None:
                continue
            owner = table.find_ancestor(exp.Select)
            if owner is not select:
                continue  # this table belongs to a nested select; handled there
            alias = table.alias or table.name
            qualified = _qualify(pred.copy(), alias)
            select.where(qualified, append=True, copy=False)
            applied.add(id(table))

    for table in tree.find_all(exp.Table):
        if (table.name in parsed_predicates or everywhere is not None) and id(table) not in applied:
            raise PolicyError(
                f"table {table.name!r} appears where its row policy cannot "
                "be attached; refusing the query")

    return tree.sql(dialect=dialect)


def _qualify(condition: exp.Expression, alias: str) -> exp.Expression:
    """Prefix unqualified column references with the table's alias, so the
    predicate binds to the policied table even in a multi-table query."""
    for column in condition.find_all(exp.Column):
        if not column.table:
            column.set("table", exp.to_identifier(alias))
    return condition


async def load_policies(db, context, user) -> dict[str, str]:
    """The calling user's predicates, table name -> SQL. Org admins bypass —
    the same rule resolve_rls_expr applies (app/core/rls.py)."""
    from sqlalchemy import select

    from ...core.rls import apply_user_context
    from ...models.models import ObjectRowPolicy, SourceObject

    if user.role.is_org_admin:
        return {}
    rows = (await db.execute(
        select(ObjectRowPolicy, SourceObject.name)
        .join(SourceObject, SourceObject.id == ObjectRowPolicy.source_object_id)
        .where(ObjectRowPolicy.role_id == user.role_id,
               ObjectRowPolicy.org_id == user.org_id,
               SourceObject.data_source_id == context.source_id))).all()
    # org_id is a plain column on the already-loaded user (cheap); org NAME would need
    # a separate Organization lookup, which isn't worth paying here for every policy row
    # -- ORGNAME() stays unresolved in this path (source-object row policies, not RLS).
    # MYSCOPE() -- "this user's org units and everything under them" -- is
    # expanded here too. It was only expanded for DATASET rules, so a
    # connection rule written with it reached the SQL unresolved and failed
    # closed for everyone (HR evaluation, item 2.1).
    from ...core.rls import apply_scope, scope_values_for
    scope = await scope_values_for(db, user)
    policies = {name: apply_scope(apply_user_context(pol.predicate, email=user.email,
                                                     user_id=user.id, org_id=user.org_id), scope)
                for pol, name in rows}
    for table, predicate in (await _dataset_rule_predicates(db, context, user)).items():
        policies[table] = f"({policies[table]}) AND ({predicate})" if table in policies else predicate
    return policies


#: A predicate no row satisfies: what a rule that cannot be translated becomes.
_NO_ROWS = "1 = 0"


def _literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _inline(sql: str, params: dict) -> str:
    """`translate_filter_expr`'s bound parameters written in as literals: the
    predicate here is parsed into the query's AST, not bound at execution."""
    import re
    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", lambda m: _literal(params[m.group(1)]), sql)


async def _dataset_rule_predicates(db, context, user) -> dict[str, str]:
    """E01: the reader's DATASET row rules, as predicates on this connection's
    tables.

    A conversation over a connection writes SQL against the source's tables,
    so a row rule on a dataset imported from (or live over) one of those
    tables did not apply to it: a member restricted to Europe in the dataset
    could ask the connection and read every region. Each dataset over this
    connection that carries a rule for this reader now puts that rule on its
    table. Fail closed throughout:

    - a rule that cannot be translated to SQL lets no row of the table through;
    - a dataset defined by a query cannot have its rule placed on the tables
      it reads (their columns differ), so those tables let no row through;
    - a query that cannot even be parsed closes every table of the source.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from ...core.rls import resolve_rls_expr
    from ...models.models import Dataset
    from ..sql_expr import translate_filter_expr

    if user.role.is_org_admin:
        return {}
    datasets = (await db.execute(
        select(Dataset).options(selectinload(Dataset.columns))
        .where(Dataset.org_id == user.org_id, Dataset.data_source_id == context.source_id)
    )).scalars().all()
    out: dict[str, list[str]] = {}
    for ds in datasets:
        expr = await resolve_rls_expr(db, user, ds.id)
        if not expr:
            continue
        if ds.source_table:
            table = str(ds.source_table).split(".")[-1].strip('"`[] ')
            try:
                sql, params = translate_filter_expr(expr, {c.name for c in ds.columns})
                # Written with ANSI double-quoted identifiers; in the source's
                # own dialect (MySQL reads "region" as a string otherwise).
                predicate = sqlglot.transpile(_inline(sql, params), read="postgres",
                                              write=_dialect(context.family))[0] if sql else _NO_ROWS
            except Exception:  # noqa: BLE001 -- untranslatable means no rows, never all rows
                predicate = _NO_ROWS
            out.setdefault(table, []).append(predicate)
        elif ds.source_query:
            try:
                tables = {t.name for t in sqlglot.parse_one(
                    ds.source_query, dialect=_dialect(context.family)).find_all(exp.Table)}
            except Exception:  # noqa: BLE001
                tables = {ANY_TABLE}
            for table in tables or {ANY_TABLE}:
                out.setdefault(table, []).append(_NO_ROWS)
                # Said, not silent: the answer tells the reader WHY these rows
                # are missing and where they can ask instead (graph adds it as
                # a concern when a step reads one of these tables).
                try:
                    closed = getattr(context, "closed_by", None)
                    if closed is None:
                        closed = {}
                        setattr(context, "closed_by", closed)
                    closed.setdefault(table, set()).add(ds.name)
                except Exception:  # noqa: BLE001 -- a note, never a reason to open
                    pass
    return {t: " AND ".join(f"({p})" for p in preds) for t, preds in out.items()}



def closed_table_note(sql: str, context) -> str | None:
    """Why a step's rows may be missing: it read a table this reader may only
    see through a dataset (see `_dataset_rule_predicates`)."""
    closed = getattr(context, "closed_by", None) or {}
    if not closed or not sql:
        return None
    low = sql.lower()
    hit = sorted({name for table, names in closed.items()
                  if table != ANY_TABLE and table.lower() in low for name in names})
    if not hit:
        return None
    named = ", ".join(f"'{n}'" for n in hit)
    return (f"your access rules hide rows of this connection that are only shared with "
            f"you through the dataset {named}; ask that dataset to see the rows you may read")
