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
    "properties": {"proposals": {"type": "array", "items": PROPOSAL_ITEM}},
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
    """The shape `validate_column_references` reads: [{name, columns:[{name}]}]."""
    return [{"name": t["name"], "columns": [{"name": c.name} for c in t["_columns"]]} for t in facts]


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
            understand._column_line(c, t["_stats"]) for c in t["_columns"][:PROMPT_COLUMNS]))
    return "\n".join(lines)


def _brief_text(brief: dict | None) -> str:
    b = brief or {}
    parts = [("Their work", b.get("work")), ("What to focus on", b.get("focus")),
             ("What they need to know", b.get("questions")), ("What to leave out", b.get("exclude"))]
    said = [f"- {k}: {v}" for k, v in parts if v]
    return "\n".join(said) if said else "- They did not say. Propose what most people would need."


def _rules(lang: str) -> str:
    return (
        "Rules:\n"
        "- Each dataset is ONE read-only SQL query (SELECT, or WITH ... SELECT) over the tables "
        "listed. Use only the listed tables and columns. Join tables where 'Joins to' says they "
        "connect, or on a shared column that clearly means the same thing in both (the same "
        "date, the same id). When the person's questions compare two tables (a stock against "
        "the market index, sales against targets), one proposal should be that join, so they "
        "can compare without building it themselves.\n"
        "- Keep rows, not totals: a dataset feeds many charts, so do not GROUP BY unless the "
        "person clearly needs a summary table.\n"
        "- Leave out what does not help: system columns, duplicate copies of the same value in "
        "another language, columns that are almost all empty, links, and personal details "
        "(names, phones, emails, ids of people) unless their work needs them. Honour 'What to "
        "leave out'.\n"
        "- Give columns plain snake_case aliases only when the original name is unclear.\n"
        "- The proposals must answer DIFFERENT questions, not three versions of one query: "
        "make the first the broad one (every relevant row and the useful columns, no narrowing "
        "filter beyond what the person asked), and let the others take a different angle -- a "
        "different table or join, a different slice of rows, or a summary table -- each saying "
        "in 'why' what it lets them see that the others do not.\n"
        "- Only filter rows when the person's answers ask for it, and say so in leaves_out.\n"
        "- name is a short plain title, the way a person would say it (e.g. 'Daily stock prices', "
        "'Cars for sale in Cairo') -- never snake_case or a table name; it becomes the dataset's "
        "name.\n"
        f"- Write name, purpose, includes, leaves_out and why in {_LANGUAGE.get(lang, 'English')}, "
        "in plain words for someone who never wrote SQL: purpose = one sentence on what it is for; "
        "includes/leaves_out = short items in business words (e.g. 'Price and mileage', "
        "'Seller phone numbers'); why = one or two sentences tying the choice to their work.\n"
    )


def build_prompt(source: DataSource, facts: list[dict], words: dict | None,
                 brief: dict | None, lang: str) -> list[dict]:
    system = ("You help a person pick the right part of a database to analyse. You propose "
              f"up to {MAX_PROPOSALS} datasets.\n" + _rules(lang))
    user = (f"Database: {source.name}\n\nAbout the person (hints, not rules):\n{_brief_text(brief)}\n\n"
            f"Tables:\n{_describe(facts, words)}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_refine_prompt(source: DataSource, facts: list[dict], words: dict | None, brief: dict | None,
                        proposal: dict, history: list[dict], message: str, lang: str) -> list[dict]:
    system = ("You change ONE dataset proposal as the person asks, keeping everything else "
              "about it. Return the whole revised proposal and a one-sentence reply saying what "
              f"you changed, in {_LANGUAGE.get(lang, 'English')}.\n" + _rules(lang))
    convo = "\n".join(f"{m['role']}: {m['text']}" for m in history[-6:])
    user = (f"Database: {source.name}\n\nAbout the person:\n{_brief_text(brief)}\n\n"
            f"Tables:\n{_describe(facts, words)}\n\nCurrent proposal:\n"
            f"name: {proposal.get('name', '')}\npurpose: {proposal.get('purpose', '')}\n"
            f"sql: {proposal.get('sql') or '(missing -- write one)'}\n"
            f"includes: {proposal.get('includes', [])}\nleaves_out: {proposal.get('leaves_out', [])}\n\n"
            + (f"Earlier in this conversation:\n{convo}\n\n" if convo else "")
            + f"The person now asks: {message}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── proposals ───────────────────────────────────────────────────────────────

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
                  repair) -> dict | None:
    """Check, run, and if needed repair one proposal. None when it cannot be used."""
    sql, why = check_sql(item.get("sql", ""), family, catalog)
    run = None
    if sql is not None:
        run = await test_run(db, user, source, sql)
        why = run["error"]
        if why is None and run["row_count"] == 0:
            why = "the query returns no rows"
    if why is not None and repair is not None:
        fixed = await repair(item, why)
        if fixed:
            item = {**item, **fixed}
            sql, why = check_sql(item.get("sql", ""), family, catalog)
            if sql is not None:
                run = await test_run(db, user, source, sql)
                why = run["error"] or ("the query returns no rows" if run["row_count"] == 0 else None)
    if why is not None or sql is None or run is None:
        logger.info("guided setup: dropped proposal %r: %s", item.get("name"), why)
        return None
    return {
        "id": uuid.uuid4().hex[:10],
        "name": str(item.get("name") or "").strip()[:120] or "Dataset",
        "purpose": str(item.get("purpose") or "").strip(),
        "sql": sql,
        "tables": _tables_in(sql, family),
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
    reason = None
    got = None
    if not source.allow_llm_sampling:
        reason = "off"
    elif client is None or not getattr(client, "enabled", True):
        reason = "unavailable"
    else:
        from .access import release
        await release(db)
        got = await client.complete_json(build_prompt(source, facts, words, brief, lang),
                                         PROPOSALS_SCHEMA, max_tokens=3500, temperature=0.2, enforce=True)
        if not got:
            reason = "failed"

    async def repair(item: dict, why: str) -> dict | None:
        if client is None or reason is not None:
            return None
        msgs = build_refine_prompt(source, facts, words, brief, item, [],
                                   f"The query failed: {why}. Fix the SQL so it runs; keep the purpose.", lang)
        fixed = await client.complete_json(msgs, REFINE_SCHEMA, max_tokens=2000, temperature=0.1, enforce=True)
        return (fixed or {}).get("proposal")

    accepted: list[dict] = []
    for item in ((got or {}).get("proposals") or [])[:MAX_PROPOSALS]:
        if isinstance(item, dict):
            ok = await _accept(db, user, source, item, catalog, family, repair)
            if ok:
                accepted.append(ok)
    if not accepted:
        for item in fallback_items(facts, family, lang, reason or ("failed" if got is not None else None), words):
            ok = await _accept(db, user, source, item, catalog, family, None)
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
    from .access import release
    await release(db)
    got = await client.complete_json(
        build_refine_prompt(source, facts, words, brief, proposal, history, message, lang),
        REFINE_SCHEMA, max_tokens=2500, temperature=0.2, enforce=True)
    if not got or not isinstance(got.get("proposal"), dict):
        return None, "failed"

    async def repair(item: dict, why: str) -> dict | None:
        fixed = await client.complete_json(
            build_refine_prompt(source, facts, words, brief, item, history,
                                f"The query failed: {why}. Fix the SQL so it runs; keep the change asked for.", lang),
            REFINE_SCHEMA, max_tokens=2000, temperature=0.1, enforce=True)
        return (fixed or {}).get("proposal")

    revised = await _accept(db, user, source, {**got["proposal"], "source": "ai"},
                            catalog_of(facts), family, repair)
    if revised is None:
        return None, "unusable"
    reply = str(got.get("reply") or "").strip()
    revised["id"] = proposal["id"]
    revised["history"] = history + [{"role": "user", "text": message},
                                    {"role": "assistant", "text": reply}]
    return revised, reply
