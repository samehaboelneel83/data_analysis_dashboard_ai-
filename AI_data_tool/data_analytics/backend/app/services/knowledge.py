"""One read path for everything the platform knows about a dataset's columns.

WHY THIS EXISTS
---------------
The platform learns a great deal about a connected database and then throws
almost all of it away at the point it matters most.

`run_catalog_sync` writes into `source_objects` / `source_columns`: the DBA's
own `COMMENT ON COLUMN`, a sentence per column from the describe pass, semantic
types, `enum_labels` recording that status 2 means "paid", which objects are
canonical, which are deprecated, and an `entities` row saying what one row of a
business object IS ("one row per completed admission"). `run_sync` writes a
thinner version of the same for uploaded files, into `dataset_columns`.

Every consumer on the DATASET side then reads `name` and `dtype` and nothing
else. `describe_for_prompt` -- the entire prompt the dashboard designer sees --
listed distinct counts and min/max and not one word of meaning, so it chose
charts from column shapes. `load_dataset_context` built the agent's world from
`{name: dtype}` and left the glossary empty by construction. The result is the
complaint that started this module: the app draws a chart that is valid and
meaningless, while the sentence explaining the column sits one table away.

WHY A RESOLVER AND NOT A COPY
-----------------------------
The tempting fix is to copy descriptions into `DatasetColumn` at import. That is
one line and it is wrong. This repository already runs that experiment:
`relationships` and `source_relationships` hold the same kind of fact in two
places, and they disagree the moment either side is edited. A copy also freezes
the knowledge at import time, so describing a column tomorrow does nothing for
the dataset imported today.

So `dataset_columns.source_column_id` records WHERE a column came from, and
meaning is resolved here, at read time. Describe `patient_id` once and every
dataset ever built from that table says it.

THE LADDER
----------
Descriptions carry provenance, and the ladder is `metadata/store.py`'s, applied
across both stores:

    source confirmed  >  dataset confirmed  >  source comment (declared)
                      >  source inferred    >  dataset inferred

A human's confirmation outranks any inference on either side; a comment written
in the database's own catalog outranks both inference passes, because it is
documentation rather than a guess. Within the same rank the SOURCE wins: it is
the shared copy, the one another dataset built from the same table will also
read.

SECURITY
--------
This module returns metadata, never rows, and opens no connection to a customer
database. It still takes `denied`: a column the viewer's role may not see must
not arrive in a prompt wearing a helpful description, because the whole point of
column security is that the model cannot ask for what it never saw. Denied
columns are dropped here, exactly as `SchemaContext.denied_columns` drops them
from the agent's render.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import (Dataset, DatasetColumn, Entity, GlossaryTerm,
                             SourceColumn, SourceObject)
from .metadata.store import CONFIRMED, DECLARED, INFERRED

#: Ranked exactly as `store._PRECEDENCE`, plus the "nothing at all" floor. A
#: description with a value but NO marker is treated as CONFIRMED, for the same
#: reason store.py does: everything written before the markers existed was
#: authored by a person, and reading absence as permission would let a later
#: inference silently overrule them.
_RANK = {INFERRED: 0, DECLARED: 1, CONFIRMED: 2}
_NONE_RANK = -1


def _rank(text: str | None, marker: str | None) -> int:
    if not text:
        return _NONE_RANK
    return _RANK.get(marker or CONFIRMED, _RANK[CONFIRMED])


@dataclass
class ColumnKnowledge:
    """What is known about one column, after both stores have been consulted."""
    name: str
    dtype: str | None = None
    description: str | None = None
    #: Which rung of the ladder `description` came from, so a UI can say whether
    #: a person approved it rather than presenting a guess as fact.
    description_source: str | None = None
    #: Whether the description came from the source catalog (and so is shared
    #: with every other dataset built from that table) or from this dataset.
    description_origin: str | None = None      # "source" | "dataset"
    semantic_type: str | None = None
    #: {"1": "new", "2": "paid"} -- what a coded value MEANS. Only the source
    #: catalog records these; an uploaded file has no such column.
    enum_labels: dict[str, str] | None = None
    #: The database's own COMMENT, kept separately from `description` so a
    #: caller can show documentation and inference differently.
    comment: str | None = None
    is_personal: bool = False
    #: How strongly this column is an outcome worth explaining -- higher first,
    #: None means "not a target". Resolved like a description: the dataset's own
    #: `column_meta` overrides the catalog, because one dataset may genuinely
    #: have a different question in mind from the table it was built from.
    target_priority: int | None = None
    #: Whether the suggestion engines may VOLUNTEER this column. Distinct from
    #: hidden: hidden removes a column from the pickers and the analysis
    #: entirely; this leaves it fully usable by anyone who asks and only stops
    #: the platform offering it unprompted. Defaults True -- absence is not a
    #: restriction. Dataset-scoped on purpose: the same column can be worth
    #: suggesting in one dataset and noise in another.
    eligible_for_suggestion: bool = True
    #: False when nothing at all is known beyond name and dtype -- lets a caller
    #: render exactly as before rather than emitting empty decoration.
    @property
    def has_meaning(self) -> bool:
        return bool(self.description or self.enum_labels or self.comment)


@dataclass
class ObjectKnowledge:
    """What is known about the thing the dataset's rows ARE."""
    name: str
    description: str | None = None
    #: An admin's assertion that this object is the source of truth for what it
    #: describes -- advisory, and the strongest "this one matters" signal the
    #: catalog carries.
    is_canonical: bool = False
    is_deprecated: bool = False
    #: From the matching `entities` row: the business name ("Admission") and the
    #: grain ("one row per completed admission"). The grain is the single fact
    #: that most often stops a model double-counting.
    business_name: str | None = None
    grain: str | None = None


@dataclass
class GlossaryEntry:
    term: str
    definition: str | None = None
    synonyms: list[str] = field(default_factory=list)
    maps_to_object: str | None = None
    maps_to_column: str | None = None


@dataclass
class DatasetKnowledge:
    dataset_id: int
    object: ObjectKnowledge
    columns: dict[str, ColumnKnowledge] = field(default_factory=dict)
    glossary: list[GlossaryEntry] = field(default_factory=list)
    #: How many columns resolved through to a source column. Zero for an upload,
    #: and zero for an import whose provenance could not be established -- the
    #: difference between "nothing is known" and "nothing was linked" matters
    #: when diagnosing a thin prompt.
    linked_columns: int = 0

    def column(self, name: str) -> ColumnKnowledge | None:
        return self.columns.get(name)

    @property
    def has_meaning(self) -> bool:
        """Whether anything here is worth putting in front of a model."""
        if self.object.description or self.object.grain or self.glossary:
            return True
        return any(c.has_meaning for c in self.columns.values())

    def targets(self) -> list[ColumnKnowledge]:
        """Outcome columns worth explaining, strongest first.

        What `key_influencers` and the tree analyses ask for when nobody has
        told them what to explain. Empty is a normal answer and means exactly
        one thing: run none of them, rather than pick something arbitrary.
        """
        named = [c for c in self.columns.values()
                 if c.target_priority is not None and c.eligible_for_suggestion]
        return sorted(named, key=lambda c: (-(c.target_priority or 0), c.name))

    def suggestable(self) -> list[str]:
        """Columns the platform may VOLUNTEER, in no particular order."""
        return [n for n, c in self.columns.items() if c.eligible_for_suggestion]

    def terms_for(self, text: str) -> list[GlossaryEntry]:
        """Glossary entries whose term or any synonym appears in `text`.

        `casefold()` rather than `lower()`, matching `SchemaContext.glossary_for`
        -- it is the unicode-correct comparison, and Arabic terms are a first
        reason this table exists.
        """
        low = (text or "").casefold()
        return [g for g in self.glossary
                if g.term.casefold() in low
                or any(s.casefold() in low for s in (g.synonyms or []))]


def _split_qualified(name: str | None) -> tuple[str | None, str | None]:
    """`"sales.orders"` -> `("sales", "orders")`; a bare name -> `(None, name)`.

    Import stores whatever the browser handed it, which is sometimes qualified
    and sometimes not, so both shapes have to find the same SourceObject.
    """
    if not name:
        return None, None
    if "." in name:
        schema, _, bare = name.rpartition(".")
        return schema.strip('"[]` ') or None, bare.strip('"[]` ') or None
    return None, name.strip('"[]` ') or None


async def _objects_for(db: AsyncSession, source_id: int) -> list[SourceObject]:
    return list((await db.execute(
        select(SourceObject).where(SourceObject.data_source_id == source_id)
    )).scalars().all())


def _match_object(objects: list[SourceObject], table: str | None) -> SourceObject | None:
    """The catalog object a dataset's `source_table` names, case-insensitively.

    Case-insensitive because the catalog stores what the database reported and
    the import stores what the user clicked, and on Postgres those differ by
    folding alone often enough to matter.
    """
    schema, bare = _split_qualified(table)
    if not bare:
        return None
    want = bare.casefold()
    matches = [o for o in objects if (o.name or "").casefold() == want]
    if schema:
        by_schema = [o for o in matches if (o.schema_name or "").casefold() == schema.casefold()]
        if by_schema:
            return by_schema[0]
    return matches[0] if len(matches) == 1 else (matches[0] if matches else None)


def _tables_named_in(sql: str | None, objects: list[SourceObject]) -> list[SourceObject]:
    """Catalog objects whose name appears as a whole word in `sql`.

    The same technique `agent/graph._detect_tables` uses on a question. It is a
    heuristic and it is used as one: it only ever NARROWS the candidate set for
    a name match, so the worst case is the wider search that would have happened
    anyway.
    """
    if not sql:
        return []
    low = sql.casefold()
    found = []
    for obj in objects:
        name = (obj.name or "").casefold()
        if name and re.search(rf"\b{re.escape(name)}\b", low):
            found.append(obj)
    return found


async def link_columns(db: AsyncSession, dataset: Dataset) -> int:
    """Fill `source_column_id` on this dataset's columns. Returns how many linked.

    Three cases, narrowest first, because a WRONG link is worse than none -- it
    would print one column's sentence beside another's numbers, which is a
    confident lie rather than a missing fact:

      1. `source_table` names a catalog object -> match that object's columns by
         name. This is the ordinary import and it is exact.
      2. No table, but SQL that mentions catalog objects (the AI-built datasets
         take this path: a proposal is imported as a query with no table) ->
         match against the columns of the objects the SQL names, and link only
         when exactly one candidate has that name.
      3. Nothing to narrow with -> match against the whole catalog, and again
         link only on a unique hit. A column name unique across an entire
         database is safe to trust; an ambiguous one is left NULL.

    Idempotent: a column that already carries a link is left alone, so a
    re-import cannot downgrade a link that a more informative earlier run made.
    Never raises on a missing catalog -- a source that was never synced simply
    links nothing, which is the honest outcome rather than a failed import.
    """
    if dataset.data_source_id is None:
        return 0

    columns = list((await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)
    )).scalars().all())
    unlinked = [c for c in columns if c.source_column_id is None]
    if not unlinked:
        return 0

    objects = await _objects_for(db, dataset.data_source_id)
    if not objects:
        return 0

    primary = _match_object(objects, dataset.source_table)
    named = _tables_named_in(dataset.source_query, objects)

    # The primary table is searched FIRST and on its own. A query-builder
    # dataset carries both a base table and a query that joins others, and
    # `id` exists on most of them -- without this precedence the base table's
    # own columns would become ambiguous the moment it was joined to anything,
    # and a dataset would lose links it deserved.
    tiers: list[list[SourceObject]] = []
    if primary is not None:
        tiers.append([primary])
    # A plain table import stops there. Every column it has came from that one
    # table, so a column the catalog's copy of that table does not list -- a
    # stale sync, a column added since -- must stay NULL rather than being
    # linked to a same-named column on some unrelated table that happens to be
    # the only other match. That is precisely the wrong link this function
    # refuses to make elsewhere, and it would be no less wrong for being easy.
    reaches_further = bool(dataset.source_query)
    if reaches_further or primary is None:
        wider = [o for o in (named or objects) if primary is None or o.id != primary.id]
        if wider:
            tiers.append(wider)
    if not tiers:
        return 0

    by_tier: list[dict[str, list[SourceColumn]]] = []
    for tier in tiers:
        rows = (await db.execute(
            select(SourceColumn).where(
                SourceColumn.source_object_id.in_([o.id for o in tier]))
        )).scalars().all()
        index: dict[str, list[SourceColumn]] = {}
        for sc in rows:
            index.setdefault((sc.name or "").casefold(), []).append(sc)
        by_tier.append(index)

    linked = 0
    for col in unlinked:
        want = (col.name or "").casefold()
        for index in by_tier:
            hits = index.get(want, [])
            # Exactly one candidate in this tier. Anything else is ambiguous
            # and falls through -- and if no tier resolves it, the column stays
            # NULL rather than being linked to a guess.
            if len(hits) == 1:
                col.source_column_id = hits[0].id
                linked += 1
                break
            if hits:
                break
    return linked


async def for_dataset(db: AsyncSession, dataset: Dataset, *,
                      denied: set[str] | None = None) -> DatasetKnowledge:
    """Everything known about this dataset's columns, both stores consulted.

    `denied` names columns this viewer's role may not see; they are dropped
    entirely rather than described, so no prompt can mention a column security
    already decided to hide.
    """
    denied_fold = {d.casefold() for d in (denied or set())}
    meta = dataset.column_meta if isinstance(dataset.column_meta, dict) else {}

    columns = list((await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)
    )).scalars().all())
    columns = [c for c in columns if (c.name or "").casefold() not in denied_fold]

    source_ids = [c.source_column_id for c in columns if c.source_column_id]
    source_by_id: dict[int, SourceColumn] = {}
    source_object: SourceObject | None = None
    if source_ids:
        rows = (await db.execute(
            select(SourceColumn).where(SourceColumn.id.in_(source_ids))
        )).scalars().all()
        source_by_id = {r.id: r for r in rows}
        object_ids = {r.source_object_id for r in rows}
        # One object means the dataset IS that table, and its description and
        # canonical/deprecated markers apply. Several means the dataset joins
        # them, and no single object's description describes the result -- so
        # none is claimed. Saying "this is the orders table" about a five-table
        # join would be worse than saying nothing.
        if len(object_ids) == 1:
            source_object = await db.get(SourceObject, object_ids.pop())

    if source_object is None and dataset.data_source_id and dataset.source_table:
        source_object = _match_object(
            await _objects_for(db, dataset.data_source_id), dataset.source_table)

    obj = ObjectKnowledge(
        name=dataset.name,
        description=(source_object.description if source_object and source_object.description
                     else dataset.description),
        is_canonical=bool(source_object.is_canonical) if source_object else False,
        is_deprecated=bool(getattr(source_object, "is_deprecated", False)) if source_object
                      else bool(getattr(dataset, "is_deprecated", False)),
    )

    if source_object is not None and dataset.data_source_id:
        entity = (await db.execute(
            select(Entity).where(Entity.data_source_id == dataset.data_source_id,
                                 Entity.primary_object == source_object.name)
        )).scalars().first()
        if entity is not None:
            obj.business_name = entity.business_name or entity.name
            obj.grain = entity.grain
            if not obj.description:
                obj.description = entity.description

    resolved: dict[str, ColumnKnowledge] = {}
    linked = 0
    for col in columns:
        src = source_by_id.get(col.source_column_id) if col.source_column_id else None
        if src is not None:
            linked += 1
        ck = ColumnKnowledge(name=col.name, dtype=col.dtype)

        # The ladder. Both candidates are scored, and the source wins ties: it
        # is the shared copy, so preferring it keeps two datasets built from one
        # table saying the same thing about the same column.
        own_rank = _rank(col.description, col.description_source)
        src_rank = _rank(src.description, src.description_source) if src else _NONE_RANK
        comment_rank = _rank(src.comment, DECLARED) if src and src.comment else _NONE_RANK

        best = max(own_rank, src_rank, comment_rank)
        if best == _NONE_RANK:
            pass
        elif src_rank == best:
            ck.description, ck.description_source = src.description, (src.description_source or CONFIRMED)
            ck.description_origin = "source"
        elif comment_rank == best:
            ck.description, ck.description_source = src.comment, DECLARED
            ck.description_origin = "source"
        else:
            ck.description, ck.description_source = col.description, (col.description_source or CONFIRMED)
            ck.description_origin = "dataset"

        if src is not None and src.comment:
            ck.comment = src.comment

        # Semantic type: the dataset's own detection wins, because it ran over
        # the bytes THIS dataset actually holds -- an import can narrow, cast or
        # mask a column out of the shape its source column described. The
        # catalog is the fallback, which is what an unprofiled dataset gets.
        ck.semantic_type = col.semantic_type or (src.semantic_type if src else None)

        if src is not None and src.enum_labels:
            ck.enum_labels = {str(k): str(v) for k, v in (src.enum_labels or {}).items()}

        from .pii import is_pii
        ck.is_personal = is_pii(ck.semantic_type)

        # The author's per-dataset say, over the catalog's shared one.
        entry = meta.get(col.name)
        entry = entry if isinstance(entry, dict) else {}
        own_target = entry.get("target_candidate_priority")
        ck.target_priority = (own_target if own_target is not None
                              else (src.target_candidate_priority if src else None))
        eligible = entry.get("eligible_for_suggestion")
        ck.eligible_for_suggestion = True if eligible is None else bool(eligible)

        resolved[col.name] = ck

    glossary: list[GlossaryEntry] = []
    if dataset.org_id is not None:
        terms = (await db.execute(
            select(GlossaryTerm).where(
                GlossaryTerm.org_id == dataset.org_id,
                # A term with no source is org-wide: "GMV" usually means the
                # same thing in every database a company has.
                (GlossaryTerm.data_source_id == dataset.data_source_id)
                | (GlossaryTerm.data_source_id.is_(None)),
            ).order_by(GlossaryTerm.term)
        )).scalars().all()
        glossary = [GlossaryEntry(term=t.term, definition=t.definition,
                                  synonyms=list(t.synonyms or []),
                                  maps_to_object=t.maps_to_object,
                                  maps_to_column=t.maps_to_column)
                    for t in terms]

    return DatasetKnowledge(dataset_id=dataset.id, object=obj, columns=resolved,
                            glossary=glossary, linked_columns=linked)


@dataclass
class SimilarDataset:
    """An existing dataset that covers much of what a new one would.

    `overlap` counts the source columns in common; `coverage` is the share of
    the PROPOSED columns this dataset already has. Coverage rather than a
    symmetric similarity on purpose: the question being asked is "would this
    existing dataset answer what I am about to build", and a big dataset that
    contains everything proposed answers it completely, however many extra
    columns it carries.
    """
    dataset_id: int
    name: str
    mode: str
    row_count: int
    overlap: int
    coverage: float
    matched_columns: list[str] = field(default_factory=list)
    #: True when the match was made on column NAMES because one side had no
    #: provenance. Weaker evidence, and the caller should say so rather than
    #: presenting it with the same confidence.
    by_name: bool = False


#: Below this share of the proposed columns, an "existing dataset like this" is
#: noise -- two datasets from one warehouse share `id` and `created_at` without
#: being about remotely the same thing. High enough that a suggestion means
#: something, low enough that a proposal adding a couple of columns to an
#: existing dataset still finds it.
SIMILAR_MIN_COVERAGE = 0.6


async def similar_datasets(db: AsyncSession, *, source_id: int, org_id: int,
                           column_names: list[str],
                           table: str | None = None,
                           query: str | None = None,
                           exclude_dataset_id: int | None = None,
                           limit: int = 5) -> list[SimilarDataset]:
    """Datasets already built from this source that cover the proposed columns.

    Answers the question the AI path could never ask: before creating a dataset
    for somebody, is there one they already have that would do? Nothing is
    blocked by the answer -- it is shown, and the person decides. A tool that
    silently refused to build what was asked for because it found something
    similar would be worse than one that built a duplicate.

    The comparison runs on SOURCE COLUMN IDENTITY where both sides have
    provenance, which is what makes it trustworthy: two datasets naming a column
    `id` are not similar, two datasets built from `orders.id` are. Where either
    side is unlinked it falls back to names and says so, because a weak answer
    the caller can label is better than no answer for an upload-shaped world.
    """
    if not column_names:
        return []

    objects = await _objects_for(db, source_id)
    if not objects:
        return []

    # What the proposal would be built from, resolved the same way an import
    # would resolve it -- the same tiering, so the comparison is like for like.
    primary = _match_object(objects, table)
    named = _tables_named_in(query, objects)
    scope = [primary] if (primary is not None and not query) else \
            ([primary] if primary is not None else []) + \
            [o for o in (named or objects) if primary is None or o.id != primary.id]

    rows = (await db.execute(
        select(SourceColumn).where(
            SourceColumn.source_object_id.in_([o.id for o in scope if o is not None]))
    )).scalars().all()
    by_name: dict[str, list[SourceColumn]] = {}
    for sc in rows:
        by_name.setdefault((sc.name or "").casefold(), []).append(sc)

    wanted_ids: set[int] = set()
    wanted_names = {(n or "").casefold() for n in column_names}
    for n in wanted_names:
        hits = by_name.get(n, [])
        if len(hits) == 1:
            wanted_ids.add(hits[0].id)

    candidates = (await db.execute(
        select(Dataset).where(Dataset.data_source_id == source_id,
                              Dataset.org_id == org_id)
    )).scalars().all()

    out: list[SimilarDataset] = []
    for ds in candidates:
        if exclude_dataset_id is not None and ds.id == exclude_dataset_id:
            continue
        cols = (await db.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
        )).scalars().all()
        if not cols:
            continue

        their_ids = {c.source_column_id for c in cols if c.source_column_id}
        matched_by_id = wanted_ids & their_ids
        if wanted_ids and their_ids and matched_by_id:
            matched = sorted(c.name for c in cols if c.source_column_id in matched_by_id)
            overlap, weak = len(matched_by_id), False
        else:
            # Neither side has usable provenance. Names, and labelled as such.
            theirs = {(c.name or "").casefold() for c in cols}
            common = wanted_names & theirs
            if not common:
                continue
            matched = sorted(c.name for c in cols
                             if (c.name or "").casefold() in common)
            overlap, weak = len(common), True

        # The denominator is every column ASKED ABOUT, never just the ones that
        # resolved. Scoring against the resolved subset made a five-column
        # proposal whose only catalogued column was `id` read as a perfect
        # match against every dataset in the database -- the question is "how
        # much of what I am about to build does this already cover", and a
        # column the catalog has never heard of is uncovered, not excused.
        denominator = len(wanted_names)
        coverage = overlap / denominator if denominator else 0.0
        if coverage < SIMILAR_MIN_COVERAGE:
            continue
        out.append(SimilarDataset(
            dataset_id=ds.id, name=ds.name, mode=ds.mode or "import",
            row_count=int(ds.row_count or 0), overlap=overlap,
            coverage=round(coverage, 3), matched_columns=matched, by_name=weak))

    # Strongest evidence first: full coverage before partial, provenance before
    # names, then the bigger dataset -- which is the more likely to be the one
    # somebody already maintains.
    out.sort(key=lambda s: (s.coverage, not s.by_name, s.row_count), reverse=True)
    return out[:limit]
