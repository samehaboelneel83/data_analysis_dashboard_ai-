"""A dataset's health, read off its stored profile (docs/discovery/PLAN.md §N-5).

One short list of checks, each passed, worth a look, or failed, with one
sentence saying what was found: is the data still arriving, is the latest
month's volume what its history made likely, did the columns change since
the last time it was measured, and are the values what their columns hold.

Nothing is read here -- every figure was measured when the dataset was
profiled -- and nothing here knows what the rows are about.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..readback import _s, as_i18n

#: Share of a column that may be empty before it is worth a look / a failure.
MISSING_WARN, MISSING_FAIL = 0.05, 0.50
#: Share of a column that is not what the column mostly holds.
MISTYPED_FAIL = 0.05
#: Share of rows that are exact copies of another row.
DUPLICATE_FAIL = 0.01
#: The newest record is late when it is this many times older than the usual
#: gap between days that hold records -- and never before two days. Late is
#: "worth a look", never a failure: a file loaded once is as old as it is, and
#: nothing here knows whether the data was meant to keep arriving.
LATE_WARN, LATE_FLOOR_HOURS = 3.0, 48.0
#: Columns named in one sentence.
NAMED = 4

PASS, WARN, FAIL = "pass", "warn", "fail"
_RANK = {PASS: 0, WARN: 1, FAIL: 2}


def _h(col: str) -> str:
    return " ".join(str(col).replace("_", " ").split())


def _names(cols: list[str]):
    shown = ", ".join(_h(c) for c in cols[:NAMED])
    return _s("health.names.more", "{shown} and {n} more", cap=False, shown=shown, n=len(cols) - NAMED) \
        if len(cols) > NAMED else shown


def _check(cid: str, group: str, status: str, title, sentence, columns=(), **figures) -> dict:
    """`title` and `sentence` are `Said`: the English text, and the key and
    pieces the browser says them with in the reader's language."""
    return {"id": cid, "group": group, "status": status, "title": str(title),
            "sentence": " ".join(str(sentence).split()),          # parts that are absent leave no gap
            "title_i18n": as_i18n(title), "sentence_i18n": as_i18n(sentence),
            "columns": list(columns), "figures": figures}


def _freshness(date: str | None, st: dict, now: datetime) -> dict:
    title = _s("health.fresh.title", "Still arriving")
    if not date or not st.get("max"):
        return _check("freshness", "freshness", PASS, title,
                      _s("health.fresh.none", "No date says when records begin, so this is not checked."), checked=False)
    try:
        newest, oldest = pd.Timestamp(st["max"]), pd.Timestamp(st.get("min") or st["max"])
    except (ValueError, TypeError):
        return _check("freshness", "freshness", PASS, title,
                      _s("health.fresh.unread", "The dates could not be read."), checked=False)
    hours = (now.replace(tzinfo=None) - newest.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600
    days_with_rows = max(int(st.get("days") or 0), 1)
    gap_hours = max((newest - oldest).total_seconds() / 3600 / max(days_with_rows - 1, 1), 24.0)
    late = hours / gap_hours
    status = PASS if hours < LATE_FLOOR_HOURS or late < LATE_WARN else WARN
    when = str(st["max"])[:10]
    sentence = (_s("health.fresh.ok", "The newest {col} is {when}.", col=_h(date), when=when) if status == PASS else
                _s("health.fresh.late", "No row is dated after {when} -- {days} days ago, where records usually arrive "
                                        "every {gap} days.", when=when, days=f"{hours / 24:,.0f}", gap=f"{gap_hours / 24:,.1f}"))
    return _check("freshness", "freshness", status, title, sentence, [date],
                  newest=str(st["max"]), delay_hours=round(hours, 1), usual_gap_hours=round(gap_hours, 1))


def _volume(date: str | None, st: dict) -> dict:
    title = _s("health.vol.title", "Rows per month")
    months = [m for m in (st.get("by_month") or []) if isinstance(m, (list, tuple)) and len(m) == 2]
    if not date or len(months) < 2:
        return _check("volume", "volume", PASS, title,
                      _s("health.vol.short", "Too little history to say what a usual month holds."),
                      checked=False, series=months)
    # The month the data stops inside is not judged.
    try:
        newest = pd.Timestamp(st["max"])
        whole = newest.day == newest.days_in_month
    except (ValueError, TypeError, KeyError):
        whole = True
    judged = months if whole else months[:-1]
    counts = [float(c) for _, c in judged]
    from ..analysis import timeline
    band = timeline.expected_band(counts, None) if len(counts) >= 2 else []
    last = band[-1] if band else None
    if last is not None:
        last = {**last, "lo": max(float(last["lo"]), 0.0)}      # a month cannot hold fewer than no rows
    if last is None:
        return _check("volume", "volume", PASS, title,
                      _s("health.vol.few", "{n} complete months so far: too few to say what a usual month holds.",
                         n=len(judged)), [date], checked=False, series=months)
    label, value = judged[-1][0], counts[-1]
    if last["lo"] <= value <= last["hi"]:
        return _check("volume", "volume", PASS, title,
                      _s("health.vol.ok", "{month} holds {rows} rows, within what the months before made likely.",
                         month=label, rows=f"{value:,.0f}"),
                      [date], month=label, rows=value, low=round(last["lo"], 1), high=round(last["hi"], 1), series=months)
    fewer = value < last["lo"]
    status = FAIL if fewer and value <= 0.5 * last["expected"] else WARN
    return _check("volume", "volume", status, title,
                  _s("health.vol.fewer" if fewer else "health.vol.more",
                     "{month} holds {rows} rows -- fewer than the {lo} to {hi} the months before made likely." if fewer else
                     "{month} holds {rows} rows -- more than the {lo} to {hi} the months before made likely.",
                     month=label, rows=f"{value:,.0f}", lo=f"{last['lo']:,.0f}", hi=f"{last['hi']:,.0f}"),
                  [date], month=label, rows=value, low=round(last["lo"], 1), high=round(last["hi"], 1),
                  expected=round(last["expected"], 1), series=months)


def _schema(profile: dict) -> dict:
    same = _s("health.schema.same.title", "Columns unchanged")
    prev = profile.get("previous")
    if not isinstance(prev, dict) or not isinstance(prev.get("columns"), dict):
        return _check("schema", "schema", PASS, same,
                      _s("health.schema.once", "Measured once so far: there is no earlier version to compare with."),
                      checked=False)
    now_cols = {n: st.get("kind") for n, st in (profile.get("columns") or {}).items()}
    before = prev["columns"]
    added = [c for c in now_cols if c not in before]
    removed = [c for c in before if c not in now_cols]
    retyped = [c for c in now_cols if c in before and before[c] and now_cols[c] and before[c] != now_cols[c]]
    since = str(prev.get("measured_at") or "")[:10]
    if not (added or removed or retyped):
        return _check("schema", "schema", PASS, same,
                      _s("health.schema.same", "The same columns, holding the same kinds of value, as on {since}.",
                         since=since), since=since)
    gone = _s("health.schema.gone", "{n} gone ({names}).", n=len(removed), names=_names(removed)) if removed else ""
    kind = _s("health.schema.retyped", "{n} now hold another kind of value ({names}).", n=len(retyped),
              names=_names(retyped)) if retyped else ""
    new = _s("health.schema.new", "{n} new ({names}).", n=len(added), names=_names(added)) if added else ""
    # A column that went away, or changed what it holds, breaks what was built on it.
    status = WARN if (removed or retyped) else PASS
    return _check("schema", "schema", status,
                  _s("health.schema.changed.title", "Columns changed") if status == WARN else
                  _s("health.schema.added.title", "Columns added"),
                  _s("health.schema.changed", "Since {since}: {gone} {kind} {new}", since=since, gone=gone, kind=kind, new=new),
                  removed + retyped + added, added=added, removed=removed, retyped=retyped, since=since)


def _per_column(profile: dict) -> list[dict]:
    columns = profile.get("columns") or {}
    empty, gaps_fail, gaps_warn, wrong_fail, wrong_warn, constant = [], [], [], [], [], []
    for name, st in columns.items():
        count = st.get("count") or 0
        if not count:
            continue
        missing, mistyped = (st.get("missing") or 0) / count, (st.get("mistyped") or 0) / count
        if missing >= 1:
            empty.append(name)
        elif missing >= MISSING_FAIL:
            gaps_fail.append(name)
        elif missing >= MISSING_WARN:
            gaps_warn.append(name)
        if mistyped >= MISTYPED_FAIL:
            wrong_fail.append(name)
        elif mistyped > 0:
            wrong_warn.append(name)
        if missing < 1 and st.get("distinct") == 1:
            constant.append(name)
    out = []
    gaps = empty + gaps_fail + gaps_warn
    e = _s("health.missing.empty", "{n} with no value at all ({names}).", n=len(empty), names=_names(empty)) if empty else ""
    h = _s("health.missing.half", "{n} more than half empty ({names}).", n=len(gaps_fail), names=_names(gaps_fail)) if gaps_fail else ""
    w = _s("health.missing.some", "{n} missing 5% or more ({names}).", n=len(gaps_warn), names=_names(gaps_warn)) if gaps_warn else ""
    out.append(_check(
        "missing", "values", FAIL if empty or gaps_fail else WARN if gaps_warn else PASS,
        _s("health.missing.title", "Values present"),
        _s("health.missing.ok", "No column is missing more than 5% of its values.") if not gaps else
        _s("health.missing.parts", "{e} {h} {w}", e=e, h=h, w=w),
        gaps, empty=empty, mostly_empty=gaps_fail, some_missing=gaps_warn))
    wrong = wrong_fail + wrong_warn
    out.append(_check(
        "mistyped", "values", FAIL if wrong_fail else WARN if wrong_warn else PASS,
        _s("health.mistyped.title", "Values of the right kind"),
        _s("health.mistyped.ok", "Every column holds one kind of value.") if not wrong else
        _s("health.mistyped.some", "{n} hold values that are not what the column mostly holds ({names}); "
                                   "those values are left out of any calculation.", n=len(wrong), names=_names(wrong)),
        wrong, many=wrong_fail, few=wrong_warn))
    out.append(_check(
        "constant", "values", WARN if constant else PASS, _s("health.constant.title", "Columns that vary"),
        _s("health.constant.ok", "Every column holds more than one value.") if not constant else
        _s("health.constant.some", "{n} hold the same value on every row ({names}): nothing can be compared by them.",
           n=len(constant), names=_names(constant)),
        constant))
    return out


def _duplicates(profile: dict) -> dict:
    title = _s("health.dup.title", "No copied rows")
    table = profile.get("table") or {}
    dup, rows = table.get("duplicates"), table.get("measured_rows") or table.get("rows") or 0
    if dup is None or not rows:
        return _check("duplicates", "rows", PASS, title, _s("health.dup.unchecked", "Not checked for this data."), checked=False)
    share = dup / rows
    status = PASS if not dup else FAIL if share >= DUPLICATE_FAIL else WARN
    return _check("duplicates", "rows", status, title,
                  _s("health.dup.ok", "No row is an exact copy of another.") if not dup else
                  _s("health.dup.some", "{n} rows are exact copies of another row ({pct}%); every total counts them twice.",
                     n=f"{dup:,}", pct=f"{share * 100:.1f}"),
                  duplicates=dup, share=round(share, 4))


def checks(profile: dict, start_date: str | None = None, now: datetime | None = None) -> dict:
    """{"summary": {pass, warn, fail, status}, "checks": [...]} for one profile
    (as the reader may know it). `start_date` is the date records begin on."""
    now = now or datetime.now(timezone.utc)
    st = (profile.get("columns") or {}).get(start_date) or {} if start_date else {}
    found = [_freshness(start_date, st, now), _volume(start_date, st), _schema(profile),
             *_per_column(profile), _duplicates(profile)]
    counted = [c for c in found if c["figures"].get("checked") is not False]
    summary = {s: sum(c["status"] == s for c in counted) for s in (PASS, WARN, FAIL)}
    worst = max((c["status"] for c in counted), key=_RANK.get, default=PASS)
    table = profile.get("table") or {}
    return {"summary": {**summary, "status": worst, "not_checked": len(found) - len(counted),
                        "columns": len(profile.get("columns") or {}), "rows": table.get("rows"),
                        "sampled": bool(table.get("sampled"))},
            "checks": sorted(found, key=lambda c: -_RANK[c["status"]])}
