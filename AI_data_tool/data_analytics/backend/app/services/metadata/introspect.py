"""Stage 1 — read a database's own catalog.

ARCHITECTURE.md stage 1.4 picks SQLAlchemy's `Inspector` for this, and the
reason it gives is worth restating: it "normalizes introspection across 10+
dialects — the biggest single saving here". Every supported family answers the
same questions through one API, so adding a sixth connector costs nothing here.

WHAT THIS STAGE NEEDS: A CONNECTION. NOTHING ELSE.
---------------------------------------------------
No dataset, no prior import, no human having decided which tables matter. That
independence is the entire point. A catalog assembled from datasets describes
the part of the database somebody already knew to import — which is precisely
backwards for the person who has just connected a source and wants to know
what is in it.

DECLARED FOREIGN KEYS ARE FACTS
--------------------------------
Foreign keys read here are what the database itself guarantees. They enter the
model as `declared`, at full confidence, and value-overlap inference is then
only asked to find the ones nobody bothered to declare. Skipping this step would
mean re-deriving by statistics what the schema already states outright — slower,
and less accurate than simply reading it.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

#: Schemas that belong to the engine rather than to the customer's data.
_SYSTEM_SCHEMAS = {
    "information_schema", "pg_catalog", "pg_toast",
    "sys", "mysql", "performance_schema", "sysaux",
    "INFORMATION_SCHEMA", "SYS", "SYSTEM",
}

#: Object-name prefixes the engine owns.
_SYSTEM_PREFIXES = ("sqlite_", "pg_", "sys_")

#: Native SQL type -> the vocabulary this platform reasons in. Ordered longest
#: first where prefixes overlap, so DOUBLE PRECISION is not matched by DOUBLE.
_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(BOOL|BOOLEAN|BIT)\b", re.I), "boolean"),
    (re.compile(r"^(TIMESTAMP|DATETIME|DATE|TIME)\b", re.I), "datetime"),
    (re.compile(r"^(JSONB|JSON)\b", re.I), "json"),
    (re.compile(r"^(SMALLINT|BIGINT|TINYINT|MEDIUMINT|INTEGER|INT)\b", re.I), "integer"),
    (re.compile(r"^(NUMERIC|DECIMAL|DOUBLE|FLOAT|REAL|MONEY|NUMBER)\b", re.I), "numeric"),
    (re.compile(r"^(VARCHAR|NVARCHAR|CHARACTER|CHAR|TEXT|CLOB|STRING|UUID|ENUM)\b", re.I), "text"),
]


def normalize_type(native: str | None) -> str:
    """Map a native SQL type onto the platform's vocabulary.

    Returns "unknown" rather than guessing when nothing matches. Inventing a
    type for an unrecognised one is worse than admitting ignorance: a wrong
    dtype silently changes how the column is treated in profiling, inference,
    role assignment and every widget built on it, with nothing to indicate the
    original cause.
    """
    if not native:
        return "unknown"
    text_form = str(native).strip()
    for pattern, normalized in _TYPE_PATTERNS:
        if pattern.match(text_form):
            return normalized
    return "unknown"


def _is_system(name: str, schema: str | None) -> bool:
    if schema and schema in _SYSTEM_SCHEMAS:
        return True
    return name.lower().startswith(_SYSTEM_PREFIXES)


def list_objects(engine, schema: str | None = None) -> list[dict]:
    """Every table and view the connection can see.

    Views are included deliberately. A view is frequently the thing a person
    actually queries — the curated join someone built precisely so nobody has to
    remember the join — and omitting them would hide the most meaningful objects
    in plenty of databases.
    """
    inspector = inspect(engine)
    found: list[dict] = []

    for name in inspector.get_table_names(schema=schema):
        if not _is_system(name, schema):
            found.append({"name": name, "schema": schema, "kind": "table"})

    try:
        for name in inspector.get_view_names(schema=schema):
            if not _is_system(name, schema):
                found.append({"name": name, "schema": schema, "kind": "view"})
    except NotImplementedError:
        # Not every dialect implements view listing. Tables alone still make a
        # usable catalog, so this is a gap rather than a failure.
        logger.info("dialect does not support view listing")

    return found


def describe_object(engine, name: str, schema: str | None = None) -> dict:
    """Columns, primary key, foreign keys and comments for one object.

    Raises if the object cannot be read. An empty result would be
    indistinguishable from a table that genuinely has no columns, and would
    enter the catalog as one — a silent lie is worse than a loud failure that
    `introspect_source` can record and step over.
    """
    inspector = inspect(engine)

    raw_columns = inspector.get_columns(name, schema=schema)
    if not raw_columns:
        raise ValueError(f"no columns returned for {name!r}")

    try:
        pk = set((inspector.get_pk_constraint(name, schema=schema) or {})
                 .get("constrained_columns") or [])
    except Exception:
        pk = set()

    columns = []
    for position, column in enumerate(raw_columns):
        native = str(column.get("type")) if column.get("type") is not None else None
        columns.append({
            "name": column["name"],
            "position": position,
            "native_type": native,
            "dtype": normalize_type(native),
            "nullable": bool(column.get("nullable", True)),
            "is_primary_key": column["name"] in pk,
            # COMMENT ON COLUMN. Documentation a human wrote in the schema
            # itself, which outranks anything this layer infers.
            "comment": column.get("comment"),
        })

    foreign_keys = []
    try:
        for fk in inspector.get_foreign_keys(name, schema=schema) or []:
            local = fk.get("constrained_columns") or []
            remote = fk.get("referred_columns") or []
            target = fk.get("referred_table")
            # Composite keys are out of scope for v1: the relationship tables
            # are single-column on each side. Recorded as skipped rather than
            # silently truncated to the first column, which would produce a
            # join that looks declared but is wrong.
            if target and len(local) == 1 and len(remote) == 1:
                foreign_keys.append({
                    "from_column": local[0],
                    "to_table": target,
                    "to_column": remote[0],
                })
            elif target:
                logger.info("skipping composite foreign key on %s -> %s", name, target)
    except Exception:
        logger.info("could not read foreign keys for %s", name, exc_info=True)

    comment = None
    try:
        comment = (inspector.get_table_comment(name, schema=schema) or {}).get("text")
    except Exception:
        pass

    return {
        "name": name,
        "schema": schema,
        "columns": columns,
        "foreign_keys": foreign_keys,
        "comment": comment,
    }


def estimated_row_counts(engine, schema: str | None = None) -> dict[str, int]:
    """Row-count ESTIMATES for every table, in one query where possible.

    ARCHITECTURE.md principle 2: "Read the engine's own statistics before
    computing your own. pg_stats in milliseconds beats a full scan in minutes."
    This is where that principle earns its keep — an 82-table source costs one
    catalog query instead of 82 sequential table scans.

    PostgreSQL keeps `pg_class.reltuples`, the same estimate its own planner
    trusts. It is approximate, and approximate is entirely sufficient for both
    uses it has here: picking a sampling strategy, and telling a reader roughly
    how large a table is. Neither ever needed an exact number.

    Returns {} on engines with no such catalog; callers fall back to per-table
    counting only when they actually need it.
    """
    dialect = engine.dialect.name
    try:
        if dialect == "postgresql":
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT c.relname, GREATEST(c.reltuples, 0)::bigint
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind IN ('r', 'p', 'm')
                      AND n.nspname = COALESCE(:schema, 'public')
                """), {"schema": schema}).fetchall()
            return {name: int(count) for name, count in rows}
    except Exception:
        logger.info("could not read row-count estimates", exc_info=True)
    return {}


def count_rows(engine, name: str, schema: str | None) -> int | None:
    """An exact count for one object.

    NOT used by introspection, and deliberately so — see `introspect_source`.
    Exposed for a caller that genuinely needs an exact number and has decided
    the scan is worth it, which introspection never has.
    """
    quoted = f'"{name}"' if schema is None else f'"{schema}"."{name}"'
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT count(*) FROM {quoted}")).scalar())
    except Exception:
        logger.info("could not count rows for %s", name, exc_info=True)
        return None


def introspect_source(
    engine, schema: str | None = None, *, with_counts: bool = False,
) -> list[dict]:
    """The whole catalog: every readable object with its columns and keys.

    NOTHING HERE SCANS A TABLE. Row counts come from the engine's own statistics
    or not at all — measured on a real source, counting the views of an 82-object
    database took minutes each, because a count on a view executes the view. An
    unknown count is handled everywhere downstream (`choose_strategy` falls back
    to a bounded read, which is what a view needs regardless), so "unknown" is
    both cheap and correct.

    One unreadable object is skipped rather than fatal. A permission-denied
    view, a table dropped between listing and describing, a dialect quirk on one
    exotic type — all normal in a real database, and none of them a reason to
    lose the other eighty-one.
    """
    # One catalog query for every table's size, rather than one scan per table.
    estimates = estimated_row_counts(engine, schema) if with_counts else {}

    objects = []
    for entry in list_objects(engine, schema=schema):
        try:
            described = describe_object(engine, entry["name"], entry["schema"])
        except Exception:
            logger.info("skipping unreadable object %s", entry["name"], exc_info=True)
            continue

        described["kind"] = entry["kind"]
        # Only ever the engine's own estimate. An object it has no statistic for
        # — a plain view, or an unsupported engine — is reported as unknown
        # rather than counted. See the note in this function's docstring: the
        # count is not worth a scan, and on a view it is not even a scan of a
        # table but an execution of the whole query.
        described["row_count_estimate"] = estimates.get(entry["name"])
        objects.append(described)

    return objects
