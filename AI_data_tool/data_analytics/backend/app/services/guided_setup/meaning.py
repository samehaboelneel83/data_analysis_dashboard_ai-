"""The Meaning map: what a connection's data MEANS (docs/meaning-map/PLAN.md).

"Cairo has the most complaints" is true and useless: Cairo handles the most
parcels. A count of events says nothing until it stands beside the number of
things those events could have happened to -- its BASE. Nothing in the
catalog says that a complaint happens to a shipment, what one row of a table
is, or whether a number is to be added up or averaged; every engine guessed
again from column names, and a designer shown only the complaints could not
form a rate whatever it was told.

So it is written down once per connection, in three layers:

* MEASURED, no model: which table's rows happen to which other table's rows
  (from the joins the catalog has and from id columns two tables share),
  with the counts that make it so; what each few-valued column holds.
* NAMED by the model: what one row is, what kind of table it is, what each
  number is (amount / level / duration / score / share / count / code), its
  unit, and whether higher is better or worse; which few-valued columns say
  what became of a row. Every name is checked against the catalog.
* CORRECTED by a person: a fact marked "not right" is never used again, and
  a number kind they set wins over the model's.

Read by Choose data (bring the base along), the Demand (is the base
missing?), the check (which totals mean something) and the dashboard (a
ranking that is only a ranking of sizes gets its rate beside it).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.models import DataSource, MeaningFact, SourceRelationship, User

logger = logging.getLogger(__name__)

#: Links measured per connection, and how long one count may take.
MAX_LINKS = 14
COUNT_TIMEOUT_S = 15.0
#: A column is a table's key when (nearly) every row has its own value.
KEY_SHARE = 0.95
#: Rows of the child that must find their parent for an inferred link to count.
MATCH_SHARE = 0.9
#: Events "happen to" a base when at most this share of the base has any, and
#: there are at most this many per base row; otherwise the child simply
#: belongs to the parent (shipments of a customer).
EVENT_COVERAGE = 0.6
EVENTS_PER_BASE = 1.5
#: A column of this many values or fewer can say what became of a row.
OUTCOME_VALUES = 8
PER = 1000
#: Groups smaller than this are too small to rank by a rate.
MIN_BASE = 30

NUMBER_KINDS = ("amount", "level", "duration", "score", "share", "count", "code")
TABLE_KINDS = ("activity", "event", "thing", "list", "snapshot", "system")
DIRECTIONS = ("higher_better", "higher_worse", "neither")
#: Kinds whose total over many rows means something.
ADDITIVE = ("amount", "count")

_ID = re.compile(r"(^id$|_id$|^id_|_key$|_no$|_code$|number$)", re.I)

MEANING_SCHEMA = {
    "type": "object",
    "properties": {
        "tables": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "row_is": {"type": "string"},
                           "kind": {"type": "string", "enum": list(TABLE_KINDS)}},
            "required": ["name", "row_is", "kind"]}},
        "numbers": {"type": "array", "items": {
            "type": "object",
            "properties": {"table": {"type": "string"}, "column": {"type": "string"},
                           "kind": {"type": "string", "enum": list(NUMBER_KINDS)},
                           "unit": {"type": "string"},
                           "direction": {"type": "string", "enum": list(DIRECTIONS)}},
            "required": ["table", "column", "kind", "unit", "direction"]}},
        "outcomes": {"type": "array", "items": {
            "type": "object",
            "properties": {"table": {"type": "string"}, "column": {"type": "string"}},
            "required": ["table", "column"]}},
    },
    "required": ["tables", "numbers", "outcomes"],
}

_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}

T = {
    "en": {
        "base": "{events} are counted against {base}: about {n} for every {per} {base_l}.",
        "base.small": "{events} are counted against {base}: fewer than 1 for every {per} {base_l}.",
        "outcome": "A row of {table} can be: {values}.",
        "add": "Add up: {cols}.",
        "avg": "Average, never add up: {cols}.",
        "better": "higher is better", "worse": "lower is better",
        "per": "{events} per {per} {base}", "kind.amount": "an amount to add up",
        "kind.level": "a level to average", "kind.duration": "a length of time", "kind.score": "a score",
        "kind.share": "a share or rate", "kind.count": "a count", "kind.code": "a code, not a number to calculate",
    },
    "ar": {
        "base": "تُحسب {events} نسبةً إلى {base}: نحو {n} لكل {per} من {base_l}.",
        "base.small": "تُحسب {events} نسبةً إلى {base}: أقل من 1 لكل {per} من {base_l}.",
        "outcome": "الصف في {table} قد يكون: {values}.",
        "add": "تُجمع: {cols}.",
        "avg": "يُحسب متوسطها ولا تُجمع: {cols}.",
        "better": "الأعلى أفضل", "worse": "الأقل أفضل",
        "per": "{events} لكل {per} من {base}", "kind.amount": "مقدار يُجمع",
        "kind.level": "مستوى يُحسب متوسطه", "kind.duration": "مدة زمنية", "kind.score": "تقييم",
        "kind.share": "نسبة أو معدل", "kind.count": "عدد", "kind.code": "رمز لا يُحسب",
    },
}


def _t(lang: str, key: str, **kw) -> str:
    return (T.get(lang, T["en"]).get(key) or T["en"][key]).format(**kw)


def _words(name: str) -> str:
    return str(name).replace("_", " ").strip()


# ── measuring ───────────────────────────────────────────────────────────────

async def _counts(db: AsyncSession, user: User, source: DataSource, table: dict, column: str) -> tuple[int, int] | None:
    """(rows, distinct values of `column`) of a table, as `user` may read it."""
    import sqlglot
    from sqlglot import exp
    from ..agent.policy import PolicyError, apply_policies, load_policies
    from ..agent.validate import _dialect
    from ..connections import preview_table
    from .access import _PolicyContext, _family, release

    family = _family(source)
    dialect = _dialect(family)
    policies = await load_policies(db, _PolicyContext(source.id, family), user)
    await release(db)
    cfg = {**dict(source.config or {}), "type": source.type}
    col = exp.column(column, quoted=True)
    tab = exp.Table(this=exp.to_identifier(table["name"], quoted=True),
                    db=exp.to_identifier(table["schema"], quoted=True) if table.get("schema") else None)
    sql = exp.select(exp.Count(this=exp.Star()).as_("n"),
                     exp.Count(this=exp.Distinct(expressions=[col])).as_("d")).from_(tab).sql(dialect=dialect)
    try:
        own = {k: v for k, v in policies.items() if k in (table["name"], "*")}
        sql = sqlglot.parse_one(apply_policies(sql, own, family), dialect=dialect).sql(dialect=dialect)
        got = await asyncio.wait_for(asyncio.to_thread(preview_table, cfg, None, sql, 1), COUNT_TIMEOUT_S)
        n, d = (got.get("rows") or [[None, None]])[0]
        return int(n), int(d)
    except (PolicyError, Exception):                            # noqa: BLE001
        return None


async def _matching(db: AsyncSession, user: User, source: DataSource, child: dict, parent: dict,
                    child_col: str, parent_col: str) -> int | None:
    """Rows of `child` whose `child_col` is a value of `parent.parent_col`."""
    from sqlglot import exp
    from ..agent.validate import _dialect
    from ..connections import preview_table
    from .access import _family

    dialect = _dialect(_family(source))
    cfg = {**dict(source.config or {}), "type": source.type}

    def tab(t):
        return exp.Table(this=exp.to_identifier(t["name"], quoted=True),
                         db=exp.to_identifier(t["schema"], quoted=True) if t.get("schema") else None)
    inner = exp.select(exp.column(parent_col, quoted=True)).from_(tab(parent))
    sql = exp.select(exp.Count(this=exp.Star()).as_("n")).from_(tab(child)).where(
        exp.In(this=exp.column(child_col, quoted=True), query=inner.subquery())).sql(dialect=dialect)
    try:
        got = await asyncio.wait_for(asyncio.to_thread(preview_table, cfg, None, sql, 1), COUNT_TIMEOUT_S)
        return int(got["rows"][0][0])
    except Exception:                                           # noqa: BLE001
        return None


async def _filled(db: AsyncSession, user: User, source: DataSource, table: dict, column: str) -> int | None:
    """Rows of `table` where `column` holds a value."""
    from sqlglot import exp
    from ..agent.validate import _dialect
    from ..connections import preview_table
    from .access import _family

    tab = exp.Table(this=exp.to_identifier(table["name"], quoted=True),
                    db=exp.to_identifier(table["schema"], quoted=True) if table.get("schema") else None)
    sql = exp.select(exp.Count(this=exp.column(column, quoted=True)).as_("n")).from_(tab).sql(
        dialect=_dialect(_family(source)))
    cfg = {**dict(source.config or {}), "type": source.type}
    try:
        got = await asyncio.wait_for(asyncio.to_thread(preview_table, cfg, None, sql, 1), COUNT_TIMEOUT_S)
        return int(got["rows"][0][0])
    except Exception:                                           # noqa: BLE001
        return None


#: Orphans up to this share of the linking rows are "a few"; beyond it the
#: link itself is in doubt.
ORPHAN_FEW = 0.01


def link_check(link: dict, filled: int | None, matched: int | None) -> dict:
    """Is a link between two tables CONSISTENT? From three counts: the child's
    rows, how many of them carry a value in the linking column, and how many
    of those values exist in the parent.

    An ORPHAN is a row pointing at nothing: it drops out of every joined
    figure without a word. Rows with no value in the column are not orphans --
    they never claimed a parent -- and are reported apart."""
    rows = int(link.get("child_rows") or 0)
    out = {**{k: link.get(k) for k in ("child", "child_column", "parent", "parent_column", "link", "declared")},
           "child_rows": rows, "parent_rows": int(link.get("parent_rows") or 0),
           "parents_with_children_pct": round(float(link.get("coverage") or 0) * 100, 1),
           "per_parent": link.get("per_base")}
    if filled is None or matched is None:
        return {**out, "verdict": "unknown", "says": "This link could not be checked."}
    orphans, empty = max(filled - matched, 0), max(rows - filled, 0)
    share = orphans / filled if filled else 0.0
    out.update(filled=filled, matched=matched, orphans=orphans, orphan_pct=round(share * 100, 2),
               without_value=empty, without_value_pct=round(empty / rows * 100, 2) if rows else 0.0)
    a, b = f"{link.get('child')}.{link.get('child_column')}", f"{link.get('parent')}.{link.get('parent_column')}"
    if not filled:
        return {**out, "verdict": "empty", "says": f"No row of {link.get('child')} has a value in {link.get('child_column')}."}
    if not orphans:
        return {**out, "verdict": "consistent", "says": f"Every {a} exists in {b}."}
    verdict = "few_orphans" if share <= ORPHAN_FEW else "many_orphans"
    return {**out, "verdict": verdict,
            "says": (f"{orphans:,} {'row' if orphans == 1 else 'rows'} of {link.get('child')} "
                     f"({'under 0.1' if share < 0.001 else f'{share * 100:.1f}'}%) hold a value of "
                     f"{link.get('child_column')} that is not in {link.get('parent')}: "
                     f"{'it is' if orphans == 1 else 'they are'} left out of anything that joins the two.")}


async def link_checks(db: AsyncSession, user: User, source: DataSource, facts: list[dict]) -> list[dict]:
    """Every measured link between the connection's tables, checked. Problems first."""
    by_name = {t["name"]: t for t in facts}
    out = []
    for link in await measure_links(db, user, source, facts):
        child, parent = by_name.get(link["child"]), by_name.get(link["parent"])
        if child is None or parent is None:
            continue
        filled = await _filled(db, user, source, child, link["child_column"])
        matched = await _matching(db, user, source, child, parent, link["child_column"], link["parent_column"])
        out.append(link_check(link, filled, matched))
    order = {"many_orphans": 0, "few_orphans": 1, "empty": 2, "unknown": 3, "consistent": 4}
    return sorted(out, key=lambda x: (order.get(x["verdict"], 9), -(x.get("orphans") or 0)))


def classify_link(child_rows: int, child_distinct: int, parent_rows: int) -> str | None:
    """"events" when the child's rows happen to a FEW of the parent's rows, a
    few times each (complaints on shipments); "belongs" when most parents have
    many (shipments of a customer). None when there is nothing to measure."""
    if not child_rows or not parent_rows:
        return None
    coverage = child_distinct / parent_rows
    per_base = child_rows / parent_rows
    return "events" if coverage <= EVENT_COVERAGE and per_base <= EVENTS_PER_BASE else "belongs"


def candidate_links(facts: list[dict], declared: list[tuple[str, str, str, str]]) -> list[tuple[str, str, str, str, bool]]:
    """(child table, child column, parent table, parent column, declared?) --
    the joins the catalog has, then id columns two business tables share
    (a database without foreign keys still has `shipment_id` in both)."""
    tables = {t["name"]: t for t in facts if t["group"] != "technical"}
    out = [(a, ac, b, bc, True) for a, ac, b, bc in declared if a in tables and b in tables]
    seen = {(a, ac, b) for a, ac, b, _bc, _d in out} | {(b, bc, a) for a, _ac, b, bc, _d in out}
    by_col: dict[str, list[str]] = {}
    for t in tables.values():
        for c in t["_columns"]:
            if _ID.search(c.name or ""):
                by_col.setdefault(c.name, []).append(t["name"])
    for col, names in by_col.items():
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if (a, col, b) not in seen and (b, col, a) not in seen:
                    seen.add((a, col, b))
                    out.append((a, col, b, col, False))
    return out[:MAX_LINKS]


async def measure_links(db: AsyncSession, user: User, source: DataSource, facts: list[dict]) -> list[dict]:
    """The links between tables, each with the counts that say what it is."""
    by_name = {t["name"]: t for t in facts}
    ids = {t["id"]: t["name"] for t in facts}
    rels = (await db.execute(select(SourceRelationship).where(
        SourceRelationship.data_source_id == source.id))).scalars().all()
    declared = [(ids[r.from_object_id], r.from_column, ids[r.to_object_id], r.to_column)
                for r in rels if r.from_object_id in ids and r.to_object_id in ids]
    cache: dict[tuple[str, str], tuple[int, int] | None] = {}

    async def counts(table: str, column: str):
        if (table, column) not in cache:
            cache[(table, column)] = await _counts(db, user, source, by_name[table], column)
        return cache[(table, column)]

    out = []
    for a, ac, b, bc, is_declared in candidate_links(facts, declared):
        ca, cb = await counts(a, ac), await counts(b, bc)
        if not ca or not cb:
            continue
        # The parent is the side where the column is the table's key; when it
        # is a key on both (one complaint per shipment), the bigger table.
        key_a, key_b = ca[1] >= KEY_SHARE * ca[0], cb[1] >= KEY_SHARE * cb[0]
        if is_declared:
            child, cc, parent, pc, cn, pn = a, ac, b, bc, ca, cb
        elif key_b and (not key_a or cb[0] >= ca[0]):
            child, cc, parent, pc, cn, pn = a, ac, b, bc, ca, cb
        elif key_a:
            child, cc, parent, pc, cn, pn = b, bc, a, ac, cb, ca
        else:
            continue                                    # a key on neither side: not a link between rows
        if not is_declared:
            hit = await _matching(db, user, source, by_name[child], by_name[parent], cc, pc)
            if hit is None or hit < MATCH_SHARE * cn[0]:
                continue
        kind = classify_link(cn[0], cn[1], pn[0])
        if kind is None:
            continue
        out.append({"child": child, "child_column": cc, "parent": parent, "parent_column": pc,
                    "link": kind, "declared": is_declared, "child_rows": cn[0], "parent_rows": pn[0],
                    "coverage": round(cn[1] / pn[0], 4), "per_base": round(cn[0] / pn[0], 5)})
    return out


def few_valued(facts: list[dict]) -> list[dict]:
    """Columns of the main tables with a handful of values, and those values
    with their shares, from the statistics the sync already holds."""
    out = []
    for t in facts:
        if t["group"] == "technical":
            continue
        for c in t["_columns"]:
            s = t["_stats"].get(c.id)
            if s is None or not s.top_k or not 2 <= (s.distinct_count or 0) <= OUTCOME_VALUES:
                continue
            if c.dtype not in ("text", "boolean"):
                continue
            values = [{"value": str(v.get("value")), "share": round(float(v.get("ratio") or 0), 4)}
                      for v in s.top_k[:OUTCOME_VALUES] if v.get("value") is not None]
            out.append({"table": t["name"], "column": c.name, "boolean": c.dtype == "boolean"
                        or {v["value"].casefold() for v in values} <= {"true", "false"}, "values": values})
    return out


#: Names of a position or sequence within something (the 2nd item of an
#: order, the 3rd payment): numbered, never added up. Structure words only.
_SEQUENCE_NAME = re.compile(r"(^|_)(seq|sequence|sequential|position|pos|index|idx|line_no|item_no|rank_no)(_|$)"
                            r"|(^|_)(item|line)_id$", re.I)


#: An end date this far ahead means "still open": the row is a period.
OPEN_END_YEAR = 9000


def holds_periods(table: dict) -> bool:
    """Whether a table's rows are periods: one of its date columns runs to a
    far-future date that stands for "not ended yet"."""
    for c in table.get("_columns") or []:
        if c.dtype not in ("date", "datetime", "timestamp"):
            continue
        s = (table.get("_stats") or {}).get(c.id)
        hi = str(getattr(s, "max_value", "") or "")
        if hi[:4].isdigit() and int(hi[:4]) >= OPEN_END_YEAR:
            return True
    return False


def never_calculated(column: str, stats=None) -> str | None:
    """Why a numeric column is a code whatever else was said, or None.
    Persona test 2026-10-12: "Add up: order item id, payment sequential" and
    "Average: latitude, longitude" on a marketplace's first page."""
    from ..column_classes import geo_level
    from ..semantic_guard import is_identifier
    if is_identifier(column):
        return "an identifier"
    if _SEQUENCE_NAME.search(column):
        return "a position in a sequence"
    if geo_level(column) in ("latitude", "longitude"):
        return "a coordinate"
    lo, hi = getattr(stats, "min_value", None), getattr(stats, "max_value", None)
    try:
        lo, hi = float(lo), float(hi)
    except (TypeError, ValueError):
        return None
    if 1800 <= lo <= hi <= 2200 and lo == int(lo) and hi == int(hi):
        return "a year"
    return None


def plain_number(column: str) -> dict:
    """What a numeric column is, from its name alone: the fallback when no
    model may read the connection."""
    from ..semantic_guard import is_identifier, is_intensive, non_additive_kind
    if is_identifier(column):
        return {"kind": "code", "unit": "", "direction": "neither"}
    if re.search(r"(day|hour|minute|duration|_time$|age$)", column, re.I):
        return {"kind": "duration", "unit": "", "direction": "neither"}
    if re.search(r"(rating|score|grade|stars)", column, re.I):
        return {"kind": "score", "unit": "", "direction": "higher_better"}
    if re.search(r"(pct|percent|ratio|rate$|share)", column, re.I):
        return {"kind": "share", "unit": "%", "direction": "neither"}
    if is_intensive(column) or non_additive_kind(column):
        return {"kind": "level", "unit": "", "direction": "neither"}
    return {"kind": "amount", "unit": "", "direction": "neither"}


# ── the model names what was measured ───────────────────────────────────────

def build_prompt(source: DataSource, facts: list[dict], links: list[dict], few: list[dict]) -> list[dict]:
    from . import understand
    system = (
        "You describe what a database MEANS, so that numbers from it are read correctly. Use only the "
        "tables and columns listed.\n"
        "- tables: for each, row_is = what ONE row is, in a few plain words ('one request made by a "
        "person', 'one visit', 'one item in stock'); kind = activity (things that happen and are counted: "
        "orders, visits, admissions, trips), event (something that happens TO a row of another table: "
        "a return, a payment, a review, a claim, a defect), thing (people, places, products), list "
        "(names for codes), snapshot (a level recorded per day or month), system.\n"
        "- numbers: for EVERY numeric column listed, kind = amount (adding it up over many rows means "
        "something: fees, quantities, weights), level (a price, a balance, a rate card: average it), "
        "duration (days, hours), score (a rating), share (a percentage or a ratio), count (a small "
        "count held in the row: attempts, items) or code (an id, a year, a phone: never calculate); "
        "unit = a currency code, kg, days... or ''; direction = higher_better (a rating, revenue), higher_worse "
        "(a delay, a cost, a number of attempts or complaints) or neither.\n"
        "- outcomes: of the few-valued columns listed, the ones that say WHAT BECAME of a row -- "
        "done or not, paid / unpaid, open / closed, passed / failed, kept / returned. Not the ones "
        "that say what KIND of thing it is (a type, a category, a channel, a method).")
    lines = []
    for t in facts:
        if t["group"] == "technical":
            continue
        lines.append(f"## {t['name']} (~{t['rows'] or 0:,} rows)")
        if t.get("description"):
            lines.append(f"Says: {t['description']}")
        lines.append("Columns: " + "; ".join(understand._column_line(c, t["_stats"]) for c in t["_columns"][:40]))
    if links:
        lines.append("\nMeasured links: " + "; ".join(
            f"{k['child']}.{k['child_column']} -> {k['parent']} ({k['child_rows']:,} rows on {k['parent_rows']:,})"
            for k in links))
    if few:
        lines.append("Few-valued columns: " + "; ".join(
            f"{f['table']}.{f['column']} = " + " / ".join(v["value"] for v in f["values"]) for f in few))
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"Database: {source.name}\n\n" + "\n".join(lines)}]


async def build(db: AsyncSession, user: User, source: DataSource, client) -> list[dict]:
    """Every fact for a connection: [{kind, subject, body, source}]. Measured
    first; the model only names and judges, and a name not in the catalog is
    dropped."""
    from . import understand
    from .access import release

    facts = await understand.load_facts(db, source)
    if not facts:
        return []
    links = await measure_links(db, user, source, facts)
    few = few_valued(facts)
    tables = {t["name"]: t for t in facts if t["group"] != "technical"}
    numeric = {(t["name"], c.name) for t in tables.values() for c in t["_columns"]
               if c.dtype in ("numeric", "integer")}
    got = None
    if source.allow_llm_sampling and client is not None and getattr(client, "enabled", True):
        await release(db)
        try:
            got = await client.complete_json(build_prompt(source, facts, links, few), MEANING_SCHEMA,
                                             max_tokens=4000, temperature=0.1, enforce=True)
        except Exception:                                       # noqa: BLE001
            logger.exception("meaning map: the model could not name the facts")
    named = {str(x.get("name")): x for x in (got or {}).get("tables") or [] if isinstance(x, dict)}
    numbers = {(str(x.get("table")), str(x.get("column"))): x for x in (got or {}).get("numbers") or []
               if isinstance(x, dict)}
    said_outcomes = {(str(x.get("table")), str(x.get("column"))) for x in (got or {}).get("outcomes") or []
                     if isinstance(x, dict)}

    out: list[dict] = []
    event_tables = {k["child"] for k in links if k["link"] == "events"}
    for name, t in tables.items():
        n = named.get(name) or {}
        kind = n.get("kind") if n.get("kind") in TABLE_KINDS else None
        if name in event_tables:
            kind = "event"                              # the counts say so, whatever the model called it
        elif kind is None or kind == "event":
            kind = "thing" if t["group"] == "supporting" else "activity"
        out.append({"kind": "grain", "subject": name, "source": "ai" if n else "measured",
                    "body": {"table": name, "row_is": str(n.get("row_is") or "").strip()[:200], "kind": kind}})
    # One base per kind of event: the finest thing it happens to (a complaint
    # is about a shipment before it is about that shipment's customer).
    finest: dict[str, dict] = {}
    for k in links:
        if k["link"] == "events" and k["parent_rows"] > finest.get(k["child"], {}).get("parent_rows", 0):
            finest[k["child"]] = k
    for k in finest.values():
        out.append({"kind": "base", "subject": f"{k['child']}>{k['parent']}", "source": "measured",
                    "body": {"events": k["child"], "base": k["parent"], "via": [k["child_column"], k["parent_column"]],
                             "coverage": k["coverage"], "per_base": k["per_base"], "per": PER,
                             "events_rows": k["child_rows"], "base_rows": k["parent_rows"]}})
    for f in few:
        if not (f["boolean"] or (f["table"], f["column"]) in said_outcomes):
            continue
        out.append({"kind": "outcome", "subject": f"{f['table']}.{f['column']}",
                    "source": "measured" if f["boolean"] else "ai",
                    "body": {"table": f["table"], "column": f["column"], "boolean": f["boolean"],
                             "values": f["values"]}})
    stats_of = {(t["name"], c.name): t["_stats"].get(c.id) for t in tables.values() for c in t["_columns"]}
    for table, column in sorted(numeric):
        n = numbers.get((table, column))
        body = ({"kind": n["kind"], "unit": str(n.get("unit") or "")[:12],
                 "direction": n.get("direction") if n.get("direction") in DIRECTIONS else "neither"}
                if n and n.get("kind") in NUMBER_KINDS else plain_number(column))
        if body.get("kind") == "amount" and holds_periods(tables[table]):
            # A row valid "until further notice" (an end date like 9999-01-01)
            # holds a value OVER a period: adding rows up adds every period a
            # person or thing was in (persona test 2026-10-12: salary history).
            body = {**body, "kind": "level", "why": "a value held over a period"}
            n = None
        forced = never_calculated(column, stats_of.get((table, column)))
        if forced and body.get("kind") != "code":
            body = {**body, "kind": "code", "unit": "", "direction": "neither", "why": forced}
            n = None                                  # measured, whatever the model said
        out.append({"kind": "number", "subject": f"{table}.{column}", "source": "ai" if n else "measured",
                    "body": {"table": table, "column": column, **body}})
    return out


async def save(db: AsyncSession, source: DataSource, built: list[dict]) -> None:
    """Keep the facts. A person's word stands: a fact they confirmed or
    rejected is not overwritten by a new measurement of the same subject."""
    old = {(f.kind, f.subject): f for f in (await db.execute(select(MeaningFact).where(
        MeaningFact.data_source_id == source.id))).scalars().all()}
    seen = set()
    for item in built:
        key = (item["kind"], item["subject"][:600])
        seen.add(key)
        row = old.get(key)
        if row is None:
            db.add(MeaningFact(org_id=source.org_id, data_source_id=source.id, kind=key[0], subject=key[1],
                               body=item["body"], source=item["source"], measured_at=datetime.utcnow()))
        elif row.source != "confirmed":
            row.body, row.source, row.measured_at = item["body"], item["source"], datetime.utcnow()
        elif row.kind == "base":
            # Their yes or no stands; the counts beside it are refreshed.
            row.body = {**item["body"]}
            row.measured_at = datetime.utcnow()
    for key, row in old.items():
        if key not in seen and row.source != "confirmed":
            await db.delete(row)
    await db.commit()


# ── reading it ──────────────────────────────────────────────────────────────

@dataclass
class Map:
    """A connection's active facts, as the steps read them."""
    grains: dict[str, dict] = field(default_factory=dict)        # table -> {row_is, kind}
    bases: list[dict] = field(default_factory=list)              # {events, base, via, per_base, ...}
    outcomes: list[dict] = field(default_factory=list)           # {table, column, boolean, values}
    numbers: dict[tuple[str, str], dict] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.grains or self.bases or self.numbers)

    def base_of(self, table: str) -> dict | None:
        return next((b for b in self.bases if b["events"] == table), None)

    def number(self, column: str, tables: list[str] | None = None) -> dict | None:
        """What a column is, by name: in the tables given first, else in the
        one table that has a column of that name."""
        hits = [(t, v) for (t, c), v in self.numbers.items() if c == column]
        for t, v in hits:
            if tables and t in tables:
                return v
        return hits[0][1] if len(hits) == 1 else None

    def events_without_base(self, tables: list[str]) -> list[dict]:
        """Bases a query's tables leave out: it holds the events but not what
        they are counted against, so it can show counts and never rates."""
        return [b for b in self.bases if b["events"] in tables and b["base"] not in tables]


async def load(db: AsyncSession, source_id: int | None) -> Map:
    if not source_id:
        return Map()
    rows = (await db.execute(select(MeaningFact).where(
        MeaningFact.data_source_id == source_id, MeaningFact.status == "active"))).scalars().all()
    m = Map()
    for r in rows:
        b = dict(r.body or {})
        if r.kind == "grain":
            m.grains[r.subject] = b
        elif r.kind == "base":
            m.bases.append(b)
        elif r.kind == "outcome":
            m.outcomes.append(b)
        elif r.kind == "number" and b.get("table") and b.get("column"):
            m.numbers[(b["table"], b["column"])] = b
    return m


def _values(o: dict, limit: int = 5) -> str:
    return ", ".join(f"{v['value']} ({v['share'] * 100:.0f}%)" if v["share"] >= 0.01 else f"{v['value']} (<1%)"
                     for v in o["values"][:limit])


def sentences(m: Map, lang: str, titles: dict[str, str] | None = None) -> list[dict]:
    """The map as a person reads it in Understand: one plain line per fact
    that changes how a number is read."""
    titles = titles or {}

    def name(table: str) -> str:
        return titles.get(table) or _words(table).capitalize()

    out = []
    for b in m.bases:
        n = b["per_base"] * b.get("per", PER)
        key = "base" if n >= 1 else "base.small"
        out.append({"kind": "base", "subject": f"{b['events']}>{b['base']}",
                    "text": _t(lang, key, events=name(b["events"]), base=name(b["base"]),
                               base_l=name(b["base"]).lower(), n=f"{n:,.0f}", per=f"{b.get('per', PER):,}")})
    for o in m.outcomes:
        if o.get("boolean"):
            yes = next((v for v in o["values"] if v["value"].casefold() == "true"), None)
            text = (f"{name(o['table'])}: {_words(o['column'])} — {yes['share'] * 100:.0f}%"
                    if yes else _t(lang, "outcome", table=name(o["table"]), values=_values(o)))
        else:
            text = _t(lang, "outcome", table=name(o["table"]), values=_values(o))
        out.append({"kind": "outcome", "subject": f"{o['table']}.{o['column']}", "text": text})
    add, avg = [], []
    for (_table, col), n in sorted(m.numbers.items()):
        label = _words(col) + (f" ({n['unit']})" if n.get("unit") else "")
        if n["kind"] in ADDITIVE:
            add.append(label)
        elif n["kind"] in ("level", "duration", "score", "share"):
            way = {"higher_better": _t(lang, "better"), "higher_worse": _t(lang, "worse")}.get(n.get("direction"))
            avg.append(label + (f" — {way}" if way else ""))
    if add:
        out.append({"kind": "numbers", "subject": "add", "text": _t(lang, "add", cols=", ".join(add[:10]))})
    if avg:
        out.append({"kind": "numbers", "subject": "avg", "text": _t(lang, "avg", cols=", ".join(avg[:10]))})
    return out


def prompt_text(m: Map, tables: list[str] | None = None, columns: set[str] | None = None) -> str:
    """The map for a model, in English: what the rows are, what is counted
    against what, what became of a row, and how each number behaves."""
    if not m:
        return ""
    keep = (lambda t: tables is None or t in tables)
    # For one dataset: only the columns it kept. Naming a column it left out
    # ("status") makes a model filter on it, and every such chart is refused.
    has = (lambda c: columns is None or c in columns)
    lines = []
    for t, g in m.grains.items():
        if keep(t) and g.get("row_is"):
            lines.append(f"- one row of `{t}` is {g['row_is']} ({g['kind']})")
    for b in m.bases:
        if tables is None or b["events"] in tables or b["base"] in tables:
            lines.append(f"- `{b['events']}` happen to `{b['base']}` (join {b['events']}.{b['via'][0]} = "
                         f"{b['base']}.{b['via'][1]}): {b['per_base'] * PER:,.0f} per {PER:,} {b['base']}; "
                         f"{b['coverage'] * 100:.1f}% of {b['base']} have any. A count of `{b['events']}` per "
                         f"group must be read against the `{b['base']}` of that group.")
    for o in m.outcomes:
        if keep(o["table"]) and has(o["column"]):
            lines.append(f"- `{o['table']}.{o['column']}` says what became of a row: {_values(o, 6)}")
    for (t, c), n in sorted(m.numbers.items()):
        if keep(t) and has(c) and n["kind"] != "code":
            way = {"higher_better": ", higher is BETTER", "higher_worse": ", higher is WORSE"}.get(n.get("direction"), "")
            lines.append(f"- `{t}.{c}` is {n['kind']}" + (f" in {n['unit']}" if n.get("unit") else "") + way)
    return "\n".join(lines)
