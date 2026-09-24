"""Visual query builder: a validated query model compiled to dialect-correct SQL.

The security stance is validation-first, not escaping-first: every table and
column name in the model must exist in the INTROSPECTED schema of the live
connection, or the compile is refused. Identifiers are therefore never
attacker-controlled strings that need escaping -- they are members of a known
set, then quoted per dialect. Only VALUES are encoded, with single-quote
doubling, the one escape SQL string literals actually define.

The model:

    {
      "table": "orders",
      "joins": [{"table": "customers", "left_column": "customer_id",
                 "right_column": "id", "how": "left"}],
      "columns": [{"table": "orders", "column": "region"},
                  {"table": "orders", "column": "amount",
                   "aggregation": "sum", "alias": "total"}],
      "filters": [{"table": "orders", "column": "amount", "op": "gte", "value": 10},
                  {"table": "orders", "column": "customer_id", "op": "in",
                   "subquery": { ...another model, selecting ONE column... }}],
      "having": [{"table": "orders", "column": "amount",
                  "aggregation": "sum", "op": "gt", "value": 1000}],
      "sort": [{"alias": "total", "dir": "desc"}],
      "limit": 1000
    }

GROUP BY is derived, never declared: when any column aggregates, every
non-aggregated selected column groups -- declaring it separately only creates
the opportunity for the two lists to disagree. HAVING, by contrast, IS
declared: it filters the aggregate itself, which no selected column implies.

A nested WHERE (`in`/`not_in`/`exists`/`not_exists` with a `subquery`) is
compiled by recursing into `build_sql`, so an inner identifier is validated
against the live schema exactly as strictly as an outer one -- nesting adds
expressiveness without adding a second, weaker code path. Depth is bounded by
`_MAX_SUBQUERY_DEPTH`.
"""
from __future__ import annotations

import re

from sqlalchemy import create_engine, inspect

_AGGS = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX",
         "count": "COUNT", "count_distinct": "COUNT_DISTINCT"}
_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
# FULL and CROSS complete the set a diagram can express. CROSS is the odd one:
# it takes no ON clause, so the compiler must not demand the columns the other
# four require -- see the join loop.
_JOIN_HOW = {"left": "LEFT JOIN", "inner": "INNER JOIN", "right": "RIGHT JOIN",
             "full": "FULL OUTER JOIN", "cross": "CROSS JOIN"}
#: Joins whose ON clause is compiled from left/right columns. CROSS has none.
_JOIN_NEEDS_ON = {"left", "inner", "right", "full"}
#: Subquery operators for a nested WHERE. `exists` takes no left column.
_SUBQUERY_OPS = {"in": "IN", "not_in": "NOT IN", "exists": "EXISTS",
                 "not_exists": "NOT EXISTS"}
_ALIAS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$")
MAX_LIMIT = 100_000
#: A nested WHERE may itself nest. Bounded because the compile is recursive and
#: a model is client-supplied: without a ceiling, a deeply self-nested payload
#: is a stack-overflow request rather than a query.
_MAX_SUBQUERY_DEPTH = 3

# ── Self-referencing hierarchies ─────────────────────────────────────────────
# Any table shaped (id, parent_id) -- an org chart, a category tree, a bill of
# materials -- walked with a recursive CTE that adds the three columns such a
# table cannot answer on its own:
#
#   level    1 for roots, +1 per generation
#   path     'root/child/grandchild', so ORDER BY path is depth-first order
#   root_id  which tree this row belongs to
#
# Generated INLINE rather than installed as a database function. A stored
# `get_hierarchy()` would need CREATE privileges on the customer's database,
# which read-only analytics connections deliberately do not have, and would be
# PL/pgSQL -- one dialect out of the five this builder supports. The CTE is the
# same algorithm expressed as something a SELECT-only user can run anywhere.
#
# The columns it adds are namespaced with a prefix that cannot collide with a
# real column, because the CTE selects `c.*` and duplicate names would make the
# outer query's references ambiguous.
_HIER_LEVEL = "__level"
_HIER_PATH = "__path"
_HIER_ROOT = "__root_id"
#: Every generated column, for validation and for offering them in the UI.
HIERARCHY_COLUMNS = (_HIER_LEVEL, _HIER_PATH, _HIER_ROOT)
#: Recursion ceiling. A cycle in the data (A parents B parents A) makes the CTE
#: run forever; every supported dialect can bound it by depth, which turns a
#: hung connection into a truncated result.
MAX_HIERARCHY_DEPTH = 50


def table_columns(cfg: dict, table: str) -> list[dict]:
    """Introspect one table's columns from the live connection."""
    from .connections import _build_url
    from . import connectors
    engine = create_engine(_build_url(cfg), connect_args=connectors.connect_args(cfg))
    try:
        insp = inspect(engine)
        return [{"name": c["name"], "type": str(c.get("type", ""))}
                for c in insp.get_columns(table, schema=cfg.get("schema") or None)]
    finally:
        engine.dispose()


def introspect_tables(cfg: dict, tables: list[str]) -> dict[str, set[str]]:
    """Column sets for every table the model references, in one engine."""
    from .connections import _build_url
    from . import connectors
    engine = create_engine(_build_url(cfg), connect_args=connectors.connect_args(cfg))
    try:
        insp = inspect(engine)
        schema = cfg.get("schema") or None
        known_tables = set(insp.get_table_names(schema=schema)) | set(insp.get_view_names(schema=schema))
        out: dict[str, set[str]] = {}
        for t in tables:
            if t not in known_tables:
                raise ValueError(f"table '{t}' does not exist on this connection")
            out[t] = {c["name"] for c in insp.get_columns(t, schema=schema)}
        return out
    finally:
        engine.dispose()


def list_functions(cfg: dict) -> list[dict]:
    """Introspect the connection's scalar functions, per dialect. Best-effort:
    a dialect with no queryable catalogue (sqlite, api) returns [] rather than
    erroring -- the builder simply offers no functions there.

    The returned names are ALSO the allowlist for function application in the
    compiler: a function can be applied to a column only because introspection
    said it exists, the same membership stance as tables and columns.
    """
    from sqlalchemy import create_engine, text

    from . import connectors
    from .connections import _build_url

    t = connectors.sql_family_of(cfg)
    queries = {
        "postgresql": """
            SELECT routine_name AS name, data_type AS returns
            FROM information_schema.routines
            WHERE routine_type = 'FUNCTION'
              AND specific_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY routine_name LIMIT 200""",
        "mysql": """
            SELECT routine_name AS name, data_type AS returns
            FROM information_schema.routines
            WHERE routine_type = 'FUNCTION' AND routine_schema = DATABASE()
            ORDER BY routine_name LIMIT 200""",
        "sqlserver": """
            SELECT routine_name AS name, data_type AS returns
            FROM information_schema.routines
            WHERE routine_type = 'FUNCTION'
            ORDER BY routine_name""",
        "oracle": """
            SELECT object_name AS name, 'unknown' AS returns
            FROM user_objects WHERE object_type = 'FUNCTION'
            ORDER BY object_name""",
    }
    sql = queries.get(t)
    if not sql:
        return []
    engine = create_engine(_build_url(cfg), connect_args=connectors.connect_args(cfg))
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
        return [{"name": r[0], "returns": r[1]} for r in rows]
    except Exception:  # noqa: BLE001 -- no catalogue access is "no functions", not an error
        return []
    finally:
        engine.dispose()


_FUNC_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,80}$")


def _quote(dialect: str, name: str) -> str:
    if dialect == "mysql":
        return f"`{name}`"
    if dialect == "sqlserver":
        return f"[{name}]"
    return f'"{name}"'


def _require(d: dict, key: str, what: str) -> str:
    """Read a required key, or raise the SAME author-readable ValueError every
    other validation here raises.

    A bare `d["column"]` raises KeyError('column'), which the router turns into
    a 400 whose entire body is `'column'` -- technically not a crash, and
    useless to the person who has to fix the query. Every required field goes
    through here so a malformed model reads as an instruction.
    """
    v = d.get(key)
    if v is None or v == "":
        raise ValueError(f"{what} is missing its '{key}'")
    return v


def _encode_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else repr(int(v))
    # single-quote doubling: the one escape SQL string literals define
    return "'" + str(v).replace("'", "''") + "'"


def _build_hierarchy_cte(spec: dict, dialect: str, known: dict[str, set[str]],
                         qtable, quote) -> tuple[str, str, set[str]]:
    """Compile `model["hierarchy"]` into a recursive CTE.

    Returns (cte_sql, cte_name, columns_of_the_cte). The caller then treats the
    CTE name as an ordinary table: joins, filters, aggregation and the rest of
    the compiler need no special case, which is the point -- a hierarchy is a
    SOURCE, not a new kind of query.

    Model shape:
        {"table": "employees", "id_column": "id", "parent_column": "manager_id",
         "root_value": null}       # optional: start at one subtree instead of
                                   # every root
    """
    table = spec.get("table")
    if table not in known:
        raise ValueError(f"hierarchy table '{table}' does not exist on this connection")
    id_col = spec.get("id_column")
    parent_col = spec.get("parent_column")
    for label, c in (("id_column", id_col), ("parent_column", parent_col)):
        if not c:
            raise ValueError(f"hierarchy needs {label}")
        if c not in known[table]:
            raise ValueError(f"column '{c}' does not exist on table '{table}'")
    if id_col == parent_col:
        # Every row would be its own parent: the anchor matches nothing and the
        # recursive term never terminates meaningfully.
        raise ValueError("id_column and parent_column must be different")

    for generated in HIERARCHY_COLUMNS:
        if generated in known[table]:
            raise ValueError(
                f"table '{table}' already has a column named '{generated}'; "
                "rename it or use a different hierarchy source")

    qt = qtable(table)
    qid, qparent = quote(id_col), quote(parent_col)
    cte = "hierarchy"
    qcte = quote(cte)
    lvl, path, root = quote(_HIER_LEVEL), quote(_HIER_PATH), quote(_HIER_ROOT)

    # Cast to text so the path concatenates and the join compares like-for-like
    # whatever the key's real type is (int ids are the common case).
    txt = "NVARCHAR(4000)" if dialect == "sqlserver" else "TEXT"
    def as_text(e: str) -> str:
        return f"CAST({e} AS {txt})"

    # `{p}` is substituted with the QUOTED path identifier: an unquoted
    # `h.__path` happens to parse in SQLite but is not portable, and the whole
    # point of this branch is dialect correctness.
    concat = ("CONCAT(h.{p}, '/', {c})" if dialect == "mysql"
              else "h.{p} + '/' + {c}" if dialect == "sqlserver"
              else "h.{p} || '/' || {c}")

    # The anchor: either every root (parent IS NULL) or one named subtree.
    root_value = spec.get("root_value", None)
    if root_value is None:
        anchor_where = f"{qid_null_check(qparent)}"
    else:
        anchor_where = f"{qid} = {_encode_value(root_value)}"

    # Both terms of a UNION must select the same columns in the same order, so
    # the base table's columns are listed EXPLICITLY rather than with `*`:
    # `*` would also re-emit the id and parent columns that the CTE already
    # projects as text, changing the arity and the types between the two terms.
    # The id and parent columns are omitted here because the CTE already
    # projects them, cast to text, as its first two columns -- listing them
    # again would emit two columns of the same name and make every outer
    # reference ambiguous.
    base_cols = [c for c in sorted(known[table]) if c not in (id_col, parent_col)]
    base_list_anchor = ", ".join(quote(c) for c in base_cols)
    base_list_child = ", ".join(f"c.{quote(c)}" for c in base_cols)

    child_id = as_text(f"c.{qid}")
    anchor = (
        f"SELECT {as_text(qid)} AS {qid}, {as_text(qparent)} AS {qparent}, "
        f"1 AS {lvl}, {as_text(qid)} AS {path}, {as_text(qid)} AS {root}"
        + (f", {base_list_anchor}" if base_cols else "")
        + f" FROM {qt} WHERE {anchor_where}"
    )
    recursive = (
        f"SELECT {child_id}, {as_text('c.' + qparent)}, "
        f"h.{lvl} + 1, {concat.format(p=path, c=child_id)}, h.{root}"
        + (f", {base_list_child}" if base_cols else "")
        + f" FROM {qt} c JOIN {qcte} h "
        f"ON {as_text('c.' + qparent)} = h.{qid} "
        f"WHERE h.{lvl} < {MAX_HIERARCHY_DEPTH}"
    )
    keyword = "WITH RECURSIVE" if dialect != "sqlserver" else "WITH"
    cte_sql = f"{keyword} {qcte} AS (\n  {anchor}\n  UNION ALL\n  {recursive}\n)"
    return cte_sql, cte, set(known[table]) | set(HIERARCHY_COLUMNS)


def qid_null_check(qparent: str) -> str:
    """The anchor's predicate: a root is a row with no parent."""
    return f"{qparent} IS NULL"


def build_sql(model: dict, dialect: str, known: dict[str, set[str]],
              schema: str | None = None,
              known_functions: set[str] | None = None,
              depth: int = 0) -> str:
    """Compile the model. Raises ValueError with an author-readable message on
    anything invalid -- the router turns those into 400s.

    `depth` is the subquery nesting level; callers leave it at 0 and the
    recursive WHERE-subquery compile increments it.
    """
    def qtable(t: str) -> str:
        q = _quote(dialect, t)
        return f"{_quote(dialect, schema)}.{q}" if schema else q

    # A hierarchy source compiles to a recursive CTE that the rest of this
    # function then treats as an ordinary table -- so joins, filters, grouping
    # and sorting need no special case at all. `known` gains the CTE with the
    # base table's columns plus __level/__path/__root_id, which means those
    # three are validated by exactly the same membership check as any real
    # column rather than by a second, weaker rule.
    hier_cte = ""
    hier_spec = model.get("hierarchy")
    if hier_spec:
        if depth > 0:
            # A recursive CTE inside an IN(...) subquery is legal in some
            # dialects and not others; refusing is honest rather than emitting
            # SQL that works on one customer's database and not the next.
            raise ValueError("a hierarchy cannot be used inside a subquery")
        cte_sql, cte_name, cte_cols = _build_hierarchy_cte(
            hier_spec, dialect, known,
            qtable, lambda n: _quote(dialect, n))
        known = {**known, cte_name: cte_cols}
        hier_cte = cte_sql + " "

        # The CTE is referenced by its own name, never schema-qualified: it is
        # not a table in the schema.
        _plain_qtable = qtable

        def qtable(t: str) -> str:  # noqa: F811 - deliberate shadow
            return _quote(dialect, t) if t == cte_name else _plain_qtable(t)

    base = model.get("table")
    if not base or base not in known:
        raise ValueError(f"base table '{base}' does not exist on this connection")

    def qcol(t: str | None, c: str) -> str:
        t = t or base
        if t not in known:
            raise ValueError(f"table '{t}' is not part of this query")
        if c not in known[t]:
            raise ValueError(f"column '{c}' does not exist on table '{t}'")
        return f"{_quote(dialect, t)}.{_quote(dialect, c)}"

    # SELECT list
    cols = model.get("columns") or []
    if not cols:
        raise ValueError("select at least one column")
    any_agg = any(c.get("aggregation") for c in cols)
    select_parts, group_parts, aliases = [], [], set()
    for c in cols:
        expr = qcol(c.get("table"), _require(c, "column", "a selected column"))
        fn = c.get("function")
        if fn:
            # membership against the INTROSPECTED function catalogue, exactly like
            # tables and columns -- a name that is not in the database's own list
            # never reaches SQL, however identifier-shaped it looks.
            if not _FUNC_NAME.match(fn) or fn not in (known_functions or set()):
                raise ValueError(f"function '{fn}' does not exist on this connection")
            expr = f"{fn}({expr})"
        agg = c.get("aggregation")
        if agg:
            if agg not in _AGGS:
                raise ValueError(f"unknown aggregation '{agg}'")
            expr = f"COUNT(DISTINCT {expr})" if agg == "count_distinct" else f"{_AGGS[agg]}({expr})"
        else:
            if any_agg:
                group_parts.append(expr)
        alias = c.get("alias") or (f"{agg}_{c['column']}" if agg else None)
        if alias:
            if not _ALIAS.match(alias):
                raise ValueError(f"alias '{alias}' must be a plain identifier")
            if alias in aliases:
                raise ValueError(f"duplicate alias '{alias}'")
            aliases.add(alias)
            expr = f"{expr} AS {_quote(dialect, alias)}"
        select_parts.append(expr)

    # FROM + JOINs
    sql_from = qtable(base)
    tables_in_query = {base}
    for j in model.get("joins") or []:
        how_key = j.get("how", "left")
        how = _JOIN_HOW.get(how_key)
        if not how:
            raise ValueError(f"unknown join type '{how_key}'")
        jt = j.get("table")
        if jt not in known:
            raise ValueError(f"joined table '{jt}' does not exist on this connection")
        # A table joined to ITSELF needs an alias per side; without one the
        # emitted `"orders"."id"` is ambiguous and the DATABASE rejects the
        # query -- a compile that "succeeds" and then fails downstream is worse
        # than a refusal, because the author is told at the wrong moment and
        # by the wrong component. This compiler has no alias vocabulary, so
        # the honest answer is to say what is missing. (A hierarchy walk is the
        # supported way to relate a table to itself; see `hierarchy`.)
        if jt in tables_in_query:
            raise ValueError(
                f"table '{jt}' is already in this query; joining it to itself needs "
                f"aliases, which this builder does not support -- use a hierarchy "
                f"walk for parent/child relationships within one table")
        tables_in_query.add(jt)
        if how_key in _JOIN_NEEDS_ON:
            left = qcol(j.get("left_table") or base, _require(j, "left_column", "a join"))
            right = qcol(jt, _require(j, "right_column", "a join"))
            sql_from += f" {how} {qtable(jt)} ON {left} = {right}"
        else:
            # CROSS JOIN is every row against every row: an ON clause is a
            # syntax error, so the columns are not read at all rather than
            # being read and ignored.
            sql_from += f" {how} {qtable(jt)}"

    # WHERE -- D3: a single joiner (AND/OR) ties every filter row together,
    # the same "one joiner for the whole row set" shape as the codeless
    # ExpressionBuilder's Simple mode (lib/simpleExpr.ts), not per-pair logic.
    joiner = model.get("filters_joiner", "and")
    if joiner not in ("and", "or"):
        raise ValueError(f"unknown filters joiner '{joiner}'")
    wheres = []
    for f in model.get("filters") or []:
        op = f.get("op", "eq")

        # Nested subquery: `col IN (SELECT …)`, or a correlated-free EXISTS.
        # The inner model is compiled by THIS function, recursively, against a
        # freshly introspected `known` for its own tables -- so an inner
        # identifier is validated exactly as strictly as an outer one and no
        # SQL is ever assembled from a raw string the author supplied.
        # `in` is overloaded on purpose: it has always meant "one of this list
        # of values", and a subquery is the same question asked of a query. So
        # the SUBQUERY branch is taken only when a subquery is actually
        # supplied -- an `in` with a list keeps its original meaning, which the
        # value-list test below pins. `exists`/`not_exists` have no list form
        # and so always require one.
        if op in _SUBQUERY_OPS and (isinstance(f.get("subquery"), dict)
                                    or op in ("exists", "not_exists")
                                    or op == "not_in"):
            inner_model = f.get("subquery")
            if not isinstance(inner_model, dict):
                raise ValueError(f"'{op}' filter needs a subquery")
            if depth >= _MAX_SUBQUERY_DEPTH:
                raise ValueError(
                    f"subqueries nest at most {_MAX_SUBQUERY_DEPTH} deep")
            inner_sql = build_sql(inner_model, dialect, known, schema,
                                  known_functions, depth=depth + 1)
            if op in ("exists", "not_exists"):
                wheres.append(f"{_SUBQUERY_OPS[op]} ({inner_sql})")
            else:
                inner_cols = inner_model.get("columns") or []
                if len(inner_cols) != 1:
                    raise ValueError(
                        f"an '{op}' subquery must select exactly one column")
                col = qcol(f.get("table"), _require(f, "column", "a filter"))
                wheres.append(f"{col} {_SUBQUERY_OPS[op]} ({inner_sql})")
            continue

        col = qcol(f.get("table"), _require(f, "column", "a filter"))
        if op in _OPS:
            wheres.append(f"{col} {_OPS[op]} {_encode_value(f.get('value'))}")
        elif op == "contains":
            v = str(f.get("value", "")).replace("'", "''")
            wheres.append(f"{col} LIKE '%{v}%'")
        elif op == "in":
            vals = f.get("value") or []
            if not isinstance(vals, list) or not vals:
                raise ValueError("'in' filter needs a non-empty list value")
            wheres.append(f"{col} IN ({', '.join(_encode_value(v) for v in vals)})")
        elif op == "is_null":
            wheres.append(f"{col} IS NULL")
        elif op == "not_null":
            wheres.append(f"{col} IS NOT NULL")
        else:
            raise ValueError(f"unknown filter op '{op}'")

    # HAVING -- filters on the AGGREGATE, which WHERE cannot express: WHERE is
    # applied before grouping, so "regions whose total exceeds 1000" has to be
    # said here. Only meaningful once something groups, and saying so is better
    # than silently emitting a HAVING the database will reject.
    havings = []
    for h in model.get("having") or []:
        agg = h.get("aggregation")
        if agg not in _AGGS:
            raise ValueError(f"unknown aggregation '{agg}' in having")
        if not group_parts:
            raise ValueError("HAVING needs at least one aggregated column")
        expr = qcol(h.get("table"), _require(h, "column", "a having row"))
        expr = (f"COUNT(DISTINCT {expr})" if agg == "count_distinct"
                else f"{_AGGS[agg]}({expr})")
        op = h.get("op", "gt")
        if op not in _OPS:
            raise ValueError(f"unknown having op '{op}'")
        havings.append(f"{expr} {_OPS[op]} {_encode_value(h.get('value'))}")

    # ORDER BY: a selected alias, or a (validated) column
    orders = []
    for s in model.get("sort") or []:
        direction = "DESC" if s.get("dir") == "desc" else "ASC"
        if s.get("alias"):
            if s["alias"] not in aliases:
                raise ValueError(f"sort alias '{s['alias']}' is not in the select list")
            orders.append(f"{_quote(dialect, s['alias'])} {direction}")
        else:
            orders.append(f"{qcol(s.get('table'), s['column'])} {direction}")

    try:
        limit = min(int(model.get("limit") or 10_000), MAX_LIMIT)
    except (TypeError, ValueError):
        limit = 10_000
    if limit < 1:
        limit = 1

    # A SUBQUERY takes no LIMIT of its own. The outer query bounds the result;
    # a limit inside `IN (...)` silently truncates the set being matched
    # against, which turns "customers in the enterprise segment" into "the
    # first 10,000 of them" -- a wrong answer that looks like a right one.
    # (Oracle and SQL Server also reject a bare inner LIMIT/TOP outright.)
    nested = depth > 0

    top = f"TOP {limit} " if dialect == "sqlserver" and not nested else ""
    sql = f"{hier_cte}SELECT {top}{', '.join(select_parts)} FROM {sql_from}"
    if wheres:
        sql += " WHERE " + f" {joiner.upper()} ".join(wheres)
    if group_parts:
        sql += " GROUP BY " + ", ".join(group_parts)
    if havings:
        sql += " HAVING " + " AND ".join(havings)
    if orders:
        sql += " ORDER BY " + ", ".join(orders)
    if nested:
        return sql
    if dialect == "oracle":
        sql += f" FETCH FIRST {limit} ROWS ONLY"
    elif dialect != "sqlserver":
        sql += f" LIMIT {limit}"
    return sql


def referenced_functions(model: dict) -> list[str]:
    """Same recursion as `referenced_tables`: a function used only inside a
    subquery must still be looked up, or the compile rejects it as unknown."""
    out = [c["function"] for c in (model.get("columns") or []) if c.get("function")]
    for f in model.get("filters") or []:
        sub = f.get("subquery")
        if isinstance(sub, dict):
            out.extend(referenced_functions(sub))
    return out


def referenced_tables(model: dict) -> list[str]:
    """Every table the model touches, INCLUDING nested subqueries.

    The router introspects exactly this list and hands it to `build_sql` as
    `known`; a subquery table missing from it fails validation as "does not
    exist on this connection" even though it does. So the walk has to recurse
    wherever the compiler recurses.
    """
    tables = [model.get("table")]
    # The hierarchy's SOURCE table must be introspected; the CTE name itself
    # must NOT be, since it is not a table in the schema. `build_sql` adds the
    # CTE to `known` after this list has been resolved.
    hier = model.get("hierarchy")
    if isinstance(hier, dict) and hier.get("table"):
        tables.append(hier["table"])
        if model.get("table") == "hierarchy":
            tables = [t for t in tables if t != "hierarchy"]
    for j in model.get("joins") or []:
        tables.append(j.get("table"))
    for f in model.get("filters") or []:
        sub = f.get("subquery")
        if isinstance(sub, dict):
            tables.extend(referenced_tables(sub))
    return [t for t in dict.fromkeys(tables) if t]
