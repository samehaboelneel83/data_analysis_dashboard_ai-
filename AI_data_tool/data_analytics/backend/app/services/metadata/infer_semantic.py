"""Stage 5 — turning structure into meaning.

Four passes, in increasing order of cost and decreasing order of certainty:

  1. semantic type   regex classifiers over the masked sample (email, phone, ...)
  2. role            measure / dimension / identifier / timestamp, from statistics
  3. deprecation     name and emptiness signals
  4. description     the LLM pass — opt-in, and the only part that leaves the box

THE AUTHOR ALWAYS WINS
-----------------------
Every write here is skipped where a human has already set the value. That is
principle 5 applied at the column level: this stage proposes, and a proposal
never overwrites a decision. The check is not an optimisation — without it, a
nightly sync would quietly revert every correction anyone made during the day,
and the corrections would look like they never saved.

THE LLM PASS IS OPTIONAL IN BOTH DIRECTIONS
--------------------------------------------
It is gated on `allow_llm_sampling` per data source (ARCHITECTURE.md open
decision #4 — even a self-hosted endpoint is a disclosure), and it degrades to a
no-op when the endpoint is unreachable. Passes 1-3 are pure local computation
and always run. A metadata sync must complete with the GPU host switched off.
"""
from __future__ import annotations

import logging
import re

from .. import pii

logger = logging.getLogger(__name__)

#: Key under which describe_with_llm returns the TABLE's own description.
#: A column cannot be named this, so it cannot collide with a real one.
_TABLE_DESCRIPTION_KEY = "__table__"
TABLE_DESCRIPTION_KEY = _TABLE_DESCRIPTION_KEY

#: Names that mark a table as no longer in use. Advisory only — a deprecated
#: table is downranked in review and retrieval, never hidden or deleted.
_DEPRECATED_PATTERNS = (
    re.compile(r"_old$", re.I), re.compile(r"_bak$", re.I),
    re.compile(r"_backup$", re.I), re.compile(r"^tmp_", re.I),
    re.compile(r"^temp_", re.I), re.compile(r"_deprecated$", re.I),
    re.compile(r"_v\d+_old$", re.I), re.compile(r"^zz_", re.I),
)

#: Currency and percentage are semantic types a regex over VALUES cannot see —
#: they live in the column NAME. Kept separate from pii's value classifiers.
_NAME_SEMANTICS = (
    ("currency", re.compile(r"(price|amount|cost|revenue|salary|total|fee|charge)", re.I)),
    ("percentage", re.compile(r"(pct|percent|rate|ratio)", re.I)),
)

#: A column this unique is an identifier regardless of what it is called.
_IDENTIFIER_UNIQUENESS = 0.98

#: Above this many distinct values a numeric column is a measure, not a
#: dimension. A numeric column with six distinct values is a category wearing an
#: integer, and grouping by it is usually what a user means.
_DIMENSION_MAX_DISTINCT = 50

_JSON_SCHEMA = {
    "type": "object",
    "properties": {"table": {"type": "string"},
                   "descriptions": {"type": "object"}},
    "required": ["descriptions"],
}


def classify_semantic_type(column_name: str, values: list) -> str | None:
    """The semantic type of a column: what its values MEAN, beyond their dtype.

    Value evidence outranks the name. A column called `amount` holding email
    addresses is an email column that someone named badly, and treating it as
    currency would mask nothing while telling the agent something false.
    """
    from_values = pii.detect_semantic_type(values)
    if from_values:
        return from_values

    for semantic_type, pattern in _NAME_SEMANTICS:
        if pattern.search(column_name):
            return semantic_type
    return None


def classify_role(
    column_name: str, dtype: str | None, stats: dict | None,
) -> str:
    """measure / dimension / identifier / timestamp.

    This is what lets the semantic layer answer "what can I group by, and what
    can I sum?" without a human enumerating it per column.
    """
    stats = stats or {}
    dtype_lower = (dtype or "").lower()

    if any(token in dtype_lower for token in ("date", "time")):
        return "timestamp"

    distinct = stats.get("distinct_count")
    row_count = stats.get("row_count")

    # Near-unique means identity, whatever the column is called. This is also
    # how an undeclared primary key announces itself.
    if distinct and row_count and distinct >= row_count * _IDENTIFIER_UNIQUENESS:
        return "identifier"

    # A name-based identifier check, for the case where row_count is unknown.
    if re.search(r"(^id$|_id$|_key$|_uuid$|^uuid$|_code$)", column_name, re.I):
        if not distinct or not row_count or distinct > _DIMENSION_MAX_DISTINCT:
            return "identifier"

    if any(token in dtype_lower for token in ("int", "float", "numeric", "decimal", "double", "real")):
        # Low-cardinality numerics are categories wearing integers -- `year`,
        # `quarter`, `floor`, a 1-5 rating. Grouping by them is exactly right.
        #
        # But cardinality ALONE decided this, and that is wrong for a
        # quantity that happens to take few values. On a real upload
        # `tuition_fee` held four prices across 240 rows, was called a
        # dimension, and the composed dashboard offered "Share of Intake by
        # Tuition Fee" -- an intake sliced by price band as though price were
        # a category. Two signals separate the cases; cardinality separates
        # neither.
        if distinct is not None and distinct <= _DIMENSION_MAX_DISTINCT:
            return "measure" if _is_continuous_quantity(column_name, dtype_lower) else "dimension"
        return "measure"

    return "dimension"


#: Names that denote a quantity rather than a label. A column called a price is
#: a price whether it holds four values or four thousand.
#:
#: Money-shaped, deliberately: these are the ones where a low-cardinality
#: quantity is common (a fee schedule, a small price list) AND where treating it
#: as a category produces a chart that looks plausible and answers nothing.
_CONTINUOUS_NAME = re.compile(
    r"(^|_)(price|prices|amount|amounts|cost|costs|fee|fees|revenue|sales|"
    r"salary|wage|balance|spend|budget|total|subtotal|charge|payment|"
    r"turnover|profit|margin|value)($|_)",
    re.IGNORECASE)


def _is_continuous_quantity(column_name: str, dtype_lower: str) -> bool:
    """True when a low-cardinality numeric is a QUANTITY, not a category.

    Two independent signals, either sufficient:

    - **A fractional dtype.** You do not group by 8,800.50. A float is a
      measurement; an integer may well be a code, a year or a rating.
    - **A monetary name.** Money is often stored in whole units, so the dtype
      signal alone would miss `revenue INTEGER`. The name carries those.

    Deliberately NOT triggered by an integer with no telling name:
    `star_rating`, `band`, `year`, `severity` and a Likert scale are all
    genuinely categorical, and reclassifying them would break every breakdown
    built on them. Pinned in `tests/test_classify_role_measures.py`.
    """
    if _CONTINUOUS_NAME.search(column_name or ""):
        return True
    return any(token in dtype_lower
               for token in ("float", "double", "real", "decimal", "numeric"))


#: The longest a single example value may be in a prompt.
#:
#: Not a tidiness rule -- a correctness one. A PostGIS geometry stringifies to a
#: multi-kilobyte WKB hex blob, and five of those across a handful of geometry
#: columns built a 31,869-token prompt against a 32,768-token context window.
#: The endpoint returned 400, `complete_json` turned that into None as designed,
#: and the table simply went undescribed -- SEVEN of 82 objects on the live
#: source, silently, with the run still reporting `ok`.
#:
#: 80 characters is past the length at which an example still teaches anything.
#: A model learns "this column holds geometry" from the first fragment; the
#: remaining four kilobytes are cost without information.
VALUE_PREVIEW_CHARS = 80


def _short(value) -> str:
    """One example value, rendered short enough to be safe in a prompt."""
    text = str(value)
    if len(text) <= VALUE_PREVIEW_CHARS:
        return text
    # The ellipsis is deliberate and visible: the model should be able to tell a
    # truncated value from a complete one, or it may describe the fragment as
    # though it were the whole value.
    return text[:VALUE_PREVIEW_CHARS] + "…"


def detect_deprecation(table_name: str, row_count: int | None) -> tuple[bool, str | None]:
    """Whether a table looks abandoned, and why.

    The reason is returned alongside the verdict so review can show it. "This
    looks deprecated" invites an argument; "named _old and holds no rows" ends
    one.
    """
    for pattern in _DEPRECATED_PATTERNS:
        if pattern.search(table_name):
            return True, f"name matches {pattern.pattern}"
    if row_count == 0:
        return True, "table is empty"
    return False, None


def apply_column_inference(
    columns: list[dict], author_overrides: dict | None = None,
) -> dict[str, dict]:
    """Run passes 1-3 over a table's columns.

    `author_overrides` is the dataset's existing `column_meta`. Any field a
    human already set is left alone — the whole point of the stage is to fill
    gaps, never to relitigate decisions.
    """
    overrides = author_overrides or {}
    out: dict[str, dict] = {}

    for column in columns:
        name = column["name"]
        author = overrides.get(name) or {}
        proposed: dict = {}

        if not author.get("semantic_type"):
            semantic_type = classify_semantic_type(name, column.get("sample_values") or [])
            if semantic_type:
                proposed["semantic_type"] = semantic_type

        if not author.get("role"):
            proposed["role"] = classify_role(name, column.get("dtype"), column.get("stats"))

        if proposed:
            out[name] = proposed

    return out


#: Object kinds that are a saved query rather than stored rows.
#:
#: Introspection reports what the driver reports, and the word varies by engine
#: -- "view", "materialized view", "m_view". A materialized view is the awkward
#: case: its rows ARE stored, but it is still defined as a query and derived
#: from other objects, which is the part a reader needs told. Grouping it here
#: describes it correctly; calling it a table would not.
_VIEW_KINDS = {"view", "materialized view", "materialized_view", "m_view"}


def build_description_prompt(table_name: str, columns: list[dict],
                             kind: str = "table") -> list[dict]:
    """The Stage 5.4 prompt.

    Carries top_k values and a MASKED five-row sample. top_k is what makes the
    descriptions worth having: a model told that `st_cd` holds 1, 2 and 3 can
    say it looks like a status code, where a model told only "integer column
    named st_cd" can say nothing useful.

    `kind` is not decoration. Without it this prompt asserted "table" outright,
    and the 48 views on the live source were each described as a table that
    "stores" its rows -- false about where the data lives and about whether it
    can be written to. A view is a saved query; the sentence worth having says
    what question it answers, not what it holds.
    """
    lines = []
    for column in columns:
        parts = [f"- {column['name']} ({column.get('dtype') or 'unknown'}"]
        role = column.get("role")
        if role:
            parts.append(f", {role}")
        parts.append(")")
        top_k = column.get("top_k") or []
        if top_k:
            values = ", ".join(_short(entry.get("value")) for entry in top_k[:8])
            parts.append(f" — common values: {values}")
        sample = column.get("sample_values") or []
        if sample and not top_k:
            parts.append(f" — examples: {', '.join(_short(v) for v in sample[:5])}")
        lines.append("".join(parts))

    is_view = (kind or "table").lower() in _VIEW_KINDS
    noun = "view" if is_view else "table"

    if is_view:
        # Say what a view IS, rather than trusting the word to carry it. The
        # failure being fixed is a model describing derived rows as stored
        # ones, and the correction has to be explicit enough to displace that.
        subject = (
            "You document a database VIEW for a data catalog. A view is a "
            "SAVED QUERY: its rows are derived from other tables when it is "
            "read, not stored in it. Write one sentence saying what question "
            "this view answers and what it is derived from, and one sentence "
            "per column describing what that column holds. Do not say the view "
            '"stores" or "contains" data.'
        )
    else:
        subject = (
            "You document a database TABLE for a data catalog. Given its "
            "columns, write one sentence describing what the table holds, and "
            "one sentence per column describing what that column holds."
        )

    return [
        {
            "role": "system",
            "content": (
                subject + " Do not speculate beyond the evidence given. Reply "
                'with ONLY a JSON object: {"table": "<sentence>", '
                '"descriptions": {"<column>": "<sentence>"}}'
            ),
        },
        {
            "role": "user",
            "content": (f"{noun.capitalize()}: {table_name}\nColumns:\n"
                        + "\n".join(lines)),
        },
    ]


#: How many columns to ask about in one call.
#:
#: Bounded by the RESPONSE, not the prompt. The reply carries one sentence per
#: column, so it grows with the column count while the prompt stays modest --
#: and a reply cut off by max_tokens is invalid JSON, which fails the contract
#: and yields nothing at all. On the live source that silently cost the six
#: ~50-column geometry cluster views their descriptions, with the run still
#: reporting `ok`.
#:
#: 40 keeps a chunk's reply near 2,000 tokens, comfortably inside any context
#: window this runs against, and leaves most tables (median well under 20
#: columns) as a single call.
COLUMNS_PER_DESCRIBE_CALL = 40

#: Output tokens allowed per column: a sentence, plus its JSON key and quoting.
#: Column names here are long (`individual_original_green_availability_geom`),
#: so the key is a real share of the cost, not a rounding error.
TOKENS_PER_COLUMN = 45

#: Fixed overhead: the table's own sentence, plus the JSON scaffolding.
DESCRIBE_TOKEN_FLOOR = 300


def _describe_token_budget(columns: list[dict]) -> int:
    """Enough room to answer for exactly the columns being asked about.

    A fixed budget is the bug: it is generous for a five-column table and short
    for a fifty-column one, and the short case fails invisibly.
    """
    return DESCRIBE_TOKEN_FLOOR + TOKENS_PER_COLUMN * len(columns)


async def describe_with_llm(
    table_name: str, columns: list[dict], client, *, allow: bool,
    kind: str = "table",
) -> dict[str, str]:
    """Ask the model to describe a table's columns.

    Returns {} — never raises — whenever the pass cannot run: consent withheld,
    no client, endpoint unreachable, or a response that never satisfied the JSON
    contract. Stage 5 is an enrichment; a sync that fails because a description
    could not be written would be a worse product than one without descriptions.

    Only descriptions for columns actually asked about are returned, because a
    model will occasionally invent a plausible extra column name and inventing
    catalog entries is exactly what this layer must not do.
    """
    if not allow:
        # Consent is per source and defaults to off. Not an error.
        return {}
    if client is None or not columns:
        return {}

    out: dict[str, str] = {}
    # Chunked, because the RESPONSE grows with the column count even though the
    # prompt is bounded. One chunk per COLUMNS_PER_DESCRIBE_CALL columns, each
    # with a budget sized to what it actually asked for.
    for start in range(0, len(columns), COLUMNS_PER_DESCRIBE_CALL):
        chunk = columns[start:start + COLUMNS_PER_DESCRIBE_CALL]
        got = await client.complete_json(
            build_description_prompt(table_name, chunk, kind), _JSON_SCHEMA,
            max_tokens=_describe_token_budget(chunk), temperature=0.1,
            background=True,
        )
        if not got:
            logger.info(
                "no LLM descriptions for %s columns %d-%d (%s)", table_name,
                start, start + len(chunk),
                getattr(client, "last_error", "unknown"),
            )
            # One failed chunk costs its own columns, not the whole table. A
            # partly described 50-column view is far better than none, and the
            # undescribed columns are simply proposed again next sync.
            continue

        asked = {c["name"] for c in chunk}
        descriptions = got.get("descriptions") or {}
        out.update({
            name: str(text).strip()
            for name, text in descriptions.items()
            if name in asked and isinstance(text, (str, int, float))
            and str(text).strip()
        })

        # The table's own sentence rides along on a request that was being made
        # anyway. Keyed on a name no column can have, so it cannot collide with
        # one. Taken from the FIRST chunk that answers: every chunk is asked,
        # since each is a self-contained prompt, but the first sentence is
        # written with no less context than the others and re-writing it per
        # chunk would just overwrite it repeatedly.
        table_text = str(got.get("table") or "").strip()
        if table_text and _TABLE_DESCRIPTION_KEY not in out:
            out[_TABLE_DESCRIPTION_KEY] = table_text

    return out


#: Only an overview. Asking for a sentence per table here made the response
#: grow with the size of the database — measured, that failed outright at 82
#: tables. Per-table sentences come from the per-table call instead.
_SOURCE_SCHEMA = {
    "type": "object",
    "properties": {"overview": {"type": "string"}},
    "required": ["overview"],
}


def build_source_prompt(
    source_name: str, tables: list[dict], relationships: list[dict] | None = None,
) -> list[dict]:
    """The prompt for describing a whole database.

    Deliberately structure-only: table names, column names, roles and semantic
    types, plus the relationships between tables. No values are sent, because
    none are needed — what makes a database comprehensible is its shape and how
    its parts connect, and that is also the part with no disclosure risk.

    Relationships matter most here. A list of tables reads as a list of tables;
    the same list with "order_items.order_id references orders.id" reads as a
    system, and the description that comes back reflects that difference.
    """
    tables_only, views_only = [], []
    for table in tables:
        columns = table.get("columns") or []
        # Key columns only. An overview is about the SHAPE of the database, and
        # listing all 1,354 columns of an 82-table source would bury that in
        # noise while costing thousands of tokens.
        key_columns = [c for c in columns
                       if c.get("role") == "identifier" or c.get("semantic_type")]
        shown = ", ".join(
            f"{c['name']}" + (f" [{c['semantic_type']}]" if c.get("semantic_type") else "")
            for c in (key_columns or columns)[:6]
        )
        rows = table.get("row_count")
        size = f", ~{rows:,} rows" if rows else ""
        line = f"- {table['name']} ({len(columns)} columns{size}): {shown}"
        # Sorted apart rather than into one list. On this source 48 of 82
        # objects are views, and a single flat list invites the overview to
        # describe half the database as storage it is not.
        target = (views_only
                  if (table.get("kind") or "table").lower() in _VIEW_KINDS
                  else tables_only)
        target.append(line)

    joins = []
    for rel in relationships or []:
        joins.append(
            f"- {rel['from_table']}.{rel['from_column']} -> "
            f"{rel['to_table']}.{rel['to_column']}"
        )

    body = f"Database connection: {source_name}"
    if tables_only:
        body += "\n\nTables (stored data):\n" + "\n".join(tables_only)
    if views_only:
        body += ("\n\nViews (saved queries derived from those tables, "
                 "not separate storage):\n" + "\n".join(views_only))
    if joins:
        body += "\n\nRelationships found:\n" + "\n".join(joins)

    return [
        {
            "role": "system",
            "content": (
                "You are documenting a database for a data catalog. Given its "
                "tables, its views and the relationships between them, write "
                "2-4 sentences on what this database is for, what its central "
                "entities are, and how they relate. Tables hold the stored "
                "data; views are saved queries over them, so treat the tables "
                "as the entities and the views as the questions people ask of "
                "them. Concrete and factual; do not speculate beyond the "
                "structure given. Do not list every table.\n"
                'Reply with ONLY a JSON object: {"overview": "..."}'
            ),
        },
        {"role": "user", "content": body},
    ]


#: Above this many distinct values, "label what this code means" turns into
#: "enumerate the data" -- a model asked to gloss 80 raw values is guessing
#: sentences for values it has never actually seen described. Mirrors the
#: eligibility check in catalog_sync.stage_describe.
ENUM_LABEL_MAX_VALUES = 12

#: Output budget per label: a short phrase, plus its JSON key/value quoting.
TOKENS_PER_LABEL = 40

#: Fixed overhead: the JSON scaffolding around however many labels are asked for.
ENUM_LABEL_TOKEN_FLOOR = 100

_ENUM_LABEL_SCHEMA = {
    "type": "object",
    "properties": {"labels": {"type": "object"}},
    "required": ["labels"],
}


def build_enum_label_prompt(table_name: str, columns: list[dict]) -> list[dict]:
    """The Stage 5.5 prompt: what does each coded value MEAN?

    `columns` is [{"name", "dtype", "description", "top_k"}, ...] -- only
    columns already known (by the caller) to be eligible: top_k exists and is
    short enough that "meaning" is a sensible question to ask.
    """
    lines = []
    for column in columns:
        values = ", ".join(
            _short(entry.get("value"))
            for entry in (column.get("top_k") or [])[:ENUM_LABEL_MAX_VALUES]
        )
        desc = f" — {column['description']}" if column.get("description") else ""
        lines.append(
            f"- {column['name']} ({column.get('dtype') or 'unknown'}){desc}: "
            f"values seen = {values}"
        )

    return [
        {
            "role": "system",
            "content": (
                "You label coded/enumerated column values for a data catalog. "
                "For each column below, and for EACH value listed under it, "
                "give a short plain-language label for what that value means "
                '(for example, a status column\'s value "3" might mean '
                '"cancelled"). Only label values actually listed; never invent '
                "a value that was not given. Do not speculate beyond the "
                "column name, description and values given. Reply with ONLY a "
                'JSON object: {"labels": {"<column>": {"<value>": "<label>"}}}'
            ),
        },
        {
            "role": "user",
            "content": f"Table: {table_name}\nColumns:\n" + "\n".join(lines),
        },
    ]


def _enum_label_token_budget(columns: list[dict]) -> int:
    total_values = sum(
        len((c.get("top_k") or [])[:ENUM_LABEL_MAX_VALUES]) for c in columns
    )
    return ENUM_LABEL_TOKEN_FLOOR + TOKENS_PER_LABEL * total_values


async def draft_enum_labels(
    table_name: str, columns: list[dict], client, *, allow: bool,
) -> dict[str, dict[str, str]]:
    """Ask the model what a coded column's values mean.

    Returns {} -- never raises -- whenever the pass cannot run: consent
    withheld, no client, no eligible columns, or a response that never
    satisfied the JSON contract. Same enrichment-never-requirement contract as
    describe_with_llm.

    Only (column, value) pairs actually asked about come back: a model that
    invents an extra value would be inventing a catalog entry, which this
    layer must never do.
    """
    if not allow or client is None or not columns:
        return {}

    got = await client.complete_json(
        build_enum_label_prompt(table_name, columns), _ENUM_LABEL_SCHEMA,
        max_tokens=_enum_label_token_budget(columns), temperature=0.1,
        background=True,
    )
    if not got:
        logger.info(
            "no LLM enum labels for %s (%s)", table_name,
            getattr(client, "last_error", "unknown"),
        )
        return {}

    asked = {
        c["name"]: {str(e.get("value")) for e in (c.get("top_k") or [])[:ENUM_LABEL_MAX_VALUES]}
        for c in columns
    }
    out: dict[str, dict[str, str]] = {}
    for name, mapping in (got.get("labels") or {}).items():
        if name not in asked or not isinstance(mapping, dict):
            continue
        cleaned = {
            str(value): str(label).strip()
            for value, label in mapping.items()
            if str(value) in asked[name]
            and isinstance(label, (str, int, float))
            and str(label).strip()
        }
        if cleaned:
            out[name] = cleaned
    return out


async def describe_source_with_llm(
    source_name: str, tables: list[dict], client, *,
    allow: bool, relationships: list[dict] | None = None,
) -> dict:
    """Describe a whole database and each of its tables.

    Returns {"overview": str, "tables": {}}, or {} when the pass cannot
    run. `tables` is always empty and kept only so callers need not branch: the
    per-table sentences come from `describe_with_llm`, which already runs once
    per table and therefore does not grow with the size of the database — consent withheld, no client, endpoint unreachable, or a response that
    never satisfied the JSON contract. Same contract as the column pass: an
    enrichment, never a requirement.

    Table names not present in the input are discarded. A model will occasionally
    return a plausible extra table, and inventing catalog entries is precisely
    what this layer must not do.
    """
    if not allow or client is None or not tables:
        return {}

    got = await client.complete_json(
        build_source_prompt(source_name, tables, relationships), _SOURCE_SCHEMA,
        max_tokens=1200, temperature=0.2,
        background=True,
    )
    if not got:
        logger.info(
            "no LLM source description for %s (%s)", source_name,
            getattr(client, "last_error", "unknown"),
        )
        return {}

    return {"overview": str(got.get("overview") or "").strip(), "tables": {}}


# ── entities: named business objects, and their grain ──────────────────────
# Tier 2 / spec section 5 (E2): "customer", "order" -- the real-world things a
# person asks about, as distinct from the raw tables/views that back them.
# One call per SOURCE, like the overview call above, since an entity's
# existence is a property of the whole catalog's shape, not of any one table.

#: A database rarely has more real business entities worth naming than this;
#: asking for more risks the model inventing thin distinctions between
#: overlapping tables. Mirrors ENUM_LABEL_MAX_VALUES's role: a sane ceiling on
#: what a single call is asked to produce.
MAX_ENTITIES = 20

#: `Entity.name`/`Entity.business_name` (models.py) are both `String(255)`.
#: An LLM has no notion of that column budget and nothing upstream of
#: `draft_entities` enforces it, so an over-length reply would insert
#: cleanly on SQLite (no length enforcement) but be rejected by Postgres in
#: production -- the exact "tests are blind, prod isn't" gap. Clamped here,
#: at the one place free-text LLM output becomes a catalog-bound dict.
ENTITY_NAME_MAX_LEN = 255

#: Output budget: a handful of sentences per entity, plus JSON scaffolding.
ENTITY_TOKEN_FLOOR = 200
TOKENS_PER_ENTITY = 80

_ENTITY_SCHEMA = {
    "type": "object",
    "properties": {"entities": {"type": "array", "items": {"type": "object"}}},
    "required": ["entities"],
}


#: `build_source_prompt`'s precedent for a per-table column line, applied
#: here for the identical reason: an 82-table/1,354-column source built a
#: prompt that silently 400'd (see TestOneHugeValueCannotCostATableItsDescription).
#: That function caps at 6 columns per table regardless of how many exist;
#: this mirrors it exactly rather than growing with table width, since a
#: catalog-wide prompt's size is what has to stay bounded, not what any one
#: table happens to contain.
MAX_ENTITY_PROMPT_COLUMNS = 6


def build_entity_prompt(source_name: str, tables: list[dict]) -> list[dict]:
    """The entity-drafting prompt (spec section 5, E2): what named business
    objects does this database model, and what is one row of each?
    Structure-only, like `build_source_prompt` -- table/column names and row
    counts, no values, since none are needed and none should leave for this.

    Column list per table is capped at `MAX_ENTITY_PROMPT_COLUMNS`, same as
    `build_source_prompt`'s `key_columns[:6]` -- this prompt lists EVERY
    table, so an uncapped column list grows with the catalog's total column
    count, not just its table count, and that is exactly the shape of the
    prompt-blowup this codebase already measured once.
    """
    lines = []
    for t in tables:
        columns = t.get("columns") or []
        shown = ", ".join(columns[:MAX_ENTITY_PROMPT_COLUMNS])
        if len(columns) > MAX_ENTITY_PROMPT_COLUMNS:
            shown += f", +{len(columns) - MAX_ENTITY_PROMPT_COLUMNS} more"
        rows = t.get("row_count")
        size = f", ~{rows:,} rows" if rows else ""
        lines.append(
            f"- {t['name']} ({t.get('kind') or 'table'}, "
            f"{len(columns)} columns{size}): {shown}")

    return [
        {
            "role": "system",
            "content": (
                "You identify the named business entities a database models "
                "-- the real-world things a person would ask about (customer, "
                "order, product, ...), each backed by one or more of the "
                "tables listed. For each entity give: name (short, "
                "lowercase_snake_case, unique), business_name (a human "
                "label), grain (one short sentence starting 'One row per ...' "
                "describing what a single record of this entity represents), "
                "description (1-2 sentences), and primary_object (the exact "
                "table name from the list that is this entity's main table, "
                "or null if none fits). Only name entities the tables given "
                "actually support; do not invent an entity with no table "
                f"behind it. Propose at most {MAX_ENTITIES} entities. Reply "
                'with ONLY a JSON object: {"entities": [{"name": "...", '
                '"business_name": "...", "grain": "...", "description": '
                '"...", "primary_object": "..."}]}'
            ),
        },
        {
            "role": "user",
            "content": f"Database: {source_name}\nTables:\n" + "\n".join(lines),
        },
    ]


def _entity_token_budget(n_tables: int) -> int:
    return ENTITY_TOKEN_FLOOR + TOKENS_PER_ENTITY * min(n_tables, MAX_ENTITIES)


async def draft_entities(
    source_name: str, tables: list[dict], client, *, allow: bool,
) -> list[dict]:
    """Ask the model what named business entities this database models.

    Returns [] -- never raises -- whenever the pass cannot run: consent
    withheld, no client, no tables, or a response that never satisfied the
    JSON contract. Same enrichment-never-requirement contract as
    describe_with_llm/draft_enum_labels.

    Only entities whose `primary_object` (when given) names a table actually
    in `tables` are trusted with that field -- same "never invent a catalog
    entry" discipline as the other drafting passes here, applied to a
    cross-reference rather than a value.
    """
    if not allow or client is None or not tables:
        return []

    got = await client.complete_json(
        build_entity_prompt(source_name, tables), _ENTITY_SCHEMA,
        max_tokens=_entity_token_budget(len(tables)), temperature=0.1,
        background=True,
    )
    if not got:
        logger.info(
            "no LLM entities for %s (%s)", source_name,
            getattr(client, "last_error", "unknown"),
        )
        return []

    table_names = {t["name"] for t in tables}
    out: list[dict] = []
    for entry in (got.get("entities") or [])[:MAX_ENTITIES]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()[:ENTITY_NAME_MAX_LEN]
        if not name:
            continue
        business_name = str(entry.get("business_name") or "").strip()
        business_name = business_name[:ENTITY_NAME_MAX_LEN] or None
        primary_object = entry.get("primary_object")
        primary_object = str(primary_object).strip() if primary_object else ""
        if primary_object not in table_names:
            primary_object = None
        out.append({
            "name": name,
            "business_name": business_name,
            "grain": str(entry.get("grain") or "").strip() or None,
            "description": str(entry.get("description") or "").strip() or None,
            "primary_object": primary_object or None,
        })
    return out
