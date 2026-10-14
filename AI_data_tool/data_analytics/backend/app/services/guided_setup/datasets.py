"""Step 2 of the guided setup: Choose data (docs/guided-setup/PLAN.md, 2b/2d).

A dataset is the part of a database a dashboard reads. Most people cannot
write the SQL that picks it, so the model proposes two or three, each saying
what it INCLUDES, what it LEAVES OUT and WHY -- from the catalog, the
Understand step's words and the person's own "About you" answers (hints,
never rules).

Nothing the model writes is trusted:

* `check_sql` refuses anything but one read (SELECT / WITH ... SELECT), any
  table outside this connection's catalog, and a qualified column the table
  does not have;
* `test_run` runs it as the PERSON -- their connection row rules parsed into
  the SQL (decision D1) -- and keeps a preview, the row count and any error;
* a proposal that fails gets one repair round with the database's own error;
  one that still fails, or returns no rows, is dropped.

When the model is off, unreachable or proposes nothing usable, `fallback`
builds one plain proposal per main table from the facts alone, so the step
always offers something.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.models import DataSource, User
from . import understand

logger = logging.getLogger(__name__)

MAX_PROPOSALS = 3
PREVIEW_ROWS = 8
#: A row count slower than this is left unknown rather than holding the step.
COUNT_TIMEOUT_S = 20.0
#: Columns per table described to the model.
PROMPT_COLUMNS = 40
#: Values shown per text column: a subject the person names ("only X") can be
#: filtered correctly only when the model has seen how the column spells it.
PROMPT_VALUES = 12
NO_ROWS = ("the query returns no rows: a filter value does not match how the data spells it -- use only "
           "values listed for the column, compare text without case, or drop that filter")

#: Columns a first dataset is better without, by what they hold.
_PERSONAL = {"email", "phone", "national_id", "ip", "credit_card", "iban"}
_LANG_COPY = re.compile(r"^(?P<base>.+?)_(ar|en|fr|arabic|english)$", re.I)

PROPOSAL_ITEM = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "purpose": {"type": "string"},
        "sql": {"type": "string"},
        "includes": {"type": "array", "items": {"type": "string"}},
        "leaves_out": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
    },
    "required": ["name", "purpose", "sql", "includes", "leaves_out", "why"],
}
PROPOSALS_SCHEMA = {
    "type": "object",
    "properties": {"proposals": {"type": "array", "items": PROPOSAL_ITEM},
                   # Every catalog column holding what the person asked to leave
                   # out: removed from every proposal by code (plan 1.10).
                   "excluded_columns": {"type": "array", "items": {
                       "type": "object",
                       "properties": {"table": {"type": "string"}, "column": {"type": "string"}},
                       "required": ["table", "column"]}}},
    "required": ["proposals"],
}
REFINE_SCHEMA = {
    "type": "object",
    "properties": {"proposal": PROPOSAL_ITEM, "reply": {"type": "string"}},
    "required": ["proposal", "reply"],
}

_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}


# ── checking SQL ─────────────────────────────────────────────────────────────

def _dialect(family: str) -> str:
    from ..agent.validate import _dialect as d
    return d(family)


def check_sql(sql: str, family: str, catalog: list[dict]) -> tuple[str | None, str | None]:
    """(clean SQL, None) for one read over this catalog, else (None, why not)."""
    import sqlglot
    from sqlglot import exp

    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        return None, "empty query"
    try:
        trees = [t for t in sqlglot.parse(text, dialect=_dialect(family)) if t is not None]
    except Exception as exc:                                        # noqa: BLE001
        return None, f"the query does not parse: {str(exc).splitlines()[0][:200]}"
    if len(trees) != 1:
        return None, "write exactly one statement"
    tree = trees[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        return None, "only a SELECT (optionally WITH ... SELECT) may be used"
    for bad in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command):
        if tree.find(bad) is not None:
            return None, "only reading is allowed"
    known = {(t["name"] or "").casefold() for t in catalog}
    ctes = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = (table.name or "").casefold()
        if name and name not in known and name not in ctes:
            return None, f"table {table.name!r} is not in this database"
    from ..suggest_dashboard import validate_column_references
    ok, why = validate_column_references(text, catalog)
    if not ok:
        return None, why
    return tree.sql(dialect=_dialect(family)), None


def _wrap(sql: str, family: str, outer: str) -> str:
    """`outer` with `{q}` replaced by the query as a subquery, in the dialect."""
    import sqlglot
    inner = sqlglot.parse_one(sql, dialect=_dialect(family))
    return sqlglot.parse_one(outer.format(q=inner.sql(dialect=_dialect(family))),
                             dialect=_dialect(family)).sql(dialect=_dialect(family))


async def test_run(db: AsyncSession, user: User, source: DataSource, sql: str) -> dict:
    """Run a proposal as `user`: {columns, rows, row_count, error}.

    The person's connection row rules are parsed into the SQL first (the same
    policies Ask AI applies), so the preview and the count are what THEY
    would get. Personal values in the preview are masked."""
    from .. import pii
    from ..agent.policy import PolicyError, apply_policies, load_policies
    from ..connections import preview_table
    from .access import _PolicyContext, _family

    from .access import release
    family = _family(source)
    policies = await load_policies(db, _PolicyContext(source.id, family), user)
    await release(db)
    try:
        secured = apply_policies(sql, policies, family)
    except PolicyError:
        return {"columns": [], "rows": [], "row_count": None, "error": "restricted"}
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    try:
        preview = await asyncio.to_thread(
            preview_table, cfg, None, _wrap(secured, family, f"SELECT * FROM ({{q}}) AS q LIMIT {PREVIEW_ROWS}"),
            PREVIEW_ROWS)
    except Exception as exc:                                        # noqa: BLE001
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        return {"columns": [], "rows": [], "row_count": None, "error": first[:300]}
    columns = list(preview.get("columns") or [])
    rows = [dict(zip(columns, r)) for r in preview.get("rows") or []]
    kinds = {c: pii.detect_semantic_type([r.get(c) for r in rows]) for c in columns}
    count = None
    try:
        got = await asyncio.wait_for(asyncio.to_thread(
            preview_table, cfg, None, _wrap(secured, family, "SELECT COUNT(*) AS n FROM ({q}) AS q"), 1),
            COUNT_TIMEOUT_S)
        count = int(got["rows"][0][0])
    except Exception:                                               # noqa: BLE001
        count = None
    from .access import jsonable
    return {"columns": columns, "rows": jsonable(pii.mask_rows(rows, kinds)), "row_count": count, "error": None}


# ── the catalog as the model sees it ────────────────────────────────────────

def catalog_of(facts: list[dict]) -> list[dict]:
    """The shape `validate_column_references` reads: [{name, columns:[{name}]}],
    plus each table's primary key ("pk"), for the join checks."""
    return [{"name": t["name"], "columns": [{"name": c.name} for c in t["_columns"]],
             "pk": [c.name for c in t["_columns"] if getattr(c, "is_primary_key", False)]} for t in facts]


#: A LEFT JOIN leaving at least this share of rows without a match is said.
UNMATCHED_NOTE_SHARE = 0.05


def join_check_sql(sql: str, family: str, catalog: list[dict]) -> tuple[str, str | None, list[str]] | None:
    """(SQL counting rows, distinct main-table keys and unmatched rows per LEFT
    JOIN; the main table's name or None; the LEFT-joined tables' names), or
    None when the query joins nothing. Persona test 2026-10-12: "one row per
    delivered order" held 97,015 rows for 96,478 orders; "current employees"
    kept the 59,900 who had left, with no salary."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    except Exception:                                               # noqa: BLE001
        return None
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    joins = select.args.get("joins") if select is not None else None
    frm = (select.args.get("from_") or select.args.get("from")) if select is not None else None
    if not joins or frm is None or not isinstance(frm.this, exp.Table):
        return None
    pks = {str(t["name"]).split(".")[-1].casefold(): t.get("pk") or [] for t in catalog}
    base = frm.this
    extra: list = []
    measures: list = [exp.alias_(exp.Count(this=exp.Star()), "n")]
    left: list[str] = []
    key = pks.get(base.name.casefold()) or []
    if len(key) == 1:
        extra.append(exp.alias_(exp.column(key[0], table=base.alias_or_name), "__key__"))
        measures.append(exp.alias_(exp.Count(this=exp.Distinct(expressions=[exp.column("__key__")])), "k"))
    for i, j in enumerate(joins):
        if str(j.args.get("side") or "").upper() != "LEFT" or not isinstance(j.this, exp.Table):
            continue
        right = j.this
        on = j.args.get("on")
        cols = [c for c in (on.find_all(exp.Column) if on is not None else [])
                if c.table and c.table.casefold() == right.alias_or_name.casefold()]
        if not cols:
            continue
        missing = exp.Is(this=exp.column(cols[0].name, table=right.alias_or_name), expression=exp.Null())
        extra.append(exp.alias_(exp.Case().when(missing, exp.Literal.number(1)).else_(exp.Literal.number(0)),
                                f"__u{i}__"))
        measures.append(exp.alias_(exp.Sum(this=exp.column(f"__u{i}__")), f"u{i}"))
        left.append(right.name)
    if len(measures) == 1:
        return None
    inner = select.copy()
    inner.set("expressions", list(inner.expressions) + extra)
    inner.set("order", None)
    outer = exp.select(*measures).from_(inner.subquery("q")).sql(dialect=_dialect(family))
    return outer, (base.name if len(key) == 1 else None), left


async def join_notes(db, user, source, sql: str, family: str, catalog: list[dict]) -> dict:
    """{"repeats": {table, rows, distinct} | None, "unmatched": [{table, share}]}."""
    from ..agent.policy import PolicyError, apply_policies, load_policies
    from ..connections import preview_table
    from .access import _PolicyContext, release
    built = join_check_sql(sql, family, catalog)
    out: dict = {"repeats": None, "unmatched": []}
    if built is None:
        return out
    check, base, left = built
    policies = await load_policies(db, _PolicyContext(source.id, family), user)
    await release(db)
    try:
        secured = apply_policies(check, policies, family)
        cfg = {**dict(source.config or {}), "type": source.type}
        got = await asyncio.wait_for(asyncio.to_thread(preview_table, cfg, None, secured, 1), COUNT_TIMEOUT_S)
        row = dict(zip(got.get("columns") or [], (got.get("rows") or [[]])[0]))
    except (PolicyError, Exception):                                # noqa: BLE001 -- a note, never a gate
        return out
    n = int(row.get("n") or 0)
    if base and row.get("k") is not None and n > int(row["k"]):
        out["repeats"] = {"table": base, "rows": n, "distinct": int(row["k"])}
    for i, table in enumerate(left):
        u = row.get(f"u{i}")
        if n and u is not None and int(u) / n >= UNMATCHED_NOTE_SHARE:
            out["unmatched"].append({"table": table, "share": round(int(u) / n, 3)})
    return out


def _describe(facts: list[dict], words: dict | None) -> str:
    titles = {t.get("name"): t for t in ((words or {}).get("tables") or []) if isinstance(t, dict)}
    lines = []
    for t in facts:
        if t["group"] == "technical":
            continue
        w = titles.get(t["name"], {})
        head = f"## {t['name']} (~{t['rows'] or 0:,} rows)"
        if w.get("title"):
            head += f" -- {w['title']}"
        lines.append(head)
        if w.get("what") or t["description"]:
            lines.append(f"What it holds: {w.get('what') or t['description']}")
        if t["related"]:
            lines.append("Joins to: " + ", ".join(t["related"]))
        lines.append("Columns: " + "; ".join(
            understand._column_line(c, t["_stats"], PROMPT_VALUES) for c in t["_columns"][:PROMPT_COLUMNS]))
    return "\n".join(lines)


def _brief_text(brief: dict | None) -> str:
    b = brief or {}
    parts = [("Their work", b.get("work")), ("What to focus on", b.get("focus")),
             ("What they need to know", b.get("questions")), ("What to leave out", b.get("exclude")),
             # Written elsewhere and passed along as background (services/ai_context.py).
             ("About them, from their profile", b.get("about")),
             ("The connection is described as", b.get("connection"))]
    said = [f"- {k}: {v}" for k, v in parts if v]
    return "\n".join(said) if said else "- They did not say. Propose what most people would need."


def _rules(lang: str) -> str:
    return (
        "Rules:\n"
        "- Each dataset is ONE read-only SQL query (SELECT, or WITH ... SELECT) over the tables "
        "listed. Use only the listed tables and columns. Join tables where 'Joins to' says they "
        "connect, or on a shared column that clearly means the same thing in both (the same "
        "date, the same id). When the person's questions compare two tables (a figure against "
        "its benchmark, actuals against targets), one proposal should be that join, so they "
        "can compare without building it themselves.\n"
        "- Keep rows, not totals: a dataset feeds many charts, so do not GROUP BY unless the "
        "person clearly needs a summary table.\n"
        "- Leave out what does not help: system columns, duplicate copies of the same value in "
        "another language, columns that are almost all empty, links, and personal details "
        "(names, phones, emails, ids of people) unless their work needs them. Honour 'What to "
        "leave out', and list in excluded_columns EVERY catalog column (table and column, as "
        "named in the catalog) that holds what they asked to leave out -- whatever language "
        "they asked in; [] when they asked for nothing to be left out.\n"
        "- Give columns plain snake_case aliases only when the original name is unclear.\n"
        "- When the person asked for a PART of the data -- one kind, one place, one period, a "
        "range ('I need ...', 'only ...', 'under ...', 'since ...') -- the FIRST proposal is "
        "exactly that part: narrow the rows to it with WHERE, spelling each value the way the "
        "column's listed values spell it (compare text without case; match a word inside a longer "
        "text with LIKE), keep the column you filtered on, and say in leaves_out what was left "
        "out. The SECOND is then the broad one (every row), for comparing their subject with the "
        "rest. When they asked for nothing in particular, the first is the broad one: every "
        "relevant row and the useful columns.\n"
        "- If the part they ask for is NOT in this database -- no listed column or value is that "
        "thing -- do not pretend: never write a filter that keeps everything, and never name a "
        "dataset after something it does not hold. Propose the broad dataset under its true name "
        "and say in 'why', plainly, that the database has nothing called what they asked for and "
        "what it has instead.\n"
        "- Narrow only by the SUBJECT (what kind of thing, where, when) -- never by what they want "
        "MEASURED. 'How many are late / returned / cancelled / unpaid' needs the rows that are not, "
        "too: without them there is no share to show. So 'only online orders, how many were "
        "cancelled' keeps every online order and the column that says whether it was cancelled.\n"
        "- Keep every column that could answer or break down their questions -- the measures, the "
        "dates, and the columns that say what kind, where and who (as categories) -- not only the "
        "ones they named: one dataset feeds many charts.\n"
        "- The proposals must answer DIFFERENT questions, not three versions of one query: the "
        "others take a different angle -- a different table or join, a different slice of rows, or "
        "a summary table -- each saying in 'why' what it lets them see that the others do not.\n"
        "- Never narrow the rows for a reason the person did not give.\n"
        "- name is a short plain title, the way a person would say it (e.g. 'Daily stock prices', "
        "'Open support requests', 'Clinic visits this year') -- never snake_case or a table name; it becomes the dataset's "
        "name.\n"
        f"- Write name, purpose, includes, leaves_out and why in {_LANGUAGE.get(lang, 'English')}, "
        "in plain words for someone who never wrote SQL: purpose = one sentence on what it is for; "
        "includes/leaves_out = short items in business words (e.g. 'Amounts and dates', "
        "'Personal phone numbers'); why = one or two sentences tying the choice to their work.\n"
    )


def _reading(meaning_text: str) -> str:
    """The Meaning map and the one rule it adds: bring the base along."""
    if not meaning_text:
        return ""
    return (
        "\n\nHOW TO READ THIS DATABASE (measured on it):\n" + meaning_text + "\n"
        "RULE -- bring the base along. A count of things that HAPPEN TO other rows says nothing until it "
        "stands beside those rows: the biggest group has the most of everything because it is the biggest. "
        "So when their request is about such things and compares anything (which, where, more, most, by "
        "..., per ...), the FIRST proposal keeps ONE ROW PER ROW OF THE BASE with the event attached -- "
        "FROM the base LEFT JOIN (SELECT the join column, COUNT(*) AS <events>_count, and EVERY number of "
        "the events their questions need -- amounts summed, durations and scores averaged -- FROM the "
        "events [WHERE the kind of event they asked for] GROUP BY the join column) -- with "
        "a true/false column `has_<event>` (the joined key IS NOT NULL), the count and summed amounts with "
        "COALESCE(..., 0) (averages left empty where there is no event), and the base's own columns that "
        "say what kind, where, when and who. If the "
        "events carry a group the base lacks, join it through the base's own column for it. "
        "Its 'why' says it includes the rows WITHOUT the event, so groups can be compared fairly. A later "
        "proposal may hold only the events, to read them one by one.\n"
        "The same holds for a column listed above as saying WHAT BECAME of a row: when they ask about one "
        "of its outcomes and compare anything ('which ... have more of them', 'where', 'by ...'), the FIRST "
        "proposal keeps ALL the rows with that column, so the share with the outcome can be compared across "
        "groups -- even when they say 'only' those rows. The rows with the outcome alone are the SECOND "
        "proposal, and its 'why' says it can count them but not compare groups fairly.\n")


def build_prompt(source: DataSource, facts: list[dict], words: dict | None,
                 brief: dict | None, lang: str, meaning_text: str = "") -> list[dict]:
    system = ("You help a person pick the right part of a database to analyse. You propose "
              f"up to {MAX_PROPOSALS} datasets.\n" + _rules(lang))
    user = (f"Database: {source.name}\n\nWhat the person said (follow it):\n{_brief_text(brief)}\n\n"
            f"Tables:\n{_describe(facts, words)}" + _reading(meaning_text))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_refine_prompt(source: DataSource, facts: list[dict], words: dict | None, brief: dict | None,
                        proposal: dict, history: list[dict], message: str, lang: str,
                        meaning_text: str = "") -> list[dict]:
    system = ("You change ONE dataset proposal as the person asks, keeping everything else "
              "about it. Return the whole revised proposal and a one-sentence reply saying what "
              f"you changed, in {_LANGUAGE.get(lang, 'English')}.\n" + _rules(lang))
    convo = "\n".join(f"{m['role']}: {m['text']}" for m in history[-6:])
    user = (f"Database: {source.name}\n\nAbout the person:\n{_brief_text(brief)}\n\n"
            f"Tables:\n{_describe(facts, words)}{_reading(meaning_text)}\n\nCurrent proposal:\n"
            f"name: {proposal.get('name', '')}\npurpose: {proposal.get('purpose', '')}\n"
            f"sql: {proposal.get('sql') or '(missing -- write one)'}\n"
            f"includes: {proposal.get('includes', [])}\nleaves_out: {proposal.get('leaves_out', [])}\n\n"
            + (f"Earlier in this conversation:\n{convo}\n\n" if convo else "")
            + f"The person now asks: {message}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── proposals ───────────────────────────────────────────────────────────────

def banned_columns(named, catalog: list[dict]) -> set[tuple[str, str]]:
    """(table, column) pairs, lower-cased, that exist in the catalog."""
    real = {(str(t["name"]).casefold(), str(c["name"]).casefold())
            for t in catalog for c in t.get("columns") or []}
    out = set()
    for x in named or []:
        if isinstance(x, dict):
            key = (str(x.get("table") or "").casefold().split(".")[-1], str(x.get("column") or "").casefold())
            if key in real or any(r[0].split(".")[-1] == key[0] and r[1] == key[1] for r in real):
                out.add(key)
    return out


def without_columns(sql: str, family: str, banned: set[tuple[str, str]]) -> tuple[str, list[str]]:
    """The query with every output column read from a banned (table, column)
    taken out of its outer SELECT, and the names taken out. Columns used only
    to join or filter stay where they are: they are not shown."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    except Exception:                                               # noqa: BLE001
        return sql, []
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is None:
        return sql, []
    alias_to_table: dict[str, str] = {}
    for t in select.find_all(exp.Table):
        name = t.name.casefold()
        alias_to_table[(t.alias or t.name).casefold()] = name
    tables = set(alias_to_table.values())
    banned_names = {c for _t, c in banned}
    keep, removed = [], []
    for proj in select.expressions:
        cols = list(proj.find_all(exp.Column))
        hit = False
        for col in cols:
            name = col.name.casefold()
            if name not in banned_names:
                continue
            table = alias_to_table.get(col.table.casefold()) if col.table else None
            owners = {table} if table else {t for t, c in banned if c == name and t in tables}
            if any((t, name) in banned for t in owners if t):
                hit = True
        if hit:
            removed.append(proj.alias_or_name)
        else:
            keep.append(proj)
    if not removed or not keep:
        return sql, []
    select.set("expressions", keep)
    return tree.sql(dialect=_dialect(family)), removed


#: A table this small, with a text column, gives names to the codes that point at it.
LOOKUP_MAX_ROWS = 10_000


def name_for(table: dict) -> str | None:
    """The column that names a lookup table's rows: its first text column that
    is neither its key nor a key to another table."""
    keys = {c.name for c in table["_columns"] if getattr(c, "is_primary_key", False)}
    keys |= {k["column"] for k in table.get("links") or []}
    return next((c.name for c in table["_columns"] if c.dtype == "text" and c.name not in keys), None)


#: The column a summary query gets for how many rows each of its rows stands for.
GROUP_SIZE_COLUMN = "row_count"


def with_group_size(sql: str, family: str) -> tuple[str, str | None]:
    """(the query, the column holding each summary row's size): a query that
    groups (GROUP BY) keeps how many rows each of its rows stands for -- its
    own COUNT(*) column, or `row_count` added. Held-out benchmark 2026-10-13:
    a unit of 4 reviews ranked "best" in a one-row-per-unit summary, where no
    group size was left to judge it by. Read from the query's structure."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    except Exception:                                               # noqa: BLE001
        return sql, None
    select = tree if isinstance(tree, exp.Select) else None
    if select is None or not select.args.get("group"):
        return sql, None
    for proj in select.expressions:
        inner = proj.this if isinstance(proj, exp.Alias) else proj
        if isinstance(inner, exp.Count) and isinstance(inner.this, exp.Star) and proj.alias_or_name:
            return sql, proj.alias_or_name
    if GROUP_SIZE_COLUMN in {p.alias_or_name.casefold() for p in select.expressions}:
        return sql, None
    select.append("expressions", exp.alias_(exp.Count(this=exp.Star()), GROUP_SIZE_COLUMN))
    return tree.sql(dialect=_dialect(family)), GROUP_SIZE_COLUMN


def with_names(sql: str, family: str, facts: list[dict]) -> tuple[str, list[str]]:
    """The query with a name beside every shown code that points into a small
    lookup table (a LEFT JOIN on the declared key), and the names added.
    Persona test 2026-10-12: departments read "d007" where the database held
    "Sales" one join away."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    except Exception:                                               # noqa: BLE001
        return sql, []
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is None or select.args.get("group"):
        return sql, []
    by_name = {t["name"].casefold(): t for t in facts}
    alias_to_table: dict[str, str] = {}
    for t in select.find_all(exp.Table):
        alias_to_table[(t.alias or t.name).casefold()] = t.name.casefold()
    joined = set(alias_to_table.values())
    shown = {p.alias_or_name.casefold() for p in select.expressions}
    added: list[str] = []
    for i, proj in enumerate(list(select.expressions)):
        col = proj.this if isinstance(proj, exp.Alias) else proj
        if not isinstance(col, exp.Column) or not col.table:
            continue
        owner = by_name.get(alias_to_table.get(col.table.casefold(), ""))
        if owner is None:
            continue
        link = next((k for k in owner.get("links") or [] if k["column"].casefold() == col.name.casefold()), None)
        lookup = by_name.get(str(link["table"]).casefold()) if link else None
        if lookup is None or lookup["name"].casefold() in joined or (lookup.get("rows") or 0) > LOOKUP_MAX_ROWS:
            continue
        label = name_for(lookup)
        if not label:
            continue
        # The lookup's own word for it ("dept_name"), unless the query already shows one.
        alias_out = label if label.casefold() not in shown else f"{proj.alias_or_name}_name"
        if alias_out.casefold() in shown:
            continue
        shown.add(alias_out.casefold())
        nick = f"nm{i}"
        select.join(exp.Table(this=exp.to_identifier(lookup["name"]), alias=exp.TableAlias(this=exp.to_identifier(nick))),
                    on=exp.EQ(this=exp.column(col.name, table=col.table), expression=exp.column(link["to_column"], table=nick)),
                    join_type="LEFT", copy=False)
        select.append("expressions", exp.alias_(exp.column(label, table=nick), alias_out))
        added.append(alias_out)
    if not added:
        return sql, []
    return tree.sql(dialect=_dialect(family)), added


def _clean_list(v) -> list[str]:
    return [str(x).strip() for x in (v or []) if str(x).strip()][:8]


def _tables_in(sql: str, family: str) -> list[str]:
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql, dialect=_dialect(family))
    except Exception:                                               # noqa: BLE001
        return []
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table) if t.name and t.name not in ctes})


async def _accept(db, user, source, item: dict, catalog: list[dict], family: str,
                  repair, meaning_map=None) -> dict | None:
    """Check, run, and if needed repair one proposal. None when it cannot be used."""
    sql, why = check_sql(item.get("sql", ""), family, catalog)
    run = None
    if sql is not None:
        run = await test_run(db, user, source, sql)
        why = run["error"]
        if why is None and run["row_count"] == 0:
            why = NO_ROWS
    if why is not None and repair is not None:
        fixed = await repair(item, why)
        if fixed:
            item = {**item, **fixed}
            sql, why = check_sql(item.get("sql", ""), family, catalog)
            if sql is not None:
                run = await test_run(db, user, source, sql)
                why = run["error"] or (NO_ROWS if run["row_count"] == 0 else None)
    if why is not None or sql is None or run is None:
        logger.info("guided setup: dropped proposal %r: %s", item.get("name"), why)
        return None
    return {
        "id": uuid.uuid4().hex[:10],
        "name": str(item.get("name") or "").strip()[:120] or "Dataset",
        "purpose": str(item.get("purpose") or "").strip(),
        "sql": sql,
        "tables": _tables_in(sql, family),
        # Events without what they are counted against: counts, never rates.
        "counts_only": [{"events": b["events"], "base": b["base"]}
                        for b in (meaning_map.events_without_base(_tables_in(sql, family)) if meaning_map else [])],
        "joins": await join_notes(db, user, source, sql, family, catalog),
        "includes": _clean_list(item.get("includes")),
        "leaves_out": _clean_list(item.get("leaves_out")),
        "why": str(item.get("why") or "").strip(),
        "source": item.get("source") or "ai",
        "test": run,
        "history": item.get("history") or [],
    }


def _useful_columns(t: dict) -> tuple[list[str], list[str]]:
    """(kept, left out) column names for a plain one-table dataset."""
    names = {c.name for c in t["_columns"]}
    keep, out = [], []
    for c in t["_columns"]:
        s = t["_stats"].get(c.id)
        copy = _LANG_COPY.match(c.name or "")
        if (c.semantic_type in _PERSONAL or c.semantic_type == "url"
                or (s is not None and s.null_ratio is not None and s.null_ratio >= 0.9)
                or (copy and copy.group("base") in names)):
            out.append(c.name)
        else:
            keep.append(c.name)
    return keep, out


_FALLBACK_TEXT = {
    "en": {"name": "{title}", "purpose": "Every row of {table}, ready to chart.",
           "why": "Made from the facts alone{reason}: the most useful table, without columns that are "
                  "empty, personal, links or copies in another language.",
           "reason_off": " (the AI is off for this connection)", "reason_down": " (the AI could not be reached)",
           "rows": "All {n} rows"},
    "ar": {"name": "{title}", "purpose": "كل صفوف {table}، جاهزة للرسوم البيانية.",
           "why": "أُعدّت من الحقائق وحدها{reason}: الجدول الأكثر فائدة، دون الأعمدة الفارغة أو الشخصية أو "
                  "الروابط أو النسخ بلغة أخرى.",
           "reason_off": " (الذكاء الاصطناعي متوقف لهذا الاتصال)",
           "reason_down": " (تعذّر الوصول إلى الذكاء الاصطناعي)", "rows": "كل الصفوف ({n})"},
}


def fallback_items(facts: list[dict], family: str, lang: str, reason: str | None,
                   words: dict | None = None) -> list[dict]:
    """One plain proposal per main table, from the facts alone."""
    import sqlglot
    from sqlglot import exp
    text = _FALLBACK_TEXT.get(lang, _FALLBACK_TEXT["en"])
    why_reason = text["reason_off"] if reason == "off" else text["reason_down"] if reason else ""
    titles = {w.get("name"): w.get("title") for w in ((words or {}).get("tables") or [])
              if isinstance(w, dict) and w.get("title")}
    items = []
    for t in [t for t in facts if t["group"] == "main"][:MAX_PROPOSALS]:
        keep, out = _useful_columns(t)
        if not keep:
            continue
        table = exp.Table(this=exp.to_identifier(t["name"], quoted=True),
                          db=exp.to_identifier(t["schema"], quoted=True) if t["schema"] else None)
        query = exp.select(*[exp.column(c, quoted=True) for c in keep]).from_(table)
        items.append({
            "name": text["name"].format(title=titles.get(t["name"]) or t["name"]),
            "purpose": text["purpose"].format(table=titles.get(t["name"]) or t["name"]),
            "sql": query.sql(dialect=_dialect(family)),
            "includes": [text["rows"].format(n=f"{t['rows'] or 0:,}")] + keep[:6],
            "leaves_out": out[:8],
            "why": text["why"].format(reason=why_reason),
            "source": "auto",
        })
    return items


async def propose(db: AsyncSession, user: User, source: DataSource, brief: dict | None,
                  words: dict | None, lang: str, client) -> tuple[list[dict], str | None]:
    """(proposals, why the model was not used or failed -- None when it was)."""
    from .access import _family

    facts = await understand.load_facts(db, source)
    if not facts:
        return [], "empty"
    family = _family(source)
    catalog = catalog_of(facts)
    from . import meaning
    m = await meaning.load(db, source.id)
    reading = meaning.prompt_text(m)
    reason = None
    got = None
    if not source.allow_llm_sampling:
        reason = "off"
    elif client is None or not getattr(client, "enabled", True):
        reason = "unavailable"
    else:
        from .access import release
        await release(db)
        got = await client.complete_json(build_prompt(source, facts, words, brief, lang, reading),
                                         PROPOSALS_SCHEMA, max_tokens=4000, temperature=0.2, enforce=True)
        if not got:
            reason = "failed"

    async def repair(item: dict, why: str) -> dict | None:
        if client is None or reason is not None:
            return None
        msgs = build_refine_prompt(source, facts, words, brief, item, [],
                                   f"The query failed: {why}. Fix the SQL so it runs; keep the purpose.", lang,
                                   reading)
        fixed = await client.complete_json(msgs, REFINE_SCHEMA, max_tokens=2000, temperature=0.1, enforce=True)
        return (fixed or {}).get("proposal")

    # What they asked to leave out, as the model named it in the catalog: taken
    # out of every query by code, not left to each query's wording (persona
    # test 2026-10-12: "leave out military numbers" kept `mil_no`).
    banned = banned_columns((got or {}).get("excluded_columns"), catalog) if (brief or {}).get("exclude") else set()
    accepted: list[dict] = []
    for item in ((got or {}).get("proposals") or [])[:MAX_PROPOSALS]:
        if isinstance(item, dict):
            if banned and item.get("sql"):
                sql, removed = without_columns(str(item["sql"]), family, banned)
                if removed:
                    item = {**item, "sql": sql,
                            "leaves_out": _clean_list(item.get("leaves_out")) + removed}
            if item.get("sql"):
                sql, named = with_names(str(item["sql"]), family, facts)
                if named:
                    item = {**item, "sql": sql}
                sql, size = with_group_size(str(item["sql"]), family)
                if size:
                    item = {**item, "sql": sql, "group_size": size}
            ok = await _accept(db, user, source, item, catalog, family, repair, m)
            if ok:
                accepted.append(ok)
    if not accepted:
        for item in fallback_items(facts, family, lang, reason or ("failed" if got is not None else None), words):
            ok = await _accept(db, user, source, item, catalog, family, None, m)
            if ok:
                accepted.append(ok)
        if reason is None:
            reason = "failed"
    return accepted, reason


async def refine(db: AsyncSession, user: User, source: DataSource, brief: dict | None,
                 words: dict | None, proposal: dict, message: str, lang: str, client) -> tuple[dict | None, str]:
    """(revised proposal or None, reply to show). The proposal keeps its id."""
    from .access import _family

    if not source.allow_llm_sampling or client is None or not getattr(client, "enabled", True):
        return None, "off"
    facts = await understand.load_facts(db, source)
    family = _family(source)
    history = list(proposal.get("history") or [])
    from . import meaning
    from .access import release
    m = await meaning.load(db, source.id)
    reading = meaning.prompt_text(m)
    await release(db)
    got = await client.complete_json(
        build_refine_prompt(source, facts, words, brief, proposal, history, message, lang, reading),
        REFINE_SCHEMA, max_tokens=2500, temperature=0.2, enforce=True)
    if not got or not isinstance(got.get("proposal"), dict):
        return None, "failed"

    async def repair(item: dict, why: str) -> dict | None:
        fixed = await client.complete_json(
            build_refine_prompt(source, facts, words, brief, item, history,
                                f"The query failed: {why}. Fix the SQL so it runs; keep the change asked for.", lang,
                                reading),
            REFINE_SCHEMA, max_tokens=2000, temperature=0.1, enforce=True)
        return (fixed or {}).get("proposal")

    revised = await _accept(db, user, source, {**got["proposal"], "source": "ai"},
                            catalog_of(facts), family, repair, m)
    if revised is None:
        return None, "unusable"
    reply = str(got.get("reply") or "").strip()
    revised["id"] = proposal["id"]
    revised["history"] = history + [{"role": "user", "text": message},
                                    {"role": "assistant", "text": reply}]
    return revised, reply


def narrowed_to(sql: str | None, dialect: str | None = None) -> set[str]:
    """The text values a dataset's own query keeps it to: the string literals
    its WHERE compares a column with by `=` or `IN` ("COMI 2023 price history"
    is `WHERE ticker = 'COMI'`). Read from the query's structure, never from
    its name. Empty when the query cannot be read."""
    import sqlglot
    from sqlglot import exp
    try:
        tree = sqlglot.parse_one(sql or "", read=dialect or None)
    except Exception:                                               # noqa: BLE001
        return set()
    out: set[str] = set()
    for where in tree.find_all(exp.Where):
        for node in where.find_all(exp.EQ, exp.In):
            for lit in node.find_all(exp.Literal):
                if lit.is_string and lit.this.strip():
                    out.add(lit.this.strip().casefold())
    return out
