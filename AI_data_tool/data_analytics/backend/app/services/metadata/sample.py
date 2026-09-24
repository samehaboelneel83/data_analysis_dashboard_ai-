"""Stage 3 — deciding how to take a sample, and building the query that does it.

There is no single right sampling method, because the binding constraint differs
by source:

  tablesample   Nearly free — the engine reads a fraction of physical pages
                rather than the table. Page-biased (rows that sit together are
                sampled together), which ARCHITECTURE.md explicitly accepts:
                for learning structure, cheap and slightly biased beats
                expensive and uniform. Physical tables only.

  head          A bounded read, no ordering: the engine stops at the LIMIT.
                O(n) rather than O(table), and the default for anything whose
                size is unknown — views most of all.

  random        Uniform, and a full sort of the table. Reserved for tables
                known to be small, because ORDER BY random() cannot stop early:
                every row is produced, randomised and sorted before the LIMIT
                applies.

  stratified    Samples every value of a low-cardinality column. The only way to
                SEE a rare category at all — and rare categories are exactly what
                the semantic layer needs, because a status appearing in 0.2% of
                rows is still a status the agent must know exists. A uniform
                1000-row sample of a million-row table will usually miss it.

  reservoir     Import-mode datasets, sampled from the already-parsed frame.

Every generated query is row-bounded. An unbounded sample against a customer's
production table is the precise failure this whole plane exists to prevent.
"""
from __future__ import annotations

from .profile import quote_identifier

#: Above this many distinct values, stratifying produces more groups than the
#: sample has room for and degenerates into an expensive ordinary sample.
STRATIFY_MAX_DISTINCT = 50

#: A column that is mostly empty stratifies into one big NULL group plus noise.
STRATIFY_MAX_NULL_RATIO = 0.5

#: Families whose TABLESAMPLE is worth using on a physical table.
_TABLESAMPLE_FAMILIES = {"postgresql", "sqlserver"}

#: Each dialect's random function, and how it spells "give me N rows".
_RANDOM_FN = {
    "postgresql": "random()",
    "sqlite": "random()",
    "mysql": "rand()",
    "sqlserver": "newid()",
    "oracle": "dbms_random.value",
}


#: Below this many rows, reading the whole table is cheaper and far more
#: reliable than sampling it. TABLESAMPLE works in PAGES, and a small table is
#: one page — any percentage under 100 is a coin flip that usually loses.
TABLESAMPLE_MIN_ROWS = 50_000

#: Above this many rows, sorting to randomise costs more than the uniformity is
#: worth. ARCHITECTURE.md already accepts biased sampling for structure
#: learning ("cheap and slightly biased beats expensive and uniform"); this is
#: the same trade applied to the fallback path.
RANDOM_MAX_ROWS = 100_000


def choose_strategy(
    *, family: str | None, kind: str = "table",
    stratify_column: str | None = None, is_import: bool = False,
    row_count: int | None = None,
) -> str:
    """Pick a sampling strategy from the source's capabilities and shape.

    Two hard-won rules, both measured against a real 82-object source:

    TABLESAMPLE only for a table known to be LARGE. The percentage is derived
    from the row count, so without one there is nothing to size it against, and
    the fallback guess fails precisely on small tables: a 40-row table sampled
    at 1% returns nothing at all, which is not a smaller sample but no sample.

    ORDER BY random() only for a table known to be SMALL. It cannot stop at the
    LIMIT — every row must be produced, randomised and sorted. On a view over
    million-row tables that measured nine and a half minutes for one object.
    Anything of unknown or unbounded size gets `head`: a plain bounded read that
    stops as soon as it has enough rows.
    """
    if is_import:
        return "reservoir"
    # Seeing every category beats sampling cheaply; this check comes first.
    if stratify_column:
        return "stratified"
    if (kind == "table" and family in _TABLESAMPLE_FAMILIES
            and row_count and row_count >= TABLESAMPLE_MIN_ROWS):
        return "tablesample"
    # ORDER BY random() cannot stop at the LIMIT — it must produce every row,
    # randomise it and sort. Affordable only on a table we KNOW is small.
    # Everything else, views above all, gets a plain bounded read.
    if row_count and row_count <= RANDOM_MAX_ROWS and kind == "table":
        return "random"
    return "head"


def pick_stratify_column(column_stats: dict[str, dict]) -> str | None:
    """Choose a column worth stratifying on, or None.

    Wants a genuine low-cardinality dimension: more than one value (one group is
    just an ordinary sample), few enough groups to fit, and not mostly null.
    Ties break toward the smallest cardinality, which gives the most rows per
    group and therefore the best chance of seeing each value's typical content.
    """
    best: tuple[int, str] | None = None
    for name, stats in (column_stats or {}).items():
        distinct = stats.get("distinct_count")
        null_ratio = stats.get("null_ratio") or 0.0
        if distinct is None or not (1 < distinct <= STRATIFY_MAX_DISTINCT):
            continue
        if null_ratio > STRATIFY_MAX_NULL_RATIO:
            continue
        if best is None or distinct < best[0]:
            best = (distinct, name)
    return best[1] if best else None


def _percentage_for(n: int, row_count: int | None) -> float:
    """The TABLESAMPLE percentage needed to yield roughly `n` rows.

    A fixed 1% is wrong in both directions: on a billion-row table it reads ten
    million rows to keep a thousand, and on a small table it returns almost
    nothing. So the fraction tracks the row count, oversampled 3x because
    page-level sampling is lumpy and undershooting means a second query.

    Floored above zero: a percentage that rounds to 0 returns no rows, which
    would look like an empty table and wrongly trip the deprecation heuristic in
    Stage 5.
    """
    if not row_count or row_count <= 0:
        return 1.0
    pct = (n / row_count) * 100.0 * 3.0
    return max(0.001, min(100.0, round(pct, 4)))


def build_sample_sql(
    table: str, *, family: str, strategy: str, n: int,
    row_count: int | None = None, stratify_column: str | None = None,
) -> str:
    """Build the sampling query for one table.

    Identifiers are quoted, and a name that cannot be quoted safely raises —
    these come from a customer's catalog, which is not a trusted input.
    """
    qt = quote_identifier(table, family)

    if strategy == "tablesample" and family in _TABLESAMPLE_FAMILIES:
        pct = _percentage_for(n, row_count)
        if family == "sqlserver":
            return f"SELECT TOP {n} * FROM {qt} TABLESAMPLE ({pct} PERCENT)"
        return f"SELECT * FROM {qt} TABLESAMPLE SYSTEM ({pct}) LIMIT {n}"

    if strategy == "stratified" and stratify_column:
        qc = quote_identifier(stratify_column, family)
        rnd = _RANDOM_FN.get(family, "random()")
        # Take an equal slice of each group, so a value holding 0.2% of the rows
        # is represented as visibly as one holding 60%.
        per_group = max(1, n // STRATIFY_MAX_DISTINCT)
        inner = (
            f"SELECT *, row_number() OVER (PARTITION BY {qc} ORDER BY {rnd}) AS _rn "
            f"FROM {qt}"
        )
        return _limit(
            f"SELECT * FROM ({inner}) _s WHERE _rn <= {per_group}", n, family
        )

    if strategy == "random":
        rnd = _RANDOM_FN.get(family, "random()")
        return _limit(f"SELECT * FROM {qt} ORDER BY {rnd}", n, family)

    # `head`: a bounded read with no ordering at all. The engine stops as soon
    # as it has n rows, so cost is O(n) rather than O(table). Biased toward
    # whatever the engine returns first, which for learning structure is a
    # trade ARCHITECTURE.md already makes for TABLESAMPLE.
    return _limit(f"SELECT * FROM {qt}", n, family)


def _limit(sql: str, n: int, family: str) -> str:
    """Row-cap a query in the dialect's own spelling.

    SQL Server puts TOP next to SELECT rather than at the end, so it is handled
    by rewriting the leading SELECT instead of appending.
    """
    if family == "sqlserver":
        return sql.replace("SELECT ", f"SELECT TOP {n} ", 1)
    if family == "oracle":
        return f"{sql} FETCH FIRST {n} ROWS ONLY"
    return f"{sql} LIMIT {n}"


def reservoir_sample_frame(df, n: int) -> list[dict]:
    """Sample an already-parsed frame — the import-mode path.

    Deterministic by a fixed seed, not by chance: two syncs of an unchanged table
    must cache the same rows, or every overlap ratio in Stage 4 would drift
    between runs for no real reason, and a relationship could cross the
    confidence threshold in one direction on Monday and back on Tuesday.
    """
    if df is None or len(df) == 0:
        return []
    if len(df) <= n:
        sampled = df
    else:
        sampled = df.sample(n=n, random_state=1618).sort_index()
    return sampled.to_dict(orient="records")


def statement_timeout_sql(family: str, seconds: int) -> str | None:
    """A session-scoped statement deadline, in the dialect's own spelling.

    Returns None where the family has no equivalent; the caller then relies on
    the driver's own timeout, or on nothing. Better to sample without a deadline
    than to refuse to sample at all — but every family that CAN be bounded is.

    Postgres and MySQL set it as a session variable. SQL Server expresses the
    same idea as a client-side query timeout rather than a server setting, so it
    is handled by the driver instead.
    """
    ms = max(1000, int(seconds) * 1000)
    if family == "postgresql":
        return f"SET statement_timeout = {ms}"
    if family == "mysql":
        return f"SET SESSION max_execution_time = {ms}"
    return None
