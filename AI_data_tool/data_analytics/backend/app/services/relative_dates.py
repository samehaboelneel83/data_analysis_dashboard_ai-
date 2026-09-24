"""Relative date filters: "last 30 days", "month to date", "rolling 12 months".

SAS Visual Analytics has no relative dates at all, and where tools do have them
they anchor silently to *today* -- so a dataset refreshed on the 14th shows a
"this month" that is half empty and reads as a sales collapse (our plan's SAS
defects #7 and #8). Two rules here answer both:

  * The anchor is an explicit, labelled choice: ``today`` or ``data_max`` (the
    latest date in the column, over the rows this reader may see). Every
    resolved window travels back with the result as a note that names the
    anchor and its date, so the reader is never guessing what "last" means.
  * A window that reaches past the anchor -- "this month" on the 14th -- is
    flagged ``incomplete``. The same test marks the last bucket of a time axis
    whose period the data has not finished (``partial_period``).

A filter is ``{"column": c, "op": "relative", "value": spec}`` with spec::

    mode    last | rolling | to_date | this | previous
    unit    day | week | month | quarter | year
    n       periods (last / rolling), 1..1000, default 1
    anchor  today | data_max (default today)
    include_current   last only: count the current, unfinished period as one of n

It resolves to ``op: "date_range"`` with ``[start, end)`` ISO dates, which the
pandas filter applies over the column coerced to dates (text dates included).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

UNITS = ("day", "week", "month", "quarter", "year")
MODES = ("last", "rolling", "to_date", "this", "previous")
ANCHORS = ("today", "data_max")
MAX_N = 1000

_UNIT_WORD = {"day": "day", "week": "week", "month": "month", "quarter": "quarter", "year": "year"}
_TO_DATE = {"day": "Today", "week": "Week to date", "month": "Month to date",
            "quarter": "Quarter to date", "year": "Year to date"}


class RelativeDateError(ValueError):
    """A relative filter spec that cannot be resolved; the message is user-facing."""


def validate_spec(spec) -> dict:
    """Normalise a spec or raise RelativeDateError with a sentence saying why."""
    if not isinstance(spec, dict):
        raise RelativeDateError("A relative date filter needs a period, e.g. last 30 days")
    mode = str(spec.get("mode") or "last")
    unit = str(spec.get("unit") or "day")
    anchor = str(spec.get("anchor") or "today")
    if mode not in MODES:
        raise RelativeDateError(f"Unknown relative period '{mode}' (use one of {', '.join(MODES)})")
    if unit not in UNITS:
        raise RelativeDateError(f"Unknown date unit '{unit}' (use one of {', '.join(UNITS)})")
    if anchor not in ANCHORS:
        raise RelativeDateError("Anchor must be 'today' or 'data_max' (the latest date in the data)")
    try:
        raw_n = spec.get("n")
        n = 1 if raw_n is None or raw_n == "" else int(raw_n)
    except (TypeError, ValueError):
        raise RelativeDateError("The number of periods must be a whole number")
    if not 1 <= n <= MAX_N:
        raise RelativeDateError(f"The number of periods must be between 1 and {MAX_N}")
    return {"mode": mode, "unit": unit, "n": n, "anchor": anchor,
            "include_current": bool(spec.get("include_current"))}


def period_start(d: date, unit: str) -> date:
    if unit == "day":
        return d
    if unit == "week":  # ISO week: Monday
        return d - timedelta(days=d.weekday())
    if unit == "month":
        return d.replace(day=1)
    if unit == "quarter":
        return d.replace(month=(d.month - 1) // 3 * 3 + 1, day=1)
    if unit == "year":
        return d.replace(month=1, day=1)
    raise RelativeDateError(f"Unknown date unit '{unit}'")


def add_periods(d: date, unit: str, k: int) -> date:
    """Shift by k whole units. Month arithmetic clamps the day (31 Mar - 1 month = 28/29 Feb)."""
    if unit == "day":
        return d + timedelta(days=k)
    if unit == "week":
        return d + timedelta(weeks=k)
    months = {"month": 1, "quarter": 3, "year": 12}[unit] * k
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    m += 1
    # clamp the day to the target month's length
    nxt = date(y + (m == 12), (m % 12) + 1, 1)
    last_day = (nxt - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day))


def _plural(n: int, unit: str) -> str:
    return f"{n} {_UNIT_WORD[unit]}{'' if n == 1 else 's'}"


def window(spec: dict, anchor_date: date) -> tuple[date, date, str, bool]:
    """(start, end_exclusive, label, incomplete) for a validated spec."""
    mode, unit, n = spec["mode"], spec["unit"], spec["n"]
    a1 = anchor_date + timedelta(days=1)  # the anchor day is always "seen"
    ps = period_start(anchor_date, unit)
    if mode == "to_date":
        return ps, a1, _TO_DATE[unit], False
    if mode == "this":
        end = add_periods(ps, unit, 1)
        label = "Today" if unit == "day" else f"This {unit}"
        return ps, end, label, end > a1
    if mode == "previous":
        label = "Yesterday" if unit == "day" else f"Previous {unit}"
        return add_periods(ps, unit, -1), ps, label, False
    if mode == "rolling":
        start = add_periods(a1, unit, -n)
        return start, a1, f"Rolling {_plural(n, unit)}", False
    # last
    if unit == "day":
        return anchor_date - timedelta(days=n - 1), a1, f"Last {_plural(n, unit)}", False
    if spec.get("include_current"):
        end = add_periods(ps, unit, 1)
        return (add_periods(ps, unit, -(n - 1)), end,
                f"Last {_plural(n, unit)} (incl. current)", end > a1)
    return add_periods(ps, unit, -n), ps, f"Last {_plural(n, unit)} (complete)", False


def as_dates(series: pd.Series) -> pd.Series:
    """The column as naive datetimes; unparseable values become NaT."""
    if pd.api.types.is_datetime64_any_dtype(series):
        dt = series
    else:
        dt = pd.to_datetime(series, errors="coerce", format="mixed") \
            if series.dtype == object else pd.to_datetime(series, errors="coerce")
    try:
        if getattr(dt.dt, "tz", None) is not None:
            dt = dt.dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return dt


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def has_relative(filters) -> bool:
    return any(isinstance(f, dict) and f.get("op") == "relative" for f in (filters or []))


def resolve_filters(df: pd.DataFrame, filters: list[dict] | None,
                    today: date | None = None) -> tuple[list[dict], list[dict]]:
    """Replace every relative filter with a concrete date_range.

    Returns (filters, notes). ``df`` is the frame the data_max anchor is read
    from -- the rows this reader may see, before the widget's own filters, so
    "latest data" means the dataset's coverage, not the last row surviving
    some other filter. A spec that cannot resolve (bad spec, missing column,
    no dates in it) becomes a filter that matches nothing, with a note saying
    why: an unapplied "last 30 days" would show all of history under that
    label, which is the one outcome worse than an empty chart.
    """
    if not has_relative(filters):
        return list(filters or []), []
    today = today or date.today()
    out: list[dict] = []
    notes: list[dict] = []
    for f in filters or []:
        if not (isinstance(f, dict) and f.get("op") == "relative"):
            out.append(f)
            continue
        col = f.get("column")
        note: dict = {"column": col}
        try:
            spec = validate_spec(f.get("value"))
            note["anchor"] = spec["anchor"]
            if not col or col not in df.columns:
                raise RelativeDateError(f"Column '{col}' is not in this dataset")
            cadence = 1.0
            if spec["anchor"] == "data_max":
                dts = as_dates(df[col])
                mx = dts.max()
                if pd.isna(mx):
                    raise RelativeDateError(f"'{col}' holds no dates to anchor to")
                anchor_date = mx.date()
                cadence = cadence_days(dts)
                note["anchor_label"] = f"latest data ({_fmt(anchor_date)})"
            else:
                anchor_date = today
                note["anchor_label"] = f"today ({_fmt(anchor_date)})"
            start, end, label, incomplete = window(spec, anchor_date)
            # Against the data's own spacing (see cadence_days): weekly data
            # ending 3 days before the month does not leave the month unfinished.
            if incomplete and (end - anchor_date - timedelta(days=1)).days < cadence:
                incomplete = False
        except RelativeDateError as e:
            note.update({"error": str(e), "label": "Relative date filter"})
            notes.append(note)
            out.append({"column": col, "op": "date_range", "value": None, "__match_none__": True})
            continue
        last = end - timedelta(days=1)
        note.update({
            "label": label, "start": start.isoformat(), "end": last.isoformat(),
            "anchor_date": anchor_date.isoformat(), "incomplete": incomplete,
            "text": f"{label}: {_fmt(start)}" + ("" if start == last else f" – {_fmt(last)}")
                    + f", counted back from {note['anchor_label']}"
                    + (" — this period is not finished yet" if incomplete else ""),
        })
        notes.append(note)
        out.append({"column": col, "op": "date_range",
                    "value": [start.isoformat(), end.isoformat()]})
    return out, notes


def apply_date_range(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    """Keep rows whose date falls in [start, end). Nulls and unparseable dates drop."""
    col = f.get("column")
    val = f.get("value")
    if f.get("__match_none__") or not isinstance(val, (list, tuple)) or len(val) != 2:
        return df.iloc[0:0]
    if col not in df.columns:
        return df
    dt = as_dates(df[col])
    start, end = pd.Timestamp(val[0]), pd.Timestamp(val[1])
    return df[(dt >= start) & (dt < end)]


_GRAN_UNIT = {"week": "week", "month": "month", "quarter": "quarter", "year": "year"}


def cadence_days(dt: pd.Series) -> float:
    """The data's own spacing: the median gap in days between its latest
    distinct dates (1 for daily data, 7 weekly, ~31 for month-start stamps).

    A period is only "unfinished" if the data would have had another date
    inside it. Weekly data ending 28 Dec has no 31 Dec to wait for, and a
    month-start series ending 1 Dec is December's figure, not a day of it --
    flagging either as partial would be the false alarm the flag exists to
    prevent.
    """
    days = pd.Series(dt.dropna().dt.normalize().unique()).sort_values()
    days = days.iloc[-400:]
    if len(days) < 3:
        return 1.0
    gaps = days.diff().dropna().dt.days
    gaps = gaps[gaps > 0]
    return float(gaps.median()) if len(gaps) else 1.0


def partial_period(df: pd.DataFrame, dim: str | None, granularity: str | None,
                   result: dict) -> dict | None:
    """The shown time bucket the data has not finished, if any.

    ``df`` is the reader's visible frame (coverage). The bucket that contains the
    coverage's latest date is partial when that date is before the bucket's last
    day -- a September bar built from data through the 14th. Returned only when
    that bucket is actually one of the result's rows.
    """
    unit = _GRAN_UNIT.get(str(granularity or "").lower())
    if not unit or not dim or dim not in df.columns:
        return None
    dt = as_dates(df[dim])
    mx = dt.max()
    if pd.isna(mx):
        return None
    through = mx.date()
    ps = period_start(through, unit)
    last_day = add_periods(ps, unit, 1) - timedelta(days=1)
    if (last_day - through).days < cadence_days(dt):
        return None
    if unit == "year":
        label = str(ps.year)
    elif unit == "quarter":
        label = f"{ps.year}-Q{(ps.month - 1) // 3 + 1}"
    elif unit == "month":
        label = ps.strftime("%Y-%m")
    else:
        iso = through.isocalendar()
        label = f"{iso[0]}-W{iso[1]:02d}"
    names = {str(r.get("name")) for r in (result.get("rows") or []) if isinstance(r, dict)}
    if label not in names:
        return None
    return {"label": label, "through": through.isoformat(), "granularity": unit,
            "text": f"{label} is partial: the data runs to {_fmt(through)}, "
                    f"the {unit} ends {_fmt(last_day)}"}
