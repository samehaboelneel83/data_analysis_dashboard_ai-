"""Compiling an aggregate dataset from a DirectQuery source.

An aggregate is a GROUP BY run where the data lives, on a schedule, so a
dashboard reads thousands of pre-summed rows instead of scanning millions.
This module turns an author's request -- a grain and some measures -- into
that SQL, and decides what it will not compile.

Two rules that are not negotiable:

  * Nothing user-supplied reaches the SQL as text. Grain and measure columns
    are validated against the source's real columns; aggregations against
    ALLOWED_AGGS; identifiers go through the same quoting DirectQuery uses.
  * Only additive aggregations. A widget on the aggregate will aggregate
    again, and only sum / count / min / max survive that at a coarser grain.
    `row_count` is always present so an average is sum / row_count.

The governance decision -- the grain must cover every column an RLS rule
reads, so the SOURCE's rules can be applied to the aggregate at read time
without ever being copied -- is checked here (`rls_columns_outside_grain`)
and enforced by the router at creation and by the scheduler at every refresh.
"""
from __future__ import annotations

import re

from .direct_query import _base_query_sql, _quote
from .sql_expr import ExpressionTranslationError, expression_columns

ALLOWED_AGGS = frozenset({"sum", "count", "min", "max"})
ROW_COUNT = "row_count"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,120}$")


def _ident(name: str) -> str:
    # Upstream _quote validates names against an allowlist and never sees a quote;
    # aggregates' names come from the same allowlist, but escaping is added here as defence in depth.
    return _quote(str(name).replace('"', '""'))


class AggregateSpecError(ValueError):
    """The request cannot be compiled; the message says which part and why."""


def normalise_spec(spec: dict, known_columns: set[str]) -> dict:
    """Validate a spec and fill in measure names. Returns a new dict."""
    grain = [str(g) for g in (spec.get("grain") or [])]
    measures_in = spec.get("measures") or []
    if not grain:
        raise AggregateSpecError("an aggregate needs at least one grain column")
    if not measures_in:
        raise AggregateSpecError("an aggregate needs at least one measure")
    seen: set[str] = set()
    for g in grain:
        if g == ROW_COUNT:
            # row_count was reserved as a measure name but not, until now, as
            # a grain name: the compiled SQL would emit "row_count" twice,
            # and core.rls strips it from the denied-columns list
            # unconditionally, so a role denied that column on the source
            # would see it again here. Fail closed regardless of whether the
            # source happens to have a real column with this name.
            raise AggregateSpecError(f"{ROW_COUNT!r} is reserved and cannot be a grain column")
        if g not in known_columns:
            raise AggregateSpecError(f"grain column {g!r} is not a column of the source")
        if g in seen:
            raise AggregateSpecError(f"grain column {g!r} is listed twice")
        seen.add(g)
    measures: list[dict] = []
    names: set[str] = set(grain) | {ROW_COUNT}
    for m in measures_in:
        col = str(m.get("column") or "")
        agg = str(m.get("agg") or "").lower()
        if col not in known_columns:
            raise AggregateSpecError(f"measure column {col!r} is not a column of the source")
        if agg not in ALLOWED_AGGS:
            raise AggregateSpecError(
                f"aggregation {agg!r} is not allowed; only sum, count, min and max "
                "re-aggregate correctly at a coarser grain")
        name = str(m.get("name") or f"{col}_{agg}")
        if not _NAME.match(name):
            raise AggregateSpecError(f"measure name {name!r} is not a plain identifier")
        if name == ROW_COUNT:
            raise AggregateSpecError(f"{ROW_COUNT!r} is reserved; it is always included")
        if name in names:
            raise AggregateSpecError(f"output name {name!r} is used twice")
        names.add(name)
        measures.append({"column": col, "agg": agg, "name": name})
    return {"grain": grain, "measures": measures}


def compile_aggregate_sql(dataset, spec: dict) -> str:
    """The GROUP BY, over the source's base query with NO RLS predicate: the
    aggregate holds every row's contribution, and RLS is applied when it is
    read, on grain columns that are guaranteed to be there."""
    grain_sql = ", ".join(_ident(g) for g in spec["grain"])
    measure_sql = ", ".join(
        f'{m["agg"].upper()}({_ident(m["column"])}) AS {_ident(m["name"])}' for m in spec["measures"])
    base = _base_query_sql(dataset).strip().rstrip(";")
    return (f"SELECT {grain_sql}, {measure_sql}, COUNT(*) AS {_ident(ROW_COUNT)} "
            f"FROM ({base}) AS src GROUP BY {grain_sql}")


def rls_columns_outside_grain(rules, grain: list[str], known_columns: set[str]) -> list[tuple[int, str]]:
    """(role_id, column) for every RLS rule column the grain does not carry.

    Empty means the grain can govern the aggregate exactly as the source is
    governed. An untranslatable rule cannot be checked and is reported as
    `<untranslatable>` -- fail closed, never silently pass."""
    g = set(grain)
    bad: list[tuple[int, str]] = []
    for rule in rules:
        try:
            cols = expression_columns(rule.filter_expr, known_columns)
        except ExpressionTranslationError:
            bad.append((rule.role_id, "<untranslatable>"))
            continue
        for c in sorted(cols):
            if c not in g:
                bad.append((rule.role_id, c))
    return bad


def uncovered_message(bad: list[tuple[int, str]], role_names: dict[int, str], *, when: str = "create") -> str:
    """The sentence explaining why a grain fails to cover the source's RLS --
    shared by the create-time refusal (routers/datasets.py) and the
    refresh-time one (refresh_scheduler.py) so an operator sees the same
    wording either way, and a service never has to import a router to say it.

    `when="create"` (the default) refuses outright, before anything is built.
    `when="refresh"` reports a refresh that ran but chose not to rewrite, so
    the aggregate keeps serving its last good data instead of one that can no
    longer be governed."""
    role_id, col = bad[0]
    who = role_names.get(role_id, f"role {role_id}")
    prefix = "Not refreshed: " if when == "refresh" else ""
    if col == "<untranslatable>":
        return (f"{prefix}The row-level security rule for role '{who}' cannot be checked "
                "against a grain; fix or remove that rule first.")
    if when == "refresh":
        return (f"Not refreshed: the row-level security rule for role '{who}' reads "
               f"'{col}', which this aggregate's grain does not include. Rebuild the "
               "aggregate with that column in its grain, or change the rule.")
    return (f"The grain must include '{col}': the row-level security rule for "
            f"role '{who}' reads it, and an aggregate without it could not be "
            "governed the way the source is.")


DEFAULT_FILTER_STALENESS_MESSAGE = (
    "Not refreshed: the source has a report-level filter expression, which an "
    "aggregate would ignore. Remove the filter expression on the source, then "
    "rebuild this aggregate.")

QUERY_CHANGED_STALENESS_MESSAGE = (
    "Not refreshed: the source's query changed since this aggregate was "
    "built; rebuild the aggregate to pick it up.")


def aggregate_staleness(source, agg) -> str | None:
    """Two cheap checks against the SOURCE that make a scheduled refresh
    refuse to rewrite an aggregate's file -- shared by `refresh_one` (which
    acts on them) and `list_aggregates` (which only REPORTS them, for the
    aggregates the scheduler's tick never reaches because they carry no
    `refresh_interval_minutes` and so are never selected by its query). One
    helper for both means the wording, and the order the checks run in,
    cannot drift between what the tick would say and what the tab shows for
    an aggregate the tick never looks at.

    Deliberately NOT the RLS-grain check `refresh_one` also makes: that one
    needs the rules query, which a pure, DB-free helper does not run.

    None means neither condition holds. `source is None` (the source row is
    gone, or has not been resolved yet) also reports nothing wrong -- the
    caller decides what a missing source means."""
    if source is None:
        return None
    if source.default_filter_expr:
        return DEFAULT_FILTER_STALENESS_MESSAGE
    if agg.aggregate_spec and compile_aggregate_sql(source, agg.aggregate_spec) != agg.source_query:
        return QUERY_CHANGED_STALENESS_MESSAGE
    return None


def derived_measure_names(spec: dict, source_column: str) -> list[str]:
    """The aggregate's output columns built from one source column -- what a
    column rule on the source must also deny on the aggregate."""
    return [m["name"] for m in spec.get("measures") or [] if m.get("column") == source_column]
