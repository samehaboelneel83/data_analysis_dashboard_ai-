"""Stage 4 — inferring foreign keys.

ARCHITECTURE.md calls this "the highest-value part of the layer", and the reason
is that declared foreign keys are frequently absent in real databases: ORMs that
never emit them, warehouses that cannot enforce them, schemas assembled by ETL.
Without join paths the semantic layer has tables and no way to connect them, so
this stage is what turns a list of tables into a model.

THE PIPELINE, CHEAPEST FILTER FIRST
------------------------------------
Comparing every column against every other is quadratic, so the expensive test
runs last and on as few pairs as possible:

  1. name candidates    string work, no I/O. `customer_id` -> `customers.id`
  2. type compatibility  a dict lookup. Kills most survivors of step 1.
  3. value overlap       a DuckDB join over cached samples. The real evidence.
  4. cardinality         which side is the parent.

Steps 1-2 exist to make step 3 affordable, not because names are trustworthy.
Names are a PRIOR; overlap is the EVIDENCE. A column called `customer_id` that
shares no values with `customers.id` is not a foreign key no matter what it is
called, and an unnamed `cid` whose every value appears in `customers.id`
probably is one.

WHY THE FLOOR IS UNFORGIVING
-----------------------------
A wrong join does not fail loudly. It silently multiplies rows, and every
aggregate computed downstream is quietly wrong in a way no error message will
ever mention. Below the review threshold a candidate is DISCARDED rather than
stored at low confidence — an unreviewed bad suggestion sitting in the model is
worse than a missing one a human can add.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Broad families for compatibility checking. A foreign key never joins a date
#: to a float, and refusing those pairs up front removes most of the work.
_TYPE_FAMILY = {
    "integer": "number", "int": "number", "bigint": "number", "smallint": "number",
    "numeric": "number", "decimal": "number", "float": "number", "double": "number",
    "real": "number", "number": "number",
    "text": "text", "string": "text", "varchar": "text", "char": "text",
    "categorical": "text", "object": "text", "uuid": "text",
    "date": "temporal", "datetime": "temporal", "timestamp": "temporal",
    "boolean": "boolean", "bool": "boolean",
}

#: Suffixes that mark a column as referring to something else.
_FK_SUFFIXES = ("_id", "_key", "_fk", "_code", "_no", "_num")

#: Column names a parent's key is likely to have.
_PK_NAMES = ("id", "key", "code", "pk", "uid", "uuid")


@dataclass
class Candidate:
    """A proposed foreign key, with the evidence that produced it."""
    from_dataset_id: int
    from_column: str
    to_dataset_id: int
    to_column: str
    overlap: float
    name_score: float
    confidence: float
    cardinality: str | None = None
    evidence: dict = field(default_factory=dict)


def singularize(name: str) -> str:
    """A crude English singulariser — `customers` -> `customer`.

    Deliberately crude. It only has to align a table name with a column prefix
    well enough to PROPOSE a pair; overlap decides whether the pair is real, so
    a wrong guess here costs one cheap comparison and never a wrong join.
    """
    lowered = name.lower()
    for suffix, replacement in (("ies", "y"), ("ses", "s"), ("s", "")):
        if lowered.endswith(suffix) and len(lowered) > len(suffix) + 1:
            return lowered[: -len(suffix)] + replacement
    return lowered


def _strip_fk_suffix(column: str) -> str:
    lowered = column.lower()
    for suffix in _FK_SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            return lowered[: -len(suffix)]
    return lowered


def name_score(
    child_table: str, child_column: str,
    parent_table: str, parent_column: str,
) -> float:
    """How strongly the NAMES suggest a reference, in [0, 1].

    A prior, never a verdict. It ranks candidates and nudges confidence; it can
    never promote a pair that the values do not support.
    """
    child_col = child_column.lower()
    parent_col = parent_column.lower()
    parent_singular = singularize(parent_table)
    stem = _strip_fk_suffix(child_col)

    # `customer_id` -> `customers.id`: the textbook case.
    if stem == parent_singular and parent_col in _PK_NAMES:
        return 1.0

    # `customer_id` -> `customers.customer_id`: the same key spelled out.
    if child_col == parent_col and child_col.endswith(_FK_SUFFIXES):
        return 0.9

    # `cust_id` -> `customers.id` where the stem is a prefix of the table name.
    if stem and parent_singular.startswith(stem) and len(stem) >= 3:
        return 0.7 if parent_col in _PK_NAMES else 0.5

    # Identical names with no reference-shaped suffix. Weak: `name` matching
    # `name` across two tables is a coincidence far more often than a key.
    #
    # Excludes bare primary-key names, and that exclusion is load-bearing. A
    # column called `id` identifies its own table's rows; it does not reference
    # another table. Without this, every table's `id` pairs with every other
    # table's `id` -- and because surrogate keys are small integers starting at
    # 1, those pairs overlap by construction (customers.id 1-100 is wholly
    # contained in orders.id 1-200, a genuine 1.0). Overlap cannot rescue this;
    # the evidence really does point the wrong way, so the name rule has to
    # refuse the pair. Measured by test_infer_keys_accuracy: this single rule
    # moved precision from 50% to its floor with recall unchanged.
    if child_col == parent_col and child_col not in _PK_NAMES:
        return 0.4

    # Deliberately NOT a candidate: "the child ends in _id/_code/_no and the
    # parent column is called id". That pairs every code column in the schema
    # with every table's primary key while saying nothing about whether they
    # are related, and low-cardinality codes overlap small lookup tables by
    # coincidence constantly -- orders.status_code holds 1-4 and categories.id
    # holds 1-4, which scores a perfect 1.0 on overlap alone. A candidate needs
    # the child's stem to relate to the parent's TABLE name, or the column
    # names to match outright. Measured by test_infer_keys_accuracy.
    return 0.0


def types_compatible(child_dtype: str | None, parent_dtype: str | None) -> bool:
    """Whether two columns could hold the same values.

    Unknown types are treated as compatible: an unrecognised dtype should cost
    one overlap check, not silently drop a real relationship. Overlap is the
    authority; this is only a cost filter.
    """
    if not child_dtype or not parent_dtype:
        return True
    a = _TYPE_FAMILY.get(str(child_dtype).lower().split("(")[0].strip())
    b = _TYPE_FAMILY.get(str(parent_dtype).lower().split("(")[0].strip())
    if a is None or b is None:
        return True
    # number/text is allowed on purpose: ids arrive as VARCHAR from one source
    # and BIGINT from another far too often to refuse the pair outright.
    if {a, b} == {"number", "text"}:
        return True
    return a == b


def looks_like_key(column: str) -> bool:
    """Whether a column name is shaped like a key at all.

    Used to skip parent columns that are obviously not keys, so a fact table's
    `amount` is never proposed as the target of a reference.
    """
    lowered = column.lower()
    return lowered in _PK_NAMES or lowered.endswith(_FK_SUFFIXES)


def _cardinality(child_distinct: int, child_rows: int) -> str:
    """One row per child value means one-to-one; repeats mean many-to-one.

    Measured on the child side because that is the side a foreign key
    constrains, and it is what tells a join planner whether the join can
    multiply rows.
    """
    if child_rows and child_distinct >= child_rows:
        return "one_to_one"
    return "many_to_one"


def confidence_from(overlap: float, name: float) -> float:
    """Blend the evidence with the prior.

    Overlap carries the weight: a perfect overlap with no name support still
    scores 0.85, because the values are the actual proof. The name contributes
    the last 15%, which is enough to rank a well-named candidate above a
    coincidence at equal overlap without ever letting a name manufacture a
    relationship the data does not show.
    """
    return round(min(1.0, overlap * (0.85 + 0.15 * name)), 6)


def infer_foreign_keys(
    tables: list[dict],
    cache,
    *,
    overlap_high: float = 0.95,
    overlap_review: float = 0.70,
    # 0.4 is the weakest score any surviving rule can produce, so this admits
    # every real signal and nothing below it.
    min_name_score: float = 0.4,
) -> list[Candidate]:
    """Propose foreign keys across a set of tables.

    `tables` is a list of {dataset_id, name, columns: [{name, dtype}]}. `cache`
    is anything exposing `overlap` and `distinct_count` — the DuckDB sample
    cache in production, a stub in tests.

    Returns candidates sorted by confidence, highest first. Anything below
    `overlap_review` is discarded rather than returned at low confidence: a bad
    suggestion nobody reviews is worse than a missing one somebody can add.
    """
    candidates: list[Candidate] = []
    seen: set[tuple[int, str, int, str]] = set()

    for child in tables:
        for child_col in child.get("columns", []):
            child_name = child_col["name"]

            for parent in tables:
                if parent["dataset_id"] == child["dataset_id"]:
                    # Self-references are real but need different handling
                    # (a hierarchy, not a join path). Out of scope for v1.
                    continue

                for parent_col in parent.get("columns", []):
                    parent_name = parent_col["name"]

                    if not looks_like_key(parent_name):
                        continue

                    score = name_score(child["name"], child_name,
                                       parent["name"], parent_name)
                    if score < min_name_score:
                        continue
                    if not types_compatible(child_col.get("dtype"), parent_col.get("dtype")):
                        continue

                    key = (child["dataset_id"], child_name,
                           parent["dataset_id"], parent_name)
                    if key in seen:
                        continue
                    seen.add(key)

                    # The expensive step, reached by as few pairs as possible.
                    overlap = cache.overlap(
                        child["dataset_id"], child_name,
                        parent["dataset_id"], parent_name,
                    )
                    if overlap < overlap_review:
                        continue

                    child_distinct = cache.distinct_count(child["dataset_id"], child_name)
                    parent_distinct = cache.distinct_count(parent["dataset_id"], parent_name)

                    # The parent side must be near-unique. A "foreign key" into
                    # a column with repeats is not a key at all, and joining on
                    # it multiplies rows — the silent-corruption case.
                    #
                    # Called directly, with no hasattr fallback. A previous
                    # version degraded to `parent_distinct` when the cache could
                    # not answer, which made the comparison
                    # `parent_distinct < parent_distinct * 0.99` — always false,
                    # so the guard did nothing in production while every test
                    # passed against a fake that DID implement it.
                    parent_rows = cache.row_count(parent["dataset_id"])
                    if parent_rows and parent_distinct < parent_rows * 0.99:
                        continue

                    child_rows = cache.row_count(child["dataset_id"])

                    candidates.append(Candidate(
                        from_dataset_id=child["dataset_id"], from_column=child_name,
                        to_dataset_id=parent["dataset_id"], to_column=parent_name,
                        overlap=overlap,
                        name_score=score,
                        confidence=confidence_from(overlap, score),
                        cardinality=_cardinality(child_distinct, child_rows),
                        evidence={
                            "overlap": overlap,
                            "name_score": score,
                            "child_distinct": child_distinct,
                            "parent_distinct": parent_distinct,
                            "high_confidence": overlap >= overlap_high,
                        },
                    ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return _drop_weaker_duplicates(candidates)


def _drop_weaker_duplicates(candidates: list[Candidate]) -> list[Candidate]:
    """Keep one proposal per child column, and one per column PAIR.

    Two separate collapses, for two separate confusions:

    A child column cannot reference two different tables at once. When several
    parents survive — common where a lookup table's ids overlap another's by
    coincidence — the strongest wins, so review asks one question per column
    rather than three.

    And a pair of columns cannot reference each other. Where two tables share a
    code column, inference proposes BOTH directions and both score identically,
    because overlap is symmetric when every value appears on both sides. Seen in
    the running app: `maps_states.state_level_code -> state_symbols.state_level_code`
    listed alongside its exact mirror. Only the better-directed one survives —
    and direction is decided by which side actually looks like a key.
    """
    best: dict[tuple[int, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.from_dataset_id, candidate.from_column)
        if key not in best:
            best[key] = candidate

    by_pair: dict[frozenset, Candidate] = {}
    for candidate in best.values():
        pair = frozenset({
            (candidate.from_dataset_id, candidate.from_column),
            (candidate.to_dataset_id, candidate.to_column),
        })
        rival = by_pair.get(pair)
        if rival is None or _better_direction(candidate, rival):
            by_pair[pair] = candidate

    return sorted(by_pair.values(), key=lambda c: c.confidence, reverse=True)


def _better_direction(a: Candidate, b: Candidate) -> bool:
    """Which of two mirrored proposals points the right way.

    A foreign key runs from the MANY side to the ONE side, so the better
    direction is the one whose parent is the more selective column: the lookup
    table with five codes is the parent, the fact table repeating them is the
    child. Where that is a tie, higher confidence wins, and failing that the
    stronger name match.
    """
    a_parent = a.evidence.get("parent_distinct") or 0
    b_parent = b.evidence.get("parent_distinct") or 0
    a_child = a.evidence.get("child_distinct") or 0
    b_child = b.evidence.get("child_distinct") or 0

    # Prefer the direction where the child is at least as diverse as the parent;
    # that is what many-to-one looks like from the child's side.
    a_ratio = (a_child / a_parent) if a_parent else 0
    b_ratio = (b_child / b_parent) if b_parent else 0
    if a_ratio != b_ratio:
        return a_ratio > b_ratio
    if a.confidence != b.confidence:
        return a.confidence > b.confidence
    return a.name_score > b.name_score
