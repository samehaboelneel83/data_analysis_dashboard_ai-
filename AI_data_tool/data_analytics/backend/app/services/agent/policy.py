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

    applied: set[int] = set()
    # Walk every SELECT (subqueries included) and AND the predicate into the
    # WHERE of each one that references a policied table.
    for select in tree.find_all(exp.Select):
        for table in select.find_all(exp.Table):
            pred = parsed_predicates.get(table.name)
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
        if table.name in parsed_predicates and id(table) not in applied:
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
    return {name: apply_user_context(pol.predicate, email=user.email,
                                     user_id=user.id, org_id=user.org_id)
            for pol, name in rows}
