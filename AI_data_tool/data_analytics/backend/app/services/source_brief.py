"""Design dashboards from a connected database the way an analyst would.

The first designer (`suggest_dashboard.suggest_dashboards`) read table names,
column types and descriptions, wrote one SQL query per idea, and accepted it
once the query returned a row. On the Egyptian food database, asked for by
"وزير التموين" (the Minister of Supply), that produced (live, 2026-10-03):

  * "Average price by governorate" -- prices exist for ONE market (Cairo's
    national average); every other governorate is empty;
  * "Average price, all commodities" -- a kilo of meat, one egg and an 800 g
    bottle of oil averaged into one number;
  * poverty joined to prices on year 2026 -- poverty has 2008 and 2014 only;
  * `priceflag = 'A'` -- the column holds 'actual'; every price tile blank;
  * "Highest risk governorate: Suhag" -- `max(governorate)`, the alphabet.

Each query RAN. None of it meant anything. The facts that would have stopped
every one of them were already in the catalog (column statistics from the
sync) and were never shown to the model, and nothing checked what a query
returned beyond "at least one row".

This module works in four steps:

  1. FACTS -- per table, what the columns really hold: empty shares, the only
     values a short column takes, the years present, the date span, and the
     consequences ("prices are in 6 units: compare a commodity with itself").
  2. BRIEF -- one model call: who this person is, the decisions they make,
     the questions that serve those decisions and which tables answer each,
     and what this data cannot answer. The brief is shown to the person.
  3. DESIGN -- one model call per batch: datasets (SQL) and charts that
     answer the brief's questions, under rules about grain and units.
  4. CHECK -- every query is run and its RESULT judged per chart: empty
     measures, single-value breakdowns, text used as a number, mixed units.
     The specific failures go back to the model once for repair.

Nothing is created here; the person picks a proposal and the client builds it.
"""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

# ── 1. facts ────────────────────────────────────────────────────────────────

#: A column holding a unit of measure. A table where it takes several values
#: holds numbers that cannot be added or averaged across rows of different units.
_UNIT_NAME = re.compile(r"(^|_)(unit|units|uom|unit_of_measure|measure_unit|currency)($|_)", re.I)
#: A year held as a plain number.
_YEAR_NAME = re.compile(r"(^|_)(year|yr|fiscal_year)($|_)", re.I)
#: Columns that name an item (what a price or quantity is OF).
_ITEM_NAME = re.compile(r"(commodity|product|item|sku|goods|article|indicator|series)", re.I)
_DATE_TYPES = ("date", "datetime", "timestamp", "time")
_NUM_TYPES = ("integer", "int", "float", "numeric", "decimal", "number", "double", "real", "bigint")


def _is_num(dtype: str | None) -> bool:
    d = (dtype or "").lower()
    return any(t in d for t in _NUM_TYPES)


def _is_date(dtype: str | None, name: str = "") -> bool:
    d = (dtype or "").lower()
    return any(t in d for t in _DATE_TYPES) or name.lower() in ("date", "month", "period")


def _short(v: Any, n: int = 40) -> str:
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def _values(top_k: list | None) -> list[tuple[str, int | None]]:
    out = []
    for e in top_k or []:
        if isinstance(e, dict) and e.get("value") is not None:
            c = e.get("count")
            out.append((str(e["value"]), int(c) if isinstance(c, (int, float)) else None))
    return out


async def load_catalog_facts(db, source_id: int) -> list[dict]:
    """The catalog with the sync's column statistics attached.

    Statistics are optional per column: a source synced before profiling ran
    simply has fewer facts, never an error.
    """
    from sqlalchemy import select

    from ..models.models import ColumnStats, SourceColumn, SourceObject

    objects = (await db.execute(
        select(SourceObject).where(SourceObject.data_source_id == source_id)
        .order_by(SourceObject.name))).scalars().all()
    if not objects:
        return []
    cols = (await db.execute(
        select(SourceColumn, ColumnStats)
        .outerjoin(ColumnStats, ColumnStats.source_column_id == SourceColumn.id)
        .where(SourceColumn.source_object_id.in_([o.id for o in objects]))
        .order_by(SourceColumn.source_object_id, SourceColumn.position))).all()
    by_obj: dict[int, list] = {}
    for col, st in cols:
        by_obj.setdefault(col.source_object_id, []).append({
            "name": col.name, "dtype": col.dtype, "description": col.description,
            "null_ratio": getattr(st, "null_ratio", None),
            "distinct": getattr(st, "distinct_count", None),
            "top_k": getattr(st, "top_k", None),
            "min": getattr(st, "min_value", None), "max": getattr(st, "max_value", None),
        })
    return [{"name": o.name, "description": o.description,
             "rows": o.row_count_estimate, "columns": by_obj.get(o.id, [])}
            for o in objects]


#: Values that mark a TOTAL row stored beside its parts (gender = 'all').
_TOTAL_VALUES = {"all", "total", "both sexes", "both", "الكل", "الإجمالي", "اجمالي", "إجمالي"}


def total_rows(catalog: list[dict]) -> dict[str, dict[str, str]]:
    """`table -> {column: the total value}` for columns that store a total
    row next to the rows it totals: summing over them counts people twice."""
    out: dict[str, dict[str, str]] = {}
    for t in catalog:
        for c in t.get("columns") or []:
            vals = _values(c.get("top_k"))
            if len(vals) < 3 or _is_num(c.get("dtype")):
                continue
            hit = next((v for v, _ in vals if v.strip().lower() in _TOTAL_VALUES), None)
            if hit is not None:
                out.setdefault(t["name"], {})[c["name"]] = hit
    return out


#: Enumerate a text column live when the sync left no values for it: Postgres
#: keeps no most-common values for a column whose values are equally common,
#: which is exactly gender = f / m / all on the refugee table.
ENRICH_MAX_DISTINCT = 60
ENRICH_MAX_COLUMNS = 80
ENRICH_MAX_ROWS = 5_000_000


async def enrich_facts(catalog: list[dict], run_query, quote=None) -> list[dict]:
    """Fill in the values of short text columns the sync did not enumerate,
    by asking the database (bounded: ENRICH_MAX_COLUMNS columns, small tables).
    Never fails: a column that cannot be read keeps the facts it had."""
    import asyncio
    quote = quote or (lambda n: '"' + n.replace('"', '') + '"')
    gate = asyncio.Semaphore(4)

    # A row estimate of 0 or none is not "empty": Postgres reports 0 for a
    # table ANALYZE never ran on. The food catalog called humanitarian_funding,
    # national_risk and returnees EMPTY, and HR's 9 departments "0 rows", and
    # the designer was told to leave them out (2026-10-03). Ask the database.
    async def exists(t):
        async with gate:
            try:
                got = await run_query(f"SELECT 1 AS present FROM {quote(t['name'])}", 1)
            except Exception:                              # noqa: BLE001
                return
            if got.get("rows"):
                if not t.get("rows"):
                    t["rows"] = None
                    try:
                        n = await run_query(f"SELECT COUNT(*) AS n FROM {quote(t['name'])}", 1)
                        t["rows"] = int((n.get("rows") or [[None]])[0][0]) or None
                    except Exception:                      # noqa: BLE001
                        pass
            else:
                t["rows"] = 0
                t["checked_empty"] = True
    await asyncio.gather(*(exists(t) for t in catalog if not t.get("rows")))

    # A row estimate is the planner's, and goes stale: the app's own database
    # said 13,433 query runs (85,386) and 28 reports (119) (live 2026-10-03).
    # Tables up to ENRICH_MAX_ROWS are counted.
    async def count(t):
        async with gate:
            try:
                n = await run_query(f"SELECT COUNT(*) AS n FROM {quote(t['name'])}", 1)
                t["rows"] = int((n.get("rows") or [[0]])[0][0])
                if t["rows"] == 0:
                    t["checked_empty"] = True
            except Exception:                              # noqa: BLE001
                pass
    await asyncio.gather(*(count(t) for t in catalog
                           if t.get("rows") and t["rows"] <= ENRICH_MAX_ROWS and not t.get("checked_empty")))

    # Statistics measured on a SAMPLE (the sync profiles 1,000 rows of a big
    # table) read as facts about the whole table: "1,000 employees" of
    # 300,024, "geolocation holds only SP" of 27 states, an employee-number
    # range sorted as text (Olist and HR, live 2026-10-03). Such a table is
    # measured again here: its short columns enumerated, its ranges read.
    for t in catalog:
        t["sampled"] = is_sampled(t)
        if t["sampled"]:
            for c in t.get("columns") or []:
                c["sample_only"] = True
                if not _is_num(c.get("dtype")) and not _is_date(c.get("dtype"), c["name"]) \
                        and (c.get("distinct") or 0) <= ENRICH_MAX_DISTINCT:
                    c["top_k"] = None          # enumerate it again, on every row

    async def ranges(t):
        cols = [c for c in t.get("columns") or [] if _is_date(c.get("dtype"), c["name"])
                or (_is_num(c.get("dtype")) and not c["name"].lower().endswith("id"))][:20]
        if not cols:
            return
        sel = ", ".join(f"MIN({quote(c['name'])}) AS lo{i}, MAX({quote(c['name'])}) AS hi{i}"
                        for i, c in enumerate(cols))
        async with gate:
            try:
                got = await run_query(f"SELECT {sel} FROM {quote(t['name'])}", 1)
            except Exception:                              # noqa: BLE001
                return
        row = (got.get("rows") or [None])[0]
        if row:
            for i, c in enumerate(cols):
                c["min"], c["max"] = row[2 * i], row[2 * i + 1]
                c["range_exact"] = True
    await asyncio.gather(*(ranges(t) for t in catalog
                           if t.get("sampled") and (t.get("rows") or 0) <= ENRICH_MAX_ROWS))

    todo = []
    for t in catalog:
        if (t.get("rows") or 0) > ENRICH_MAX_ROWS or t.get("checked_empty"):
            continue
        for c in t.get("columns") or []:
            if c.get("top_k") or _is_num(c.get("dtype")) or _is_date(c.get("dtype"), c["name"]):
                continue
            d = c.get("distinct")
            if d is not None and d > ENRICH_MAX_DISTINCT:
                continue
            todo.append((t, c))
    async def one(t, c):
        async with gate:
            try:
                q = (f"SELECT {quote(c['name'])} AS value, COUNT(*) AS n FROM {quote(t['name'])} "
                     f"GROUP BY {quote(c['name'])} ORDER BY n DESC")
                got = await run_query(q, ENRICH_MAX_DISTINCT + 1)
            except Exception:                              # noqa: BLE001
                return
            rows = got.get("rows") or []
            if 0 < len(rows) <= ENRICH_MAX_DISTINCT:
                total = sum(int(r[1] or 0) for r in rows) or 1
                c["top_k"] = [{"value": r[0], "count": int(r[1] or 0)} for r in rows if r[0] is not None]
                c["distinct"] = len(c["top_k"])
                c["sample_only"] = False
                nulls = sum(int(r[1] or 0) for r in rows if r[0] is None)
                if c.get("null_ratio") is None:
                    c["null_ratio"] = nulls / total
    # The busiest tables first: the budget is spent where the rows are.
    todo.sort(key=lambda tc: -(tc[0].get("rows") or 0))
    await asyncio.gather(*(one(t, c) for t, c in todo[:ENRICH_MAX_COLUMNS]))
    return catalog


#: The sync profiles big tables on this many rows.
SAMPLE_ROWS = 1000


def is_sampled(t: dict) -> bool:
    """Whether a table's statistics describe something other than the table
    as it is now: a sample of a big table, or a sync from when the table was
    smaller (the app's own agent_runs: stats of 3 rows, 350 rows live). Its
    counted values add up to well under the rows it has."""
    rows = t.get("rows") or 0
    if rows < 20:
        return False
    seen = [sum(n or 0 for _, n in _values(c.get("top_k"))) for c in t.get("columns") or [] if c.get("top_k")]
    if seen:
        return max(seen) < 0.9 * rows
    distinct = [c.get("distinct") or 0 for c in t.get("columns") or []]
    return rows > SAMPLE_ROWS * 2 and bool(distinct) and 0 < max(distinct) <= SAMPLE_ROWS


def table_warnings(table: dict) -> list[str]:
    """What a designer must know before using this table, in plain words."""
    out: list[str] = []
    cols = table.get("columns") or []
    rows = table.get("rows")
    if rows == 0 and table.get("checked_empty"):
        out.append("this table is EMPTY: do not use it")
        return out
    item_cols = [c["name"] for c in cols if _ITEM_NAME.search(c["name"]) and not _is_num(c.get("dtype"))]
    for c in cols:
        name, nulls, vals = c["name"], c.get("null_ratio"), _values(c.get("top_k"))
        distinct = c.get("distinct")
        if c.get("sample_only"):
            # Nothing measured on a sample is stated as true of the table.
            if _is_date(c.get("dtype"), name) and c.get("range_exact") and str(c.get("max") or "").startswith("9999"):
                out.append(f"{name} = '{str(c['max'])[:10]}' marks a record that is STILL OPEN (current): filter "
                           f"{name} = '{str(c['max'])[:10]}' for current rows; never subtract or chart that date")
            continue
        if _UNIT_NAME.search(name) and (distinct or len(vals)) and (distinct or len(vals)) > 1:
            units = ", ".join(v for v, _ in vals[:8])
            nums = [x["name"] for x in cols if _is_num(x.get("dtype")) and not _YEAR_NAME.search(x["name"])
                    and not x["name"].lower().endswith("_id") and x["name"] not in ("latitude", "longitude")]
            what = f" ({', '.join(item_cols)})" if item_cols else ""
            out.append(f"{', '.join(nums) or 'the numbers'} are in {distinct or len(vals)} different units "
                       f"({units}): never SUM or AVG them across items. Compare each item{what} with "
                       f"ITSELF -- over time, as % change, or as an index -- or group by the item")
        if nulls is not None and nulls >= 0.5 and not _is_num(c.get("dtype")):
            only = f"; its only values are {', '.join(repr(v) for v, _ in vals[:3])}" \
                if vals and len(vals) <= 3 else ""
            out.append(f"{name} is {round(nulls * 100)}% empty{only}: "
                       f"a breakdown or join by {name} covers only a small part of the rows")
        elif vals and 1 <= len(vals) <= 2 and distinct is not None and distinct <= 2 \
                and not _is_num(c.get("dtype")) and (rows or 0) > 5:
            out.append(f"{name} holds only {', '.join(repr(v) for v, _ in vals)}: "
                       f"it is not a useful breakdown")
        tot = next((v for v, _ in vals if v.strip().lower() in _TOTAL_VALUES), None) \
            if len(vals) >= 3 and not _is_num(c.get("dtype")) else None
        if tot is not None:
            out.append(f"{name} = {tot!r} rows are TOTALS of the other {name} rows: filter {name} = "
                       f"{tot!r} for a total, or {name} <> {tot!r} for a breakdown -- never sum both")
        if _is_date(c.get("dtype"), name) and str(c.get("max") or "").startswith("9999"):
            out.append(f"{name} = '{str(c['max'])[:10]}' marks a record that is STILL OPEN (current): filter "
                       f"{name} = '{str(c['max'])[:10]}' for current rows; never subtract or chart that date")
        if _YEAR_NAME.search(name) and vals and len(vals) <= 6:
            years = sorted(v for v, _ in vals)
            out.append(f"{name} has ONLY these values: {', '.join(years)} -- use them as they are, "
                       f"say the year in titles, and never join or filter on a year that is not listed")
    return out


#: Characters of facts a prompt may carry. The app's own database has 70
#: tables and 557 columns; in full that is a prompt the local model cannot
#: hold. Past the budget the smaller tables are listed by name and columns.
FACTS_BUDGET = 30_000


def facts_text(catalog: list[dict], max_values: int = 12, budget: int = FACTS_BUDGET) -> str:
    """The catalog as a designer should read it: columns with what they hold."""
    full = {t["name"]: _table_facts(t, max_values) for t in catalog}
    if sum(len(b) for b in full.values()) <= budget:
        return "\n\n".join(full[t["name"]] for t in catalog)
    # Biggest tables in full, the rest in one line each.
    keep, used = set(), 0
    for t in sorted(catalog, key=lambda t: -(t.get("rows") or 0)):
        if t.get("checked_empty"):
            continue
        if used + len(full[t["name"]]) <= budget * 0.8:
            keep.add(t["name"])
            used += len(full[t["name"]])
    out = []
    for t in catalog:
        if t["name"] in keep:
            out.append(full[t["name"]])
        elif t.get("checked_empty"):
            out.append(f"TABLE {t['name']}: EMPTY")
        else:
            rows = t.get("rows")
            cols = ", ".join(c["name"] for c in t.get("columns") or [])
            out.append(f"TABLE {t['name']}" + (f" (~{rows:,} rows)" if rows else "") + f": {_short(cols, 300)}")
    return _short("\n\n".join(out), budget + 2000)


def _table_facts(t: dict, max_values: int = 12) -> str:
    if True:
        rows = t.get("rows")
        head = f"TABLE {t['name']}" + (f" (~{rows:,} rows)" if isinstance(rows, int) and rows > 0
                                         else " (EMPTY)" if t.get("checked_empty") else "")
        if t.get("description"):
            head += f"\n  about: {_short(t['description'], 300)}"
        lines = [head]
        if t.get("sampled"):
            lines.append(f"  (statistics marked 'sample' were measured on part of the ~{rows:,} rows: "
                         f"they show what values look like, not how many there are)")
        for c in t.get("columns") or []:
            bits = [f"{c['name']} ({c.get('dtype') or '?'})"]
            if c.get("sample_only"):
                bits.append("sample")
                if c.get("distinct") and c["distinct"] >= SAMPLE_ROWS * 0.8:
                    c = {**c, "distinct": None}
                    bits.append("mostly unique")
                if not c.get("range_exact"):
                    c = {**c, "min": None, "max": None}
            nulls = c.get("null_ratio")
            if isinstance(nulls, (int, float)) and nulls >= 0.05:
                bits.append(f"{round(nulls * 100)}% empty")
            vals = _values(c.get("top_k"))
            distinct = c.get("distinct")
            if vals and (distinct is None or distinct <= 40) and not (
                    _is_num(c.get("dtype")) and not _YEAR_NAME.search(c["name"]) and len(vals) > 8):
                shown = ", ".join(f"{_short(v, 30)}" + (f" ({n})" if n is not None else "")
                                  for v, n in vals[:max_values])
                more = f" … {distinct} values" if distinct and distinct > max_values else ""
                bits.append(f"values: {shown}{more}")
            elif distinct is not None:
                bits.append(f"{distinct:,} distinct")
            if c.get("min") is not None and c.get("max") is not None and (
                    _is_num(c.get("dtype")) or _is_date(c.get("dtype"), c["name"])):
                bits.append(f"range {_short(c['min'], 20)} … {_short(c['max'], 20)}")
            if c.get("description"):
                bits.append(f"— {_short(c['description'], 110)}")
            lines.append("  - " + "; ".join(bits))
        for w in table_warnings(t):
            lines.append(f"  ! {w}")
        return "\n".join(lines)


def mixed_unit_tables(catalog: list[dict]) -> dict[str, dict]:
    """`table -> {"unit": col, "items": [cols], "measures": [cols]}` for every
    table whose numbers come in several units."""
    out = {}
    for t in catalog:
        cols = t.get("columns") or []
        for c in cols:
            vals = _values(c.get("top_k"))
            n = c.get("distinct") or len(vals)
            if _UNIT_NAME.search(c["name"]) and n and n > 1:
                # What a price is OF: the commodity (or its id), never a group
                # of commodities such as a category.
                items = [x["name"] for x in cols if x["name"] != c["name"] and _ITEM_NAME.search(x["name"])]
                measures = [x["name"] for x in cols if _is_num(x.get("dtype")) and not _YEAR_NAME.search(x["name"])
                            and not x["name"].lower().endswith("_id")
                            and x["name"].lower() not in ("latitude", "longitude")]
                out[t["name"]] = {"unit": c["name"], "items": items + [c["name"]], "measures": measures,
                                  "values": [v for v, _ in vals[:6]]}
                break
    return out


# ── 2. brief ────────────────────────────────────────────────────────────────

BRIEF_SCHEMA = {
    "type": "object",
    "required": ["language", "role", "understanding", "questions", "cannot_answer"],
    "properties": {
        "language": {"type": "string"},
        "role": {"type": "string"},
        "understanding": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question", "decision", "tables", "how"],
                "properties": {
                    "question": {"type": "string"},
                    "decision": {"type": "string"},
                    "tables": {"type": "array", "items": {"type": "string"}},
                    "how": {"type": "string"},
                },
            },
        },
        "cannot_answer": {"type": "array", "items": {"type": "string"}},
        "dashboards": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "questions"],
                "properties": {"title": {"type": "string"},
                               "questions": {"type": "array", "items": {"type": "integer"}}},
            },
        },
    },
}

BRIEF_SYSTEM = """You are a senior analyst preparing to build dashboards for \
one specific person. Before any chart, you write a BRIEF.

1. role: what this person is responsible for and the decisions they take \
(budgets, subsidies, stock, prices, staffing, targeting...). Two sentences.
2. understanding: what this database really contains, read from the FACTS \
below (which tables have real data, over which years, at what level: \
national, governorate, item). Two or three sentences, honest about gaps.
3. questions: the 6 to 9 questions whose answers would change one of this \
person's decisions, and that THIS data can answer. For each: the question, \
the decision it informs, the tables it needs, and `how`: the exact measure \
and grain (e.g. "price of each commodity per month, % change vs the same \
month a year earlier", "share of poor people per governorate x population = \
number of poor people"). Prefer questions that reveal something the person \
does not already know: what changed fastest, where the most people are \
affected, what is out of line, what moves together. Ask about the WORLD the \
data describes (prices, people, places), never about the data itself (units, \
codes, data quality). Cover every table that bears on this person's \
decisions at least once (a population group growing fast is a demand \
question), and skip the rest. Never ask a question that your own \
`understanding` says the data cannot answer.
4. cannot_answer: what this person would want but this data cannot tell \
(missing breakdowns, old years, empty tables) -- so nobody is misled.

Be brief -- every word costs the person waiting time: role and \
understanding at most 2 sentences each; each question at most 25 words, \
`decision` at most 15, `how` at most 25; at most 5 cannot_answer lines of 20 \
words.
5. dashboards: group the questions into {count} dashboards by subject (each \
built on ONE query, so its questions should need the same tables): a title \
and the question numbers (1-based) it answers.

Rules: read the FACTS, and quote only numbers that appear in them (row \
counts, years, values) -- never invent a count. A column that is mostly empty or has one value cannot \
be a breakdown. Numbers in different units are never added or averaged \
together. A table with only old years answers questions about those years \
only, and says so. Ignore tables irrelevant to this person's job. Write \
`role`, `understanding`, every question and every `cannot_answer` line in \
the LANGUAGE of the person's request (`language` = its ISO code, e.g. "ar")."""


def build_brief_prompt(facts: str, persona: str, request: str | None,
                       joins_text: str = "", count: int = 3) -> list[dict]:
    user = (f"The person: {persona}\n"
            + (f"Their request, in their words: {request}\n" if request else "")
            + f"\nFACTS ABOUT THE DATABASE (measured)\n{facts}{joins_text}\n\n"
            "Write the brief.")
    return [{"role": "system", "content": BRIEF_SYSTEM.replace("{count}", str(count))},
            {"role": "user", "content": user}]


# ── 3. design ───────────────────────────────────────────────────────────────

WIDGET_TYPES = ("kpi", "bar", "line", "pie", "table")
AGGREGATIONS = ("sum", "avg", "count", "countd", "min", "max")

DESIGN_SCHEMA = {
    "type": "object",
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "purpose", "sql", "widgets"],
                "properties": {
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "sql": {"type": "string"},
                    "widgets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["widget_type", "title", "question", "dimension",
                                         "dimension2", "measure", "aggregation"],
                            "properties": {
                                "widget_type": {"type": "string", "enum": list(WIDGET_TYPES)},
                                "title": {"type": "string"},
                                "question": {"type": "string"},
                                "dimension": {"type": "string"},
                                "dimension2": {"type": "string"},
                                "measure": {"type": "string"},
                                "aggregation": {"type": "string", "enum": list(AGGREGATIONS)},
                                "filter_column": {"type": "string"},
                                "filter_value": {"type": "string"},
                                "sort": {"type": "string", "enum": ["", "asc", "desc"]},
                                "limit": {"type": "integer"},
                                "dimension_granularity": {"type": "string",
                                                          "enum": ["", "year", "quarter", "month"]},
                                "columns": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
    },
}

DESIGN_SYSTEM = """You turn an analyst's BRIEF into dashboards. Each dashboard \
is ONE SQL SELECT (its dataset) plus 4 to 6 charts over that query's output \
columns. Write the simplest SQL that answers (a few CTEs, no unused columns) \
and keep titles short: the person is waiting for it. Every chart answers one question of the brief; its `question` field \
repeats that question and its `title` states what the chart shows in plain \
words, in the language of the brief.

SQL -- build the dataset at the grain the questions need:
- one row per item per period (e.g. commodity x month) or per place, never one \
row per raw record when a summary is meant;
- compute the measures the questions need IN SQL, with clear snake_case \
aliases. Change and level are always computed PER ITEM -- partition by every \
column that identifies the series (item AND market/place/unit), never by a \
group of different items such as a category:
  * % change vs a year earlier: self-join the same item on period = period - \
interval '1 year' (safer than LAG when months are missing);
  * index vs a base period: value / the item's own first value x 100;
  * volatility: the standard deviation of the item's monthly % change, or its \
std / mean -- never the raw std of prices (dear items always win);
  * a rate x population = number of people; a share of a total;
  * a rate is SUM(part) / SUM(whole) at the grain of the chart -- never the \
AVG of rates of groups of different size; a ranking of a ratio (bad reviews \
per seller) shows only groups with enough volume -- put that minimum on the \
ranking chart itself (filter_column total_orders, filter_value ">= 20"), never \
as a WHERE/HAVING on the whole dataset, or every total leaves the small groups out;
- when KPIs need "the latest period", add a 0/1 column such as is_latest \
(1 on the most recent period OF EACH ITEM) and filter the KPI on it;
- use ONLY tables and columns in the FACTS, ONLY the joins listed, ONLY filter \
values that appear in the FACTS (exact spelling and case);
- join places on their codes (admin1_code, ..._code) when both tables have \
one -- names are spelled differently across sources; never wrap a joined \
measure in COALESCE(..., 0): a failed join must stay visible as empty;
- a column that is mostly empty or has a single value is never a join key or \
a breakdown;
- numbers in different units (see the ! lines) are NEVER summed or averaged \
across items: group by the item, or turn them into % change / index first \
(percentages and indexes CAN then be averaged across items);
- an old year stays its year: name it in the title ("poverty, 2014");
- never UNION ALL different subjects into one result (columns of different \
types and meanings); never LEFT JOIN two one-to-many tables to the same rows \
and count both -- aggregate each in its own CTE first;
- ONE dashboard = ONE subject at ONE grain. Never CROSS JOIN or JOIN ... ON \
TRUE to put unrelated tables side by side: every row repeats and every SUM is \
multiplied. A question that needs a table which does not join on a key \
belongs to another dashboard -- leave it out;
- alias every output column with AS; one SELECT (WITH ... SELECT is fine), \
no semicolons, no colon inside string literals; PostgreSQL syntax unless the \
facts say otherwise.

CHARTS (fields not used: "" or 0 or []):
- kpi: one headline ANSWER (a % change, a number of people, the highest or \
lowest value), never a count of rows or of items listed. measure = a NUMERIC column; aggregation sum/avg/max/min, \
or count/countd of anything. Use filter_column/filter_value (e.g. is_latest = \
1) to pick the period. Never max/min of a text column.
- line: dimension = the date column (dimension_granularity month, quarter or \
year when it is a raw date); dimension2 = the item column to draw one line per \
item (at most ~8 items: pick them with filter_column and filter_value \
"Rice|Lentils|Sugar" -- several values separated by |, spelled exactly as in \
the FACTS).
- bar: dimension = a category with at least 2 values; sort desc and a limit \
(10-15) for rankings; dimension2 optional for side-by-side groups.
- pie: a share of a whole -- only for counts or sums of the SAME unit, at most \
6 slices.
- table: `columns` = the output columns to list; dimension = the first of them; \
sort desc on the column that matters (put it as measure); limit 10-25.
- dimension, dimension2, measure, filter_column and every entry of `columns` \
MUST be output aliases of that dashboard's SQL.

Make the dashboards DIFFERENT: each answers different questions of the brief \
(e.g. prices and inflation of staples; where the poor live and how many; \
pressure from new population such as refugees). A chart that only counts rows, \
or draws one number against itself, is not allowed."""


def build_design_prompt(brief: dict, facts: str, persona: str, title: str,
                        questions: list[dict], joins_text: str = "") -> list[dict]:
    """Ask for ONE dashboard answering one group of the brief's questions.

    One call per dashboard, concurrently: a single call for three dashboards
    ran past the model timeout on the local Qwen (7,000 tokens of output), and
    a dashboard that fails its check is repaired without re-asking for the
    ones that passed."""
    qs = "\n".join(f"{i + 1}. {q.get('question')} -- decision: {q.get('decision')} -- "
                   f"tables: {', '.join(q.get('tables') or [])} -- how: {q.get('how')}"
                   for i, q in enumerate(questions))
    no = "\n".join(f"- {x}" for x in brief.get("cannot_answer") or [])
    user = (f"FOR: {persona} -- {brief.get('role', '')}\n"
            f"LANGUAGE for titles: {brief.get('language') or 'en'}\n\n"
            f"THIS DASHBOARD: {title}\nITS QUESTIONS\n{qs}\n"
            + (f"\nTHE DATA CANNOT ANSWER (do not try)\n{no}\n" if no else "")
            + f"\nFACTS ABOUT THE TABLES (measured)\n{facts}{joins_text}\n\n"
            "Return exactly 1 dashboard under 'proposals'.")
    return [{"role": "system", "content": DESIGN_SYSTEM}, {"role": "user", "content": user}]


def question_groups(brief: dict, count: int) -> list[tuple[str, list[dict]]]:
    """The brief's dashboards as (title, questions); its own grouping when it
    gave a usable one, else the questions dealt round-robin."""
    qs = [q for q in brief.get("questions") or [] if isinstance(q, dict) and q.get("question")]
    out: list[tuple[str, list[dict]]] = []
    used: set[int] = set()
    for d in brief.get("dashboards") or []:
        if not isinstance(d, dict):
            continue
        picked = []
        for n in d.get("questions") or []:
            try:
                i = int(n) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(qs) and i not in used:
                used.add(i)
                picked.append(qs[i])
        if picked:
            out.append((str(d.get("title") or picked[0]["question"]), picked))
    if not out:
        k = max(1, min(count, len(qs)))
        out = [(qs[i]["question"], qs[i::k]) for i in range(k)]
    left = [q for i, q in enumerate(qs) if i not in used] if used else []
    if left and len(out) < count:
        out.append((left[0]["question"], left))
    return out[:count]


def tables_for(questions: list[dict], catalog: list[dict], joins: list[dict] | None) -> list[dict]:
    """The catalog narrowed to the tables these questions name, plus the
    tables they join to -- a shorter prompt is a faster and more careful one."""
    names = {t for q in questions for t in (q.get("tables") or [])}
    for j in joins or []:
        if j.get("from_table") in names or j.get("to_table") in names:
            names |= {j.get("from_table"), j.get("to_table")}
    picked = [t for t in catalog if t["name"] in names]
    return picked or catalog


# ── 4. check what each query RETURNS ───────────────────────────────────────

# Whole words between underscores: "duration" contains "ratio" (the app's own
# database, live 2026-10-03: total_duration_ms was refused as a percentage).
_TITLE_RATE = re.compile(r"\b(rate|ratio|share|percent|percentage)\b|%", re.I)
_RATE_WORDS = re.compile(r"(^|_)(rate|ratio|pct|percent|percentage|share)(_|$)|_per_", re.I)
_SIZE_WORDS = re.compile(r"^(total_|n_|num_|count|orders$|total$|n$)|(_count|_orders|_total)$", re.I)
_PCT_WORDS = re.compile(r"(pct|percent|ratio|rate|index|change|share|growth|yoy|mom|_per_|score)", re.I)


def normalise_widget(w: dict) -> dict:
    """A proposed chart in the shape the client builds and the checks read."""
    out = {k: w.get(k) for k in ("widget_type", "title", "question", "dimension", "dimension2",
                                 "measure", "aggregation", "sort", "limit",
                                 "dimension_granularity", "columns")}
    for k in ("dimension", "dimension2", "measure", "sort", "dimension_granularity", "title", "question"):
        out[k] = str(out.get(k) or "").strip()
    out["columns"] = [str(c).strip() for c in (w.get("columns") or []) if str(c).strip()]
    try:
        out["limit"] = max(0, int(w.get("limit") or 0))
    except (TypeError, ValueError):
        out["limit"] = 0
    fc, fv = str(w.get("filter_column") or "").strip(), w.get("filter_value")
    if fc and fv is not None and str(fv).strip() != "":
        # "total_orders >= 5" / ">= 5": a comparison written into the value
        # (Olist, live 2026-10-03) becomes the comparison it means.
        cmp = re.match(r"^\s*(?:" + re.escape(fc) + r"\s*)?(>=|<=|!=|<>|>|<|=)\s*(.+?)\s*$", str(fv), re.I)
        if cmp:
            op = {">=": "gte", "<=": "lte", ">": "gt", "<": "lt", "=": "eq", "!=": "neq", "<>": "neq"}[cmp.group(1)]
            out["filters"] = [{"column": fc, "op": op, "value": _typed(cmp.group(2).strip("'\""))}]
        else:
            # "Wheat flour|Rice|Oil (maize)": a few items on one chart.
            parts = [p.strip() for p in str(fv).split("|") if p.strip()]
            out["filters"] = ([{"column": fc, "op": "in", "value": [_typed(p) for p in parts]}]
                              if len(parts) > 1 else [{"column": fc, "op": "eq", "value": _typed(fv)}])
    if out["widget_type"] == "kpi":
        out["dimension"] = out["dimension2"] = ""
    if out["widget_type"] == "table" and out["columns"] and not out["dimension"]:
        out["dimension"] = out["columns"][0]
    return out


def _typed(v):
    s = str(v).strip()
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except ValueError:
        return {"true": True, "false": False}.get(s.lower(), s)


def _num_share(series) -> float:
    import pandas as pd
    vals = pd.to_numeric(series, errors="coerce")
    present = series.notna().sum()
    return float(vals.notna().sum()) / present if present else 0.0


def volume_cut(sql: str) -> tuple[str, str] | None:
    """`(column, threshold)` when the query's final SELECT drops small groups
    (WHERE total_orders >= 10): its totals then leave those groups out. Olist,
    live 2026-10-04: "late orders, SP = 5,661", really 6,016."""
    try:
        import sqlglot
        import sqlglot.expressions as exp
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:                                    # noqa: BLE001
        return None
    for clause in (tree.args.get("where"), tree.args.get("having")):
        if clause is None:
            continue
        for cmp in clause.find_all(exp.GTE, exp.GT):
            col, lit = cmp.this, cmp.expression
            if isinstance(col, exp.Column) and isinstance(lit, exp.Literal) and _SIZE_WORDS.search(col.name):
                try:
                    if float(str(lit.this)) >= 2:
                        return col.name, str(lit.this)
                except ValueError:
                    continue
    return None


def coalesced_to_zero(sql: str) -> set[str]:
    """Output names whose value is COALESCE(..., 0) of something -- directly or
    through a CTE column of that name. Only these can hide a failed join as a
    zero; a rate that is genuinely 0 for most small cities is not one (Olist,
    live 2026-10-04: real zero failure rates were refused)."""
    try:
        import sqlglot
        import sqlglot.expressions as exp
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:                                    # noqa: BLE001
        return set()
    filled: set[str] = set()
    for _ in range(3):
        for sel in tree.find_all(exp.Select):
            for proj in sel.expressions:
                name = proj.alias_or_name.lower()
                direct = any(isinstance(c, exp.Coalesce) and any(
                    isinstance(a, exp.Literal) and str(a.this) in ("0", "0.0")
                    for a in [*(c.expressions or [])])
                    for c in proj.find_all(exp.Coalesce))
                inherited = any(col.name.lower() in filled for col in proj.find_all(exp.Column))
                if direct or inherited:
                    filled.add(name)
    return filled


def assess(proposal: dict, columns: list[str], rows: list[list],
           mixed: dict[str, dict] | None = None, bad: set[int] | None = None) -> list[str]:
    """What is wrong with each chart, judged on the query's real output.

    Empty list = every chart draws something worth reading. Each message names
    the chart and the fix, because it goes back to the model as is.
    """
    import pandas as pd
    problems: list[str] = []
    if not rows:
        return ["the query returned no rows: a filter, join or year does not match the data "
                "(check the values listed in the FACTS)"]
    df = pd.DataFrame(rows, columns=columns)
    have = {c.lower(): c for c in df.columns}

    def col(name: str):
        c = have.get((name or "").lower())
        return df[c] if c is not None else None

    last_count = 0
    zero_filled = coalesced_to_zero(proposal.get("sql") or "")
    cut = volume_cut(proposal.get("sql") or "")
    unit_cols = [c for c in df.columns if _UNIT_NAME.search(c)]
    date_cols = [c for c in df.columns if re.search(r"(date|month|period|week|quarter)$|^(year|yr)$", c, re.I)
                 and df[c].nunique() > 1]
    for i, w in enumerate(proposal.get("widgets") or []):
        if bad is not None and i > 0 and len(problems) > last_count:
            bad.add(i - 1)
        last_count = len(problems)
        t, title = w.get("widget_type"), w.get("title") or w.get("widget_type")
        frame = df
        for f in w.get("filters") or []:
            s = col(f.get("column"))
            if s is None:
                problems.append(f"'{title}': filter column '{f.get('column')}' is not in the SQL output")
                break
            s = frame[s.name]          # filters narrow one after another
            if f.get("op") in ("gt", "gte", "lt", "lte", "neq"):
                num = pd.to_numeric(s, errors="coerce")
                v = f.get("value")
                mask = {"gt": num > v, "gte": num >= v, "lt": num < v, "lte": num <= v}.get(f["op"]) \
                    if isinstance(v, (int, float)) else (s.astype(str) != str(v))
                if mask is None or not mask.any():
                    problems.append(f"'{title}': no row has {f.get('column')} {f['op']} {v!r}")
                    break
                frame = frame[mask.values]
                continue
            wanted = f.get("value") if isinstance(f.get("value"), list) else [f.get("value")]
            wanted_l = {str(v).strip().lower() for v in wanted}
            norm = s.astype(str).str.strip().str.lower()
            missing = [v for v in wanted if str(v).strip().lower() not in set(norm)]
            if missing:
                problems.append(f"'{title}': no row has {f.get('column')} = "
                                f"{', '.join(repr(v) for v in missing)} -- use values from the FACTS")
                break
            mask = norm.isin(wanted_l)
            frame = frame[mask.values]
        else:
            names = [w.get("dimension"), w.get("dimension2"), w.get("measure"), *(w.get("columns") or [])]
            missing = [n for n in names if n and col(n) is None]
            if missing:
                problems.append(f"'{title}': {', '.join(missing)} is not an output column of the SQL")
                continue
            agg = w.get("aggregation") or "sum"
            m = col(w.get("measure")) if w.get("measure") else None
            if m is not None:
                m = frame[m.name]
                if m.notna().mean() < 0.5:
                    problems.append(f"'{title}': {w['measure']} is empty in {round((1 - m.notna().mean()) * 100)}% "
                                    f"of rows -- the join or filter that feeds it does not match the data")
                if agg not in ("count", "countd") and t != "table" and _num_share(m.dropna()) < 0.9:
                    problems.append(f"'{title}': {agg} of {w['measure']} -- it is text, not a number. "
                                    f"Use a numeric measure (or count)")
                elif agg in ("avg", "sum") and t != "table" and m.dropna().nunique() <= 1 and len(frame) > 2:
                    problems.append(f"'{title}': {w['measure']} has the same value on every row -- nothing to show")
                elif agg == "sum" and t == "kpi" and not w.get("dimension"):
                    # A KPI adding a per-group number that the join repeated on
                    # every row: "Total delivered revenue: 337.05M" summed each
                    # method's revenue once per month (Olist, live 2026-10-04;
                    # really 15.4M).
                    for c in frame.columns:
                        if c == m.name or pd.api.types.is_numeric_dtype(frame[c]) or not 2 <= frame[c].nunique() <= 50:
                            continue
                        g = frame.groupby(c)[m.name]
                        sizes, uniq = g.size(), g.nunique(dropna=True)
                        multi = sizes[sizes > 1].index
                        if len(multi) >= 2 and (uniq.loc[multi] <= 1).mean() >= 0.8 and m.nunique() > 1:
                            problems.append(f"'{title}': {w['measure']} repeats the same value on the "
                                            f"{int(sizes.max())} rows of each {c} -- adding it up counts each "
                                            f"{c} several times. Give the total its own column or query")
                            break
                elif agg == "sum":
                    # A per-group number copied onto every row of a finer grain
                    # (a department's headcount on each of its job-title rows):
                    # summing it multiplies it. HR, live 2026-10-03.
                    keys = [col(k).name for k in (w.get("dimension"), w.get("dimension2")) if k and col(k) is not None]
                    if keys:
                        g = frame.groupby(keys)[m.name]
                        sizes, uniq = g.size(), g.nunique(dropna=True)
                        multi = sizes[sizes > 1].index
                        if len(multi) >= 2 and (uniq.loc[multi] <= 1).mean() >= 0.8 \
                                and frame[m.name].nunique() > 1:
                            problems.append(f"'{title}': {w['measure']} repeats the same value on the "
                                            f"{int(sizes.max())} rows of each {', '.join(keys)} -- the query's grain "
                                            f"is finer than this number, so SUM multiplies it. Use max/avg, or "
                                            f"give this number its own dataset at its own grain")
            if m is not None and t != "table" and _TITLE_RATE.search(title or "") \
                    and not _RATE_WORDS.search(w.get("measure") or ""):
                vals = pd.to_numeric(m, errors="coerce").dropna()
                if len(vals) and (vals % 1 == 0).all() and vals.max() > 1:
                    # "Cancellation rate by payment method: credit_card 444" --
                    # the bars were cancelled orders (Olist, live 2026-10-04).
                    problems.append(f"'{title}': the title promises a rate/ratio/share but the chart draws "
                                    f"{w['measure']}, a count. Compute the rate in SQL (SUM(x)/SUM(n)) and "
                                    f"draw that column, or retitle the chart")
            if m is not None and _RATE_WORDS.search(w.get("measure") or "") and (agg == "max" or w.get("sort") == "desc"
                                                                                  or t == "kpi"):
                # "Highest low-score rate: 1" -- a seller with one bad review.
                size = next((c for c in frame.columns if _SIZE_WORDS.search(c) and c != m.name
                             and pd.api.types.is_numeric_dtype(frame[c])), None)
                if size is not None:
                    vals = pd.to_numeric(m, errors="coerce")
                    top = frame.loc[vals.nlargest(min(10, int(vals.notna().sum()))).index, size]
                    if len(top) and pd.to_numeric(top, errors="coerce").min() < 10:
                        problems.append(f"'{title}': the top of this {w['measure']} ranking includes groups with "
                                        f"only {int(pd.to_numeric(top, errors='coerce').min())} {size} -- a rate "
                                        f"from a handful of cases is noise. Filter this chart to groups with enough "
                                        f"volume: filter_column {size}, filter_value \">= 20\"")
            if t == "line" and w.get("dimension"):
                xs = frame[col(w["dimension"]).name]
                nums = pd.to_numeric(xs, errors="coerce").dropna()
                # Fractions on the axis are a measurement, not a period or a step.
                if pd.api.types.is_numeric_dtype(xs) and xs.nunique() > 40 and len(nums) \
                        and (nums % 1 != 0).mean() > 0.5:
                    problems.append(f"'{title}': {w['dimension']} is a continuous number on the x-axis "
                                    f"({xs.nunique()} values) -- bin it into ranges in SQL, or put a date "
                                    f"on the axis")
            if m is not None and agg == "sum" and _RATE_WORDS.search(w.get("measure") or "") and t != "table":
                # Percentages do not add up: "overall failure rate" was the SUM
                # of 5,000 groups' rates (Olist, live 2026-10-03).
                keys = [col(k).name for k in (w.get("dimension"), w.get("dimension2")) if k and col(k) is not None]
                multi = (frame.groupby(keys).size() > 1).any() if keys else len(frame) > 1
                if multi:
                    problems.append(f"'{title}': SUM of {w['measure']} adds percentages of different groups -- "
                                    f"a rate is SUM(part)/SUM(total) at the chart's grain; compute it in SQL at "
                                    f"that grain (or chart the counts)")
            if m is not None and agg == "avg" and _RATE_WORDS.search(w.get("measure") or ""):
                # The average of group rates is not the rate: a state with 3
                # orders weighs as much as one with 40,000 (Olist, live
                # 2026-10-03: "overall cancellation rate" averaged 441 pairs).
                size = next((c for c in frame.columns if _SIZE_WORDS.search(c) and c != m.name
                             and pd.api.types.is_numeric_dtype(frame[c])), None)
                if size is not None:
                    keys = [col(k).name for k in (w.get("dimension"), w.get("dimension2")) if k and col(k) is not None]
                    grp = frame.groupby(keys)[size] if keys else None
                    multi = (grp.size() > 1).any() if grp is not None else len(frame) > 1
                    sizes = pd.to_numeric(frame[size], errors="coerce")
                    if multi and sizes.max() > 3 * max(1, sizes.min()):
                        problems.append(f"'{title}': averages {w['measure']} over rows of very different size "
                                        f"({size} from {int(sizes.min())} to {int(sizes.max())}) -- the average of "
                                        f"rates is not the rate. Compute it as SUM(part)/SUM(total) at the chart's "
                                        f"grain, or weight it")
            if cut and agg in ("sum", "count", "countd") and t != "table":
                problems.append(f"'{title}': the dataset drops every group with {cut[0]} below {cut[1]} "
                                f"(WHERE {cut[0]} >= {cut[1]}), so this total leaves them out. Remove that "
                                f"WHERE and put the minimum on the ranking chart as a filter")
            if m is not None and w["measure"].lower() in zero_filled:
                zeros = (pd.to_numeric(m, errors="coerce") == 0).mean()
                if zeros >= 0.2:
                    problems.append(f"'{title}': {w['measure']} is 0 on {round(zeros * 100)}% of rows -- a "
                                    f"COALESCE(..., 0) is hiding rows the join did not match; join on the "
                                    f"code columns and let unmatched rows stay empty")
            for key in ("dimension", "dimension2"):
                d = w.get(key)
                if d and t in ("bar", "line", "pie"):
                    n = frame[col(d).name].nunique(dropna=True)
                    if n < 2:
                        problems.append(f"'{title}': {d} has a single value here -- not a breakdown")
                    if key == "dimension2" and n > 15 and not w.get("filters"):
                        problems.append(f"'{title}': {n} different {d} -- too many lines/bars; choose a few "
                                        f"with filter_column or drop dimension2")
            late = claims_latest_unfiltered(w, frame, date_cols)
            if late:
                problems.append(late)
            if t == "pie" and w.get("dimension") and frame[col(w["dimension"]).name].nunique() > 8:
                problems.append(f"'{title}': a pie of more than 8 slices -- use a bar")
            # Numbers in several units, aggregated across items.
            if m is not None and agg in ("sum", "avg") and unit_cols and not _PCT_WORDS.search(w["measure"]):
                for u in unit_cols:
                    if frame[u].nunique() > 1:
                        by = {(w.get("dimension") or "").lower(), (w.get("dimension2") or "").lower(),
                              *[(f.get("column") or "").lower() for f in w.get("filters") or []]}
                        units_per_group = None
                        keys = [have[b] for b in by if b in have and b]
                        if keys:
                            units_per_group = frame.groupby(keys)[u].nunique().max()
                        if not keys or (units_per_group or 0) > 1:
                            problems.append(f"'{title}': {agg} of {w['measure']} mixes {frame[u].nunique()} units "
                                            f"({', '.join(map(str, frame[u].dropna().unique()[:4]))}) -- "
                                            f"break it down by the item, or chart a % change / index instead")
                        break
    n_w = len(proposal.get("widgets") or [])
    if bad is not None and n_w and len(problems) > last_count:
        bad.add(n_w - 1)
    return problems


# ── SQL lints: what the rows cannot show ─────────────────────────────────────

def data_end(catalog: list[dict]) -> str | None:
    """The latest real date in the data (ISO), ignoring open-ended sentinels
    such as 9999-01-01."""
    best = None
    for t in catalog:
        for c in t.get("columns") or []:
            if not _is_date(c.get("dtype"), c["name"]):
                continue
            v = str(c.get("max") or "")[:10]
            if len(v) == 10 and v[4] == "-" and "1900" < v < "2200":
                best = v if best is None or v > best else best
    return best


def sql_problems(sql: str, mixed: dict[str, dict] | None,
                 totals: dict[str, dict[str, str]] | None = None, end: str | None = None,
                 joins: list[dict] | None = None, catalog: list[dict] | None = None) -> list[str]:
    """Mistakes in the query's logic that its output cannot reveal.

    Both seen live on the food database (2026-10-03):
      * a "share of each category in the basket" built as SUM(AVG(price)) over
        categories -- a kilo of meat plus one egg plus a bottle of oil;
      * `ROW_NUMBER() ... AS rn` computed to keep each item's latest month and
        never filtered on, so "latest inflation" read fifteen years of history
        (Garlic +358%, from 2016).
    """
    try:
        import sqlglot
        import sqlglot.expressions as exp
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:                                    # noqa: BLE001
        return []
    out: list[str] = []

    # 1. a latest-row rank nobody filters on
    for proj in tree.find_all(exp.Alias):
        if not any(isinstance(n, (exp.RowNumber,)) or n.key in ("rank", "denserank")
                   for n in proj.find_all(exp.Expression)):
            continue
        if not proj.find(exp.Window):
            continue
        name = proj.alias.lower()
        used = False
        for cond in [*tree.find_all(exp.Where), *tree.find_all(exp.Qualify), *tree.find_all(exp.Join)]:
            if any(c.name.lower() == name for c in cond.find_all(exp.Column)):
                used = True
                break
        if not used:
            out.append(f"{name} ranks the rows (ROW_NUMBER/RANK) but no WHERE or JOIN keeps only "
                       f"{name} = 1 -- every period is still in the data, so a 'latest' chart reads "
                       f"the whole history. Filter on it, or add a 0/1 is_latest column")

    # 1a. "today" in data that stopped long ago (HR ends in 2002: tenure to
    #     CURRENT_DATE added 24 years to every open assignment).
    if end and re.search(r"\b(current_date|current_timestamp|now\s*\(|getdate\s*\(|sysdate|date\s*\(\s*'now')",
                         sql, re.I):
        from datetime import date, timedelta
        if end < (date.today() - timedelta(days=180)).isoformat():
            out.append(f"the query uses today's date, but the data ends on {end}: measure 'now' as the "
                       f"data's own latest date (e.g. (SELECT MAX(date) FROM ...)) or '{end}'")

    # 1b. totals summed with their parts (refugees: gender 'all' + 'm' + 'f')
    named = {t.name.lower() for t in tree.find_all(exp.Table)}
    if totals and any(tree.find_all(exp.Sum)):
        for table, cols in totals.items():
            if table.lower() not in named:
                continue
            for col, value in cols.items():
                if not re.search(rf"\b{re.escape(col)}\b\s*(=|<>|!=|\bin\b|\bnot\s+in\b)", sql, re.I):
                    out.append(f"{table}.{col} holds total rows ({col} = '{value}') beside the rows they "
                               f"total, and the query sums without choosing: filter {col} = '{value}' for "
                               f"totals or {col} <> '{value}' for a breakdown")

    # 2. unrelated tables placed side by side: every row repeats
    #    Seen live: refugees by age CROSS JOINed onto 27 governorates, and the
    #    KPI "total refugees" summed 27 copies of each count.
    grouped_ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)
                    if isinstance(c.this, exp.Select) and (c.this.args.get("group") or
                                                          not any(c.this.find_all(exp.AggFunc)))}
    for j in tree.find_all(exp.Join):
        on = j.args.get("on")
        loose = (str(j.args.get("kind") or "").upper() == "CROSS" or (j.args.get("side") is None and on is None
                                                                       and not j.args.get("using"))
                 or (on is not None and on.sql().strip().upper() in ("TRUE", "1 = 1", "1=1"))
                 or (on is not None and not _links_columns(on)))
        if not loose:
            continue
        src = j.this
        name = (src.alias_or_name if hasattr(src, "alias_or_name") else "").lower()
        real = src.name.lower() if isinstance(src, exp.Table) else ""
        many_sub = False
        if isinstance(src, exp.Subquery):
            inner = src.this
            # One row only when it aggregates everything with no GROUP BY.
            many_sub = not (isinstance(inner, exp.Select) and not inner.args.get("group")
                            and any(inner.find_all(exp.AggFunc)))
        if many_sub or real in grouped_ctes or (isinstance(src, exp.Table) and real not in
                                                {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}):
            out.append(f"{name or real} is joined with no key (CROSS JOIN, ON TRUE, or an ON that compares "
                       f"no column of one side with a column of the other) and has many rows: "
                       f"every row of the query repeats once per row of it, so every SUM is multiplied. "
                       f"Join on a key, or leave that subject to another dashboard")

    # 2b. fan trap: two one-to-many joins off one table, then COUNT/SUM --
    #     each count is multiplied by the other. "Most viewed report: 2,099
    #     views" was views x query runs (the app's own database, 2026-10-03).
    for sel in tree.find_all(exp.Select):
        if not sel.args.get("group"):
            continue
        js = [j for j in sel.args.get("joins") or [] if str(j.args.get("side") or "").upper() == "LEFT"]
        if len(js) < 2:
            continue
        joined = {(j.this.alias_or_name or "").lower() for j in js if hasattr(j.this, "alias_or_name")}
        counted = set()
        for agg in sel.find_all(exp.Count, exp.Sum):
            if agg.find_ancestor(exp.Select) is not sel:
                continue
            for c in agg.find_all(exp.Column):
                if (c.table or "").lower() in joined:
                    counted.add(c.table.lower())
        distinct_ok = all(isinstance(a.this, exp.Distinct) for a in sel.find_all(exp.Count)
                          if a.find_ancestor(exp.Select) is sel)
        if len(counted) >= 2 and not distinct_ok:
            out.append(f"{', '.join(sorted(counted))} are both LEFT JOINed to the same rows and counted "
                       f"together: each count is multiplied by the other (fan trap). Aggregate each table "
                       f"in its own CTE, then join the totals")
            break

    # 2a'. two summaries joined on something neither is unique on: seller
    #     stats JOIN city stats ON seller_state = customer_state paired every
    #     seller with every city of its state (Olist, live 2026-10-04).
    grouped = {}
    for c in tree.find_all(exp.CTE):
        inner = c.this
        if isinstance(inner, exp.Select) and inner.args.get("group"):
            keys = set()
            for e in inner.args["group"].expressions:
                if isinstance(e, exp.Column):
                    keys.add(e.name.lower())
                elif isinstance(e, exp.Literal) and str(e.this).isdigit():
                    i = int(str(e.this)) - 1
                    if 0 <= i < len(inner.expressions):
                        keys.add(inner.expressions[i].alias_or_name.lower())
            # Output names of the key columns (a key may be renamed with AS).
            out_keys = set()
            for proj in inner.expressions:
                base = proj.unalias()
                if isinstance(base, exp.Column) and base.name.lower() in keys:
                    out_keys.add(proj.alias_or_name.lower())
            grouped[c.alias_or_name.lower()] = out_keys or keys
    for sel in tree.find_all(exp.Select):
        srcs = {}
        for t in [_from(sel)] + list(sel.args.get("joins") or []):
            node = t.this if t is not None else None
            if isinstance(node, exp.Table) and node.name.lower() in grouped:
                srcs[(node.alias_or_name or node.name).lower()] = node.name.lower()
        for j in sel.args.get("joins") or []:
            node, on = j.this, j.args.get("on")
            if not (isinstance(node, exp.Table) and node.name.lower() in grouped and on is not None):
                continue
            used: dict[str, set[str]] = {}
            for col in on.find_all(exp.Column):
                cte = srcs.get((col.table or "").lower())
                if cte:
                    used.setdefault(cte, set()).add(col.name.lower())
            if len(used) == 2 and all(not grouped[c] <= cols for c, cols in used.items()):
                a, b = list(used)
                out.append(f"{a} and {b} are joined on {', '.join(sorted(used[a]))} = "
                           f"{', '.join(sorted(used[b]))}, which is unique in neither (one row per "
                           f"{', '.join(sorted(grouped[a]))} vs per {', '.join(sorted(grouped[b]))}): every row "
                           f"of one meets every matching row of the other. Keep them in separate dashboards")
                break

    # 2b'. rows repeated by a join to a "many" table, then counted. Olist:
    #     orders LEFT JOIN order_payments inside a CTE, then COUNT(*) and
    #     SUM(CASE status = 'canceled') per state -- an order paid in three
    #     instalments counted three times (SP: 345 cancelled, really 327).
    out.extend(fanout_problems(tree, joins or []))
    out.extend(child_count_problems(tree, joins or []))
    out.extend(sibling_join_problems(tree, joins or []))

    # 2c. joins the database does not know (reports.id = query_runs.dataset_id)
    if joins and catalog:
        from .suggest_dashboard import _table_aliases
        aliases = _table_aliases(tree)
        known_pairs = {frozenset({(j["from_table"].lower(), j["from_column"].lower()),
                                  (j["to_table"].lower(), j["to_column"].lower())}) for j in joins}
        tables = {t["name"].lower() for t in catalog}
        for j in tree.find_all(exp.Join):
            on = j.args.get("on")
            for eq in (on.find_all(exp.EQ) if on is not None else []):
                l, r = eq.this, eq.expression
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
                    continue
                lt, rt = aliases.get((l.table or "").lower()), aliases.get((r.table or "").lower())
                if not lt or not rt or lt not in tables or rt not in tables or lt == rt:
                    continue
                if l.name.lower() == r.name.lower():
                    continue
                if frozenset({(lt, l.name.lower()), (rt, r.name.lower())}) not in known_pairs:
                    out.append(f"{lt}.{l.name} = {rt}.{r.name} is not a relationship of this database -- "
                               f"use only the joins listed")
                    break

    # 3. prices of different items added or averaged together
    if mixed:
        carriers = {m.lower() for t in mixed.values() for m in t["measures"]}
        items = {i.lower() for t in mixed.values() for i in t["items"]}
        units = ", ".join(sorted({v for t in mixed.values() for v in (t.get("values") or [t["unit"]])}))

        def cols(node) -> set[str]:
            return {c.name.lower() for c in node.find_all(exp.Column)}

        def ratio(node) -> bool:
            # (a - b) / b, a / first(a): a ratio of two prices has no unit.
            return any(cols(d.this) & carriers and cols(d.expression) & carriers
                       for d in node.find_all(exp.Div))

        flagged: set[str] = set()
        for _ in range(3):  # CTEs feed each other; three passes settle the names
            for sel in tree.find_all(exp.Select):
                group = sel.args.get("group")
                group_cols = cols(group) if group else set()
                # GROUP BY 1, 2: positions name the projections.
                for e in (group.expressions if group else []):
                    if isinstance(e, exp.Literal) and str(e.this).isdigit():
                        i = int(str(e.this)) - 1
                        if 0 <= i < len(sel.expressions):
                            group_cols |= cols(sel.expressions[i]) | {sel.expressions[i].alias_or_name.lower()}
                for proj in sel.expressions:
                    alias = proj.alias_or_name.lower()
                    used = cols(proj)
                    if isinstance(proj.unalias(), exp.Column) and used & items:
                        items.add(alias)
                    if not used & carriers or ratio(proj):
                        continue
                    for agg in proj.find_all(exp.Sum, exp.Avg):
                        if not cols(agg) & carriers:
                            continue
                        win = agg.parent if isinstance(agg.parent, exp.Window) else None
                        if win is not None:
                            part = set()
                            for e in win.args.get("partition_by") or []:
                                part |= cols(e)
                            ok = bool(part & items)
                        else:
                            ok = bool(group_cols & items)
                        if not ok:
                            key = agg.sql()[:80]
                            if key not in flagged:
                                flagged.add(key)
                                out.append(f"{key} adds or averages prices of DIFFERENT items, which are in "
                                           f"different units ({units}) -- group by the item "
                                           f"({', '.join(sorted(items)[:3])}) or compare % changes instead")
                    carriers.add(alias)
    return out


def many_sides(joins: list[dict]) -> dict[str, set[str]]:
    """`one table -> tables with many rows per row of it`, from the
    relationships' cardinality."""
    out: dict[str, set[str]] = {}
    for j in joins or []:
        card = str(j.get("cardinality") or "").lower()
        a, b = str(j.get("from_table") or "").lower(), str(j.get("to_table") or "").lower()
        if not a or not b or a == b:
            continue
        if card == "many_to_one":
            out.setdefault(b, set()).add(a)
        elif card == "one_to_many":
            out.setdefault(a, set()).add(b)
    return out


def sibling_join_problems(tree, joins: list[dict]) -> list[str]:
    """Two tables that each have several rows per parent, joined to each
    other on the parent's key: every payment meets every item of its order,
    so a SUM of either side is multiplied. "Total revenue: 20.31M" joined
    order_payments to order_items on order_id; it is 16.01M (Olist, live
    2026-10-04, qwen3.5-9b)."""
    import sqlglot.expressions as exp
    # table -> {fk column: parent}
    children: dict[str, dict[str, str]] = {}
    for j in joins or []:
        card = str(j.get("cardinality") or "").lower()
        a, b = str(j.get("from_table") or "").lower(), str(j.get("to_table") or "").lower()
        ca, cb = str(j.get("from_column") or "").lower(), str(j.get("to_column") or "").lower()
        if card == "many_to_one" and a and b and a != b:
            children.setdefault(a, {})[ca] = b
        elif card == "one_to_many" and a and b and a != b:
            children.setdefault(b, {})[cb] = a
    if len(children) < 2:
        return []
    out = []
    for sel in tree.find_all(exp.Select):
        if not any(sel.find_all(exp.Sum, exp.Count, exp.Avg)):
            continue
        alias: dict[str, str] = {}
        for t in [_from(sel)] + list(sel.args.get("joins") or []):
            node = t.this if t is not None else None
            if isinstance(node, exp.Table):
                alias[node.alias_or_name.lower()] = node.name.lower()
        for j in sel.args.get("joins") or []:
            on = j.args.get("on")
            if on is None:
                continue
            for eq in on.find_all(exp.EQ):
                l, r = eq.this, eq.expression
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
                    continue
                ta, tb = alias.get(l.table.lower()), alias.get(r.table.lower())
                if not ta or not tb or ta == tb:
                    continue
                pa = children.get(ta, {}).get(l.name.lower())
                pb = children.get(tb, {}).get(r.name.lower())
                if pa and pa == pb:
                    out.append(f"{ta} and {tb} both have several rows per {_singular(pa)}: joined on "
                               f"{l.name} they pair every {ta} row with every {tb} row of the same "
                               f"{_singular(pa)}, so their SUMs and COUNTs are multiplied. Aggregate each "
                               f"to one row per {_singular(pa)} first, or keep them in separate queries")
                    break
    return out[:2]


def _from(sel):
    """The FROM clause, under either key sqlglot has used for it."""
    return sel.args.get("from") or sel.args.get("from_")


def _singular(name: str) -> str:
    n = name.lower()
    for suf, rep in (("ies", "y"), ("sses", "ss"), ("s", "")):
        if n.endswith(suf) and len(n) > len(suf) + 2:
            return n[: -len(suf)] + rep
    return n


def child_count_problems(tree, joins: list[dict]) -> list[str]:
    """COUNT(*) over a table that has several rows per parent record, named
    as a count of the parent: "total orders" counted from order_payments
    counts payments (Olist, live 2026-10-04: credit card 76,795 "orders",
    76,505 really -- an order paid with two cards counted twice)."""
    import sqlglot.expressions as exp
    parents: dict[str, set[str]] = {}
    for j in joins or []:
        card = str(j.get("cardinality") or "").lower()
        a, b = str(j.get("from_table") or "").lower(), str(j.get("to_table") or "").lower()
        if card == "many_to_one" and a and b and a != b:
            parents.setdefault(a, set()).add(b)
        elif card == "one_to_many" and a and b and a != b:
            parents.setdefault(b, set()).add(a)
    if not parents:
        return []
    # A CTE that only filters or reshapes a child table, without grouping it,
    # still has one row per child row: "order_payment_base" (order_payments
    # joined to orders) then COUNT(*) AS total_orders (Olist, 2026-10-04).
    ctes = {c.alias_or_name.lower(): c.this for c in tree.find_all(exp.CTE) if isinstance(c.this, exp.Select)}

    def grain_of(name: str, depth: int = 0) -> str:
        sel = ctes.get(name)
        if sel is None or depth > 5:
            return name
        if sel.args.get("group") or sel.args.get("distinct") or any(sel.find_all(exp.AggFunc)):
            return name
        frm = _from(sel)
        node = frm.this if frm is not None else None
        return grain_of(node.name.lower(), depth + 1) if isinstance(node, exp.Table) else name

    out = []
    for sel in tree.find_all(exp.Select):
        frm = _from(sel)
        src = frm.this if frm is not None else None
        if not isinstance(src, exp.Table):
            continue
        child = grain_of(src.name.lower())
        if child not in parents:
            continue
        for proj in sel.expressions:
            cnt = proj.unalias() if isinstance(proj, exp.Alias) else proj
            if not (isinstance(cnt, exp.Count) and (cnt.this is None or isinstance(cnt.this, exp.Star))):
                continue
            alias = proj.alias_or_name.lower()
            for parent in parents[child]:
                word = _singular(parent)
                if word != _singular(child) and re.search(rf"(^|_){re.escape(word)}s?(_|$)", alias):
                    out.append(f"{alias} = COUNT(*) over {child}, which has several rows per {word}: it counts "
                               f"{child} rows, not {parent}. Use COUNT(DISTINCT <{word} key>)")
                    break
    return out[:2]


def grain_count_problems(tree) -> list[dict]:
    """Counts of a key taken over a CTE whose grain is the key AND something
    else: `{alias, cte, key, keys, others, groups}`. With `others` (grain
    columns the outer query does not group by) each count is inflated; with
    only `groups`, each group is right but a total summed across the groups
    is not. "Total delivered orders: 97,325" summed per-instalment-plan order
    counts; there are 96,478 orders (Olist, live 2026-10-04)."""
    import sqlglot.expressions as exp
    grains: dict[str, list[str]] = {}
    for c in tree.find_all(exp.CTE):
        sel = c.this
        if not isinstance(sel, exp.Select) or not sel.args.get("group"):
            continue
        keys = []
        for g in sel.args["group"].expressions:
            if isinstance(g, exp.Literal) and g.is_int:              # GROUP BY 1, 2
                i = int(g.this) - 1
                proj = sel.expressions[i] if 0 <= i < len(sel.expressions) else None
                if proj is not None and isinstance(proj.unalias(), exp.Column):
                    keys.append(proj.alias_or_name.lower())
            elif isinstance(g, exp.Column):
                keys.append(g.name.lower())
        if len(keys) >= 2:
            grains[c.alias_or_name.lower()] = keys
    out = []
    for sel in tree.find_all(exp.Select):
        frm = _from(sel)
        src = frm.this if frm is not None else None
        if not isinstance(src, exp.Table) or src.name.lower() not in grains or sel.args.get("joins"):
            continue
        keys = grains[src.name.lower()]
        mine = [g.name.lower() for g in (sel.args.get("group").expressions if sel.args.get("group") else [])
                if isinstance(g, exp.Column)]
        for proj in sel.expressions:
            cnt = proj.unalias() if isinstance(proj, exp.Alias) else proj
            if not isinstance(cnt, exp.Count) or isinstance(cnt.this, exp.Distinct):
                continue
            target = cnt.this.name.lower() if isinstance(cnt.this, exp.Column) else \
                next((k for k in keys if _KEY_NAME.search(k)), None)
            if target not in keys or not _KEY_NAME.search(target):
                continue
            others = [k for k in keys if k != target and k not in mine]
            groups = [k for k in keys if k != target and k in mine]
            if others or groups:
                out.append({"alias": proj.alias_or_name, "cte": src.name, "key": target, "keys": keys,
                            "others": others, "groups": groups})
    return out[:3]


_KEY_NAME = re.compile(r"(^|_)(id|key|code|no)$", re.I)


def grain_probes(sql: str) -> list[dict]:
    """Each suspected double count with the query that settles it. Only the
    data can say whether it is real: a CTE grouped by (seller_id,
    seller_state) has one row per seller, since a seller has one state. The
    probe returns `n` rows against `k` distinct keys."""
    import sqlglot
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:                                      # noqa: BLE001
        return []
    found = grain_count_problems(tree)
    with_ = tree.args.get("with") or tree.args.get("with_")
    if not found or with_ is None:
        return []
    for f in found:
        probe = sqlglot.parse_one(f"SELECT COUNT(*) AS n, COUNT(DISTINCT {f['key']}) AS k FROM {f['cte']}",
                                  read="postgres")
        probe.set("with" if "with" in tree.args else "with_", with_.copy())
        f["probe"] = probe.sql(dialect="postgres")
    return found


def distinct_total_probes(sql: str) -> list[dict]:
    """COUNT(DISTINCT key) per group, then summed by a KPI: an order paid by
    credit card and voucher is one order in each group, so the sum counts it
    twice. "Orders using multiple payments: 5,207" summed four per-method
    counts (Olist, live 2026-10-04). Each entry carries the same count taken
    without the groups -- the real total -- as a query to compare against:
    `{alias, groups, probe}`."""
    import sqlglot
    import sqlglot.expressions as exp
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:                                      # noqa: BLE001
        return []
    with_ = tree.args.get("with") or tree.args.get("with_")
    wkey = "with" if "with" in tree.args else "with_"
    out = []
    for sel in tree.find_all(exp.Select):
        group = sel.args.get("group")
        if not group or not _from(sel):
            continue
        groups = [g.alias_or_name.lower() for g in group.expressions if isinstance(g, exp.Column)]
        for proj in sel.expressions:
            if not isinstance(proj, exp.Alias):
                continue
            cnt = proj.unalias()
            if not (isinstance(cnt, exp.Count) and isinstance(cnt.this, exp.Distinct)):
                continue
            probe = sel.copy()
            probe.set("expressions", [exp.alias_(cnt.copy(), "k")])
            for arg in ("group", "having", "order", "limit", "offset", "qualify"):
                probe.set(arg, None)
            if sel is not tree and with_ is not None:
                probe.set(wkey, with_.copy())
            out.append({"alias": proj.alias.lower(), "groups": groups, "probe": probe.sql(dialect="postgres")})
    return out[:4]


def grain_messages(found: dict, n, k, widgets: list[dict]) -> tuple[str | None, dict[int, str]]:
    """(whole-query problem, {widget index: problem}) for a confirmed probe."""
    key, cte = found["key"], found["cte"]
    if found["others"]:
        return (f"{found['alias']} counts {key} over {cte}, which has one row per ({', '.join(found['keys'])}): "
                f"a {key} with two {found['others'][0]} values is counted twice ({int(n):,} rows for "
                f"{int(k):,} {key} values). Use COUNT(DISTINCT {key})"), {}
    per = {}
    for i, w in enumerate(widgets):
        if str(w.get("measure") or "").lower() != found["alias"].lower():
            continue
        if (w.get("aggregation") or "sum") != "sum" or w.get("widget_type") == "table":
            continue
        dims = {str(d).lower() for d in (w.get("dimension"), w.get("dimension2")) if d}
        if not set(found["groups"]) <= dims:
            per[i] = (f"'{w.get('title')}': sums {found['alias']} across {', '.join(found['groups'])}, but one "
                      f"{key} sits in several of them ({int(n):,} counted vs {int(k):,} real). Take this total "
                      f"from its own COUNT(DISTINCT {key}) column, or drop it")
    return None, per


def fanout_problems(tree, joins: list[dict]) -> list[str]:
    """A query that joins a table to one with many rows per row (an order to
    its payments) and then counts rows, or sums a number of the first table,
    counts each row once per match. Followed through CTEs: the join can sit
    in one CTE and the COUNT(*) in the next."""
    import sqlglot.expressions as exp
    many = many_sides(joins)
    if not many:
        return []
    ctes = {c.alias_or_name.lower(): c.this for c in tree.find_all(exp.CTE) if isinstance(c.this, exp.Select)}
    # name -> (base table, many table, columns that came from the base)
    fanned: dict[str, tuple[str, str, set[str]]] = {}
    out: list[str] = []

    def real_tables(sel) -> dict[str, str]:
        names = {}
        for t in [_from(sel)] + list(sel.args.get("joins") or []):
            node = t.this if t is not None else None
            if isinstance(node, exp.Table):
                names[(node.alias_or_name or node.name).lower()] = node.name.lower()
        return names

    def check(sel, label: str):
        frm = _from(sel)
        src = frm.this if frm is not None else None
        if not isinstance(src, exp.Table):
            return
        alias_map = real_tables(sel)
        src_name = src.name.lower()
        inherited = fanned.get(src_name)
        hit = None
        for j in sel.args.get("joins") or []:
            node = j.this
            if isinstance(node, exp.Table) and node.name.lower() in many.get(src_name, set()):
                hit = (src_name, node.name.lower())
                break
        base, multi = (hit or (inherited[0], inherited[1]) if (hit or inherited) else (None, None))
        if base is None:
            return
        base_aliases = {a for a, r in alias_map.items() if r == base}
        base_cols = set(inherited[2]) if inherited and not hit else set()
        group = sel.args.get("group")
        if group:
            for agg in sel.find_all(exp.Count, exp.Sum):
                if agg.find_ancestor(exp.Select) is not sel:
                    continue
                if isinstance(agg, exp.Count):
                    if isinstance(agg.this, exp.Distinct):
                        continue
                    if isinstance(agg.this, exp.Star) or agg.this is None:
                        out.append(f"COUNT(*) in {label} counts one row per {multi} row ({base} joined to "
                                   f"{multi}, which has many rows per {base}): use COUNT(DISTINCT <{base} key>)"
                                   f" or join {multi} after aggregating it")
                        return
                cols = list(agg.find_all(exp.Column))
                from_base = [c for c in cols if (c.table or "").lower() in base_aliases
                             or (not hit and c.name.lower() in base_cols)]
                if from_base:
                    out.append(f"{agg.sql()[:60]} in {label} adds a number of {base} once per {multi} row "
                               f"({multi} has many rows per {base}): aggregate {multi} in its own CTE first, "
                               f"or COUNT(DISTINCT <{base} key>)")
                    return
        elif label != "the final SELECT":
            cols = set()
            for proj in sel.expressions:
                used = list(proj.find_all(exp.Column))
                if used and all((c.table or "").lower() in base_aliases or (not hit and c.name.lower() in base_cols)
                                for c in used):
                    cols.add(proj.alias_or_name.lower())
            fanned[label.split()[-1]] = (base, multi, cols)

    for name, sel in ctes.items():
        check(sel, f"CTE {name}")
    main = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if main is not None and main not in ctes.values():
        check(main, "the final SELECT")
    return out[:2]


_LATEST_WORDS = re.compile(r"(latest|current|today|this (month|year)|last (month|12 months|year)|"
                           r"أحدث|آخر|الحالي|الحالية|حاليا|حالياً|هذا الشهر|هذا العام)", re.I)


def claims_latest_unfiltered(w: dict, frame, date_cols: list[str]) -> str | None:
    """A chart whose title promises the latest period but which reads them all."""
    if not _LATEST_WORDS.search(f"{w.get('title', '')}") or w.get("filters"):
        return None
    dims = {w.get("dimension"), w.get("dimension2")}
    for d in date_cols:
        if d in dims:
            return None
        keys = [k for k in (w.get("dimension"), w.get("dimension2")) if k and k in frame.columns]
        spread = frame.groupby(keys)[d].nunique().max() if keys else frame[d].nunique()
        if (spread or 0) > 1:
            return (f"'{w.get('title')}': the title says latest/current but the chart reads every "
                    f"{d} ({int(spread)} periods) -- filter it to the latest period (is_latest = 1)")
    return None


def _links_columns(on) -> bool:
    """Whether a join condition compares a column with another column. "ON
    opa.payment_type = 'boleto'" links nothing: every boleto row met every row
    of the other side, and boleto revenue was summed once per year (Olist,
    live 2026-10-04)."""
    from sqlglot import exp
    for node in on.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between):
        sides = [node.this, node.expression] if not isinstance(node, exp.Between) else \
            [node.this, node.args.get("low"), node.args.get("high")]
        cols = [x for x in sides if x is not None and x.find(exp.Column) is not None]
        if len(cols) >= 2:
            quals = {c.table.lower() for x in cols for c in x.find_all(exp.Column)}
            if len(quals) != 1 or "" in quals:
                return True
    return False


def _label(v) -> str:
    """An axis label as people write it: 2016, not 2016.0."""
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def _fmt(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1e6:
        return f"{f / 1e6:,.2f}M"
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{f:,.2f}".rstrip("0").rstrip(".")


def findings(proposal: dict, columns: list[str], rows: list[list], cut: bool = False) -> None:
    """Each chart's answer in one line, read off the rows it will draw: the
    highest and lowest group, or "flat" when the groups barely differ. Shown
    in the chat under the chart's title, so the person sees the answer before
    building anything -- and a flat result is said, not dressed up (the demo
    orders differ by under 3% across channels)."""
    import pandas as pd
    if not rows:
        return
    df = pd.DataFrame(rows, columns=columns)
    have = {c.lower(): c for c in df.columns}
    for w in proposal.get("widgets") or []:
        try:
            frame = df
            for f in w.get("filters") or []:
                c = have.get(str(f.get("column")).lower())
                if c is None:
                    break
                v = f.get("value")
                vals = v if isinstance(v, list) else [v]
                if f.get("op") in ("gt", "gte", "lt", "lte"):
                    num = pd.to_numeric(frame[c], errors="coerce")
                    frame = frame[{"gt": num > v, "gte": num >= v, "lt": num < v, "lte": num <= v}[f["op"]]]
                else:
                    frame = frame[frame[c].astype(str).str.strip().str.lower()
                                  .isin({str(x).strip().lower() for x in vals})]
            m = have.get((w.get("measure") or "").lower())
            d = have.get((w.get("dimension") or "").lower())
            agg = w.get("aggregation") or "sum"
            if m is None or frame.empty:
                continue
            num = pd.to_numeric(frame[m], errors="coerce")
            fn = {"sum": "sum", "avg": "mean", "max": "max", "min": "min", "count": "count",
                  "countd": "nunique"}.get(agg, "sum")
            if fn == "count":
                num = frame[m].notna().astype(int)        # count rows, not numbers: ids are text
                fn = "sum"
            if w.get("widget_type") == "kpi":
                val = (frame[m].nunique() if fn == "nunique" else getattr(num, fn)())
                if cut and fn in ("sum", "count", "nunique"):
                    # A total of the first 5,000 rows is not the total: "orders
                    # using multiple payments: 147" (2,961 really; Olist, live
                    # 2026-10-04). Say nothing rather than a wrong number.
                    continue
                w["finding"] = _fmt(val)
                if cut:
                    w["finding"] += f" (on the first {len(rows):,} rows)"
                # Name the group only when one row holds the extreme: a value
                # repeated on every row has no "where" ("65.7 (00010242fe…)").
                if fn in ("max", "min") and num.notna().any() and int((num == val).sum()) == 1:
                    # "Highest yoy change: 30" says nothing until it says what.
                    row = frame.loc[num.idxmax() if fn == "max" else num.idxmin()]
                    labels = [c for c in frame.columns if c != m and not pd.api.types.is_numeric_dtype(frame[c])
                              and 1 < frame[c].nunique() and not _is_date(None, c)
                              and not re.search(r"(date|month|period|time|year)", c, re.I)]
                    if labels:
                        best = max(labels, key=lambda c: frame[c].nunique())
                        w["finding"] += f" ({row[best]})"
                continue
            if d is None or w.get("widget_type") not in ("bar", "pie", "line"):
                continue
            g = (frame.groupby(d)[m].nunique() if fn == "nunique"
                 else num.groupby(frame[d]).agg(fn)).dropna()
            if len(g) < 2:
                continue
            hi, lo = g.idxmax(), g.idxmin()
            mean = g.abs().mean()
            if w.get("widget_type") == "line":
                first, last = g.iloc[0], g.iloc[-1]
                w["finding"] = (f"{_fmt(first)} at {_label(g.index[0])} → {_fmt(last)} at {_label(g.index[-1])}; "
                                f"peak {_fmt(g[hi])} at {_label(hi)}")
            elif mean and (g.max() - g.min()) / mean < 0.05:
                w["finding"] = (f"Flat: every {d} is within {100 * (g.max() - g.min()) / mean:.1f}% "
                                f"({_fmt(g.min())} to {_fmt(g.max())}) -- no real difference")
            else:
                w["finding"] = f"Highest {hi}: {_fmt(g[hi])}; lowest {lo}: {_fmt(g[lo])}"
        except Exception:                                  # noqa: BLE001
            continue
        if cut and w.get("finding"):
            # Read off the first rows only: the built dashboard has them all.
            w["finding"] += f" (on the first {len(rows):,} rows)"


def _wrap_limit(sql: str, limit: int) -> str:
    return wrap_limit(sql, limit)


def wrap_limit(sql: str, limit: int, family: str | None = None) -> str:
    """The query, cut to `limit` rows by the database in its own dialect."""
    body, n = sql.strip().rstrip(";"), int(limit)
    fam = (family or "").lower()
    if fam in ("mssql", "sqlserver"):
        return f"SELECT TOP {n} * FROM ({body}) AS q"
    if fam == "oracle":
        return f"SELECT * FROM ({body}) q FETCH FIRST {n} ROWS ONLY"
    return f"SELECT * FROM ({body}) AS q LIMIT {n}"


#: Repairs per dashboard after its first design (each dashboard is repaired on
#: its own, concurrently, so a failing one costs time only on its own path).
REPAIR_ROUNDS = 2


#: Model time a whole request may take before it answers with the dashboards
#: that are ready; the rest are reported as not built.
DESIGN_DEADLINE_S = 420


def brief_cache_key(client, messages: list) -> str:
    import hashlib
    who = [type(client).__name__] + [str(getattr(client, a, "") or "") for a in ("provider", "base_url", "model")]
    body = json.dumps([who, messages, BRIEF_SCHEMA], sort_keys=True, default=str)
    return "brief:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _brief_get(key: str):
    try:
        from .analyst_panel import _cache_get
        return _cache_get(key)
    except Exception:                                      # noqa: BLE001
        return None


def _brief_set(key: str, value: dict) -> None:
    try:
        from .analyst_panel import _cache_set
        _cache_set(key, value)
    except Exception:                                      # noqa: BLE001
        pass


async def _distinct_totals(p: dict, out: dict, run_query) -> tuple[set[int], list[str]]:
    """Widgets that add up per-group distinct counts, checked against the
    count taken once over everything (see `distinct_total_probes`)."""
    import pandas as pd
    cols = [str(c).lower() for c in out.get("columns") or []]
    rows = out.get("rows") or []
    bad: set[int] = set()
    msgs: list[str] = []
    if not rows:
        return bad, msgs
    frame = pd.DataFrame(rows, columns=cols)
    totals: dict[str, float | None] = {}
    for found in distinct_total_probes(p["sql"]):
        if found["alias"] not in cols:
            continue
        for i, w in enumerate(p["widgets"]):
            if str(w.get("measure") or "").lower() != found["alias"] or (w.get("aggregation") or "sum") != "sum" \
                    or w.get("widget_type") == "table":
                continue
            dims = {str(d).lower() for d in (w.get("dimension"), w.get("dimension2")) if d}
            if dims & set(found["groups"]) or not found["groups"]:
                continue
            if found["probe"] not in totals:
                try:
                    got = await run_query(found["probe"], 1)
                    totals[found["probe"]] = float((got.get("rows") or [[None]])[0][0])
                except Exception:                          # noqa: BLE001
                    totals[found["probe"]] = None          # cannot tell: let it through
            real = totals[found["probe"]]
            summed = pd.to_numeric(frame[found["alias"]], errors="coerce").sum()
            if real is not None and summed > real * 1.001:
                bad.add(i)
                msgs.append(f"'{w.get('title')}': adds up {found['alias']} over the "
                            f"{', '.join(found['groups'])} groups, but one record can be in several groups: "
                            f"{summed:,.0f} summed vs {real:,.0f} really. Give the total its own "
                            f"COUNT(DISTINCT ...) without the groups, or drop it")
    return bad, msgs


async def design(*, client, catalog: list[dict], persona: str, request: str | None,
                 joins: list[dict] | None, run_query: Callable[[str, int], Awaitable[dict]],
                 count: int = 3, progress=None, quote=None, fresh: bool = False,
                 deadline_s: float = DESIGN_DEADLINE_S,
                 enriched: bool = False) -> tuple[list[dict], dict | None, str]:
    """`(proposals, brief, reason)`. Every returned proposal has run, and every
    chart in it was judged on the rows it will draw."""
    import asyncio

    from .suggest_dashboard import _describe_joins, validate_column_references

    import time
    clock = time.monotonic()
    timings: dict = {}
    if not enriched:
        await enrich_facts(catalog, run_query, quote)
        timings["facts_s"] = round(time.monotonic() - clock, 1)
    mixed = mixed_unit_tables(catalog)
    totals = total_rows(catalog)
    end = data_end(catalog)
    known = {t["name"] for t in catalog}

    async def tell(stage: str):
        if progress is not None:
            try:
                await progress(stage)
            except Exception:                              # noqa: BLE001
                pass

    await tell("brief")
    brief_messages = build_brief_prompt(facts_text(catalog), persona, request, _describe_joins(joins), count)
    # The same person asking the same thing of the same data gets the same
    # brief, kept a week -- a minute of model time saved on every "Retry".
    key = brief_cache_key(client, brief_messages)
    brief = None if fresh else _brief_get(key)
    timings["brief_cached"] = brief is not None
    if brief is None:
        brief = await client.complete_json(brief_messages, BRIEF_SCHEMA, max_tokens=3000,
                                           enforce=True, temperature=0.2)
        if isinstance(brief, dict) and brief.get("questions"):
            _brief_set(key, brief)
    timings["brief_s"] = round(time.monotonic() - clock - timings.get("facts_s", 0), 1)
    if not isinstance(brief, dict) or not brief.get("questions"):
        return [], None, "the model could not write a brief for this data"
    brief = {**brief, "_facts": facts_text(catalog), "_timings": timings}

    await tell("design")

    async def one(title: str, questions: list[dict]) -> tuple[dict | None, str]:
        started = time.monotonic()
        try:
            return await _one(title, questions)
        finally:
            timings.setdefault("dashboards_s", {})[title] = round(time.monotonic() - started, 1)

    async def _one(title: str, questions: list[dict]) -> tuple[dict | None, str]:
        tables = tables_for(questions, catalog, joins)
        names = {t["name"] for t in tables}
        joins_text = _describe_joins([j for j in joins or []
                                      if j.get("from_table") in names and j.get("to_table") in names])
        messages = build_design_prompt(brief, facts_text(tables), persona, title, questions, joins_text)
        why = "the model did not return a dashboard"
        for round_ in range(REPAIR_ROUNDS + 1):
            got = await client.complete_json(messages, DESIGN_SCHEMA, max_tokens=3500,
                                             enforce=True, temperature=0.2)
            props = (got or {}).get("proposals") if isinstance(got, dict) else None
            if not props or not isinstance(props[0], dict):
                return None, why
            raw = props[0]
            p = {"title": str(raw.get("title") or title), "purpose": str(raw.get("purpose") or ""),
                 "sql": clean_sql(str(raw.get("sql") or "")),
                 "questions": [q.get("question") for q in questions],
                 "widgets": [normalise_widget(w) for w in raw.get("widgets") or [] if isinstance(w, dict)]}
            why = _static_problems(p, known, catalog, validate_column_references)
            if not why:
                lint = sql_problems(p["sql"], mixed, totals, end, joins, catalog)
                why = "; ".join(lint) if lint else None
            out = None
            per_widget: dict[int, str] = {}
            if not why:
                for found in grain_probes(p["sql"]):
                    try:
                        got_ = await run_query(found["probe"], 1)
                        n, k = (got_.get("rows") or [[0, 0]])[0][:2]
                    except Exception:                      # noqa: BLE001
                        continue                           # cannot tell: let it through
                    if float(n or 0) > float(k or 0):
                        whole_, each = grain_messages(found, n, k, p["widgets"])
                        if whole_:
                            why = whole_
                            break
                        per_widget.update(each)
            if not why:
                try:
                    out = await run_query(p["sql"], 5000)
                except (TimeoutError, asyncio.TimeoutError):
                    why = ("the query took too long on the real data -- aggregate each table in its own "
                           "CTE first and join the small results, never row-by-row joins of big tables")
                except Exception as exc:                   # noqa: BLE001
                    why = f"the database refused the query: {str(exc)[:300]}"
            if out is not None:
                bad: set[int] = set()
                problems = assess(p, out.get("columns") or [], out.get("rows") or [], mixed, bad)
                for i, msg in per_widget.items():
                    bad.add(i)
                    problems.append(msg)
                bad_, more = await _distinct_totals(p, out, run_query)
                bad |= bad_
                problems.extend(more)
                if not problems:
                    findings(p, out.get("columns") or [], out.get("rows") or [],
                             cut=len(out.get("rows") or []) >= 5000)
                    return {**p, "row_count": len(out.get("rows") or [])}, ""
                good = [w for k, w in enumerate(p["widgets"]) if k not in bad]
                whole = [pr for pr in problems if not pr.startswith("'")]
                if not whole and len(good) >= 2 and round_ == REPAIR_ROUNDS:
                    # The charts that failed are dropped, the rest stand.
                    p = {**p, "widgets": good}
                    findings(p, out.get("columns") or [], out.get("rows") or [],
                             cut=len(out.get("rows") or []) >= 5000)
                    return {**p, "row_count": len(out.get("rows") or []), "dropped": problems}, ""
                why = "; ".join(problems[:8])
            if round_ == REPAIR_ROUNDS:
                break
            await tell("repair")
            # Several subjects forced into one query (cross joins, UNIONs of
            # unlike rows, fan traps) twice running: the last attempt answers
            # only the questions that share the first one's tables. The app's
            # own database lost all three dashboards this way (live 2026-10-03).
            mixing = re.search(r"no key|UNION|fan trap|not a relationship", why or "", re.I)
            if mixing and round_ == REPAIR_ROUNDS - 1 and len(questions) > 1:
                base = set(questions[0].get("tables") or [])
                narrow = [q for q in questions if set(q.get("tables") or []) <= base] or questions[:1]
                if len(narrow) < len(questions):
                    questions = narrow
                    tables = tables_for(questions, catalog, joins)
                    names = {t["name"] for t in tables}
                    joins_text = _describe_joins([j for j in joins or []
                                                  if j.get("from_table") in names and j.get("to_table") in names])
                    messages = build_design_prompt(brief, facts_text(tables), persona, title, questions,
                                                   joins_text)
                    messages[-1]["content"] += (
                        "\nOne subject only: ONE query over these tables, no CROSS JOIN, no UNION.")
                    continue
            messages = messages + [
                {"role": "assistant", "content": json.dumps({"proposals": [raw]}, ensure_ascii=False)[:5000]},
                {"role": "user", "content":
                    f"This dashboard was run on the real data and rejected: {why}\n"
                    "Fix exactly those problems (read the FACTS again for real values, years and "
                    "units) and return the corrected dashboard under 'proposals'."},
            ]
        return None, f"{title}: {why}"

    groups = question_groups(brief, count)
    tasks = [asyncio.ensure_future(one(t, qs)) for t, qs in groups]
    done, pending = await asyncio.wait(tasks, timeout=deadline_s)
    for t in pending:
        t.cancel()
    results = []
    for (title, _), t in zip(groups, tasks):
        if t in pending:
            # Past the deadline: answer with what is ready rather than keep
            # the person waiting on the slowest repair.
            results.append((None, f"{title}: not finished in time"))
        else:
            results.append(t.exception() if t.exception() else t.result())
    kept, reasons = [], []
    for r in results:
        if isinstance(r, BaseException):
            log.warning("one dashboard design failed: %s", r, exc_info=r)
            reasons.append(f"{type(r).__name__}")
            continue
        p, why = r
        if p:
            kept.append(p)
        elif why:
            reasons.append(why)
    timings["total_s"] = round(time.monotonic() - clock, 1)
    # The reasons travel even when some dashboards were kept: what was left
    # out, and why, is what the next prompt fix is built from.
    return kept, brief, "; ".join(reasons)[:1500]


_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.I)
_WRITES = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|attach|pragma|copy)\b", re.I)
_TABLES = re.compile(r"\b(?:from|join)\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_.]*)[\"`\]]?", re.I)


def clean_sql(sql: str) -> str:
    """The query without comments and trailing semicolons: a ';' inside a
    "-- note;" comment was refused as a second statement (Olist, 2026-10-04)."""
    body = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    body = "\n".join(re.sub(r"--[^'\n]*$", "", line) for line in body.splitlines())
    return body.strip().rstrip(";").strip()


def _tables_named(sql: str) -> set[str]:
    """The real tables a query reads -- not its CTEs, and not the `date` in
    `EXTRACT(year FROM date)`, which a FROM/JOIN regex reported as an unknown
    table and so refused a working dashboard (live, 2026-10-03)."""
    try:
        import sqlglot
        import sqlglot.expressions as exp
        tree = sqlglot.parse_one(sql, read="postgres")
        ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        return {t.name for t in tree.find_all(exp.Table) if t.name and t.name.lower() not in ctes}
    except Exception:                                    # noqa: BLE001
        body = re.sub(r"extract\s*\([^)]*\)", "", sql, flags=re.I)
        ctes = {m.lower() for m in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", body, re.I)}
        return {t.split(".")[-1] for t in _TABLES.findall(body) if t.split(".")[-1].lower() not in ctes}


def _static_problems(p: dict, known: set[str], catalog: list[dict], validate_refs) -> str | None:
    """Safety and spelling, before the database is asked.

    Output columns are NOT checked here against `AS` aliases: the query is run
    and its real output columns are what `assess` checks every chart against.
    The alias rule refused `p.admin1_name` selected without `AS` and every
    query written as a CTE (live, 2026-10-03), both of which run fine."""
    sql = p["sql"]
    if not p["widgets"]:
        return "no charts were proposed"
    if not _READ_ONLY.match(sql):
        return "the query must be one SELECT (a WITH ... SELECT is fine)"
    if [part for part in re.sub(r"'[^']*'", "''", sql).split(";")[1:] if part.strip()]:
        return "the query must be a single statement"
    if _WRITES.search(re.sub(r"'[^']*'", "''", sql)):
        return "the query must not modify anything"
    lower_known = {k.lower() for k in known}
    unknown = [u for u in sorted(_tables_named(sql)) if u.lower() not in lower_known]
    if unknown:
        return f"the query names tables this database does not have: {', '.join(unknown)}"
    for w in p["widgets"]:
        if w.get("widget_type") not in WIDGET_TYPES:
            return f"unknown chart type {w.get('widget_type')}"
        if (w.get("aggregation") or "sum") not in AGGREGATIONS:
            return f"unknown aggregation {w.get('aggregation')}"
    ok, why = validate_refs(sql, catalog)
    return None if ok else why
