"""Where things stand: rows by stage, how long they have been there, what is
late (docs/discovery/PLAN.md §N, stage boards).

For a table whose rows move through stages -- a column that says where each
row stands, the date it began, and optionally the date it was finished and
the date it was due. Everything is read from those columns:

  * a row is OPEN when it has no finish date -- no list of "closed" words;
  * a finished row was ON TIME when it finished on or before its due date;
  * an open row is OVERDUE when its due date is before the newest date in
    the data -- "now" is as of the data, never the clock, so a file loaded
    last month is not suddenly all overdue.

Stages are shown in the order stored for the column (an ordinal's `order`),
or, with none, from the stage holding the most open rows down.
"""
from __future__ import annotations

import pandas as pd

from ..analysis_contract import AnalysisContract
from ..readback import _s, as_i18n

#: More stages than this is not a board anyone reads.
MAX_STAGES = 20


class StageBoardError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def _dates(df: pd.DataFrame, col: str | None) -> pd.Series | None:
    if not col:
        return None
    if col not in df.columns:
        raise StageBoardError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=col))
    return pd.to_datetime(df[col], errors="coerce")


def stage_board(df: pd.DataFrame, stage_col: str, start_date: str, done_date: str | None = None,
                due_date: str | None = None, column_meta: dict | None = None) -> AnalysisContract:
    if stage_col not in df.columns:
        raise StageBoardError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=stage_col))
    start, done, due = _dates(df, start_date), _dates(df, done_date), _dates(df, due_date)
    if start is None or start.notna().sum() == 0:
        raise StageBoardError(_s("no.change_drivers.3", "{a} holds no dates", cap=False, a=start_date))
    stage = df[stage_col].astype(object).where(df[stage_col].notna(), "(empty)").astype(str)
    names = stage.value_counts()
    if len(names) > MAX_STAGES:
        raise StageBoardError(_s("no.stage_board.1", "'{a}' has {b} values; a board of stages needs {c} or fewer", cap=False, a=stage_col, b=len(names), c=MAX_STAGES))
    if len(names) < 2:
        raise StageBoardError(_s("no.stage_board.2", "'{a}' has one value: there are no stages to set side by side", cap=False, a=stage_col))

    # "Now" is the newest date the data holds, in any of its date columns.
    as_of = max(s.max() for s in (start, done, due) if s is not None and s.notna().any())
    is_open = done.isna() if done is not None else pd.Series(True, index=df.index)
    # A due DATE (no time of day) is due by the end of that day: a row that
    # finished at 15:00 on the day it was due was on time, not fifteen hours
    # late (the shipments data read 21% on time until this was so).
    if due is not None and due.notna().any() and (due.dropna() == due.dropna().dt.normalize()).all():
        due = due + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    age_days = (as_of - start).dt.total_seconds() / 86400
    overdue = (is_open & due.notna() & (due < as_of)) if due is not None else None
    on_time = ((done <= due) & done.notna() & due.notna()) if (done is not None and due is not None) else None
    judged = (done.notna() & due.notna()) if on_time is not None else None

    from .. import semantic_guard as guard
    stored = guard.value_order(stage_col, column_meta)
    if stored:
        order = [s for s in stored if s in names.index] + [s for s in names.index if s not in stored]
        order_source = "stored"
    else:
        open_by = stage[is_open].value_counts()
        order = sorted(names.index, key=lambda s: (-int(open_by.get(s, 0)), -int(names[s])))
        order_source = "open_rows"

    total = int(len(df))
    rows = []
    for s in order:
        here = stage == s
        opened = here & is_open
        item = {"stage": s, "rows": int(here.sum()), "share_pct": round(float(here.sum()) / total * 100, 1) if total else 0.0,
                "open": int(opened.sum())}
        ages = age_days[opened].dropna()
        if len(ages):
            # How long the rows still in this stage have been going.
            item["median_age_days"] = round(float(ages.median()), 1)
            item["oldest_days"] = round(float(ages.max()), 1)
        if overdue is not None:
            item["overdue"] = int((here & overdue).sum())
        if on_time is not None:
            j = int((here & judged).sum())
            if j:
                item["finished"] = j
                item["on_time_pct"] = round(float((here & on_time).sum()) / j * 100, 1)
        rows.append(item)

    meta = {"stage_col": stage_col, "start_date": start_date, "done_date": done_date, "due_date": due_date,
            "as_of": str(as_of)[:10], "order_source": order_source, "rows": total,
            "open": int(is_open.sum()) if done is not None else None}
    caveats = [_s("an.now", "\"Now\" is the newest date in the data ({d}), not today.", d=str(as_of)[:10])]
    if done is None:
        caveats.append(_s("an.nofinish", "With no finish date, every row counts as still going: ages are since each row began."))
    else:
        caveats.append(_s("an.open", "A row is open when {done} is empty -- including one that ended without ever "
                                     "being finished, which nothing here can tell from one still going.", done=done_date))
    if on_time is not None:
        j = int(judged.sum())
        meta["finished"] = j
        meta["on_time_pct"] = round(float(on_time.sum()) / j * 100, 1) if j else None
    if overdue is not None:
        opened = int(is_open.sum())
        meta["overdue"] = int(overdue.sum())
        meta["overdue_pct"] = round(float(overdue.sum()) / opened * 100, 1) if opened else None
        no_due = int((is_open & due.isna()).sum())
        if no_due:
            caveats.append(_s("an.nodue", "{n} open rows have no {due} and cannot be late or on time.", n=f"{no_due:,}", due=due_date))
    if order_source == "open_rows":
        caveats.append(_s("an.noorder", "No order is stored for {c}: stages are listed from the one holding the most open rows.",
                          c=stage_col))
    return AnalysisContract(
        kind="stage_board",
        columns=[{"name": "stage", "type": "text"}, {"name": "rows", "type": "number"}, {"name": "open", "type": "number"}],
        rows=rows, meta={**meta, "warnings_i18n": [as_i18n(c) for c in caveats]}, warnings=[str(c) for c in caveats])
