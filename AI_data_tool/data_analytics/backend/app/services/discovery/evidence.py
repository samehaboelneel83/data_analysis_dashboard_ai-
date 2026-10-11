"""A look at the rows before a card is offered (docs/discovery/PLAN.md §X-1).

Tier 0 offers a card when the table COULD support it: a date with times of
day could show a weekly rhythm; two numbers of one unit could be a number and
its yardstick; a two-valued column could mark two groups worth comparing. On
real data that produced cards that were mechanical or wrong -- a fee set
against the price of the parcel, scenarios on a factor that explains nothing,
a board whose "stage" was the region.

So when the rows are in hand anyway, each of those cards is checked on them,
cheaply, and one of three things happens:

  * it is KEPT WITH EVIDENCE -- the band and the figures that earned it, and
    a sentence that says what was found;
  * it is KEPT AS IT WAS -- the check has nothing to say either way;
  * it is WITHHELD, with the reason -- returned beside the cards, so "why was
    this not suggested" has an answer.

Every check is a measurement of the rows the reader may see. None of them
knows what the rows are about, and a check that fails for any reason leaves
its card exactly as it was.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..readback import Said, _s

logger = logging.getLogger(__name__)

#: Rows looked at; a sample beyond that (seeded).
SAMPLE = 200_000
#: A weekday or an hour has to differ from the average by this share to be a rhythm.
RHYTHM_MIN, RHYTHM_MODERATE, RHYTHM_STRONG = 0.10, 0.20, 0.50
#: A month of the year has to differ this much, year after year, to be a season.
SEASON_MODERATE, SEASON_STRONG = 0.20, 0.50
#: Two numbers are a number and its yardstick only if they move together row by row.
PAIR_TOGETHER = 0.5
#: A scenario needs a factor the fit can see: evidence for it, a fit worth
#: reading, and the two moving together per row -- not only because busier
#: periods hold more of everything.
SCENARIO_P, SCENARIO_R2, SCENARIO_TOGETHER = 0.05, 0.30, 0.30
#: A stage column separates rows still going from finished ones.
STAGE_SEPARATES, STAGE_MIN_ROWS = 0.5, 20
#: The latest change against the usual change between periods.
CHANGE_MODERATE, CHANGE_STRONG = 2.0, 4.0

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _day(i: int) -> Said:
    return _s(f"day.{_DAYS[i].lower()}", _DAYS[i])


def _month(m: int) -> Said:
    return _s(f"mon.{_MONTHS[m - 1].lower()}", _MONTHS[m - 1])


def _col(name) -> str:
    return " ".join(str(name).replace("_", " ").split())


def _band(value: float, moderate: float, strong: float) -> str:
    return "strong" if value >= strong else "moderate" if value >= moderate else "weak"


def _ev(band: str, strength: float, kind: str, **figures) -> dict:
    return {"band": band, "strength": round(float(min(max(strength, 0.0), 1.0)), 3), "kind": kind, "figures": figures}


def _amounts(df: pd.DataFrame, config: dict) -> tuple[pd.Series, pd.Series] | None:
    """(dates, the amount each row adds) for a calendar card: its measure, or 1 per row when it counts."""
    date = config.get("dimension")
    if date not in df.columns:
        return None
    dt = pd.to_datetime(df[date], errors="coerce")
    measure, how = config.get("measure"), str(config.get("aggregation") or "sum").lower()
    if how == "count" or not measure or measure == date or measure not in df.columns:
        amount = pd.Series(1.0, index=df.index)
    else:
        amount = pd.to_numeric(df[measure], errors="coerce").fillna(0.0)
    keep = dt.notna()
    return dt[keep], amount[keep]


# ── the checks ───────────────────────────────────────────────────────────────
def _weekly_rhythm(card: dict, df: pd.DataFrame, _meta) -> tuple[str, dict | None, str]:
    got = _amounts(df, card["action"]["config"])
    if got is None:
        return "keep", None, ""
    dt, amount = got
    daily = amount.groupby(dt.dt.normalize()).sum()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"), fill_value=0.0)
    by_day = daily.groupby(daily.index.dayofweek).mean()
    by_hour = amount.groupby(dt.dt.hour).sum().reindex(range(24), fill_value=0.0)
    mean_day, mean_hour = float(by_day.mean()), float(by_hour.mean())
    if mean_day <= 0 or mean_hour <= 0:
        return "keep", None, ""
    day_spread = float(by_day.max() - by_day.min()) / mean_day
    hour_spread = float(by_hour.max() - by_hour.min()) / mean_hour
    spread = max(day_spread, hour_spread)
    if spread < RHYTHM_MIN:
        return "drop", None, _s("ev.no.rhythm", "Every day of the week and every hour holds about the same: there is no rhythm to show.")
    top_day, low_day, top_hour = int(by_day.idxmax()), int(by_day.idxmin()), int(by_hour.idxmax())
    # Lead with what is large. Hours that are simply empty at night make a
    # big spread by themselves; a +2% weekday is not a finding and is not
    # dressed as one (seen on the shipments data).
    hours_with = [h for h in range(24) if by_hour[h] >= 0.5 * mean_hour]
    hours = (_s("ev.hours.window", "Most of it falls between {a}:00 and {b}:00, busiest from {h}:00",
                a=f"{min(hours_with):02d}", b=f"{max(hours_with) + 1:02d}", h=f"{top_hour:02d}")
             # ...when those hours are one stretch of the day, and not nearly all of it.
             if hours_with and len(hours_with) < 20 and max(hours_with) - min(hours_with) + 1 == len(hours_with) else
             _s("ev.hours.peak", "The busiest hour starts at {h}:00", h=f"{top_hour:02d}"))
    if day_spread >= RHYTHM_MIN:
        sentence = _s("ev.rhythm.days", "Busiest on {top} ({top_pct}% on an average day), quietest on {low} ({low_pct}%). {hours}.",
                      top=_day(top_day), top_pct=f"{(by_day.max() / mean_day - 1) * 100:+.0f}",
                      low=_day(low_day), low_pct=f"{(by_day.min() / mean_day - 1) * 100:+.0f}", hours=hours)
    else:
        sentence = _s("ev.rhythm.hours", "{hours}. The days of the week are about the same.", hours=hours)
    return "keep", _ev(_band(spread, RHYTHM_MODERATE, RHYTHM_STRONG), spread / 2, "rhythm",
                       day_spread=round(day_spread, 3), hour_spread=round(hour_spread, 3),
                       busiest_day=_DAYS[top_day], quietest_day=_DAYS[low_day], busiest_hour=top_hour), sentence


def _yearly_season(card: dict, df: pd.DataFrame, _meta) -> tuple[str, dict | None, str]:
    got = _amounts(df, card["action"]["config"])
    if got is None:
        return "keep", None, ""
    dt, amount = got
    monthly = amount.groupby(dt.dt.to_period("M")).sum()
    if dt.max().day != dt.max().days_in_month and len(monthly) > 1:
        monthly = monthly.iloc[:-1]                         # the month the data stops inside
    if len(monthly) < 13:
        return "keep", None, ""
    # Each month against its own year's average, then the same month across years.
    year_mean = monthly.groupby(monthly.index.year).transform("mean")
    index = (monthly / year_mean.where(year_mean != 0)).dropna()
    by_month = index.groupby(index.index.month).mean()
    seen = index.groupby(index.index.month).count()
    by_month = by_month[seen >= 2]                          # a month seen once is not a season
    if len(by_month) < 6:
        return "keep", None, ""
    spread = float(by_month.max() - by_month.min())
    top, low = int(by_month.idxmax()), int(by_month.idxmin())
    if spread < SEASON_MODERATE:
        return "keep", None, ""
    return "keep", _ev(_band(spread, SEASON_MODERATE, SEASON_STRONG), spread / 2, "season",
                       spread=round(spread, 3), highest_month=_MONTHS[top - 1], lowest_month=_MONTHS[low - 1]), \
        _s("ev.season", "{top} runs {top_pct}% against its year's average month and {low} {low_pct}%, year after year.",
           top=_month(top), top_pct=f"{(by_month.max() - 1) * 100:+.0f}", low=_month(low),
           low_pct=f"{(by_month.min() - 1) * 100:+.0f}")


def _pair(card: dict, df: pd.DataFrame, _meta) -> tuple[str, dict | None, str]:
    action = card["action"]
    cfg = action.get("config") or action.get("params") or {}
    a = cfg.get("measure")
    b = cfg.get("reference") or cfg.get("bridge_from") or cfg.get("difference_of")
    if a not in df.columns or b not in df.columns:
        return "keep", None, ""
    x, y = pd.to_numeric(df[a], errors="coerce"), pd.to_numeric(df[b], errors="coerce")
    both = x.notna() & y.notna()
    if both.sum() < 30 or x[both].std() == 0 or y[both].std() == 0:
        return "keep", None, ""
    r = float(np.corrcoef(x[both], y[both])[0, 1])
    if not np.isfinite(r) or r < PAIR_TOGETHER:
        return "drop", None, _s("ev.no.pair", "The two numbers do not move together row by row, so one is not a yardstick "
                                              "for the other: their difference would not mean anything.")
    total_a, total_b = float(x[both].sum()), float(y[both].sum())
    gap = (total_a - total_b) / abs(total_b) * 100 if total_b else 0.0
    return "keep", _ev(_band(abs(gap), 2.0, 10.0), min(abs(gap) / 20, 1.0), "difference",
                       together=round(r, 3), difference_pct=round(gap, 1)), \
        _s("ev.pair", "The two move together row by row, and in total the first is {gap}% against the second.", gap=f"{gap:+.1f}")


def _two_groups(card: dict, df: pd.DataFrame, meta) -> tuple[str, dict | None, str]:
    from ..analysis.two_groups import TwoGroupsError, compare_two_groups
    p = card["action"]["params"]
    try:
        m = compare_two_groups(df, p["group_col"], p["outcome"], column_meta=meta).to_dict()["meta"]
    except TwoGroupsError:
        return "drop", None, _s("ev.no.groups", "The two groups cannot be set side by side on these rows.")
    if m["verdict"] == "not_clear":
        return "drop", None, _s("ev.no.differ", "On these rows the two groups do not clearly differ.")
    lift = abs(m["lift_pct"] or 0.0)
    sure = max(m["chance_higher"], 1 - m["chance_higher"])
    band = "strong" if sure >= 0.99 and lift >= 10 else "moderate"
    return "keep", _ev(band, min(lift / 50, 1.0), "two_groups", lift_pct=m["lift_pct"], chance_higher=m["chance_higher"],
                       difference=m["difference"], baseline=m["baseline"], other=m["other"]), \
        _s(f"ev.groups.{m['verdict']}" + (".lift" if m["lift_pct"] is not None else ""),
           ("{other} is higher than {base}" if m["verdict"] == "higher" else "{other} is lower than {base}")
           + ", and the rows seen leave little room for the opposite." + (" Lift {lift}%." if m["lift_pct"] is not None else ""),
           other=m["other"], base=m["baseline"], lift=f"{m['lift_pct']:+.1f}" if m["lift_pct"] is not None else "")


def _scenarios(card: dict, df: pd.DataFrame, _meta) -> tuple[str, dict | None, str]:
    from ..analysis.forecast_scenario import ForecastScenarioError, forecast_scenario
    p = card["action"]["params"]
    factor = (p.get("factors") or [None])[0]
    try:
        fit = forecast_scenario(df, p["date_column"], p["measure"], [factor], {}, granularity="month")
    except ForecastScenarioError:
        return "drop", None, _s("ev.no.history", "There is too little history to project this.")
    f = next((x for x in fit["factors"] if x["column"] == factor), None)
    x, y = pd.to_numeric(df[factor], errors="coerce"), pd.to_numeric(df[p["measure"]], errors="coerce")
    both = x.notna() & y.notna()
    together = float(np.corrcoef(x[both], y[both])[0, 1]) if both.sum() >= 30 and x[both].std() and y[both].std() else 0.0
    if f is None or f["p_value"] > SCENARIO_P or fit["r2"] < SCENARIO_R2:
        return "drop", None, _s("ev.no.link", "The projection finds no clear link between the two: scenarios on it would be guesses.")
    if not np.isfinite(together) or abs(together) < SCENARIO_TOGETHER:
        return "drop", None, _s("ev.no.volume", "The two rise and fall together only because busier periods hold more of "
                                                "everything; row by row they are not linked.")
    return "keep", _ev("strong" if abs(together) >= 0.6 and fit["r2"] >= 0.6 else "moderate", abs(together), "scenario",
                       r2=fit["r2"], p_value=f["p_value"], together=round(together, 3)), \
        _s("ev.scenario", "The two are linked row by row ({r}), and the projection explains {r2} of the past.",
           r=f"{together:+.2f}", r2=f"{fit['r2']:.0%}")


def _stages(card: dict, df: pd.DataFrame, meta) -> tuple[str, dict | None, str]:
    """Pick the stage column the ROWS say is one: the category whose values
    best separate rows still going from finished ones."""
    from .. import semantic_guard as guard
    p = card["action"]["params"]
    done = p.get("done_date")
    if done not in df.columns:
        return "keep", None, ""
    is_open = pd.to_datetime(df[done], errors="coerce").isna()
    best, best_sep = None, -1.0
    for c in df.columns:
        s = df[c]
        if c in (p.get("start_date"), done, p.get("due_date")) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            continue
        if guard.is_identifier(c, meta) or not (2 <= s.nunique(dropna=True) <= 12):
            continue
        share = is_open.groupby(s.astype(str)).agg(["mean", "count"])
        share = share[share["count"] >= STAGE_MIN_ROWS]
        if len(share) < 2:
            continue
        sep = float(share["mean"].max() - share["mean"].min())
        if sep > best_sep:
            best, best_sep = c, sep
    if best is None or best_sep < STAGE_SEPARATES:
        return "drop", None, _s("ev.no.stages", "No column separates the rows still going from the finished ones, "
                                                "so there are no stages to show.")
    if best != p["stage_col"]:
        was = p["stage_col"]
        p["stage_col"] = best
        card["fields"] = [best if f == was else f for f in card.get("fields", [])]
        title = _s("card.stage.t", "Where rows stand, by {c}", c=_col(best))
        card["title"], card["title_i18n"] = str(title), title.as_i18n()
    keep = [i for i, l in enumerate(card.get("limits", [])) if "picked from the table's shape" not in l]
    said = card.get("limits_i18n") or [None] * len(card.get("limits", []))
    card["limits"] = [card["limits"][i] for i in keep]
    card["limits_i18n"] = [said[i] if i < len(said) else None for i in keep]
    return "keep", _ev("strong" if best_sep >= 0.9 else "moderate", best_sep, "stages",
                       separates=round(best_sep, 3), open_rows=int(is_open.sum())), \
        _s("ev.stages", "{col} separates the {n} rows still going from the finished ones.",
           col=_col(best), n=f"{int(is_open.sum()):,}")


def _latest_change(card: dict, df: pd.DataFrame, _meta) -> tuple[str, dict | None, str]:
    p = card["action"]["params"]
    date, measure = p.get("date_column"), p.get("measure")
    if date not in df.columns or measure not in df.columns:
        return "keep", None, ""
    dt = pd.to_datetime(df[date], errors="coerce")
    v = pd.to_numeric(df[measure], errors="coerce")
    keep = dt.notna() & v.notna()
    monthly = v[keep].groupby(dt[keep].dt.to_period("M")).sum()
    if keep.any() and dt[keep].max().day != dt[keep].max().days_in_month and len(monthly) > 1:
        monthly = monthly.iloc[:-1]
    if len(monthly) < 6:
        return "keep", None, ""
    steps = monthly.diff().dropna().abs()
    usual = float(steps.iloc[:-1].median())
    last = float(monthly.iloc[-1] - monthly.iloc[-2])
    if usual <= 0:
        return "keep", None, ""
    times = abs(last) / usual
    if times < CHANGE_MODERATE:
        return "keep", None, ""
    return "keep", _ev(_band(times, CHANGE_MODERATE, CHANGE_STRONG), min(times / 8, 1.0), "change",
                       times_usual=round(times, 1), period=str(monthly.index[-1])), \
        _s("ev.change.up" if last > 0 else "ev.change.down",
           "{period} moved {times} times as much as a usual month does (up)." if last > 0 else
           "{period} moved {times} times as much as a usual month does (down).",
           period=str(monthly.index[-1]), times=f"{times:.1f}")


def _which(card: dict):
    action = card.get("action") or {}
    cap, cfg = card.get("capability"), action.get("config") or {}
    if card.get("evidence") is not None:
        return None                                         # already found on the rows
    if cap == "explain_variance" or cfg.get("bridge_from") or cfg.get("difference_of"):
        return _pair
    if cap == "compare_two_groups":
        return _two_groups
    if cap == "compare_scenarios":
        return _scenarios
    if cap == "stage_board":
        return _stages
    if cap == "explain_change":
        return _latest_change
    grain2 = cfg.get("dimension2_granularity")
    if action.get("kind") == "add_widget" and cfg.get("dimension") == cfg.get("dimension2"):
        if grain2 == "hour_of_day":
            return _weekly_rhythm
        if grain2 in ("year", "month_of_year"):
            return _yearly_season
    return None


def look(cards: list[dict], df: pd.DataFrame, column_meta: dict | None) -> tuple[list[dict], list[dict]]:
    """(the cards worth offering, the ones withheld with their reasons)."""
    from .profile import sample_rows
    cap = sample_rows()
    frame = df if len(df) <= cap else df.sample(cap, random_state=0)
    kept, withheld = [], []
    for card in cards:
        check = _which(card)
        if check is None:
            kept.append(card)
            continue
        try:
            verdict, evidence, sentence = check(card, frame, column_meta)
        except Exception:                                   # noqa: BLE001 -- a check never loses a card
            logger.warning("discovery: evidence check failed for %s", card.get("capability"), exc_info=True)
            kept.append(card)
            continue
        if verdict == "drop":
            withheld.append({"capability": card.get("capability"), "title": card.get("title"), "reason": str(sentence),
                             "reason_i18n": sentence.as_i18n() if isinstance(sentence, Said) else None,
                             "fields": card.get("fields", [])})
            continue
        if evidence is not None:
            card["evidence"] = evidence
            card["why"] = {"reason": "evidence", "detail": str(sentence)}
            card["found"] = str(sentence)
            card["found_i18n"] = sentence.as_i18n() if isinstance(sentence, Said) else None
        kept.append(card)
    return kept, withheld
