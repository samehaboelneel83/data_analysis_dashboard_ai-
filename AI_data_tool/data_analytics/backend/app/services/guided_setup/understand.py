"""Step 1 of the guided setup: Understand (docs/guided-setup/PLAN.md, 1a).

"What does this database hold, and where do I start?" -- answered in plain
language, tables ranked from most to least useful, in the reader's language.

Two layers, so the step never comes back empty:

* FACTS, always: what the metadata sync measured -- rows, columns, date
  ranges, what holds numbers, how the tables join -- plus a usefulness score
  computed from them (`score_table`). No model involved.
* WORDS, when the connection allows the model to read it: an overview, a
  business title and a one-line "what it holds / what it is good for" per
  table, its own ranking, and questions the data can answer. Every table name
  the model returns is checked against the catalog; anything else is dropped.

A human's words always win: a confirmed source or table description replaces
the model's text for that item (principle 5 of the metadata layer).
"""
from __future__ import annotations

import logging
import math
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.models import (ColumnStats, DataSource, SourceColumn, SourceObject,
                              SourceRelationship)

logger = logging.getLogger(__name__)

#: Tables described to the model in full; the rest are named only, so an
#: 80-table warehouse costs what a 25-table one does.
PROMPT_TABLES = 25
#: Columns listed per table in the prompt.
PROMPT_COLUMNS = 30
#: Text values shown per column in the prompt (from the sync's top-k).
PROMPT_TOP_VALUES = 3

GROUPS = ("main", "supporting", "technical")

#: Table names that are plumbing, not business data.
_TECHNICAL = re.compile(
    r"(^|_)(log|logs|audit|tmp|temp|backup|bak|migrations?|alembic|schema|session|sessions|"
    r"cache|queue|job|jobs|celery|django|auth|token|tokens|permission|permissions|sys|meta)($|_)",
    re.I)
_NUMERIC = {"numeric", "integer"}
_ID_NAME = re.compile(r"(^id$|_id$|^id_|_key$|^key$|code$|_no$|^no$)", re.I)
#: A year is a point in time to group by, not an amount to add up.
_YEAR_NAME = re.compile(r"(^|_)(year|yr)($|_)", re.I)


# ── facts ────────────────────────────────────────────────────────────────────

def _is_measure(col: SourceColumn) -> bool:
    if col.semantic_type in ("currency", "percentage"):
        return True
    return (col.dtype in _NUMERIC and not col.is_primary_key
            and not _ID_NAME.search(col.name or "") and not _YEAR_NAME.search(col.name or ""))


def _is_date(col: SourceColumn) -> bool:
    return col.dtype in ("datetime", "date", "timestamp") or col.semantic_type == "timestamp"


def score_table(t: dict) -> float:
    """How useful a table is likely to be to someone starting out.

    Business tables are big, carry numbers to add up and dates to trend over,
    and connect to other tables. Plumbing (logs, migrations, sessions) and
    tables marked deprecated sink; one an admin marked canonical rises."""
    s = math.log10((t["rows"] or 0) + 1)
    s += 0.7 * min(3, len(t["measures"]))
    s += 1.5 if t["dates"] else 0.0
    s += 0.5 * min(4, len(t["related"]))
    s += 0.3 * min(5, len(t["dimensions"]))
    if t["canonical"]:
        s += 2.0
    if t["deprecated"]:
        s -= 5.0
    if t["technical"]:
        s -= 3.0
    if t["kind"] == "view":
        s -= 0.5
    return round(s, 3)


def group_of(t: dict) -> str:
    if t["technical"] or t["deprecated"]:
        return "technical"
    if not t["measures"] and not t["dates"] and (t["rows"] or 0) < 1000:
        return "supporting"   # a lookup list: names for codes used elsewhere
    return "main"


async def load_facts(db: AsyncSession, source: DataSource) -> list[dict]:
    """One dict per table or view the sync found, ranked by `score_table`."""
    objects = (await db.execute(select(SourceObject).where(
        SourceObject.data_source_id == source.id))).scalars().all()
    if not objects:
        return []
    ids = [o.id for o in objects]
    cols = (await db.execute(select(SourceColumn).where(SourceColumn.source_object_id.in_(ids))
                             .order_by(SourceColumn.source_object_id, SourceColumn.position))).scalars().all()
    stats = {s.source_column_id: s for s in (await db.execute(select(ColumnStats).where(
        ColumnStats.source_column_id.in_([c.id for c in cols] or [-1])))).scalars().all()}
    rels = (await db.execute(select(SourceRelationship).where(
        SourceRelationship.from_object_id.in_(ids)))).scalars().all()
    names = {o.id: o.name for o in objects}
    related: dict[int, set[str]] = {i: set() for i in ids}
    for r in rels:
        if r.to_object_id in names:
            related[r.from_object_id].add(names[r.to_object_id])
            related[r.to_object_id].add(names[r.from_object_id])

    by_obj: dict[int, list[SourceColumn]] = {}
    for c in cols:
        by_obj.setdefault(c.source_object_id, []).append(c)

    out = []
    for o in objects:
        columns = by_obj.get(o.id, [])
        dates = [c for c in columns if _is_date(c)]
        lo = [str(stats[c.id].min_value) for c in dates if c.id in stats and stats[c.id].min_value]
        hi = [str(stats[c.id].max_value) for c in dates if c.id in stats and stats[c.id].max_value]
        measures = [c.name for c in columns if _is_measure(c)]
        t = {
            "id": o.id, "name": o.name, "schema": o.schema_name, "kind": (o.kind or "table").lower(),
            "rows": o.row_count_estimate, "columns_count": len(columns),
            "measures": measures,
            "dimensions": [c.name for c in columns if c.dtype in ("text", "boolean")
                           and c.name not in measures and not c.is_primary_key],
            "dates": [c.name for c in dates],
            "date_from": min(lo)[:10] if lo else None, "date_to": max(hi)[:10] if hi else None,
            # Ranges from the sync's sample are approximate; the page says so.
            "dates_exact": bool(dates) and all(c.id in stats and stats[c.id].exact for c in dates),
            "related": sorted(related[o.id]),
            "canonical": bool(o.is_canonical), "deprecated": bool(o.is_deprecated),
            "technical": bool(_TECHNICAL.search(o.name or "")),
            "description": o.comment or o.description,
            "description_source": "schema" if o.comment else o.description_source,
            "_columns": columns, "_stats": stats,
        }
        t["score"] = score_table(t)
        t["group"] = group_of(t)
        out.append(t)
    # Group first: a 90,000-row log is still plumbing, and must not outrank
    # the lookup list that names the brands in the business table.
    out.sort(key=lambda t: (GROUPS.index(t["group"]), -t["score"], t["name"]))
    return out


#: Tables whose exact date range is measured, and the time each query may take.
RANGE_TABLES = 6
RANGE_TIMEOUT_S = 15.0


async def exact_ranges(db, user, source: DataSource, facts: list[dict]) -> dict[str, dict]:
    """{table: {"from", "to"}}: the real first and last date of the main
    tables, measured with MIN/MAX as `user` (their row rules parsed in).

    The sync's statistics come from a sample, and a sample's range can be
    years off (EGX, 2026-10-07: sampled May 2009-May 2023, real Jan 2000-Dec
    2023). The period is among the first things a reader takes in, so it is
    measured; a table that does not answer in time keeps its sampled range."""
    import asyncio
    import sqlglot
    from sqlglot import exp
    from ..agent.policy import PolicyError, apply_policies, load_policies
    from ..agent.validate import _dialect
    from ..connections import preview_table
    from .access import _PolicyContext, _family

    family = _family(source)
    dialect = _dialect(family)
    policies = await load_policies(db, _PolicyContext(source.id, family), user)
    from .access import release
    await release(db)
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    out: dict[str, dict] = {}
    for t in [t for t in facts if t["dates"] and t["group"] != "technical"][:RANGE_TABLES]:
        col = exp.column(t["dates"][0], quoted=True)
        table = exp.Table(this=exp.to_identifier(t["name"], quoted=True),
                          db=exp.to_identifier(t["schema"], quoted=True) if t["schema"] else None)
        sql = exp.select(exp.Min(this=col).as_("lo"), exp.Max(this=col.copy()).as_("hi")).from_(table).sql(dialect=dialect)
        try:
            own = {k: v for k, v in policies.items() if k in (t["name"], "*")}
            sql = sqlglot.parse_one(apply_policies(sql, own, family), dialect=dialect).sql(dialect=dialect)
            got = await asyncio.wait_for(asyncio.to_thread(preview_table, cfg, None, sql, 1), RANGE_TIMEOUT_S)
            lo, hi = (got.get("rows") or [[None, None]])[0]
        except (PolicyError, Exception):                    # noqa: BLE001
            continue
        if lo is not None and hi is not None:
            out[t["name"]] = {"from": str(lo)[:10], "to": str(hi)[:10]}
    return out


def apply_ranges(facts: list[dict], ranges: dict[str, dict] | None) -> list[dict]:
    """The measured ranges in place of the sampled ones."""
    for t in facts:
        r = (ranges or {}).get(t["name"])
        if r:
            t["date_from"], t["date_to"], t["dates_exact"] = r["from"], r["to"], True
    return facts


def relationships_of(facts: list[dict]) -> list[dict]:
    return [{"from_table": t["name"], "to_table": other}
            for t in facts for other in t["related"] if t["name"] < other]


# ── words ────────────────────────────────────────────────────────────────────

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "tables": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "title": {"type": "string"},
                "what": {"type": "string"}, "useful_for": {"type": "string"},
                "group": {"type": "string", "enum": list(GROUPS)},
            },
            "required": ["name", "title", "what"],
        }},
        "order": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["overview", "tables", "order"],
}

_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}


def _column_line(c: SourceColumn, stats: dict) -> str:
    kind = c.semantic_type or c.dtype or "?"
    s = stats.get(c.id)
    extra = ""
    if s is not None:
        if s.top_k and c.dtype in ("text", "boolean"):
            vals = [str(v.get("value")) for v in s.top_k[:PROMPT_TOP_VALUES] if v.get("value") is not None]
            if vals:
                extra = " e.g. " + ", ".join(vals)
        elif s.min_value is not None and s.max_value is not None:
            extra = f" {str(s.min_value)[:19]}..{str(s.max_value)[:19]}"
        if s.null_ratio:
            extra += f" ({s.null_ratio:.0%} empty)"
    return f"{c.name} [{kind}]{extra}"


def build_prompt(source: DataSource, facts: list[dict], language: str,
                 samples: dict[str, list[dict]]) -> list[dict]:
    """Facts in, plain words out. Values (top values, ranges, a masked sample
    row) are only here because the connection allows the model to read it."""
    lang = _LANGUAGE.get(language, "English")
    lines = []
    for t in facts[:PROMPT_TABLES]:
        head = f"## {t['name']} ({t['kind']}, ~{t['rows'] or 0:,} rows"
        if t["date_from"]:
            head += f", dates {t['date_from']} to {t['date_to']}"
        head += ")"
        lines.append(head)
        if t["description"] and t["description_source"] in ("confirmed", "schema"):
            lines.append(f"Described by its owner: {t['description']}")
        if t["related"]:
            lines.append("Joins to: " + ", ".join(t["related"]))
        lines.append("Columns: " + "; ".join(
            _column_line(c, t["_stats"]) for c in t["_columns"][:PROMPT_COLUMNS]))
        if samples.get(t["name"]):
            lines.append(f"Sample row: {samples[t['name']][0]}")
    rest = [t["name"] for t in facts[PROMPT_TABLES:]]
    if rest:
        lines.append("Other tables (names only): " + ", ".join(rest))

    system = (
        "You explain a database to a person who may never have used one: a lawyer, a manager, "
        "a shop owner, or a developer. Be concrete and plain; no jargon such as schema, "
        "foreign key, null, dtype or nan. Name things by what they mean in the business.\n"
        "Periods: use ONLY the dates given for each table; never guess a period from the sample "
        "rows or the example values. If no dates are given, say nothing about the period.\n"
        f"Write every text field in {lang}. Keep table `name` exactly as given.\n"
        "Return JSON:\n"
        "- overview: 2-4 short sentences: what this database is about, what period it covers, "
        "and who would find it useful.\n"
        "- tables: one entry per table listed with columns: title (a short business name), "
        "what (one sentence: what one row is and what it holds), useful_for (one sentence: "
        "what someone could learn from it), group (main = business data worth analysing, "
        "supporting = lists that give names to codes used elsewhere, technical = system "
        "plumbing nobody analyses).\n"
        "- order: the table names from most to least useful for analysis.\n"
        "- questions: 3 to 5 questions a person could answer with this data, in plain words."
    )
    user = f"Database: {source.name}\n\n" + "\n".join(lines)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def merge_words(facts: list[dict], words: dict | None) -> dict:
    """Facts plus the model's words, the model's text checked against the catalog."""
    known = {t["name"] for t in facts}
    by_name = {}
    for item in (words or {}).get("tables") or []:
        name = item.get("name") if isinstance(item, dict) else None
        if name in known:
            by_name[name] = item
    order = [n for n in dict.fromkeys((words or {}).get("order") or []) if n in known]
    # The model's order first, then the facts' order for anything it skipped.
    position = {n: i for i, n in enumerate(order + [t["name"] for t in facts if t["name"] not in order])}

    tables = []
    for t in sorted(facts, key=lambda t: position[t["name"]]):
        w = by_name.get(t["name"], {})
        human = t["description"] if t["description_source"] in ("confirmed", "schema") else None
        group = w.get("group") if w.get("group") in GROUPS else t["group"]
        # A model cannot promote a table the facts call plumbing or deprecated.
        if t["group"] == "technical":
            group = "technical"
        tables.append({
            "id": t["id"], "name": t["name"], "schema": t["schema"], "kind": t["kind"],
            "title": (w.get("title") or "").strip() or None,
            "what": human or (w.get("what") or "").strip() or t["description"] or None,
            "what_source": ("you" if t["description_source"] == "confirmed" else
                            "database" if human else "ai" if w.get("what") else
                            ("ai" if t["description"] else None)),
            "useful_for": (w.get("useful_for") or "").strip() or None,
            "group": group,
            "rows": t["rows"], "columns_count": t["columns_count"],
            "measures": t["measures"][:8], "dates": t["dates"][:4],
            "date_from": t["date_from"], "date_to": t["date_to"], "dates_exact": t["dates_exact"],
            "related": t["related"], "canonical": t["canonical"], "deprecated": t["deprecated"],
        })
    questions = [q.strip() for q in (words or {}).get("questions") or []
                 if isinstance(q, str) and q.strip()][:5]
    return {"overview": ((words or {}).get("overview") or "").strip() or None,
            "tables": tables, "questions": questions}


async def describe(source: DataSource, facts: list[dict], language: str,
                   samples: dict[str, list[dict]], client) -> tuple[dict | None, str | None]:
    """The model's words, or (None, reason): "off" (the connection does not
    allow it), "unavailable" (no model configured), "failed"."""
    if not source.allow_llm_sampling:
        return None, "off"
    if client is None or not getattr(client, "enabled", True):
        return None, "unavailable"
    got = await client.complete_json(build_prompt(source, facts, language, samples), SUMMARY_SCHEMA,
                                     max_tokens=3000, temperature=0.2)
    if not got:
        logger.info("guided setup: no summary for %s (%s)", source.name,
                    getattr(client, "last_error", "unknown"))
        return None, "failed"
    return got, None


def totals(facts: list[dict]) -> dict:
    lo = [t["date_from"] for t in facts if t["date_from"] and t["group"] != "technical"]
    hi = [t["date_to"] for t in facts if t["date_to"] and t["group"] != "technical"]
    return {
        "tables": sum(1 for t in facts if t["kind"] != "view"),
        "views": sum(1 for t in facts if t["kind"] == "view"),
        "rows": sum(t["rows"] or 0 for t in facts if t["kind"] != "view"),
        "date_from": min(lo) if lo else None, "date_to": max(hi) if hi else None,
        "dates_exact": all(t["dates_exact"] for t in facts if t["date_from"] and t["group"] != "technical"),
    }
