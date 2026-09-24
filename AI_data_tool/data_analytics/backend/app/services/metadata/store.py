"""Provenance-aware writes for the metadata plane.

THE RULE THIS MODULE EXISTS TO ENFORCE
--------------------------------------
ARCHITECTURE.md principle 5: "Inference is a proposal, never a fact. Everything
derived carries `confidence` and `source`. Human confirmation outranks inference
permanently."

`source` is a precedence ladder, not a label:

    confirmed  >  declared  >  inferred

- `confirmed` — a human looked at the proposal and approved it. Nothing
  overwrites it. Not a later sync, not a higher-confidence guess, not a
  re-read of the source catalog. Ever.
- `declared`  — read from the source's own catalog (a real FOREIGN KEY). A
  fact about the database, refreshed from the database, but still not
  something inference may contradict.
- `inferred`  — this layer's guess. Recomputed freely on every sync, because
  otherwise the model would freeze at whatever the first run happened to
  produce.

Every inference stage writes through the functions here rather than touching
the ORM, so the rule is enforced in ONE place and cannot be forgotten in the
fifth stage of a six-stage pipeline. If a resync could silently revert a
confirmation, the review UI would be a lie: a user confirms a join, comes back
the next morning, and finds their answer replaced by whatever last night's
sampler guessed. That failure is silent, data-dependent, and destroys trust in
every other number the product shows — which is why it gets its own module and
its own test file rather than an `if` in the sync loop.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.models import ColumnStats, Relationship

# The three legal values of `source`, most authoritative first.
CONFIRMED = "confirmed"
DECLARED = "declared"
INFERRED = "inferred"

#: Ranked precedence. A write may proceed only if it is at least as
#: authoritative as what is already stored.
_PRECEDENCE = {INFERRED: 0, DECLARED: 1, CONFIRMED: 2}


class ProvenanceError(Exception):
    """A write was refused because it would violate the precedence ladder, or
    because it crossed an organization boundary. Raised rather than returned:
    a caller that ignores a refusal is a bug, and a silent no-op here would be
    exactly the kind of quiet data loss this module exists to prevent."""


def _clamp(confidence: float) -> float:
    """Confidence is a probability, so it lives in [0, 1].

    Clamped rather than rejected: an overlap ratio computed from a sample can
    round fractionally above 1.0, and refusing the whole relationship over a
    floating-point artefact would lose a real inference.
    """
    return max(0.0, min(1.0, float(confidence)))


def _may_overwrite(existing_source: str | None, new_source: str) -> bool:
    """The ladder. Equal rank may overwrite (a resync refreshes its own kind);
    lower rank may not.

    An unrecognized stored value is treated as maximally authoritative. That is
    deliberate: if a future migration adds a fourth level and this table has not
    caught up, refusing the write loses one inference, whereas allowing it could
    destroy a human decision. Fail toward keeping data.
    """
    if existing_source is None:
        return True
    existing_rank = _PRECEDENCE.get(existing_source)
    if existing_rank is None:
        return False
    return _PRECEDENCE[new_source] >= existing_rank


async def _find_edge(
    db: AsyncSession, *, org_id: int,
    from_dataset_id: int, from_column: str,
    to_dataset_id: int, to_column: str,
) -> Relationship | None:
    """Look up one edge by its identity.

    An edge is identified by (org, from dataset+column, to dataset+column) — not
    by the pair of tables. Two different columns joining the same two tables are
    two distinct edges (`orders.customer_id` and `orders.billing_customer_id`
    both reach `customers.id`), and collapsing them would silently drop one.
    """
    stmt = select(Relationship).where(
        Relationship.org_id == org_id,
        Relationship.from_dataset_id == from_dataset_id,
        Relationship.from_column == from_column,
        Relationship.to_dataset_id == to_dataset_id,
        Relationship.to_column == to_column,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _upsert_relationship(
    db: AsyncSession, *, org_id: int,
    from_dataset_id: int, from_column: str,
    to_dataset_id: int, to_column: str,
    source: str, confidence: float,
    evidence: dict | None, cardinality: str | None,
) -> Relationship:
    """The single write path for relationships. Both public upserts funnel here
    so the precedence check cannot be bypassed."""
    existing = await _find_edge(
        db, org_id=org_id,
        from_dataset_id=from_dataset_id, from_column=from_column,
        to_dataset_id=to_dataset_id, to_column=to_column,
    )

    if existing is not None:
        if not _may_overwrite(existing.source, source):
            # Not an error — a resync re-proposing an already-confirmed edge is
            # the normal, expected case. Return what is stored, unchanged, so
            # the caller sees the authoritative row rather than its own guess.
            return existing
        existing.confidence = _clamp(confidence)
        existing.source = source
        existing.evidence = evidence
        existing.cardinality = cardinality
        return existing

    row = Relationship(
        org_id=org_id,
        from_dataset_id=from_dataset_id, from_column=from_column,
        to_dataset_id=to_dataset_id, to_column=to_column,
        confidence=_clamp(confidence), source=source,
        evidence=evidence, cardinality=cardinality,
    )
    db.add(row)
    await db.flush()
    return row


async def upsert_inferred_relationship(
    db: AsyncSession, *, org_id: int,
    from_dataset_id: int, from_column: str,
    to_dataset_id: int, to_column: str,
    confidence: float,
    evidence: dict | None = None,
    cardinality: str | None = None,
) -> Relationship:
    """Propose a foreign key discovered by Stage 4 inference.

    Returns the stored row, which may be one this call did NOT write — if a
    human already confirmed this edge, their version comes back untouched.
    """
    return await _upsert_relationship(
        db, org_id=org_id,
        from_dataset_id=from_dataset_id, from_column=from_column,
        to_dataset_id=to_dataset_id, to_column=to_column,
        source=INFERRED, confidence=confidence,
        evidence=evidence, cardinality=cardinality,
    )


async def upsert_declared_relationship(
    db: AsyncSession, *, org_id: int,
    from_dataset_id: int, from_column: str,
    to_dataset_id: int, to_column: str,
    cardinality: str | None = None,
) -> Relationship:
    """Record a real FOREIGN KEY read from the source catalog.

    Always full confidence — the database asserts it, so there is nothing to be
    uncertain about. Still cannot overwrite a confirmation: a human who
    deliberately corrected a declared key knew something the catalog did not.
    """
    return await _upsert_relationship(
        db, org_id=org_id,
        from_dataset_id=from_dataset_id, from_column=from_column,
        to_dataset_id=to_dataset_id, to_column=to_column,
        source=DECLARED, confidence=1.0,
        evidence=None, cardinality=cardinality,
    )


async def confirm_relationship(db: AsyncSession, relationship_id: int, *, org_id: int) -> Relationship:
    """Promote an edge to `confirmed` — the terminal state.

    Idempotent, so a double-click in the review UI is harmless. Org-scoped and
    fail-closed: confirming across a tenant boundary raises rather than quietly
    doing nothing, because a silent no-op would show the user a success they did
    not get.
    """
    row = await db.get(Relationship, relationship_id)
    if row is None or row.org_id != org_id:
        raise ProvenanceError(
            f"relationship {relationship_id} is not visible to org {org_id}"
        )
    row.source = CONFIRMED
    row.confidence = 1.0
    return row


async def upsert_column_stats(
    db: AsyncSession, *, dataset_column_id: int | None = None,
    source_column_id: int | None = None,
    null_ratio: float | None = None,
    distinct_count: int | None = None,
    top_k: list | None = None,
    min_value: str | None = None,
    max_value: str | None = None,
    avg_width: int | None = None,
    exact: bool = False,
) -> ColumnStats:
    """Replace the statistics for one column, of either kind.

    A column belongs either to the SOURCE catalog (every column of every table
    the connection can see) or to a user-created dataset. Exactly one id is
    given; passing both or neither raises rather than writing a row that is
    ambiguous or unreachable.

    Unlike relationships, statistics carry no provenance ladder — they are
    measurements, not proposals, and the newest measurement always wins. What
    they carry instead is `exact`, which travels WITH the values and is
    overwritten alongside them. That pairing is the point: an estimated
    distinct_count arriving after a measured one must drop `exact` to False in
    the same write, or a caller would read fresh estimates while believing they
    were exact.
    """
    if (dataset_column_id is None) == (source_column_id is None):
        # Neither or both. Both would create a row belonging to two different
        # columns; neither would create an orphan. Refusing beats writing a row
        # nothing can ever look up.
        raise ValueError(
            "exactly one of dataset_column_id / source_column_id is required")

    if source_column_id is not None:
        where = ColumnStats.source_column_id == source_column_id
        key = {"source_column_id": source_column_id}
    else:
        where = ColumnStats.dataset_column_id == dataset_column_id
        key = {"dataset_column_id": dataset_column_id}

    existing = (await db.execute(select(ColumnStats).where(where))).scalar_one_or_none()

    if existing is None:
        existing = ColumnStats(**key)
        db.add(existing)

    existing.null_ratio = null_ratio
    existing.distinct_count = distinct_count
    existing.top_k = top_k
    existing.min_value = min_value
    existing.max_value = max_value
    existing.avg_width = avg_width
    existing.exact = exact
    existing.computed_at = datetime.utcnow()
    await db.flush()
    return existing


#: Fields the semantics writer below governs. Each carries its own
#: "<field>_source" marker in the same dict, so provenance travels WITH the
#: value rather than in a parallel structure that can drift out of step.
SEMANTIC_FIELDS = ("role", "semantic_type")


def apply_inferred_column_semantics(
    column_meta: dict | None, proposals: dict[str, dict],
) -> tuple[dict, list[str]]:
    """Merge inference into a dataset's , human values intact.

    Returns the new blob and the list of columns actually changed, so a caller
    can skip the write (and the JSON-column flag_modified dance) when nothing
    moved.

    WHY THIS LIVES HERE RATHER THAN IN THE STEP THAT CALLS IT
    ---------------------------------------------------------
    This module's docstring states the rule it exists to keep in ONE place:
    confirmed > declared > inferred, and inference never overwrites a human.
    `Dataset.column_meta` is the second place that rule has to hold -- the
    first is `ColumnStats`/`Relationship` above -- and it is the one the
    ANALYSES read, via `insights.effective_roles`. Putting the merge in the
    automation step would mean the rule lived in the fifth step of a
    seven-step pipeline, which is exactly the arrangement the module docstring
    argues against.

    A field with a value but NO source marker is treated as CONFIRMED, not as
    unmarked-and-therefore-free. Everything written before this function
    existed was authored by a person through the Fields pane; reading absence
    as permission would quietly relabel every one of those columns on the
    first automation run, which is the silent revert this module was built to
    prevent.
    """
    out = dict(column_meta or {})
    changed: list[str] = []

    for name, proposed in (proposals or {}).items():
        current = out.get(name)
        current = dict(current) if isinstance(current, dict) else {}
        touched = False

        for field in SEMANTIC_FIELDS:
            value = proposed.get(field)
            if value is None:
                continue
            if current.get(field) is not None and current.get(f"{field}_source") != INFERRED:
                # Human or catalog. Outranks inference permanently.
                continue
            if current.get(field) == value and current.get(f"{field}_source") == INFERRED:
                continue                      # already says this; no write
            current[field] = value
            current[f"{field}_source"] = INFERRED
            touched = True

        if touched:
            out[name] = current
            changed.append(name)

    return out, changed
