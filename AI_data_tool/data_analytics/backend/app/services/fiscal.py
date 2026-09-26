"""Fiscal years and quarters for time axes (E10, calendar choices).

An organisation whose year runs July to June reads "FY2025/26", not 2025 and
2026 half each. The month the fiscal year starts in is the org's setting
(`Organization.fiscal_year_start_month`); a widget may name its own
(`fiscal_start_month` in its config).

Labels sort as text, which is how every chart orders its categories:

- start in January: the fiscal year is the calendar year -> `FY2025`,
  `FY2025-Q1`;
- any other month: the year is named by both calendar years it spans ->
  `FY2025/26`, `FY2025/26-Q1` -- no convention to guess about whether
  "FY2026" means the year that starts or the one that ends in 2026.

Inside the widget pipeline the start month rides on the granularity itself
(`fiscal_year@7`), put there by `with_fiscal_start` before the config reaches
the shapers: every place that buckets dates -- the dimension, a drill filter
on a clicked bucket, a lattice -- then agrees without each being told.
"""
from __future__ import annotations

import pandas as pd

FISCAL_GRANULARITIES = ("fiscal_year", "fiscal_quarter")


def _start(value) -> int:
    try:
        m = int(value)
    except (TypeError, ValueError):
        return 1
    return m if 1 <= m <= 12 else 1


def parse(granularity: str) -> tuple[str, int] | None:
    """`fiscal_quarter@7` -> ("fiscal_quarter", 7); not fiscal -> None."""
    base, _, month = str(granularity or "").lower().partition("@")
    if base not in FISCAL_GRANULARITIES:
        return None
    return base, _start(month or 1)


def fiscal_label(dt: pd.Series, granularity: str, start_month: int) -> pd.Series:
    """The fiscal bucket of each date; missing dates stay missing."""
    start_month = _start(start_month)
    # Months since the fiscal year began: shifting every date back by
    # (start - 1) months lands it in the calendar year its fiscal year began.
    shifted_month = (dt.dt.month - start_month) % 12          # 0..11 within the fiscal year
    first_year = dt.dt.year - (dt.dt.month < start_month).astype("Int64")
    if start_month == 1:
        name = "FY" + first_year.astype("Int64").astype(str)
    else:
        second = (first_year + 1) % 100
        name = "FY" + first_year.astype("Int64").astype(str) + "/" + \
            second.astype("Int64").astype(str).str.zfill(2)
    if granularity == "fiscal_quarter":
        name = name + "-Q" + (shifted_month // 3 + 1).astype("Int64").astype(str)
    return name.where(dt.notna())


def with_fiscal_start(config: dict, org_start_month: int | None) -> dict:
    """The config with each fiscal granularity carrying its start month.

    The widget's own `fiscal_start_month` wins; otherwise the org's. Returns
    the same dict when nothing is fiscal, a shallow copy otherwise."""
    if not isinstance(config, dict):
        return config
    month = _start(config.get("fiscal_start_month") or org_start_month or 1)

    def tag(g):
        p = parse(g) if isinstance(g, str) else None
        return f"{p[0]}@{month}" if p and "@" not in g else g

    gran = config.get("dimension_granularity")
    filters = config.get("filters")
    new_gran = tag(gran)
    new_filters = filters
    if isinstance(filters, list) and any(isinstance(f, dict) and parse(f.get("granularity") or "")
                                         for f in filters):
        new_filters = [{**f, "granularity": tag(f["granularity"])}
                       if isinstance(f, dict) and parse(f.get("granularity") or "") else f
                       for f in filters]
    if new_gran == gran and new_filters is filters:
        return config
    out = dict(config)
    if gran is not None:
        out["dimension_granularity"] = new_gran
    if filters is not None:
        out["filters"] = new_filters
    return out
