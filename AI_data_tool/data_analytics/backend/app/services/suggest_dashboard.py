"""Propose a whole dashboard for a named kind of person.

The existing suggestion path (`insights.suggest_widgets_from_findings` and
`report_composer.compose_page`) starts from a dataset that already exists and
ranks by statistical interest. That is the right engine once you have a table to
look at. It cannot help the person who has just connected a database and does not
know which of its tables to join, and it has no notion of WHO is asking -- an
instructor, a student-affairs officer and a dean want three different dashboards
out of one database.

This fills that gap: catalog + role in, one SQL query and a widget list out.

IT ONLY PROPOSES
----------------
Nothing is created until the caller accepts. A dashboard that appears by itself
and is subtly wrong is worse than no dashboard, because nobody audits what they
did not ask for.

WHY THE VALIDATION IS HERE AND NOT IN THE PROMPT
------------------------------------------------
The proposed SQL is executed to build a dataset, so it must be a single read.
Asking the model nicely is not a control: `validate_suggestion` refuses anything
that is not one `SELECT`, anything naming a table outside this source's catalog,
and any widget bound to a column the query does not return. The last one is not a
security rule -- it is the mistake models actually make, aliasing a column in the
prose and forgetting it in the SELECT, which renders as a broken tile.
"""
from __future__ import annotations

import re

#: Widget types this may propose. A deliberately small set: these five cover the
#: shapes a first-draft dashboard needs, and every one of them is driven by the
#: same dimension/measure/aggregation contract, so a proposal is runnable without
#: a per-type translation step. The catalogue has 64; suggesting an exotic one the
#: user then has to configure by hand is not help.
ALLOWED_WIDGETS = ("kpi", "bar", "line", "pie", "table")

#: Aggregations offered to the model, a subset of the engine's 16. Left out are
#: the ones whose meaning depends on the grain (std, variance, percentiles) --
#: wrong on a first draft more often than right.
ALLOWED_AGGREGATIONS = ("sum", "avg", "count", "countd", "min", "max")

_SELECT_ONLY = re.compile(r"^\s*select\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|pragma|grant)\b",
    re.IGNORECASE)
#: Table names as they appear after FROM or JOIN. Good enough to check membership
#: of the catalog; it is a guard on top of a read-only statement, not a parser.
_TABLE_REF = re.compile(r"\b(?:from|join)\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_.]*)[\"`\]]?",
                        re.IGNORECASE)
#: `AS alias` and bare trailing aliases in the projection.
_ALIAS = re.compile(r"\bas\s+[\"`\[]?([A-Za-z_][A-Za-z0-9_]*)[\"`\]]?", re.IGNORECASE)

SUGGESTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "sql", "widgets"],
    "properties": {
        "title": {"type": "string"},
        "sql": {"type": "string"},
        "widgets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["widget_type", "title", "dimension", "measure", "aggregation"],
                "properties": {
                    "widget_type": {"type": "string", "enum": list(ALLOWED_WIDGETS)},
                    "title": {"type": "string"},
                    # Empty string, not null: a KPI has no dimension, and strict
                    # JSON mode is happier with one type per field than with a
                    # nullable one.
                    "dimension": {"type": "string"},
                    "measure": {"type": "string"},
                    "aggregation": {"type": "string", "enum": list(ALLOWED_AGGREGATIONS)},
                },
            },
        },
    },
}


def _describe(catalog: list[dict]) -> str:
    out = []
    for t in catalog:
        cols = ", ".join(
            f"{c['name']} ({c.get('dtype') or 'unknown'})" for c in (t.get("columns") or []))
        line = f"- {t['name']}"
        if t.get("description"):
            line += f" — {t['description']}"
        out.append(line + f"\n    columns: {cols}")
    return "\n".join(out)


def _describe_joins(joins: list[dict] | None) -> str:
    """The database's own foreign keys, written out as join clauses.

    Without these the model has to guess how the tables connect, and on the
    Moodle schema it guessed `mdl_user_enrolments.courseid` twice — a column that
    does not exist, because that table reaches a course through `mdl_enrol`. It
    guessed the same wrong thing through the repair round too, which is the tell
    that this was not carelessness: the prompt listed every table and every
    column and never said how they join. The sync had already found 19 real keys;
    not passing them on was the actual bug.
    """
    if not joins:
        return ""
    lines = "\n".join(
        f"- {j['from_table']}.{j['from_column']} = {j['to_table']}.{j['to_column']}"
        for j in joins)
    return ("\n\nThese are the ONLY joins that exist in this database. Use them "
            "exactly as written; do not invent a join or a column:\n" + lines)


def build_prompt(catalog: list[dict], for_role: str, goal: str | None = None,
                 joins: list[dict] | None = None,
                 data_range: str | None = None) -> list[dict]:
    """The messages that ask for one dashboard, for one kind of person."""
    want = f"\nWhat they said they want: {goal}" if goal else ""
    # The model has no clock, and a connected database is rarely live. Told only
    # to design for an instructor, it proposed "Today's Pulse" filtered to the
    # last 7 days — valid SQL, zero rows, every tile blank, because the newest
    # event in that database was three months old.
    when = (f"\n\nThe data runs from {data_range}. There is nothing more recent "
            f"than the end of that range, so do not build a dashboard about "
            f"today or the last few days — it would come back empty."
            if data_range else "")
    system = (
        "You design a first-draft analytics dashboard from a database schema.\n"
        "You return ONE SQL SELECT that produces a single flat table, and a list of "
        "widgets over that table's output columns.\n"
        "Rules that matter:\n"
        f"- widget_type is one of: {', '.join(ALLOWED_WIDGETS)}\n"
        f"- aggregation is one of: {', '.join(ALLOWED_AGGREGATIONS)}\n"
        "- every dimension and measure MUST be a column alias your SQL selects\n"
        "- a kpi has an empty dimension\n"
        "- alias every selected column with AS, in snake_case\n"
        "- one SELECT only. No INSERT, UPDATE, DELETE, DDL or second statement.\n"
        "- prefer 5 to 8 widgets: a headline row of kpis, then the breakdowns that "
        "answer this person's actual job."
    )
    user = (
        f"The dashboard is for: {for_role}.{want}\n\n"
        f"The database contains these tables:\n{_describe(catalog)}"
        f"{_describe_joins(joins)}{when}\n\n"
        f"Design the dashboard this {for_role} would open every morning."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_suggestion(suggestion: dict, known_tables: set[str]) -> tuple[bool, str]:
    """`(ok, reason)`. Everything the model proposes passes through here first."""
    sql = (suggestion or {}).get("sql") or ""
    widgets = (suggestion or {}).get("widgets") or []

    if not _SELECT_ONLY.match(sql):
        return False, "the query must be a single SELECT"
    # A trailing semicolon is fine; a second statement after one is not.
    if [part for part in sql.split(";")[1:] if part.strip()]:
        return False, "the query must be a single statement"
    if _FORBIDDEN.search(sql):
        return False, "the query must not modify anything"

    referenced = {t.split(".")[-1] for t in _TABLE_REF.findall(sql)}
    unknown = sorted(t for t in referenced if t not in known_tables)
    if unknown:
        return False, f"the query names tables this connection does not have: {', '.join(unknown)}"

    if not widgets:
        return False, "no widgets were proposed"

    aliases = {a.lower() for a in _ALIAS.findall(sql)}
    for w in widgets:
        kind = w.get("widget_type")
        if kind not in ALLOWED_WIDGETS:
            return False, f"unknown widget type: {kind}"
        if w.get("aggregation") not in ALLOWED_AGGREGATIONS:
            return False, f"unknown aggregation: {w.get('aggregation')}"
        for field in ("dimension", "measure"):
            col = (w.get(field) or "").strip()
            if col and col.lower() not in aliases:
                return False, (f"widget '{w.get('title')}' uses {field} '{col}', "
                               "which the query does not select")
    return True, ""



def _table_aliases(tree) -> dict[str, str]:
    """`alias (or bare name) -> real table name`, for every table in the query.

    CTE names are collected too, so a reference into a CTE can be recognised and
    SKIPPED rather than judged against a catalog that has never heard of it.
    """
    import sqlglot.expressions as exp

    cte_names = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    out: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        real = (table.name or "").casefold()
        if real in cte_names:
            continue
        out[(table.alias or table.name or "").casefold()] = real
    return out


def validate_column_references(sql: str, catalog: list[dict]) -> tuple[bool, str]:
    """`(ok, why not)` for every QUALIFIED column reference in the SQL.

    Only qualified references (`alias.column`) are judged. A bare column could
    belong to any table in the FROM list and resolving it properly would mean
    reimplementing the planner; the database is the right judge of those, and the
    probe still asks it.

    Unparseable SQL returns ok: this is a helper that makes a specific, common
    mistake legible, never a second gate that can refuse a working query.
    """
    try:
        import sqlglot
        tree = sqlglot.parse_one(sql)
    except Exception:                                    # noqa: BLE001
        return True, ""
    if tree is None:
        return True, ""

    import sqlglot.expressions as exp

    columns_by_table = {
        (t.get("name") or "").casefold(): {
            (c.get("name") or "").casefold() for c in (t.get("columns") or [])
        }
        for t in catalog
    }
    aliases = _table_aliases(tree)

    for column in tree.find_all(exp.Column):
        qualifier = (column.table or "").casefold()
        if not qualifier:
            continue
        real = aliases.get(qualifier)
        # An alias we cannot resolve to a catalog table is a subquery or a CTE
        # output. Not ours to judge.
        if real is None or real not in columns_by_table:
            continue
        name = (column.name or "").casefold()
        if name in columns_by_table[real]:
            continue

        owners = sorted(tbl for tbl, cols in columns_by_table.items() if name in cols)
        where = ""
        if owners:
            # Name the alias the query already gave that table where it has one,
            # so the fix is a substitution rather than a search.
            by_table = {v: k for k, v in aliases.items()}
            shown = ", ".join(
                f"{tbl} (aliased {by_table[tbl]})" if tbl in by_table else tbl
                for tbl in owners)
            where = f" It is a column of {shown}."
        return False, (
            f"the query references {column.table}.{column.name}, but "
            f"{column.table} is {real}, which has no column of that name.{where}"
        )

    return True, ""

#: How many generations one request may cost. The first real run against the
#: Moodle catalog failed validation on attempt 1 (a KPI whose measure was the
#: word "count") and passed on attempt 2, which is the shape this bounds: a
#: careless alias is worth one retry, a model that cannot follow the contract is
#: not worth five.
MAX_ATTEMPTS = 3


async def suggest_dashboard(catalog: list[dict], for_role: str,
                            goal: str | None = None,
                            probe=None) -> tuple[dict | None, str]:
    """Ask the model, refuse anything the validation dislikes, retry with the reason.

    Returns `(suggestion, reason)`. A None suggestion with a reason is the normal
    unhappy path -- the endpoint is off, unreachable, or kept proposing something
    unusable -- and the caller shows the reason rather than a broken dashboard.

    The retry carries the SPECIFIC rejection back to the model, which is the
    agent's own repair pattern (`services/agent/graph.py`): "invalid, try again"
    produces another guess, while "widget 'X' uses measure 'count', which the
    query does not select" produces a fix.
    """
    try:
        from .llm import get_client
        client = get_client()
    except Exception:                                    # noqa: BLE001
        return None, "the model endpoint is not configured"
    if client is None:
        return None, "the model endpoint is not configured"

    known = {t["name"] for t in catalog}
    messages = build_prompt(catalog, for_role, goal)
    why = "the model did not return a usable dashboard"

    for attempt in range(MAX_ATTEMPTS):
        got = await client.complete_json(
            messages, SUGGESTION_SCHEMA, max_tokens=1600, enforce=True)
        if not got:
            # Unreachable or empty. A network failure will not become a valid
            # dashboard on the next try, so stop rather than spend the attempts.
            return None, why
        ok, why = validate_suggestion(got, known)
        if ok:
            # Before the round trip. The catalog already knows which columns
            # belong to which table, so an alias mistake needs no database to
            # find -- and naming the table that DOES have the column is what
            # turns a retry into a fix rather than another guess.
            ok, why = validate_column_references(got.get("sql") or "", catalog)
        if ok and probe is not None:
            # Static checks say the SQL is safe and its aliases line up. Only the
            # database knows whether it RUNS. The first suggestion that passed
            # every check above still died on "DISTINCT is not supported for
            # window functions", so the database gets the last word and its own
            # message is what the model is asked to fix.
            failure = await probe(got["sql"])
            if failure:
                ok, why = False, f"the database refused the query: {failure}"
        if ok:
            return got, ""
        if attempt < MAX_ATTEMPTS - 1:
            messages = messages + [
                {"role": "assistant", "content": _compact(got)},
                {"role": "user", "content":
                    f"That was rejected: {why}. Fix exactly that and return the "
                    "whole dashboard again. Every dimension and measure must be a "
                    "column alias your SQL selects."},
            ]
    return None, why


def _compact(suggestion: dict) -> str:
    """The rejected attempt, small enough to hand back without doubling the prompt."""
    import json
    return json.dumps(suggestion, separators=(",", ":"))[:1500]


#: One proposal's schema, reused for the batch below so the two cannot drift.
_PROPOSAL_SCHEMA = SUGGESTION_SCHEMA

BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {"proposals": {"type": "array", "items": _PROPOSAL_SCHEMA}},
}


def build_batch_prompt(catalog: list[dict], for_role: str, count: int,
                       goal: str | None = None,
                       joins: list[dict] | None = None,
                       data_range: str | None = None) -> list[dict]:
    """Ask for `count` dashboards in one call.

    One call, not `count` calls: the catalog is the expensive part of this prompt
    and sending it three times triples the wait for nothing. The "different
    question" line is load-bearing -- without it the model returns one dashboard
    phrased three ways, which is not a choice.
    """
    messages = build_prompt(catalog, for_role, goal, joins, data_range)
    messages[0]["content"] += (
        f"\n\nReturn {count} DIFFERENT proposals under the key 'proposals'. "
        f"Each one answers a different question this person has — the daily "
        f"check, the problem hunt, the longer trend. Do not restate one "
        f"dashboard {count} times."
    )
    return messages


PERSONA_SCHEMA = {
    "type": "object",
    "properties": {"persona": {"type": ["string", "null"]}},
    "required": ["persona"],
    "additionalProperties": False,
}


async def stated_persona(question: str | None, client=None) -> str | None:
    """Who the person SAID they are, or None when they did not say.

    Measured live: "i am a department manager and i need ... a dashboard" was
    designed "for a Platform Admin" -- the person's role in this system, read
    off their account, while the words "department manager" sat unread in the
    request. Their system role is a fact about their permissions; who the
    dashboard is FOR is whatever they told us, and they told us.

    The model does the reading -- no list of job titles to keep up to date.
    A short enforced-JSON call; any failure means None and the caller keeps
    the role, which is exactly the old behaviour.
    """
    if not question or not question.strip():
        return None
    client = client or get_client()
    got = await client.complete_json(
        [{"role": "system", "content": (
            "Does this request say who the person is, or who the dashboard is "
            "for -- a job, a role, a kind of user (\"I am a department manager\", "
            "\"for our sales team\", \"as a student\")? Return it in 1-4 words, "
            "in the person's own terms, as `persona`. If the request names no "
            "such person, return null. Never guess one from the subject matter.")},
         {"role": "user", "content": f"Request: {question}"}],
        PERSONA_SCHEMA, enforce=True, max_tokens=40, temperature=0.0)
    persona = (got or {}).get("persona") if isinstance(got, dict) else None
    persona = persona.strip() if isinstance(persona, str) else None
    return persona or None


async def suggest_dashboards(catalog: list[dict], for_role: str,
                             goal: str | None = None, count: int = 3,
                             probe=None,
                             joins: list[dict] | None = None,
                             data_range: str | None = None) -> tuple[list[dict], str]:
    """`(proposals, reason)` — several dashboards to choose from.

    Each proposal is validated and probed on its own. Two good proposals and one
    that will not run is a useful answer; discarding all three because of the
    third is not. `reason` is only meaningful when the list comes back empty.
    """
    try:
        from .llm import get_client
        client = get_client()
    except Exception:                                    # noqa: BLE001
        return [], "the model endpoint is not configured"
    if client is None:
        return [], "the model endpoint is not configured"

    messages = build_batch_prompt(catalog, for_role, count, goal, joins, data_range)
    known = {t["name"] for t in catalog}
    kept: list[dict] = []
    rejected: list[str] = []

    # One generation, then at most one repair round. The repair exists because
    # every failure seen on the first real run through the chat was the kind a
    # model fixes when told: an invented column (`mdl_user_enrolments.courseid`
    # -- that table joins through `mdl_enrol`), and a `strftime('%H:%M', ...)`
    # whose colon SQLAlchemy reads as a bind parameter. Without it the person
    # asks for a dashboard and gets an error.
    for attempt in range(2):
        got = await client.complete_json(messages, BATCH_SCHEMA,
                                         max_tokens=4000, enforce=True)
        if not got or not got.get("proposals"):
            break

        rejected = []
        for proposal in got["proposals"][: count - len(kept)]:
            ok, why = await _check(proposal, known, probe, catalog)
            if ok:
                kept.append(proposal)
            else:
                rejected.append((proposal, why))

        if len(kept) >= count or not rejected or attempt == 1:
            break

        # Only the failures go back. Re-asking for the whole batch would risk
        # losing a proposal that was already good.
        messages = messages + [
            {"role": "assistant", "content": _compact(
                {"proposals": [p for p, _ in rejected]})},
            {"role": "user", "content":
                "These were rejected:\n"
                + "\n".join(f"- {p.get('title') or 'untitled'}: {why}"
                            for p, why in rejected)
                + "\nReturn corrected versions of ONLY these, under 'proposals'. "
                  "Use only columns that exist in the schema above, and avoid a "
                  "colon inside any string literal."},
        ]

    if kept:
        return kept, ""
    if rejected:
        return [], "; ".join(f"{p.get('title') or 'untitled'}: {why}"
                             for p, why in rejected)
    return [], "the model did not return any dashboards"


async def _check(proposal: dict, known: set[str], probe,
                 catalog: list[dict] | None = None) -> tuple[bool, str]:
    """Static checks, then the database's opinion.

    `catalog` is optional so every existing caller keeps working, but passing it
    is what lets a wrong table alias be named precisely instead of coming back
    as a truncated driver error the model then fails to act on.
    """
    ok, why = validate_suggestion(proposal, known)
    if not ok:
        return False, why
    if catalog:
        ok, why = validate_column_references(proposal.get("sql") or "", catalog)
        if not ok:
            return False, why
    if probe is None:
        return True, ""
    failure = await probe(proposal["sql"])
    if failure:
        return False, f"the database refused the query: {failure}"
    return True, ""


async def load_catalog(db, source_id: int) -> list[dict]:
    """The tables, columns and descriptions the sync wrote for one connection.

    Lives here rather than in the router because two callers need it -- the
    endpoint and the agent graph -- and a service reaching up into a router to
    borrow it is the upward dependency `test_layer_conformance` exists to stop.
    """
    from sqlalchemy import select

    from ..models.models import SourceColumn, SourceObject

    objects = (await db.execute(
        select(SourceObject).where(SourceObject.data_source_id == source_id)
        .order_by(SourceObject.name)
    )).scalars().all()
    if not objects:
        return []

    by_object: dict[int, list] = {}
    for col in (await db.execute(
        select(SourceColumn)
        .where(SourceColumn.source_object_id.in_([o.id for o in objects]))
        .order_by(SourceColumn.source_object_id, SourceColumn.position)
    )).scalars().all():
        by_object.setdefault(col.source_object_id, []).append(col)

    return [{
        "name": o.name,
        "description": o.description,
        "columns": [{"name": c.name, "dtype": c.dtype} for c in by_object.get(o.id, [])],
    } for o in objects]


async def load_joins(db, source_id: int) -> list[dict]:
    """The join paths the sync recorded for one connection, named table-to-table.

    Declared foreign keys first: those are facts the database states, while an
    inferred relationship is a guess from value overlap. Both are offered, but a
    low-confidence guess is left out — a wrong join produces a plausible dashboard
    of wrong numbers, which is the failure mode this whole module exists to avoid.
    """
    from sqlalchemy import select

    from ..models.models import SourceObject, SourceRelationship

    names = dict((await db.execute(
        select(SourceObject.id, SourceObject.name)
        .where(SourceObject.data_source_id == source_id)
    )).all())
    if not names:
        return []

    rows = (await db.execute(
        select(SourceRelationship)
        .where(SourceRelationship.data_source_id == source_id)
        .order_by(SourceRelationship.source.desc(), SourceRelationship.confidence.desc())
    )).scalars().all()

    out = []
    for r in rows:
        if r.source != "declared" and (r.confidence or 0) < 0.8:
            continue
        left, right = names.get(r.from_object_id), names.get(r.to_object_id)
        if left and right:
            out.append({"from_table": left, "from_column": r.from_column,
                        "to_table": right, "to_column": r.to_column})
    return out


async def load_data_range(db, source_id: int) -> str | None:
    """How current this connection's data is, as "earliest to latest".

    Read from the profile the sync already computed — `min_value`/`max_value` on
    the date-ish columns — rather than by querying the source again. The model
    has no clock and no way to know a connected database is not live; without
    this it proposes a dashboard about today and every tile comes back blank.
    """
    from sqlalchemy import select

    from ..models.models import ColumnStats, SourceColumn, SourceObject

    rows = (await db.execute(
        select(SourceColumn.name, ColumnStats.min_value, ColumnStats.max_value)
        .join(SourceObject, SourceObject.id == SourceColumn.source_object_id)
        .join(ColumnStats, ColumnStats.source_column_id == SourceColumn.id)
        .where(SourceObject.data_source_id == source_id)
    )).all()

    lo, hi = None, None
    for name, min_v, max_v in rows:
        from .ingest import looks_like_time_column
        if not looks_like_time_column(name):
            continue
        for raw, keep_low in ((min_v, True), (max_v, False)):
            iso = _as_date(raw)
            if iso is None:
                continue
            if keep_low and (lo is None or iso < lo):
                lo = iso
            if not keep_low and (hi is None or iso > hi):
                hi = iso
    if lo and hi:
        return f"{lo} to {hi}"
    return None


def _as_date(raw) -> str | None:
    """A profiled value as an ISO date, whether it was stored as an epoch or text."""
    from datetime import datetime, timezone
    try:
        n = float(str(raw))
    except (TypeError, ValueError):
        text = str(raw or "")[:10]
        return text if len(text) == 10 and text[4] == "-" else None
    if 946684800 <= n <= 2208988800:
        return datetime.fromtimestamp(n, timezone.utc).date().isoformat()
    if 946684800000 <= n <= 2208988800000:
        return datetime.fromtimestamp(n / 1000, timezone.utc).date().isoformat()
    return None
