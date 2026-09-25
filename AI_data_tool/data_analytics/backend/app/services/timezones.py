"""One timezone policy for every stored instant.

Layer 2 (ingestion). E07. Timestamps that carry a UTC offset arrived three
ways and were stored as they came:

- A Postgres `timestamptz` column comes back tz-aware. Across a daylight-saving
  change (Egypt has one again since 2023) it holds TWO offsets, and pandas then
  keeps it as a column of objects: typed "datetime", yet every `.dt` on it
  fails. The dataset looked ready and no date chart on it could be drawn.
- A CSV with mixed offsets ("...+02:00", "...+03:00", "...Z"): the same.
- A CSV with ONE offset worked, but only by accident of the reader: pandas kept
  the local wall time while DuckDB pushdown converted the same text to UTC, so
  the two paths could put the same row on different days.

The policy: at ingest, any column of offset-carrying instants is converted to
ONE reference zone (`settings.data_timezone`, UTC unless configured) and
stored as plain wall-clock time in that zone -- no offsets on disk, so every
reader agrees. A timestamp with no offset is left exactly as it was: it
already IS wall-clock time, and no zone can be invented for it.
"""
from __future__ import annotations

import re

import pandas as pd

_OFFSET_RE = re.compile(r"\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?\s*(Z|[+-]\d{2}(:?\d{2})?)$")
_SAMPLE = 200


def reference_zone() -> str:
    from ..core.config import settings
    return (getattr(settings, "data_timezone", "") or "UTC").strip() or "UTC"


def _has_offset(v) -> bool:
    if isinstance(v, str):
        return bool(_OFFSET_RE.search(v.strip()))
    tz = getattr(v, "tzinfo", None)
    return tz is not None


def _to_zone(v, zone: str):
    t = pd.Timestamp(v)
    if t.tzinfo is not None:
        t = t.tz_convert(zone).tz_localize(None)
    return t


def _normalize_column(s: pd.Series, zone: str) -> pd.Series | None:
    if isinstance(s.dtype, pd.DatetimeTZDtype):
        return s.dt.tz_convert(zone).dt.tz_localize(None)
    if s.dtype != object:
        return None
    values = s.dropna()
    if values.empty:
        return None
    sample = values.head(_SAMPLE)
    if not any(_has_offset(v) for v in sample):
        return None
    if all(isinstance(v, str) for v in sample) and all(_has_offset(v) for v in values):
        # Every value names its offset: one vectorised parse through UTC.
        try:
            out = pd.to_datetime(s, utc=True, format="ISO8601")
        except (ValueError, TypeError):
            try:
                out = pd.to_datetime(s, utc=True, format="mixed")
            except (ValueError, TypeError):
                return None
        return out.dt.tz_convert(zone).dt.tz_localize(None)
    # Offsets beside plain values (an incremental refresh appending tz-aware
    # rows to naive stored ones): a plain value is already wall-clock time in
    # the reference zone and stays as it is.
    try:
        return pd.to_datetime(s.map(lambda v: v if pd.isna(v) else _to_zone(v, zone)))
    except (ValueError, TypeError):
        return None


def normalize_instants(df: pd.DataFrame, zone: str | None = None) -> list[str]:
    """Convert every offset-carrying column of `df` IN PLACE to naive
    wall-clock time in `zone` (default: the reference zone). Returns the
    names of the columns converted. A column that cannot be parsed whole is
    left untouched: a wrong date is worse than an unconverted one."""
    zone = zone or reference_zone()
    done = []
    for name in list(df.columns):
        col = df[name]
        if isinstance(col, pd.DataFrame):      # duplicate names are refused elsewhere
            continue
        out = _normalize_column(col, zone)
        if out is not None:
            df[name] = out
            done.append(str(name))
    return done
