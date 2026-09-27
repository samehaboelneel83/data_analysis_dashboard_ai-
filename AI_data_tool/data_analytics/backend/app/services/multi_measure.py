"""Several measures on one axis: revenue AND cost per region, as one chart.

A bar, line or area widget keeps its first measure in `measure` and any more
in `extra_measures`. The router resolves each measure through the ordinary
single-measure path -- the same engines, filters, row and column security,
parameters and caching -- and this module merges the results into the
`crosstab` shape a split series already has (one column per series), which
every chart renderer already draws as grouped or stacked series.

Resolving per measure rather than teaching three engines a list keeps one
code path per engine: a second implementation of grouping would be a second
place for the numbers to disagree.
"""
from __future__ import annotations

#: The widget types whose value axis takes more than one measure. MIRRORS
#: `MULTI_MEASURE_WIDGETS` in frontend/src/types/report.ts (pinned by
#: tests/test_frontend_constant_mirrors.py).
MULTI_MEASURE_WIDGETS = frozenset({"bar", "line", "area"})


def measure_list(widget_type: str, config: dict | None) -> list[str] | None:
    """The measures to draw, when there is more than one; else None.

    None also when a series split (`dimension2`) is set: a split already fills
    the series slot, and save refuses the combination -- a stored one draws
    as the split, its first measure only, rather than failing to render."""
    cfg = config or {}
    extra = cfg.get("extra_measures")
    if widget_type not in MULTI_MEASURE_WIDGETS or not isinstance(extra, list) or cfg.get("dimension2"):
        return None
    names = [m for m in [cfg.get("measure"), *extra] if isinstance(m, str) and m]
    names = list(dict.fromkeys(names))
    return names if len(names) >= 2 else None


def merge_measure_series(parts: list[dict], measures: list[str]) -> dict:
    """One `crosstab` from one single-measure result per measure.

    Categories keep the FIRST measure's order (its sort, ranking and Top N
    decide the axis); a category only a later measure has is appended. A
    category a measure has no value for is None, not 0 -- nothing was
    measured there. Anything that is not a series (an error, an empty result,
    a refusal) is returned as it is: the first measure that cannot draw says
    why for the whole chart."""
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "series":
            return part
    order: list = []
    seen: set = set()
    values: list[dict] = []
    for part in parts:
        by_name = {}
        for row in part.get("rows") or []:
            name = row.get("name")
            by_name[name] = row.get("value")
            if name not in seen:
                seen.add(name)
                order.append(name)
        values.append(by_name)
    first = parts[0]
    dimension = first.get("dimension")
    return {
        "type": "crosstab",
        "dimension": dimension,
        "measures": measures,
        "aggregation": first.get("aggregation"),
        # The last column is the row total in a split; summing different
        # measures (revenue + cost) means nothing, so it is left empty.
        "columns": [dimension or "name", *measures, "__total__"],
        "rows": [[name, *(v.get(name) for v in values), None] for name in order],
        "total": len(order),
        "rows_scanned": first.get("rows_scanned"),
        **({"truncation": first["truncation"]} if "truncation" in first else {}),
        **({"missing_category": first["missing_category"]} if "missing_category" in first else {}),
    }
