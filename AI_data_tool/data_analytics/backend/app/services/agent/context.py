"""What the agent may know about a source.

This is an INTERFACE with a v1 implementation (spec F6): Layer 3 — entities,
glossary, embeddings, retrieval — does not exist, and the Layer 1 catalog is
its serviceable stand-in. A real semantic layer replaces `load_context`
without touching the graph.

The one rule that must survive any replacement is F1: only `confirmed` and
`declared` relationships enter `joins`. Inference proposes; a human confirms;
the agent executes only on what survived that ladder.
"""
from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import or_, select

from ...models.models import (ColumnStats, DataSource, Dataset, DatasetColumn,
                              Entity, GlossaryTerm, Relationship, SourceColumn,
                              SourceObject, SourceRelationship)
from ..metadata import store
from ..retrieval import entity_document, rank_documents, rank_objects

logger = logging.getLogger(__name__)


@dataclass
class ObjectInfo:
    name: str
    kind: str
    description: str | None
    columns: dict[str, str] = field(default_factory=dict)
    # T1: an admin's assertion that this object is the source of truth for
    # what its description says it holds. Default False keeps every existing
    # caller (notably load_dataset_context, which has no such flag) unchanged.
    is_canonical: bool = False
    # T2: {column name: {raw value (stringified): label}} -- what a coded
    # column's values MEAN. Populated only for columns with a short enough
    # top_k that an enumeration reading makes sense; see catalog_sync.py.
    enum_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    # The measured trap: the agent picked maps_states.students_count for a
    # submissions question -- a column literally named what was asked, but
    # 100% NULL. Names of columns whose ColumnStats.null_ratio >=
    # HIGH_NULL_RATIO (catalog already knows this; we just have to surface
    # it). Default empty set keeps every existing caller unchanged.
    high_null: set[str] = field(default_factory=set)
    # {column name: what it MEANS}. The catalog has held these since the
    # describe pass shipped and nothing ever showed them to a model: the
    # enriched line carried dtypes and enum labels, and a column's sentence
    # -- the single most informative thing known about it -- stayed in the
    # database. Rendered in pass 2 ONLY, beside the dtype it belongs to, so
    # the skeleton pass that guarantees every object gets NAMED is untouched.
    descriptions: dict[str, str] = field(default_factory=dict)


#: Compact rendering caps at this many value=label pairs per column, so one
#: heavily-enumerated column cannot blow up the prompt budget of every other
#: object in the context. Tightened from 12 (H7 fix): a render carrying every
#: object's full label set is what pushed whole OBJECTS out of an 82-object
#: catalog's prompt (see MAX_CHARS below) -- shrinking this buys back budget
#: pass 2 spends on more objects rather than deeper labels for a few.
MAX_RENDERED_ENUM_LABELS = 6

#: A label longer than this is truncated with a visible ellipsis. Column
#: VALUES stay exact (never truncated: a wrong WHERE literal is worse than a
#: verbose one) -- only the human-written gloss is capped, and glosses this
#: long are rare and mostly redundant with the value itself.
MAX_LABEL_CHARS = 24

#: [CANONICAL ...] marker text, shared between the pass-1 skeleton line and
#: the pass-2 enriched line so degrading an entry back to its skeleton (or
#: never getting to enrich it at all) can never cost it this marker -- see
#: SchemaContext.render's guarantee that canonical objects keep it either way.
_CANONICAL_MARKER = (
    " [CANONICAL — the source of truth for what it describes; "
    "prefer it over recomputing from raw tables]"
)


#: The measured trap: the agent picked `maps_states.students_count` for a
#: submissions question -- a column literally named what was asked, but
#: 100% NULL. A column whose ColumnStats.null_ratio is at or above this
#: threshold is marked ALL NULL in the enriched render so the model never
#: picks it. 0.98 rather than a strict 1.0: a null_ratio computed from an
#: estimate (ColumnStats.exact == False) can miss 100% by a hair, and a
#: column that is 98%+ empty is just as useless for answering a question.
HIGH_NULL_RATIO = 0.98

_ALL_NULL_MARKER = " (ALL NULL — contains no data, never use it)"


def _truncate_label(label: str) -> str:
    if len(label) <= MAX_LABEL_CHARS:
        return label
    return label[:MAX_LABEL_CHARS - 1] + "…"


#: A column's description is capped in the render for the same reason labels
#: are: one verbose column must not spend the budget that names another whole
#: object. Generous enough for a real sentence, short enough that twenty of
#: them still fit beside their dtypes.
MAX_COLUMN_DESC_CHARS = 80


def _short_column_desc(text: str | None) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) > MAX_COLUMN_DESC_CHARS:
        text = text[:MAX_COLUMN_DESC_CHARS - 1] + "…"
    return text


def _render_column(name: str, dtype: str, labels: dict[str, str] | None, *,
                   high_null: bool = False, description: str | None = None) -> str:
    """`name dtype`, or `name dtype (1=new, 2=paid)` when labelled, or
    `name dtype (ALL NULL — contains no data, never use it)` when the
    catalog's ColumnStats says this column is (near-)entirely empty.

    A described column appends `— what it means` after all of that. ALL NULL
    still short-circuits: a column with no data in it is not worth a sentence,
    and the instruction never to use it must be the last word on the line.
    """
    if high_null:
        return f"{name} {dtype}{_ALL_NULL_MARKER}"
    desc = _short_column_desc(description)
    tail = f" — {desc}" if desc else ""
    if not labels:
        return f"{name} {dtype}{tail}"
    pairs = ", ".join(f"{v}={_truncate_label(l)}"
                      for v, l in list(labels.items())[:MAX_RENDERED_ENUM_LABELS])
    return f"{name} {dtype} ({pairs}){tail}"


#: SchemaContext.render's default budget (H7 fix). Qwen's context window is
#: 32k tokens; a rendered object line runs roughly 1 token per 3-4 chars, so
#: 24000 chars is on the order of 6-8k tokens -- generous room for an 82+
#: object catalog's SKELETON pass (which is what pass 1 actually needs to
#: guarantee) while still leaving most of the window for the system prompt,
#: few-shot examples, the question, and the model's own completion. Raised
#: from 8000: that budget was sized for a small catalog and, combined with
#: the old single-pass-then-slice render, is what silently dropped objects
#: from an 85k-char render (see render()'s docstring). Not raised to the full
#: window -- classify.py and generate.py both add several KB of their own
#: prompt text on top of this, and enforcing SOME ceiling is still what keeps
#: a genuinely enormous catalog from crowding out everything else in the
#: request, now via graceful degradation (pass 1/2) rather than a silent cut.
DEFAULT_RENDER_MAX_CHARS = 24000


#: Task R2 (spec §2): how many top-scored objects `render` asks
#: `retrieval.rank_objects` for. Bounded rather than "rank everything" so a
#: meaningful "rest, in today's order" tier still exists on catalogs larger
#: than this — the ranking's job is to prioritize enrichment on the objects
#: most likely to matter for THIS question, not to re-order the whole
#: catalog.
RENDER_RETRIEVAL_TOP_K = 12


#: Task R3 (review fix): how many entities `_entities_block` ever shows.
#: Unlike Glossary (small AND question-filtered) or Joins (bounded by the
#: schema's actual FK count), a source's entity count has no inherent cap --
#: dozens of drafted entities must not shrink the objects budget in direct
#: proportion, the same shape of problem H7 fixed for objects themselves.
MAX_RENDERED_ENTITIES = 8


#: Measured trap: `maps_state_student_solution` vs
#: `maps_state_student_solution_details` were BOTH skeleton-tier on the live
#: catalog. Skeletons carried no description, so nothing distinguished the
#: placements table from the details table ("detailed coordinate data for
#: student solutions ... symbols") and the model counted from the wrong one
#: twice, deterministically. A hard-truncated description at skeleton tier is
#: cheap disambiguation -- 90 chars is enough to carry "detailed coordinate
#: data for student solutions" without reintroducing the old per-object
#: budget blowup a full description caused.
MAX_SKELETON_DESC_CHARS = 90


def _short_desc(description: str | None) -> str:
    if not description:
        return ""
    if len(description) <= MAX_SKELETON_DESC_CHARS:
        return description
    return description[:MAX_SKELETON_DESC_CHARS - 1] + "…"


def _skeleton_object_line(o: ObjectInfo, column_cap: int | None) -> str:
    """Pass 1's minimal line: name, kind, canonical marker, a HARD-TRUNCATED
    description, then column NAMES only -- no dtypes, no labels, no full
    description. `column_cap` shortens a verbose column list (None = show
    every column) so this can always be made to fit a budget without ever
    dropping the object itself, or the short description: for table
    SELECTION, what a table IS beats what it contains -- exact columns are
    validated by V2 regardless of how compressed the listing gets."""
    canonical = _CANONICAL_MARKER if o.is_canonical else ""
    short_desc = _short_desc(o.description)
    desc_part = f" -- {short_desc}" if short_desc else ""
    # Exclude high-null columns entirely rather than listing the bare name:
    # a skeleton line carries no marker (pass 2 is the only place that can
    # explain WHY), so a bare "students_count" here is pure bait -- the
    # model picks the name-matching column with no signal it is empty. V2
    # validation (has_column) reads o.columns directly, never the render, so
    # a user who names the column explicitly is unaffected by this omission.
    names = [n for n in o.columns if n not in o.high_null]
    if column_cap is None or len(names) <= column_cap:
        cols = ", ".join(names)
    elif column_cap == 0:
        cols = f"{len(names)} columns" if names else ""
    else:
        cols = ", ".join(names[:column_cap]) + f", +{len(names) - column_cap} more"
    return f"- {o.name} ({o.kind}){canonical}{desc_part}: {cols}"


def _full_object_line(o: ObjectInfo) -> str:
    """Pass 2's enriched line: dtypes, enum labels, and the description --
    everything the skeleton line left out."""
    canonical = _CANONICAL_MARKER if o.is_canonical else ""
    cols = ", ".join(_render_column(n, t, o.enum_labels.get(n),
                                    high_null=n in o.high_null,
                                    description=o.descriptions.get(n))
                     for n, t in o.columns.items())
    desc = f" -- {o.description}" if o.description else ""
    return f"- {o.name} ({o.kind}){canonical}: {cols}{desc}"


@dataclass
class JoinInfo:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    provenance: str


@dataclass
class GlossaryInfo:
    """T3: a business term the agent should know, plus its synonyms —
    including non-English aliases (Arabic included; matching is a plain
    case/unicode-fold containment check, and Arabic has no case, so no
    special-casing is needed for it to work). `maps_to_object`/`_column`
    are advisory, like `is_canonical` — surfaced in the prompt, never
    enforced by V3."""
    term: str
    definition: str | None
    synonyms: list[str] = field(default_factory=list)
    maps_to_object: str | None = None
    maps_to_column: str | None = None


@dataclass
class EntityInfo:
    """Tier 2 / spec section 5 (E2): a named business object this source
    models -- "customer", "order" -- distinct from the raw SourceObject(s)
    that back it. `grain` is the fact the agent most needs: what a single
    row of this entity actually represents ("One row per completed order"),
    so it neither double-counts nor picks the wrong table to aggregate.
    `primary_object` is advisory (like GlossaryInfo.maps_to_object) -- the
    render never enforces it, only mentions it."""
    name: str
    business_name: str | None = None
    grain: str | None = None
    description: str | None = None
    primary_object: str | None = None


@dataclass
class SchemaContext:
    source_id: int
    family: str
    objects: dict[str, ObjectInfo] = field(default_factory=dict)
    joins: list[JoinInfo] = field(default_factory=list)
    # T3. Filled in BOTH modes. It used to be empty in dataset mode -- "the
    # dataset-mode path has no source to scope terms against yet" -- which
    # meant asking about the same data through a dataset silently lost every
    # business term the org had defined. `knowledge.for_dataset` scopes them
    # through the dataset's own source, so the excuse no longer holds.
    glossary: list[GlossaryInfo] = field(default_factory=list)
    # Task R3. Empty by default -- render's Entities block is a no-op string
    # when this is empty, which is exactly what keeps every existing caller
    # (and the pinned render(question=None) snapshot) byte-identical. Dataset
    # mode now contributes one entry per dataset whose catalog names an
    # entity, so its grain reaches the model there too.
    entities: list[EntityInfo] = field(default_factory=list)
    # Column security (R1 of the 2026-09-03 competitive assessment): columns
    # this USER's role must not see, per table. Populated by run_agent from
    # ColumnSecurityRule -- the loaders leave it empty because they have no
    # user. Two consumers: the render sees these columns already REMOVED
    # from `objects` (the model cannot ask for what it never saw), and
    # validate_sql's V6 rung fails closed if generated SQL names one anyway
    # -- the same drop-then-refuse pair the import and DirectQuery widget
    # paths use.
    denied_columns: dict[str, set[str]] = field(default_factory=dict)

    def has_table(self, name: str) -> bool:
        return name in self.objects

    def has_column(self, table: str, column: str) -> bool:
        info = self.objects.get(table)
        return bool(info) and column in info.columns

    def join_allowed(self, t1: str, c1: str, t2: str, c2: str) -> bool:
        """Order-insensitive: SQL may write either side first."""
        want = {(t1, c1), (t2, c2)}
        return any({(j.from_table, j.from_column),
                    (j.to_table, j.to_column)} == want for j in self.joins)

    def glossary_for(self, question: str) -> list[GlossaryInfo]:
        """Terms whose name or any synonym appears (case/unicode-fold,
        substring) in the question. `casefold()` rather than `lower()`
        because it is the unicode-correct comparison — Arabic has no case
        distinction at all, so plain containment already works for it, and
        casefold is just the safe default for every script."""
        q = question.casefold()
        return [g for g in self.glossary
               if g.term.casefold() in q
               or any(s.casefold() in q for s in g.synonyms)]

    def join_path(self, from_table: str, to_table: str) -> list[JoinInfo] | None:
        """T4: the shortest chain of joins connecting two tables, BFS over
        `self.joins` treated as an UNDIRECTED graph (a join edge works
        either way round in a query). `self.joins` is already
        provenance-filtered at load time (F1: only confirmed/declared
        relationships ever enter it) — so this never needs to re-check
        provenance, and an inferred-only edge can never appear in a
        returned path because it was never in `self.joins` to begin with.

        Returns None when either table is unknown to this context, or when
        no path connects them (including from_table == to_table with no
        self-join, which returns None rather than an empty path)."""
        if from_table not in self.objects or to_table not in self.objects:
            return None
        adjacency: dict[str, list[tuple[str, JoinInfo]]] = {}
        for j in self.joins:
            adjacency.setdefault(j.from_table, []).append((j.to_table, j))
            adjacency.setdefault(j.to_table, []).append((j.from_table, j))

        visited = {from_table}
        queue: deque[tuple[str, list[JoinInfo]]] = deque([(from_table, [])])
        while queue:
            node, path = queue.popleft()
            if node == to_table and path:
                return path
            for neighbor, edge in adjacency.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [edge]))
        return None

    def _ordered_objects(
        self, ranking: list[tuple[str, float]] | None = None,
    ) -> list[ObjectInfo]:
        """H7 fix, priority order: CANONICAL objects first (any kind), then
        tables, then views — alphabetical within each group. This is both the
        listing order and the pass-2 enrichment order, so a budget that runs
        out always runs out on the LEAST important objects, never on the
        canonical ones the agent was specifically told to prefer.

        `ranking` (Task R2, spec §2-3) is an optional retrieval-scored
        `[(object_name, score), ...]` list, most relevant first — as
        returned by `retrieval.rank_objects`. None or empty behaves exactly
        as before (the sole priority order above), which is what keeps
        `render(question=None)` byte-identical to pre-R2 output. Given, the
        return order becomes three tiers:

          1. Retrieval-ranked objects, re-sorted by (score desc, canonical
             first, name) so canonical status breaks a score tie rather than
             the arbitrary dict/ranking-list order.
          2. 1-hop join-whitelist neighbors of the top-3 ranked objects (the
             "orders question pulls order_lines in" promotion, spec §3) not
             already in tier 1, in the static priority order.
          3. Everything else, in today's static priority order — unranked
             objects "keep old relative order" among themselves.

        Ranking never DROPS an object: every name in `self.objects` still
        appears exactly once, in one of the three tiers (H7 breadth is a
        listing-order guarantee, not a filter)."""
        def group(o: ObjectInfo) -> int:
            if o.is_canonical:
                return 0
            return 1 if o.kind != "view" else 2
        default_order = sorted(self.objects.values(), key=lambda o: (group(o), o.name))
        if not ranking:
            return default_order

        score_by_name = {name: score for name, score in ranking if name in self.objects}
        if not score_by_name:
            return default_order

        ranked_objs = sorted(
            (self.objects[name] for name in score_by_name),
            key=lambda o: (-score_by_name[o.name], 0 if o.is_canonical else 1, o.name),
        )
        top_names = {o.name for o in ranked_objs}

        top3 = {o.name for o in ranked_objs[:3]}
        neighbor_names: set[str] = set()
        for j in self.joins:
            if j.from_table in top3 and j.to_table in self.objects and j.to_table not in top_names:
                neighbor_names.add(j.to_table)
            if j.to_table in top3 and j.from_table in self.objects and j.from_table not in top_names:
                neighbor_names.add(j.from_table)
        promoted = sorted((self.objects[n] for n in neighbor_names),
                          key=lambda o: (group(o), o.name))
        promoted_names = {o.name for o in promoted}

        rest = [o for o in default_order
               if o.name not in top_names and o.name not in promoted_names]
        return ranked_objs + promoted + rest

    def _joins_block(self) -> str:
        lines = [f"- {j.from_table}.{j.from_column} = {j.to_table}.{j.to_column}"
                 for j in self.joins]
        if not lines:
            return ""
        return "\n\nJoins you may use (the ONLY joins allowed):\n" + "\n".join(lines)

    def _glossary_block(self, question: str | None) -> str:
        if not question:
            return ""
        matched = self.glossary_for(question)
        if not matched:
            return ""
        q = question.casefold()
        glines = []
        for g in matched:
            line = f"- {g.term}"
            if g.definition:
                line += f": {g.definition}"
            if g.maps_to_object:
                target = g.maps_to_object
                if g.maps_to_column:
                    target += f".{g.maps_to_column}"
                line += f" [-> {target}]"
            # Live bug (verified): the hint was descriptive prose and the
            # model still copied the QUESTION's spelling of a synonym into
            # a SQL predicate, getting zero rows against the STORED
            # (term's canonical) spelling. When the match came from a
            # SYNONYM rather than the term text itself, and the term maps
            # to a column a predicate could target, state the substitution
            # mechanically rather than trust prose to convey it.
            if g.maps_to_column and g.term.casefold() not in q:
                matched_synonym = next(
                    (s for s in g.synonyms if s.casefold() in q), None)
                if matched_synonym:
                    line += (
                        f" NOTE: the question wrote '{matched_synonym}' "
                        f"but the STORED value is '{g.term}' — use the "
                        "stored spelling verbatim in SQL predicates.")
            glines.append(line)
        return "\n\nGlossary (matched from the question):\n" + "\n".join(glines)

    def _entities_block(self, question: str | None) -> str:
        """Task R3 (spec section 5): a compact "Entities:" block, present only
        when this source HAS entities -- empty (`self.entities == []`) is the
        common case today (no draft has run, or the source has none), and
        must render as "" so `render(question=None)` stays byte-identical to
        before entities existed.

        Capped at `MAX_RENDERED_ENTITIES` (review fix): unlike the Glossary
        block, which is safe only because it is small AND question-matched,
        this block has neither guard on its own -- a source with dozens of
        drafted entities would otherwise shrink the objects budget in direct
        proportion to entity count, the same shape of bug H7 fixed for
        objects. A truncated block says so with a "(+K more)" tail line
        rather than silently dropping the rest.

        Selection: top-`MAX_RENDERED_ENTITIES` by retrieval relevance when a
        question is given (entities are retrieval documents too --
        `rank_documents`, same never-raise contract as `rank_objects`), first
        `MAX_RENDERED_ENTITIES` alphabetically otherwise. The reservation
        rule in `render` is what keeps this block from ever costing an
        object its NAME in pass 1 regardless of how many entities it lists."""
        if not self.entities:
            return ""
        if question:
            try:
                docs = [entity_document(e) for e in self.entities]
                ranking = rank_documents(docs, question, len(docs))
                rank_of = {name: i for i, (name, _) in enumerate(ranking)}
                ordered = sorted(self.entities,
                                 key=lambda e: rank_of.get(e.name, len(rank_of)))
            except Exception:
                logger.exception(
                    "entity ranking failed at the context layer; "
                    "degrading to alphabetical order")
                ordered = sorted(self.entities, key=lambda e: e.name)
        else:
            ordered = sorted(self.entities, key=lambda e: e.name)

        shown = ordered[:MAX_RENDERED_ENTITIES]
        omitted = len(ordered) - len(shown)

        lines = []
        for e in shown:
            line = f"- {e.name}"
            if e.business_name:
                line += f" ({e.business_name})"
            if e.grain:
                line += f": {e.grain}"
            if e.description:
                line += f" -- {e.description}"
            if e.primary_object:
                line += f" [{e.primary_object}]"
            lines.append(line)
        if omitted > 0:
            lines.append(f"(+{omitted} more)")
        return "\n\nEntities:\n" + "\n".join(lines)

    def _retrieval_ranking(self, question: str | None) -> list[tuple[str, float]] | None:
        """`retrieval.rank_objects(self, question, RENDER_RETRIEVAL_TOP_K)`,
        wrapped defensively. `rank_objects` is documented never to raise --
        this except clause is "trust but verify" (spec's Error handling
        section): a failure anywhere in this call, expected or not, must
        degrade `render` to today's static ordering, never break it."""
        if not question:
            return None
        try:
            return rank_objects(self, question, RENDER_RETRIEVAL_TOP_K)
        except Exception:
            logger.exception(
                "retrieval ranking failed at the context layer; "
                "degrading to static object order")
            return None

    def render(self, max_chars: int = DEFAULT_RENDER_MAX_CHARS, *,
              question: str | None = None) -> str:
        """The prompt block. Kinds labelled, and ONLY allowed joins listed —
        offering an inferred join in the prompt would invite the model to
        write SQL that V3 then rejects.

        H7 fix (round-4 live measurement: conditional accuracy 75% -> 25%).
        The old implementation built one fully-enriched line per object, then
        sliced the WHOLE text to `max_chars`. On an 82-object catalog whose
        full render ran to 85k+ chars, that slice landed mid-list and
        silently dropped every object past it -- including the canonical
        `omda_symbol_count`, alphabetically after the early `cycle_students`
        that survived. The model then wrote SQL against whatever tables
        happened to still be in its prompt, which were not the right ones.

        Fixed structurally, not just with a bigger budget (still raised
        below, but that alone does not bound a catalog large enough): a
        two-pass render.

          Pass 1 -- breadth. EVERY object gets a minimal skeleton line (name,
          kind, canonical marker, plain column names) built to fit inside the
          objects budget by shortening (never dropping) a verbose column
          list. Every object NAME is guaranteed present at any sane budget.

          Pass 2 -- depth. Remaining budget is spent upgrading skeleton lines
          to fully enriched ones (dtypes, descriptions, enum labels), walked
          in the SAME priority order as the listing: canonical objects, then
          tables, then views. A budget that runs out always runs out on the
          least important objects.

        `question` is optional and additive (T3): omitted, this behaves as it
        did before glossary support existed -- no Glossary block, matching
        `render(question=None)` exactly. Given, and any glossary term/synonym
        matches it, a compact Glossary block is appended. Its budget (like
        the joins block's) is reserved BEFORE pass 1 runs, per the same
        guarantee: neither block may be the thing that pushes an object's
        NAME out of pass 1.

        `question` given also asks retrieval (Task R2, spec section 2-3) to
        reorder pass-2 enrichment priority: `_ordered_objects` places the
        retrieval-ranked top objects first, then 1-hop join neighbors of the
        top-3, then the rest unchanged. This is priority-order-only -- H7's
        breadth guarantee (every name survives pass 1) is untouched, because
        ranking only changes the ORDER `_ordered_objects` returns, never
        which objects are in it. Retrieval failures degrade to today's
        static order: `rank_objects` itself never raises, and the call here
        is additionally wrapped so a defect in this layer's own use of it
        can never take the render down either (spec's Error handling
        section -- "trust but verify").

        `self.entities` (Task R3) appends an optional "Entities:" block after
        Glossary, present only when the source HAS entities -- see
        `_entities_block`. Its budget is reserved before pass 1 exactly like
        the joins/glossary blocks, so it can never push an object's name out
        of pass 1 either; empty entities (today's default for every existing
        caller) render as "", which is what keeps this byte-identical to
        pre-R3 output.
        """
        header = "Objects:\n"
        joins_block = self._joins_block()
        glossary_block = self._glossary_block(question)
        entities_block = self._entities_block(question)
        ranking = self._retrieval_ranking(question)
        ordered = self._ordered_objects(ranking)

        # Pass 1: reserve joins'/glossary's/entities' room, then guarantee
        # every name. Entities follow the identical reservation rule as the
        # joins and glossary blocks -- subtracted from the objects budget
        # BEFORE pass 1 runs, so it can shrink pass 1's column verbosity but
        # can never push an object NAME out of it (see _skeleton_lines).
        reserved = len(joins_block) + len(glossary_block) + len(entities_block)
        objects_budget = max(max_chars - len(header) - reserved, 0)
        lines = self._skeleton_lines(ordered, objects_budget)

        # Pass 2: spend what's left enriching, canonical/table/view order.
        used = len(header) + (len("\n") * max(len(lines) - 1, 0)
                              + sum(len(l) for l in lines))
        remaining = max_chars - reserved - used
        for i, o in enumerate(ordered):
            full_line = _full_object_line(o)
            delta = len(full_line) - len(lines[i])
            if delta <= remaining:
                lines[i] = full_line
                remaining -= delta

        return (header + "\n".join(lines) + joins_block + glossary_block
                + entities_block)

    @staticmethod
    def _skeleton_lines(ordered: list[ObjectInfo], budget: int) -> list[str]:
        """Every object's minimal line, degrading column verbosity FIRST
        (never object count, never the short description) until the joined
        lines fit `budget` -- or, in an adversarial case even a zero-column
        skeleton cannot fit, returning the smallest attempt anyway. Columns
        degrade before the description because, for table SELECTION, what a
        table IS beats what it contains: `_skeleton_object_line` bakes the
        (already hard-truncated) description into every cap level, so it is
        never a knob this ladder turns -- it survives at cap 0 exactly as it
        does at cap None. Keeping every NAME outranks the budget: that is
        the whole guarantee this pass exists to make."""
        for cap in (None, 30, 15, 8, 4, 2, 1, 0):
            lines = [_skeleton_object_line(o, cap) for o in ordered]
            total = sum(len(l) for l in lines) + max(len(lines) - 1, 0)
            if total <= budget or cap == 0:
                return lines
        return lines  # pragma: no cover -- loop always returns at cap == 0


def suggest_join_route(context: SchemaContext, tables: list[str]) -> str | None:
    """T4: chain `join_path` across consecutive pairs of `tables` (already
    known to `context`) into one prompt-ready hint — `"Join route: a.x = b.y
    THEN b.z = c.w"`. None if fewer than two tables are given, or if any
    consecutive pair has no path — a partial route would misdirect the model
    more than no route at all."""
    if len(tables) < 2:
        return None
    legs: list[JoinInfo] = []
    for a, b in zip(tables, tables[1:]):
        path = context.join_path(a, b)
        if not path:
            return None
        legs.extend(path)
    if not legs:
        return None
    parts = [f"{j.from_table}.{j.from_column} = {j.to_table}.{j.to_column}"
             for j in legs]
    return "Join route: " + " THEN ".join(parts)


async def load_context(db, source_id: int, org_id: int) -> SchemaContext:
    source = await db.get(DataSource, source_id)
    family = source.type if source and source.org_id == org_id else "postgresql"

    ctx = SchemaContext(source_id=source_id, family=family or "postgresql")
    if source is None or source.org_id != org_id:
        # Same shape as check_org's 404: reveal nothing, not even emptiness
        # semantics. The router turns an empty context into "not found".
        return ctx

    objects = (await db.execute(select(SourceObject).where(
        SourceObject.data_source_id == source_id,
        SourceObject.org_id == org_id))).scalars().all()
    by_id = {}
    for o in objects:
        info = ObjectInfo(name=o.name, kind=o.kind or "table",
                          description=o.comment or o.description,
                          is_canonical=bool(o.is_canonical))
        ctx.objects[o.name] = info
        by_id[o.id] = info

    if by_id:
        columns = (await db.execute(select(SourceColumn).where(
            SourceColumn.source_object_id.in_(list(by_id))))).scalars().all()
        col_by_id = {}
        for c in columns:
            obj_info = by_id[c.source_object_id]
            obj_info.columns[c.name] = c.dtype or "unknown"
            if c.enum_labels:
                obj_info.enum_labels[c.name] = c.enum_labels
            # The DBA's COMMENT outranks the describe pass's sentence, the
            # same precedence `services/knowledge.py` applies -- documentation
            # somebody wrote beats a guess about the same column.
            if c.comment or c.description:
                obj_info.descriptions[c.name] = c.comment or c.description
            col_by_id[c.id] = (obj_info, c.name)

        if col_by_id:
            stats = (await db.execute(select(ColumnStats).where(
                ColumnStats.source_column_id.in_(list(col_by_id))))).scalars().all()
            for s in stats:
                obj_info, col_name = col_by_id.get(s.source_column_id, (None, None))
                if obj_info is not None and (s.null_ratio or 0.0) >= HIGH_NULL_RATIO:
                    obj_info.high_null.add(col_name)

        rels = (await db.execute(select(SourceRelationship).where(
            SourceRelationship.data_source_id == source_id,
            SourceRelationship.org_id == org_id,
            SourceRelationship.source.in_([store.CONFIRMED, store.DECLARED]),
        ))).scalars().all()
        for r in rels:
            f, t = by_id.get(r.from_object_id), by_id.get(r.to_object_id)
            if f and t:
                ctx.joins.append(JoinInfo(f.name, r.from_column,
                                          t.name, r.to_column, r.source))

    # T3: this source's own terms, plus every ORG-WIDE term (data_source_id
    # NULL) — a term like "GMV" usually means the same thing everywhere in
    # the org, not just on the one connection where someone happened to
    # define it.
    terms = (await db.execute(select(GlossaryTerm).where(
        GlossaryTerm.org_id == org_id,
        or_(GlossaryTerm.data_source_id == source_id,
            GlossaryTerm.data_source_id.is_(None)),
    ))).scalars().all()
    for t in terms:
        ctx.glossary.append(GlossaryInfo(
            term=t.term, definition=t.definition,
            synonyms=list(t.synonyms or []),
            maps_to_object=t.maps_to_object, maps_to_column=t.maps_to_column))

    # Task R3: this source's entities. Source-scoped only (unlike glossary,
    # entities have no org-wide analogue -- a "customer" entity's grain is
    # specific to how ONE connection's tables model it).
    entities = (await db.execute(select(Entity).where(
        Entity.data_source_id == source_id, Entity.org_id == org_id))).scalars().all()
    for e in entities:
        ctx.entities.append(EntityInfo(
            name=e.name, business_name=e.business_name, grain=e.grain,
            description=e.description, primary_object=e.primary_object))
    return ctx


def _table_name(name: str) -> str:
    """Lowercase, every run of non-alphanumeric characters collapsed to one
    underscore, leading/trailing underscores trimmed. Deduplication (the
    `_2`, `_3`... suffixes) is NOT this function's job — see
    `dataset_table_names`, which both load_dataset_context and the
    dataset-mode executor (Task 17) call so the two sides can never derive
    different names for the same dataset."""
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return base or "table"


def dataset_table_names(names: list[str]) -> list[str]:
    """Order-preserving, collision-safe DuckDB table names for a list of
    dataset names. Exported so graph.py can derive the EXACT same mapping
    load_dataset_context used, by calling this with datasets in the same
    order — never by re-deriving the naming logic independently."""
    used: set[str] = set()
    out: list[str] = []
    for name in names:
        base = _table_name(name)
        candidate = base
        n = 2
        while candidate in used:
            candidate = f"{base}_{n}"
            n += 1
        used.add(candidate)
        out.append(candidate)
    return out


async def load_dataset_context(db, dataset_ids: list[int], org_id: int) -> SchemaContext:
    """The dataset-mode counterpart to load_context (Task 16 — spec F1 amendment
    for import/multi-file mode). source_id is 0 (there is no single DataSource;
    the "source" is a set of datasets) and family is always "duckdb", since the
    generated SQL runs against an in-memory DuckDB connection with each dataset's
    frame registered as a table (see executor.execute_on_datasets)."""
    ctx = SchemaContext(source_id=0, family="duckdb")
    if not dataset_ids:
        return ctx

    rows = (await db.execute(select(Dataset).where(
        Dataset.id.in_(dataset_ids), Dataset.org_id == org_id))).scalars().all()
    by_id = {d.id: d for d in rows}
    # Preserve the caller's ordering; silently drop ids that don't exist or
    # belong to another org — same "reveal nothing" shape as load_context.
    ordered = [by_id[i] for i in dataset_ids if i in by_id]
    if not ordered:
        return ctx

    table_names = dataset_table_names([d.name for d in ordered])
    name_by_dataset_id: dict[int, str] = {}
    for ds, tname in zip(ordered, table_names):
        ctx.objects[tname] = ObjectInfo(name=tname, kind="dataset",
                                        description=ds.description)
        name_by_dataset_id[ds.id] = tname

    columns = (await db.execute(select(DatasetColumn).where(
        DatasetColumn.dataset_id.in_(list(name_by_dataset_id))))).scalars().all()
    for c in columns:
        tname = name_by_dataset_id.get(c.dataset_id)
        if tname:
            ctx.objects[tname].columns[c.name] = c.dtype or "unknown"

    # Everything ABOVE this line is what dataset mode used to be: a table name,
    # a dataset description, and {column: dtype}. Source mode has carried
    # canonical markers, coded-value meanings, entities and a glossary since
    # they shipped; a question asked about the same data through a dataset got
    # none of it, purely because the loader read a different table.
    #
    # `knowledge.for_dataset` resolves all of it through each column's
    # provenance, so the two modes finally answer from the same facts.
    from ...services import knowledge as knowledge_service

    for ds in ordered:
        tname = name_by_dataset_id[ds.id]
        info = ctx.objects[tname]
        try:
            know = await knowledge_service.for_dataset(db, ds)
        except Exception:                                    # noqa: BLE001
            # Never fatal. A context that loses its enrichment still answers
            # questions; one that raises answers nothing, and the enrichment is
            # the part most likely to meet a half-migrated database.
            logger.warning("could not resolve knowledge for dataset %s", ds.id,
                        exc_info=True)
            continue

        if know.object.description and not info.description:
            info.description = know.object.description
        info.is_canonical = know.object.is_canonical
        for name, entry in know.columns.items():
            if name not in info.columns:
                continue
            if entry.enum_labels:
                info.enum_labels[name] = entry.enum_labels
            if entry.description:
                info.descriptions[name] = entry.description

        # The entity behind this dataset, if the catalog named one. Its grain
        # ("one row per completed order") is the fact that most often stops a
        # model double-counting, and dataset mode has never had it.
        if know.object.grain or know.object.business_name:
            already = {e.name for e in ctx.entities}
            ename = know.object.business_name or tname
            if ename not in already:
                ctx.entities.append(EntityInfo(
                    name=ename, business_name=know.object.business_name,
                    grain=know.object.grain, description=know.object.description,
                    primary_object=tname))

        # T3's terms, which `load_dataset_context` used to leave empty by
        # construction -- the comment on SchemaContext.glossary said as much.
        # Org-wide terms apply to any dataset; a source's terms apply to the
        # datasets built from it.
        have = {(g.term or "").casefold() for g in ctx.glossary}
        for g in know.glossary:
            if (g.term or "").casefold() in have:
                continue
            have.add((g.term or "").casefold())
            ctx.glossary.append(GlossaryInfo(
                term=g.term, definition=g.definition,
                synonyms=list(g.synonyms or []),
                maps_to_object=g.maps_to_object, maps_to_column=g.maps_to_column))

    rels = (await db.execute(select(Relationship).where(
        Relationship.org_id == org_id,
        Relationship.from_dataset_id.in_(list(name_by_dataset_id)),
        Relationship.to_dataset_id.in_(list(name_by_dataset_id)),
        Relationship.source.in_([store.CONFIRMED, store.DECLARED]),
    ))).scalars().all()
    for r in rels:
        ft = name_by_dataset_id.get(r.from_dataset_id)
        tt = name_by_dataset_id.get(r.to_dataset_id)
        if ft and tt:
            ctx.joins.append(JoinInfo(ft, r.from_column, tt, r.to_column, r.source))
    return ctx
