"""Snapshot dataflows (4.6): a history from a source that only shows today.

A live dataset answers "how many people work here NOW". A snapshot dataflow
asks that on every run and APPENDS the answer under the period it was asked
in, so twelve monthly runs are a twelve-month trend -- no SQL, no warehouse.
Re-running inside the same period replaces that period's rows, so a daily
schedule keeps the current month current and freezes the months behind it.

History tables carry their own past: with `backfill` naming a start and an
end date column (dept_emp.from_date / to_date) the first run reconstructs
every month since `start` -- a row is counted in a month when it started by
the month's end and had not ended by then.

Spec (Dataflow.snapshot):
    {"every": "month" | "week" | "day",
     "group_by": ["dept_name"],               # optional
     "measure": null | "emp_no",              # null counts rows
     "agg": "count" | "nunique" | "sum" | "avg",
     "as": "headcount",                       # value column name
     "backfill": {"from_column": "from_date", "to_column": "to_date",
                  "start": "2020-01-01"}}     # optional
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

PERIOD_COL = "snapshot_period"
EVERY = ("month", "week", "day")
AGGS = ("count", "nunique", "sum", "avg")
MAX_BACKFILL_PERIODS = 600


def validate_spec(spec: dict | None, columns: set[str]) -> dict | None:
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ValueError("snapshot must be an object")
    every = spec.get("every", "month")
    if every not in EVERY:
        raise ValueError(f"snapshot 'every' must be one of {', '.join(EVERY)}")
    group_by = spec.get("group_by") or []
    if not isinstance(group_by, list) or any(c not in columns for c in group_by):
        raise ValueError("snapshot group_by names a column the source does not have")
    agg = spec.get("agg") or ("count" if not spec.get("measure") else "sum")
    if agg not in AGGS:
        raise ValueError(f"snapshot 'agg' must be one of {', '.join(AGGS)}")
    measure = spec.get("measure") or None
    if measure and measure not in columns:
        raise ValueError(f"snapshot measure '{measure}' is not a column of the source")
    if agg in ("sum", "avg", "nunique") and not measure:
        raise ValueError(f"'{agg}' needs a measure column")
    name = str(spec.get("as") or ("rows" if agg == "count" and not measure else f"{agg}_{measure}"))[:60]
    out = {"every": every, "group_by": group_by, "measure": measure, "agg": agg, "as": name}
    bf = spec.get("backfill")
    if bf:
        fc, tc = bf.get("from_column"), bf.get("to_column")
        if fc not in columns or tc not in columns:
            raise ValueError("backfill needs the source's start and end date columns")
        try:
            start = date.fromisoformat(str(bf.get("start"))[:10])
        except ValueError:
            raise ValueError("backfill 'start' must be a date (YYYY-MM-DD)")
        out["backfill"] = {"from_column": fc, "to_column": tc, "start": start.isoformat()}
    return out


def period_start(d: date, every: str) -> date:
    if every == "month":
        return d.replace(day=1)
    if every == "week":
        return d - timedelta(days=d.weekday())
    return d


def period_end(start: date, every: str) -> date:
    if every == "month":
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt - timedelta(days=1)
    if every == "week":
        return start + timedelta(days=6)
    return start


def _aggregate(frame: pd.DataFrame, spec: dict) -> pd.DataFrame:
    g, m, agg, name = spec["group_by"], spec["measure"], spec["agg"], spec["as"]
    if not g:
        if agg == "count":
            v = int(frame[m].notna().sum()) if m else int(len(frame))
        elif agg == "nunique":
            v = int(frame[m].nunique())
        else:
            s = pd.to_numeric(frame[m], errors="coerce")
            v = float(s.sum() if agg == "sum" else s.mean())
        return pd.DataFrame({name: [v]})
    grouped = frame.groupby(g, dropna=False)
    if agg == "count":
        res = grouped[m].count() if m else grouped.size()
    elif agg == "nunique":
        res = grouped[m].nunique()
    else:
        num = frame.assign(__v=pd.to_numeric(frame[m], errors="coerce")).groupby(g, dropna=False)["__v"]
        res = num.sum() if agg == "sum" else num.mean()
    return res.rename(name).reset_index()


def snapshot_rows(frame: pd.DataFrame, spec: dict, today: date | None = None) -> pd.DataFrame:
    """The rows this run contributes: one period (or, with backfill, every
    period from `start` to today), each tagged with its period start."""
    today = today or datetime.utcnow().date()
    every = spec["every"]
    bf = spec.get("backfill")
    if not bf:
        out = _aggregate(frame, spec)
        out.insert(0, PERIOD_COL, period_start(today, every).isoformat())
        return out
    # An end date past pandas' range (the 9999-01-01 "still open" sentinel)
    # coerces to NaT, which is read as "not ended" -- what it means.
    starts = pd.to_datetime(frame[bf["from_column"]], errors="coerce")
    ends = pd.to_datetime(frame[bf["to_column"]], errors="coerce")
    p = period_start(date.fromisoformat(bf["start"]), every)
    last = period_start(today, every)
    parts = []
    n = 0
    while p <= last and n < MAX_BACKFILL_PERIODS:
        end = pd.Timestamp(period_end(p, every))
        active = frame[(starts <= end) & (ends.isna() | (ends > end))]
        part = _aggregate(active, spec)
        part.insert(0, PERIOD_COL, p.isoformat())
        parts.append(part)
        nxt = period_end(p, every) + timedelta(days=1)
        p, n = nxt, n + 1
    return pd.concat(parts, ignore_index=True) if parts else _aggregate(frame.iloc[0:0], spec)


def merge(existing: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Append `new`, replacing any rows of the same periods already there."""
    if existing is None or existing.empty or PERIOD_COL not in existing.columns:
        return new.reset_index(drop=True)
    periods = set(new[PERIOD_COL].astype(str))
    keep = existing[~existing[PERIOD_COL].astype(str).isin(periods)]
    out = pd.concat([keep, new], ignore_index=True)
    return out.sort_values(PERIOD_COL, kind="stable").reset_index(drop=True)


async def source_frame(db, user, src, steps: list[dict]) -> pd.DataFrame:
    """The source's rows for this user, after the recipe's steps -- from its
    file, or read live from its connection for a DirectQuery dataset."""
    import asyncio

    from ..core.config import settings
    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from .analysis_frame import load_directquery_frame
    from .ingest import load_file
    from .prep import apply_prep_steps, resolve_join_frames
    from .widget_data import apply_rls_filter

    rls = await resolve_rls_expr(db, user, src.id)
    denied = await resolve_denied_columns(db, user, src.id) or []
    aux = await resolve_join_frames(db, user, steps)
    if src.mode == "directquery" and not src.filename:
        got = await load_directquery_frame(db, src, rls_filter_expr=rls, denied=set(denied),
                                           row_cap=int(settings.import_row_cap or 0) or None)
        if got.sampled:
            raise ValueError(f"'{src.name}' has {got.total_rows:,} rows, more than a dataflow reads "
                             f"from a live source. Filter it, or add an aggregate on the dataset.")
        frame = got.frame
        return await asyncio.to_thread(apply_prep_steps, frame, steps, aux)

    def _run():
        df = load_file(src.filename)
        df = apply_rls_filter(df, rls)
        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)
        return apply_prep_steps(df, steps, aux)
    return await asyncio.to_thread(_run)
