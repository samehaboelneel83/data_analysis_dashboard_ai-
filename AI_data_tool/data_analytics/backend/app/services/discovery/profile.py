"""What is REMEMBERED about a dataset, so that asking "what can I do with this
data?" does not read the data again (docs/discovery/PLAN.md, phase 1).

Until now nothing was kept: `DatasetColumn.stats` was written as `{}` at every
import and never filled, and the profile and the insights were recomputed from
every row on every request.

Kept here, per column (table `dataset_profiles`, one row per dataset -- NOT in
`DatasetColumn.stats` or `column_meta`, which every dataset payload returns):

    kind       number | date | flag | text
    count, missing, distinct
    number:    min, max, mean, std, p5, p25, p50, p75, p95, whole, negative, zero
    text:      len_min, len_max, len_avg, top (labels of a CATEGORY only),
               numeric_share (texts that are really numbers)
    date:      min, max, median, periods (months that hold rows)

and for the table: the rows, the exact duplicates, its structure.

THE VERSION is the data's fingerprint (the file's size and write time; a day
for a live source). Same fingerprint, nothing is measured again.

WHO MAY WRITE IT. The stored profile describes the WHOLE dataset, so it is
written only from a read with no row rule and no hidden column. A reader with
either gets `for_reader`: hidden columns removed, and -- under a row rule --
every figure that is a VALUE (ranges, labels) withheld, because those would
be values of rows they may not see.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

#: Bump when the shape of what is stored changes: every dataset re-measures.
SCHEMA = 5
#: Rows measured; a larger table is sampled (and the profile says so).
SAMPLE_ROWS = 200_000
#: A text column with at most this many different values is a category, and
#: its labels are kept; beyond that only its shape is.
CATEGORY_MAX = 50
TOP_KEPT = 12
#: Figures that are values of rows, withheld from a reader under a row rule.
_VALUES = ("min", "max", "mean", "std", "p5", "p25", "p50", "p75", "p95", "median", "top", "least",
           "len_min", "len_max", "patterns", "pattern", "by_month")


def fingerprint(dataset) -> str:
    """What changes when the data does."""
    path = getattr(dataset, "filename", None)
    if path and getattr(dataset, "mode", "import") != "directquery":
        try:
            st = os.stat(path)
            return f"{SCHEMA}:f:{st.st_size}:{st.st_mtime_ns}"
        except OSError:
            pass
    # A live source has no file to stamp: its profile is good for the day.
    return f"{SCHEMA}:d:{datetime.now(timezone.utc):%Y-%m-%d}:{getattr(dataset, 'row_count', 0) or 0}"


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else round(f, 6)


#: A text column is "really" numbers or dates when at least this share parses.
MAJORITY = 0.8
#: ...and a text column with at most this share of numbers has stray numbers in it.
STRAY = 0.05
#: A shape most values share is a pattern worth stating.
PATTERN_SHARE = 0.8
_MASK = str.maketrans("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                      "a" * 26 + "A" * 26 + "9" * 10)


def mask_of(value: str) -> str:
    """The SHAPE of a value: letters as a/A, digits as 9, everything else kept
    ("AB-1234" -> "AA-9999"). Letters outside A-Z (Arabic, accented) read as "a"."""
    out = []
    for ch in str(value)[:32].translate(_MASK):
        out.append(ch if ch in "aA9" or not ch.isalpha() else "a")
    return "".join(out)


def _patterns(text: pd.Series) -> list[list]:
    """The shapes the values take, most common first: [[mask, share], ...]."""
    sample = text.sample(min(len(text), 2000), random_state=0)
    counts = sample.map(mask_of).value_counts()
    return [[m, round(float(c) / len(sample), 3)] for m, c in counts.head(3).items()]


#: Months of row counts kept for a date.
MONTHS_KEPT = 36


def _column(s: pd.Series) -> dict:
    n = int(len(s))
    out: dict = {"count": n, "missing": int(s.isna().sum())}
    q = s.dropna()
    try:
        counts = q.value_counts()
    except TypeError:                                   # unhashable cells (lists, dicts)
        q = q.astype(str)
        counts = q.value_counts()
    out["distinct"] = int(len(counts))
    # Values that occur exactly once -- all of them, in a key; none, in a category.
    out["unique"] = int((counts == 1).sum())
    out["mistyped"] = 0
    if pd.api.types.is_bool_dtype(s):
        out["kind"] = "flag"
        out["top"] = [[str(k), int(v)] for k, v in q.value_counts().head(2).items()]
    elif pd.api.types.is_datetime64_any_dtype(s):
        out["kind"] = "date"
        if len(q):
            ordered = q.sort_values()
            out.update(min=str(ordered.iloc[0]), max=str(ordered.iloc[-1]), median=str(ordered.iloc[len(ordered) // 2]))
            try:
                out["periods"] = int(q.dt.to_period("M").nunique())
            except Exception:                           # noqa: BLE001 -- tz-aware or out of range
                out["periods"] = 0
            # What the calendar readings need: how many years, how many days,
            # and whether the values carry a time of day at all (a date read
            # from a file is midnight on every row).
            try:
                out["years"] = int(q.dt.year.nunique())
                out["days"] = int(q.dt.normalize().nunique())
                out["hours"] = int(q.dt.hour.nunique())
                out["timed"] = round(float(((q.dt.hour != 0) | (q.dt.minute != 0)).mean()), 3)
                # Rows per month, for the last three years: what a usual month
                # holds (services/discovery/health.py). Of the measured rows.
                per = q.dt.to_period("M").value_counts().sort_index().tail(MONTHS_KEPT)
                out["by_month"] = [[str(k), int(v)] for k, v in per.items()]
            except Exception:                           # noqa: BLE001
                pass
    elif pd.api.types.is_numeric_dtype(s):
        out["kind"] = "number"
        v = pd.to_numeric(q, errors="coerce").dropna()
        if len(v):
            qs = v.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
            out.update(min=_num(v.min()), max=_num(v.max()), mean=_num(v.mean()), std=_num(v.std()),
                       p5=_num(qs.iloc[0]), p25=_num(qs.iloc[1]), p50=_num(qs.iloc[2]),
                       p75=_num(qs.iloc[3]), p95=_num(qs.iloc[4]),
                       whole=bool((v == v.round()).all()), negative=int((v < 0).sum()), zero=int((v == 0).sum()))
    else:
        out["kind"] = "text"
        text = q.astype(str)
        if len(text):
            lengths = text.str.len()
            out.update(len_min=int(lengths.min()), len_max=int(lengths.max()), len_avg=round(float(lengths.mean()), 1))
            # Texts that are really something else: a number or a date typed
            # into a text column. Judged on a sample; an estimate, and labelled.
            is_number = pd.to_numeric(text.str.replace(",", "", regex=False), errors="coerce").notna()
            share = float(is_number.mean())
            out["numeric_share"] = round(share, 3)
            # MISTYPED: the values that are not what the column mostly holds.
            # Mostly numbers -> the texts among them; mostly text with a few
            # stray numbers -> those. A column of codes that are all digits is
            # all numbers and has nothing mistyped.
            if MAJORITY <= share < 1:
                out["holds"], out["mistyped"] = "number", int((~is_number).sum())
            elif 0 < share <= STRAY:
                out["holds"], out["mistyped"] = "text", int(is_number.sum())
            else:
                out["holds"] = "number" if share == 1 else "text"
            if out["distinct"] <= CATEGORY_MAX:
                ranked = text.value_counts()
                out["top"] = [[str(k)[:60], int(c)] for k, c in ranked.head(TOP_KEPT).items()]
                out["least"] = [str(ranked.index[-1])[:60], int(ranked.iloc[-1])]
            else:
                # A code, a reference, a phone: most values share one shape.
                shapes = _patterns(text)
                out["patterns"] = shapes
                # ...short enough to be a format someone chose (a reference, a
                # code), not the outline of a sentence or a web address.
                if shapes and shapes[0][1] >= PATTERN_SHARE and len(shapes[0][0]) <= 24 \
                        and any(ch in shapes[0][0] for ch in "9-/.:_#"):
                    out["pattern"] = shapes[0][0]
    return out


def sample_rows() -> int:
    """Rows a dataset is measured on, as set now (settings.discovery_sample_rows)."""
    from ...core.config import settings
    return int(getattr(settings, "discovery_sample_rows", SAMPLE_ROWS) or SAMPLE_ROWS)


def compute(df: pd.DataFrame, type_map: dict | None = None) -> dict:
    """{"table": {...}, "columns": {name: stats}} for a frame. Pure; no I/O.

    `type_map` is what the platform reads each column as (analytics.detect_types):
    a date kept in a file as text is measured as the date it is, or the
    profile would call the day a record began a column of labels."""
    total = int(len(df))
    cap = sample_rows()
    frame = df if total <= cap else df.sample(cap, random_state=0)
    dates = [c for c, t in (type_map or {}).items() if t == "datetime" and c in frame.columns
             and not pd.api.types.is_datetime64_any_dtype(frame[c])]
    if dates:
        frame = frame.copy()
        for c in dates:
            frame[c] = pd.to_datetime(frame[c], errors="coerce")
    columns = {}
    for col in df.columns:
        name = str(col)
        if name.startswith("__"):
            continue
        try:
            columns[name] = _column(frame[col])
        except Exception:                                   # noqa: BLE001 -- one odd column never loses the rest
            logger.exception("profile: column %r could not be measured", name)
            columns[name] = {"count": int(len(frame)), "kind": "text", "missing": 0, "distinct": 0}
    try:
        duplicates = int(frame.duplicated().sum())
    except TypeError:
        duplicates = None
    return {"table": {"rows": total, "measured_rows": int(len(frame)), "sampled": total > len(frame),
                      "duplicates": duplicates},
            "columns": columns}


async def stored(db, dataset) -> dict | None:
    """The kept profile when it is of the data as it is now, else None."""
    from ...models.models import DatasetProfile
    row = await db.get(DatasetProfile, dataset.id)
    if row is None or row.version != fingerprint(dataset) or not isinstance(row.body, dict) \
            or not row.body.get("columns"):
        return None
    return row.body


async def remember(db, dataset, profile: dict) -> None:
    """Keep a profile measured on the WHOLE dataset -- in its own table, which
    no dataset payload returns. Never raises."""
    try:
        from ...models.models import DatasetProfile
        row = await db.get(DatasetProfile, dataset.id)
        if row is None:
            row = DatasetProfile(dataset_id=dataset.id)
            db.add(row)
        # What the columns were the last time the DATA was different: the
        # yardstick for "did the columns change" (health.py). A re-measure of
        # the same data carries the older yardstick forward.
        old = row.body if isinstance(row.body, dict) else None
        if old and old.get("columns"):
            same_data = str(row.version or "").split(":", 1)[-1] == fingerprint(dataset).split(":", 1)[-1]
            previous = old.get("previous") if same_data else {
                "measured_at": row.measured_at.isoformat() if row.measured_at else None,
                "rows": (old.get("table") or {}).get("rows"),
                "columns": {n: st.get("kind") for n, st in old["columns"].items()}}
            if previous:
                profile = {**profile, "previous": previous}
        row.version = fingerprint(dataset)
        row.body = profile
        row.measured_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception:                                           # noqa: BLE001
        logger.exception("profile: keeping the profile of dataset %s failed", getattr(dataset, "id", None))
        try:
            await db.rollback()
        except Exception:                                       # noqa: BLE001
            pass


async def keep_structure(db, dataset, structure: dict) -> None:
    """Add what the frame showed of the table's structure (hierarchies, a
    parent pointer, coordinates) to the kept profile. Never raises."""
    try:
        from sqlalchemy.orm.attributes import flag_modified
        from ...models.models import DatasetProfile
        row = await db.get(DatasetProfile, dataset.id)
        if row is None or not isinstance(row.body, dict):
            return
        body = dict(row.body)
        body["table"] = {**(body.get("table") or {}), "structure": {k: bool(v) for k, v in structure.items()}}
        row.body = body
        flag_modified(row, "body")
        await db.commit()
    except Exception:                                           # noqa: BLE001
        logger.exception("profile: keeping the structure of dataset %s failed", getattr(dataset, "id", None))


def for_reader(profile: dict, denied: set[str] | None = None, row_rule: bool = False) -> dict:
    """The profile as one reader may know it."""
    denied = {str(d) for d in (denied or ())}
    columns = {}
    for name, stats in profile["columns"].items():
        if name in denied:
            continue
        columns[name] = {k: v for k, v in stats.items() if k not in _VALUES} if row_rule else dict(stats)
    out = {"table": dict(profile["table"]), "columns": columns, "restricted": bool(row_rule or denied)}
    prev = profile.get("previous")
    if isinstance(prev, dict) and isinstance(prev.get("columns"), dict):
        out["previous"] = {**prev, "columns": {n: k for n, k in prev["columns"].items() if n not in denied}}
    return out


def card_of(name: str, stats: dict, now: datetime | None = None) -> dict:
    """One column's profile as a reader meets it: what is valid, what is not
    and why, and the figures that describe it. Derived from the stored
    statistics; nothing is read."""
    count, missing, mistyped = stats.get("count") or 0, stats.get("missing") or 0, stats.get("mistyped") or 0
    filled = max(count - missing, 0)

    def pct(v):
        return round(100.0 * v / count, 1) if count else 0.0
    unique = stats.get("unique") or 0
    card = {
        "column": name, "kind": stats.get("kind"), "cells": count,
        "valid": {"count": filled - mistyped, "pct": pct(filled - mistyped)},
        "unique": {"count": unique, "pct": pct(unique)},
        "nonunique": {"count": max(filled - unique, 0), "pct": pct(max(filled - unique, 0))},
        "invalid": {"count": missing + mistyped, "pct": pct(missing + mistyped)},
        "mistyped": {"count": mistyped, "pct": pct(mistyped), "holds": stats.get("holds")},
        "missing": {"count": missing, "pct": pct(missing)},
        "distinct": stats.get("distinct"),
    }
    for key in ("min", "max", "mean", "p50", "len_min", "len_max", "top", "least", "pattern", "patterns",
                "median", "periods", "years", "days", "hours", "timed"):
        if stats.get(key) is not None:
            card[key] = stats[key]
    if stats.get("top"):
        card["most_common"] = stats["top"][0]
    if stats.get("kind") == "date" and stats.get("max"):
        # DATA DELAY: how old the newest value is. A date ahead of today (a
        # due date, a plan) has no delay to speak of.
        try:
            newest = pd.Timestamp(stats["max"])
            newest = newest.tz_localize(None) if newest.tzinfo else newest
            hours = ((now or datetime.now(timezone.utc)).replace(tzinfo=None) - newest.to_pydatetime()).total_seconds() / 3600
            card["delay_hours"] = round(hours, 1) if hours >= 0 else None
        except Exception:                                   # noqa: BLE001
            card["delay_hours"] = None
    return card


async def ensure(db, dataset, df: pd.DataFrame | None, *, denied: set[str] | None = None,
                 row_rule: bool = False, type_map: dict | None = None) -> tuple[dict, bool]:
    """(the profile this reader may use, whether it came from the store).

    A kept profile of the current data is returned without touching `df`. With
    none, `df` -- the reader's own secured frame, already in hand -- is
    measured; the result is KEPT only when that frame is the whole dataset."""
    import asyncio
    kept = await stored(db, dataset)
    if kept is not None:
        return for_reader(kept, denied, row_rule), True
    if df is None:
        return {"table": {"rows": getattr(dataset, "row_count", 0) or 0}, "columns": {}, "restricted": False}, False
    measured = await asyncio.to_thread(compute, df, type_map)
    if not row_rule and not denied:
        await remember(db, dataset, measured)
    return for_reader(measured, None, False) if not (row_rule or denied) else \
        {**measured, "restricted": True}, False
