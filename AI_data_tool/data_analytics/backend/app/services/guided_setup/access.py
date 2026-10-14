"""What the guided setup (and the model it asks) may read: what the user may read.

Decision D1 of docs/guided-setup/PLAN.md: the AI sees exactly what the
logged-in person sees. Two things follow for a source table:

* the connection must be one this person may SEE (the Connections list's
  rule, `visible_source_ids`), else the routers answer 404;
* rows come through the person's own connection row rules -- the same
  `ObjectRowPolicy` predicates Ask AI parses into its SQL (agent/policy.py),
  never post-filtered and failing closed when a rule cannot be attached.

Values a sync classified as personal (email, phone, national id...) are
masked as they are in the metadata sample cache, so a sample shown on screen
or sent to the model never carries more than the catalog already does.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.models import DataSource, SourceColumn, SourceObject, User

logger = logging.getLogger(__name__)

#: Most sample rows any one table returns to the setup.
MAX_SAMPLE_ROWS = 20


@dataclass
class _PolicyContext:
    """The two fields `load_policies` reads from Ask AI's SchemaContext."""
    source_id: int
    family: str


async def visible_source_ids(db: AsyncSession, user: User) -> set[int] | None:
    """Connections this user may SEE. None means all of them (admins).

    Yours, plus any that backs a dataset you can read -- a member who was
    given a dataset still needs to see the connection behind it for the
    dataset picker and the Ask-AI scope selector to make sense. Seeing a
    connection is not using it: the config comes back redacted, importing
    stays admin-only, and changing it needs `_may_administer` (data_sources).
    """
    from sqlalchemy import or_
    from ...core.capability import readable_dataset_ids
    from ...models.models import Dataset

    if user.role and user.role.is_org_admin:
        return None
    ids = set((await db.execute(
        select(DataSource.id).where(
            DataSource.org_id == user.org_id,
            or_(DataSource.created_by == user.id, DataSource.created_by.is_(None)))
    )).scalars().all())
    readable = await readable_dataset_ids(db, user)
    q = select(Dataset.data_source_id).where(
        Dataset.org_id == user.org_id, Dataset.data_source_id.isnot(None))
    if readable is not None:
        q = q.where(Dataset.id.in_(readable or {-1}))
    ids |= set(x for x in (await db.execute(q)).scalars().all() if x is not None)
    return ids


async def visible_source(db: AsyncSession, source_id: int, user: User) -> DataSource | None:
    """The connection, if this user may see it; None otherwise. The routers
    answer None with a 404 (never 403: that would confirm the id exists)."""
    source = await db.get(DataSource, source_id)
    if source is None or source.org_id != user.org_id:
        return None
    visible = await visible_source_ids(db, user)
    if visible is not None and source.id not in visible:
        return None
    return source


async def release(db: AsyncSession) -> None:
    """End the current (read-only) transaction before a long wait.

    A guided-setup job reads a little, then waits minutes for a model or a
    remote database. An open transaction across that wait holds its locks:
    a migration's ALTER TABLE queued behind it, and every query queued behind
    the ALTER (live freeze, 2026-10-07). The sessions here do not expire on
    commit, so loaded objects stay usable."""
    await db.commit()


def jsonable(rows: list[dict]) -> list[dict]:
    """Rows as JSON can store them: dates, decimals and other database types as
    text. Sample rows are kept on the journey (a JSON column); a date in them
    failed the save and left the step waiting forever (EGX, 2026-10-07)."""
    import json
    return json.loads(json.dumps(rows, default=str))


def _family(source: DataSource) -> str:
    from .. import connectors
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    return connectors.sql_family_of(cfg) or "postgresql"


def sample_sql(obj: SourceObject, family: str, limit: int, policies: dict[str, str]) -> str:
    """`SELECT * FROM <table> LIMIT n` with the user's row rules parsed in.

    Built as an AST so a schema or table name is quoted by the dialect, never
    pasted; `apply_policies` raises PolicyError rather than run without a rule."""
    import sqlglot
    from sqlglot import exp
    from ..agent.policy import apply_policies
    from ..agent.validate import _dialect

    dialect = _dialect(family)
    table = exp.Table(this=exp.to_identifier(obj.name, quoted=True),
                      db=exp.to_identifier(obj.schema_name, quoted=True) if obj.schema_name else None)
    query = exp.select("*").from_(table).limit(max(1, min(int(limit), MAX_SAMPLE_ROWS)))
    sql = query.sql(dialect=dialect)
    sql = apply_policies(sql, policies, family)
    # Round-trip so the policy-injected form is what runs, in the source's dialect.
    return sqlglot.parse_one(sql, dialect=dialect).sql(dialect=dialect)


async def sample_rows(db: AsyncSession, user: User, source: DataSource,
                      obj: SourceObject, limit: int = 5) -> dict:
    """A few rows of `obj` as `user` may see them.

    Returns {"columns", "rows" (list of dicts), "restricted": bool, "error"}.
    `restricted` says a row rule narrowed the sample, so the caller can say so
    instead of letting a filtered sample pass for the whole table. Never raises
    for a source that cannot be read: the setup still describes the structure.
    """
    from .. import pii
    from ..agent.policy import PolicyError, load_policies
    from ..connections import preview_table

    family = _family(source)
    policies = await load_policies(db, _PolicyContext(source.id, family), user)
    await release(db)
    own = {k: v for k, v in policies.items() if k in (obj.name, "*")}
    try:
        sql = sample_sql(obj, family, limit, own)
    except PolicyError:
        # A rule that cannot be attached closes the table: show nothing.
        return {"columns": [], "rows": [], "restricted": True, "error": "restricted"}

    cfg = dict(source.config or {})
    cfg["type"] = source.type
    try:
        result = await asyncio.to_thread(preview_table, cfg, None, sql, limit)
    except Exception as exc:  # noqa: BLE001 -- a dead source still gets described
        logger.info("guided setup: sample of %s failed: %s", obj.name, exc)
        return {"columns": [], "rows": [], "restricted": bool(own), "error": "unreachable"}

    columns = list(result.get("columns") or [])
    rows = [dict(zip(columns, r)) for r in result.get("rows") or []]
    kinds = dict((await db.execute(
        select(SourceColumn.name, SourceColumn.semantic_type)
        .where(SourceColumn.source_object_id == obj.id))).all())
    # A column the sync never classified is checked on the values in hand.
    for c in columns:
        if not kinds.get(c):
            kinds[c] = pii.detect_semantic_type([r.get(c) for r in rows])
    return {"columns": columns, "rows": jsonable(pii.mask_rows(rows, kinds)),
            "restricted": bool(own), "error": None}
