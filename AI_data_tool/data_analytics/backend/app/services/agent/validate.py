"""The validation ladder, rungs V1-V3 and V6 (V4 is policy.py, V5 lives in
executor.py; V6 — column security — runs here because it is an AST check).

Cheapest first (D4.1): parse costs microseconds, schema costs a dict lookup
(the Layer 1 catalog already holds all columns — V2 alone eliminates the most
common failure, hallucinated names), joins cost a set lookup against the
provenance-filtered whitelist. Most failures never reach a database.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from .context import SchemaContext


@dataclass
class ValidationFailure:
    rung: str
    detail: str


_DIALECTS = {"postgresql": "postgres", "mysql": "mysql", "mssql": "tsql",
             "oracle": "oracle", "sqlite": "sqlite", "duckdb": "duckdb"}


def _dialect(family: str) -> str:
    return _DIALECTS.get((family or "").lower(), "postgres")


def validate_sql(sql: str, context: SchemaContext) -> ValidationFailure | None:
    """First failure wins; None means rungs V1-V3 all passed."""
    # ── V1: parse, and SELECT-only ─────────────────────────────────────────
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(context.family))
    except Exception as exc:
        return ValidationFailure("V1", f"does not parse: {exc}")
    if tree is None or not isinstance(tree, (exp.Select, exp.Union)):
        return ValidationFailure(
            "V1", "only SELECT statements are allowed; the agent reads, never writes")

    # Still V1, and for the same reason: an answer about the data has to come
    # FROM the data. A query that references no table returns whatever the
    # model typed into its SELECT list -- traced live, a question about which
    # attributes were worth visualising came back as
    # `SELECT 'id' AS attribute, 'Numeric ID' AS description ... UNION ALL ...`
    # and was rendered as a five-row grid with Show SQL, CSV and Excel beside
    # it. Every rung below checks that the names used are REAL; none of them
    # fires when there are no names at all, so invented rows were the one
    # fabrication this ladder passed. The repair loop gets this message back
    # and rewrites against a real table.
    if not any(True for _ in tree.find_all(exp.Table)):
        return ValidationFailure(
            "V1", "this query reads no table, so its rows would be values you "
            "wrote rather than data. Select from a table in the schema.")

    # ── V6: column security fails closed (before V2 on purpose) ────────────
    # The denied columns were already REMOVED from the context before the
    # model saw it, so ordinarily nothing reaches this rung. It exists for
    # the query that names one anyway (from a memorised example, a glossary
    # phrase, or plain guessing): silently rewriting the query would be the
    # import path's DROP semantics applied where it does not belong — SQL is
    # built from names, and a rewritten query is a wrong answer that looks
    # right. Refuse instead, exactly like the DirectQuery widget path.
    # Deliberately table-insensitive: a denied name is refused wherever it
    # appears, because alias resolution can be defeated and the cost of the
    # conservative reading is one honest degradation.
    if context.denied_columns:
        denied_all = {str(name).casefold()
                      for cols in context.denied_columns.values() for name in cols}
        for col in tree.find_all(exp.Column):
            if col.name and col.name.casefold() in denied_all:
                return ValidationFailure(
                    "V6",
                    f"column '{col.name}' is blocked by a column-security "
                    "rule for this user. Answer without it — do not select, "
                    "filter on or derive from it in any form.")


    # ── V2: every table and column must exist in the catalog ───────────────
    # CTE names (WITH x AS (...)) are valid table references even though
    # they're not in the catalog. Columns *inside* a CTE body are checked
    # against the catalog as usual (its FROM clauses point at real tables,
    # so a hallucinated table there still fails V2 below).
    #
    # An unqualified reference to a CTE's OUTPUT column is scoped, not
    # global: it is permitted only when (a) that CTE is actually referenced
    # in the SAME SELECT's FROM/JOIN, and (b) the column name is one the CTE
    # actually projects (derived from its own SELECT list where derivable —
    # `SELECT *`/non-trivial expressions fall back to permissive, since
    # deriving full SQL projection semantics is out of scope). A blanket
    # "any CTE anywhere in the statement excuses any unqualified column"
    # rule was a verified bypass (`WITH t2 AS (...) SELECT bogus_col FROM
    # orders, t2` used to pass) — real resolution against catalog tables
    # present in that SELECT is preferred, and a column matching neither
    # still fails V2.
    cte_names = {cte.alias for cte in tree.find_all(exp.CTE) if cte.alias}

    def _cte_output_columns(cte: exp.CTE) -> set[str] | None:
        """None means 'could not be derived' — treated as permissive."""
        inner = cte.this
        if not isinstance(inner, exp.Select):
            return None
        names: set[str] = set()
        for e in inner.expressions:
            if isinstance(e, exp.Star):
                return None
            if isinstance(e, exp.Alias) and e.alias:
                names.add(e.alias)
            elif isinstance(e, exp.Column):
                names.add(e.name)
            else:
                return None
        return names

    cte_output_columns = {
        cte.alias: _cte_output_columns(cte)
        for cte in tree.find_all(exp.CTE) if cte.alias
    }

    alias_to_table: dict[str, str] = {}
    cte_aliases: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name
        ref = table.alias or name
        if name in cte_names:
            alias_to_table[ref] = name
            cte_aliases.add(ref)
            continue
        if not context.has_table(name):
            return ValidationFailure("V2", f"no such table: {name}")
        alias_to_table[ref] = name

    # Output aliases from every SELECT's projection list (`expr AS alias`)
    # are valid unqualified references elsewhere in that query — e.g. an
    # ORDER BY or HAVING referring to a computed column by its alias.
    output_aliases: set[str] = set()
    for select in tree.find_all(exp.Select):
        for e in select.expressions:
            if isinstance(e, exp.Alias) and e.alias:
                output_aliases.add(e.alias)

    def _select_scope(select: exp.Select) -> dict[str, str]:
        """ref -> real table/CTE name for tables belonging directly to this
        SELECT's own FROM/JOIN — not a nested subquery's."""
        scope: dict[str, str] = {}
        for t in select.find_all(exp.Table):
            if t.find_ancestor(exp.Select) is not select:
                continue
            scope[t.alias or t.name] = t.name
        return scope

    select_scopes = {id(s): _select_scope(s) for s in tree.find_all(exp.Select)}

    for column in tree.find_all(exp.Column):
        cname = column.name
        qualifier = column.table  # empty string when unqualified
        if qualifier:
            table = alias_to_table.get(qualifier)
            if table is None:
                return ValidationFailure("V2", f"unknown alias: {qualifier}")
            if qualifier in cte_aliases:
                continue  # CTE output column — see note above
            if not context.has_column(table, cname):
                return ValidationFailure(
                    "V2", f"no such column: {qualifier}.{cname} "
                          f"(table {table})")
        else:
            if cname in output_aliases:
                continue
            owner_select = column.find_ancestor(exp.Select)
            scope = (select_scopes.get(id(owner_select), {})
                     if owner_select is not None else {})
            real_tables = [n for n in scope.values() if n not in cte_names]
            if any(context.has_column(t, cname) for t in real_tables):
                continue
            scoped_cte_names = {n for n in scope.values() if n in cte_names}
            if any(cte_output_columns.get(n) is None
                   or cname in cte_output_columns.get(n, set())
                   for n in scoped_cte_names):
                continue  # a CTE in THIS select's FROM projects this column
            return ValidationFailure("V2", f"no such column: {cname}")

    # ── V3: every join must be a confirmed or declared edge ────────────────
    def _resolve(col: exp.Column) -> tuple[str, str] | None:
        if col.table:
            t = alias_to_table.get(col.table)
            return (t, col.name) if t else None
        owners = [t for t in alias_to_table.values()
                  if context.has_column(t, col.name)]
        return (owners[0], col.name) if len(owners) == 1 else None

    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            return ValidationFailure("V3", "JOIN without an ON condition")
        for eq in on.find_all(exp.EQ):
            left, right = eq.left, eq.right
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                lt, rt = _resolve(left), _resolve(right)
                if lt is None or rt is None:
                    return ValidationFailure("V3", f"cannot resolve join: {eq.sql()}")
                if not context.join_allowed(lt[0], lt[1], rt[0], rt[1]):
                    return ValidationFailure(
                        "V3",
                        f"join {lt[0]}.{lt[1]} = {rt[0]}.{rt[1]} is not a "
                        "confirmed or declared relationship. Inferred "
                        "relationships are proposals awaiting human review "
                        "and may not be executed on.")

    return None
