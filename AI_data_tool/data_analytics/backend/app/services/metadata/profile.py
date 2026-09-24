"""Stage 2 — column statistics.

ARCHITECTURE.md principle 2: read the engine's own statistics before computing
your own. `pg_stats` answers in milliseconds what a full scan answers in
minutes, and the metadata plane runs nightly across every table of every
connected source — the difference between those two costs is the difference
between a feature and an incident.

Three paths, chosen by capability:

  postgresql family   pg_stats. One query per table, no scan. exact=False.
  other SQL families  one aggregate query per table.            exact=True.
  import-mode         computed from the cached frame.           exact=True.

WHAT `exact` IS FOR
--------------------
Postgres statistics are estimates sampled by ANALYZE; an aggregate is a
measurement. Both are useful and they are NOT interchangeable, so every row
records which it is. Deciding "is this a dimension or a measure?" is fine on an
estimate. Showing a user "1,204 distinct customers" as fact is not. Callers
branch on the flag; this module's only job is to set it honestly.

WHY top_k MATTERS MORE THAN THE REST
-------------------------------------
The doc calls it the highest-value statistic, and the reason is concrete:
knowing that `status` holds ('active','churned') and not ('A','C') is what stops
a generated query inventing WHERE values. Everything else here describes shape;
top_k describes content.
"""
from __future__ import annotations

import math

#: Above this many distinct values a column is not an enumeration, and the
#: GROUP BY needed to enumerate it stops being cheap. ARCHITECTURE.md stage 2:
#: "Always compute top_k where distinct_count < 100."
TOP_K_MAX_DISTINCT = 100

#: Hard cap on stored entries, so a column that sneaks past the threshold cannot
#: write an unbounded JSON blob into the catalog.
TOP_K_LIMIT = 100

#: Identifier quoting per SQL family. Column names arrive from a source catalog,
#: which is not a trusted input — a table can legally be created with a quote in
#: a column name, and unquoted `order` is a syntax error before it is anything else.
_QUOTES = {
    "postgresql": ('"', '"'),
    "oracle": ('"', '"'),
    "sqlite": ('"', '"'),
    "mysql": ("`", "`"),
    "sqlserver": ("[", "]"),
}


def normalize_n_distinct(n_distinct, row_count: int | None) -> int | None:
    """Turn pg_stats.n_distinct into an absolute count.

    Postgres encodes three different meanings in one float:

        > 0   an absolute count of distinct values
        < 0   the NEGATIVE FRACTION of rows that are distinct: -0.5 on a
              million rows means 500,000. -1 means every row is unique, which
              is how an undeclared candidate key announces itself.
        = 0   unknown — ANALYZE has never run on this column.

    Taking a negative value at face value yields "-0.5 distinct values" and
    quietly corrupts every dimension-vs-measure decision downstream, which is
    why this conversion is a named, tested function rather than an inline cast.
    """
    if n_distinct is None:
        return None
    value = float(n_distinct)

    if value == 0:
        # Unknown, not zero. Reporting 0 would make the column look empty.
        return None
    if value > 0:
        return int(value)

    # Negative: a fraction of the row count, which we therefore need.
    if not row_count:
        return None
    return min(row_count, int(round(abs(value) * row_count)))


def parse_pg_array(literal) -> list[str | None]:
    """Parse a PostgreSQL array literal such as ``{active,churned,"Cairo, EG"}``.

    This is NOT JSON — json.loads cannot read it, and eval must never see it.
    The rules that matter: elements are comma-separated; an element may be
    double-quoted, in which case it may contain commas and backslash-escaped
    quotes; and a bare (unquoted) NULL is the SQL null, while a quoted "NULL" is
    the four-character string.
    """
    if literal is None:
        return []
    # Some drivers decode anyarray into a real list before we see it.
    if isinstance(literal, (list, tuple)):
        return list(literal)

    text = str(literal).strip()
    if not text or text == "{}":
        return []
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    if not text:
        return []

    out: list[str | None] = []
    buf: list[str] = []
    in_quotes = False
    escaped = False
    quoted_element = False

    for ch in text:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            in_quotes = not in_quotes
            quoted_element = True
        elif ch == "," and not in_quotes:
            out.append(_finish_element(buf, quoted_element))
            buf, quoted_element = [], False
        else:
            buf.append(ch)

    out.append(_finish_element(buf, quoted_element))
    return out


def _finish_element(buf: list[str], quoted: bool) -> str | None:
    """A bare NULL is the SQL null; a quoted "NULL" is the literal string."""
    text = "".join(buf)
    if not quoted and text.strip().upper() == "NULL":
        return None
    return text if quoted else text.strip()


def build_top_k(values, freqs, row_count: int | None) -> list[dict] | None:
    """Pair most-common values with their frequencies, most common first.

    Returns None rather than [] when there is nothing to report: None means
    "not computed", whereas [] would assert the column has no common values,
    which is a different and false statement.
    """
    if not values or not freqs:
        return None

    values = list(values)
    freqs = list(freqs)
    # pg_stats can return the two arrays at different lengths. A stats read must
    # never take down a sync, so truncate to the shorter rather than raising.
    pairs = list(zip(values, freqs))
    if not pairs:
        return None

    pairs.sort(key=lambda vf: vf[1], reverse=True)

    out = []
    for value, freq in pairs[:TOP_K_LIMIT]:
        ratio = round(float(freq), 6)
        out.append({
            "value": None if value is None else str(value),
            "count": int(round(ratio * row_count)) if row_count else None,
            "ratio": ratio,
        })
    return out or None


def should_compute_top_k(distinct_count: int | None) -> bool:
    """Whether enumerating this column is both worthwhile and bounded.

    Unknown cardinality is a no: without a count there is no guarantee the
    GROUP BY is bounded, and an unbounded scan against a customer's production
    table is precisely what the metadata plane exists to avoid.
    """
    if distinct_count is None:
        return False
    return 0 <= distinct_count < TOP_K_MAX_DISTINCT


def from_pg_stats_row(row: dict, row_count: int | None) -> dict:
    """Convert one pg_stats row into a stats dict ready for the store.

    Tolerates a row with everything missing: a column ANALYZE has never touched
    is normal, and absent statistics must not fail the stage.
    """
    n_distinct = normalize_n_distinct(row.get("n_distinct"), row_count)
    values = parse_pg_array(row.get("most_common_vals"))
    freqs = row.get("most_common_freqs") or []

    null_frac = row.get("null_frac")
    avg_width = row.get("avg_width")

    return {
        "null_ratio": float(null_frac) if null_frac is not None else None,
        "distinct_count": n_distinct,
        "top_k": build_top_k(values, freqs, row_count),
        "min_value": None,      # pg_stats histogram bounds are not exact extremes
        "max_value": None,
        "avg_width": int(avg_width) if avg_width is not None else None,
        # ANALYZE samples; it does not count. Never claim otherwise.
        "exact": False,
    }


def profile_frame(df) -> dict[str, dict]:
    """Profile an in-memory frame — the import-mode path.

    Everything here is computed over every row, so `exact` is True throughout.
    """
    stats: dict[str, dict] = {}
    total = len(df)

    for name in df.columns:
        series = df[name]
        non_null = series.dropna()
        present = len(non_null)

        # 0/0 is unknown, not zero: an empty column has no null RATIO.
        null_ratio = round((total - present) / total, 6) if total else None
        distinct = int(non_null.nunique()) if present else 0

        top_k = None
        if present and should_compute_top_k(distinct):
            counts = non_null.value_counts().head(TOP_K_LIMIT)
            top_k = [
                {
                    "value": str(value),
                    "count": int(count),
                    # Ratio of PRESENT values, not of all rows — otherwise the
                    # ratios of a nullable column silently fail to sum to 1.
                    "ratio": round(int(count) / present, 6),
                }
                for value, count in counts.items()
            ]

        stats[name] = {
            "null_ratio": null_ratio,
            "distinct_count": distinct,
            "top_k": top_k,
            "min_value": _as_text(non_null.min()) if present else None,
            "max_value": _as_text(non_null.max()) if present else None,
            "avg_width": _avg_width(non_null) if present else None,
            "exact": True,
        }

    return stats


def _as_text(value) -> str | None:
    """min/max are TEXT columns so a date, a decimal and an integer all round
    trip without the storage layer choosing a lossy type for them."""
    if value is None:
        return None
    try:
        if hasattr(value, "isoformat"):
            return value.isoformat()
    except Exception:
        pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return str(value)


def _avg_width(series) -> int | None:
    """Mean byte width, matching what pg_stats reports, so the two paths produce
    a comparable number."""
    try:
        if series.dtype == object:
            widths = series.astype(str).str.len()
            return int(round(float(widths.mean())))
        return int(series.dtype.itemsize)
    except Exception:
        return None


def quote_identifier(name: str, family: str) -> str:
    """Quote a table or column name for one SQL family.

    Rejects a name containing its own closing quote rather than escaping it.
    These names come from a source catalog — an untrusted input, since a table
    can legally be created with a quote in a column name — and this SQL is built
    by concatenation because identifiers cannot be bound as parameters. Refusing
    the pathological case is the safe half of that trade; the column simply goes
    unprofiled.
    """
    open_q, close_q = _QUOTES.get(family, ('"', '"'))
    if close_q in name or "\\" in name or "\x00" in name:
        raise ValueError(f"unsafe identifier for {family}: {name!r}")
    return f"{open_q}{name}{close_q}"


def build_profile_sql(table: str, columns: list[str], *, family: str) -> str:
    """One aggregate query covering every column — the non-Postgres path.

    A single query rather than one per column: N round trips against a remote
    warehouse is the slow part, not the aggregation itself.
    """
    qt = quote_identifier(table, family)
    parts = ["count(*) AS row_count"]
    for name in columns:
        qc = quote_identifier(name, family)
        safe = name.replace('"', "").replace("`", "")
        parts.append(f"count({qc}) AS present__{safe}")
        parts.append(f"count(distinct {qc}) AS distinct__{safe}")
        parts.append(f"min({qc}) AS min__{safe}")
        parts.append(f"max({qc}) AS max__{safe}")
    return f"SELECT {', '.join(parts)} FROM {qt}"


def build_top_k_sql(table: str, column: str, *, family: str) -> str:
    """Enumerate a low-cardinality column's values.

    Bounded by LIMIT even though the caller has already checked the distinct
    count: that count may be an estimate, and an estimate that is wrong must not
    turn into an unbounded result set.
    """
    qt = quote_identifier(table, family)
    qc = quote_identifier(column, family)
    return (
        f"SELECT {qc} AS value, count(*) AS freq "
        f"FROM {qt} GROUP BY {qc} ORDER BY freq DESC LIMIT {TOP_K_LIMIT}"
    )
