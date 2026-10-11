"""Reading a series of periods: what was expected, what fell outside it, and
where the level changed (docs/discovery/PLAN.md, phase 3: #4 and #18).

Pure functions over a list of numbers in time order -- one value per period,
already aggregated by whoever calls (a chart's own rows, an insight scan). No
library beyond numpy: these run wherever the platform does, offline.

EXPECTED RANGE. For each period, from the periods BEFORE it only (a value is
never judged against itself or the future):
  * with a season (days of a week, months of a year) and enough history, the
    same phase of earlier cycles -- Mondays against Mondays;
  * otherwise the last few periods, carried forward along their own trend, so
    a series that simply grows is not "unusual" every period.
The range is the centre plus or minus a multiple of the typical deviation,
both taken robustly (median, median absolute deviation): one earlier spike
does not widen the range that judges the next one.

CHANGE OF LEVEL. The one split of the series whose two sides differ most,
kept only when shuffling the order almost never produces as big a difference
and the shift is large enough to matter.

What these say is an OBSERVATION ("outside its usual range", "the level
changed from here"). They never say why.
"""
from __future__ import annotations

import math

import numpy as np

#: How many typical deviations from the centre still count as usual.
BAND_K = 3.0
#: Periods looked back at when there is no season to follow.
WINDOW = 12
#: Earlier periods needed before a period can be judged at all.
MIN_HISTORY = 6
#: Earlier cycles at the same phase used, and the fewest that make a season usable.
SEASON_CYCLES, SEASON_MIN = 8, 4
#: The range is never narrower than this share of the centre: a perfectly
#: steady history would otherwise flag every rounding difference.
FLOOR_SHARE = 0.05
#: A change of level: each side at least this long, at least this relative
#: shift, and no more likely than this to arise from the order alone.
MIN_SEGMENT, MIN_SHIFT, CHANGE_ALPHA = 4, 0.10, 0.01
PERMUTATIONS = 400
_SEED = 42

#: How many periods make one cycle, by the size of a period.
SEASON = {"day": 7, "month": 12, "quarter": 4}


def season_of(granularity: str | None, periods: int) -> int | None:
    """The cycle to compare against, when the series is long enough to hold
    at least SEASON_MIN + 1 of them."""
    s = SEASON.get(str(granularity or "").lower())
    return s if s and periods >= s * (SEASON_MIN + 1) else None


def _mad(x: np.ndarray, centre: float) -> float:
    return float(np.median(np.abs(x - centre))) * 1.4826


def _trend(w: np.ndarray) -> tuple[float, float]:
    """(slope, intercept) of the window by the median of pairwise slopes."""
    n = len(w)
    idx = np.arange(n, dtype=float)
    i, j = np.triu_indices(n, 1)
    slope = float(np.median((w[j] - w[i]) / (idx[j] - idx[i]))) if n > 1 else 0.0
    return slope, float(np.median(w - slope * idx))


def expected_band(values: list[float | None], season: int | None = None, k: float = BAND_K) -> list[dict | None]:
    """For each period: {"expected", "lo", "hi"} from earlier periods, or None
    while there is too little history to say."""
    y = np.array([np.nan if v is None else float(v) for v in values], dtype=float)
    out: list[dict | None] = []
    for t in range(len(y)):
        centre = spread = None
        if season:
            same = y[max(t - season * SEASON_CYCLES, t % season):t:season]
            same = same[~np.isnan(same)]
            if len(same) < SEASON_MIN:
                # A series with a rhythm is not judged before enough cycles
                # have passed: against its last few periods a weekend would be
                # "unusual" every week.
                out.append(None)
                continue
            centre = float(np.median(same))
            spread = _mad(same, centre)
        if centre is None:
            w = y[max(0, t - WINDOW):t]
            w = w[~np.isnan(w)]
            if len(w) < MIN_HISTORY:
                out.append(None)
                continue
            slope, intercept = _trend(w)
            centre = intercept + slope * len(w)                 # carried one period forward
            spread = _mad(w - slope * np.arange(len(w)), intercept)
        spread = max(spread, FLOOR_SHARE * abs(centre), 1e-9)
        out.append({"expected": centre, "lo": centre - k * spread, "hi": centre + k * spread})
    return out


def anomalies(values: list[float | None], band: list[dict | None]) -> list[dict]:
    """The periods outside their expected range: index, value, the range, which
    side, and how far outside in typical deviations."""
    found = []
    for i, (v, b) in enumerate(zip(values, band)):
        if v is None or b is None:
            continue
        if b["lo"] <= float(v) <= b["hi"]:
            continue
        half = (b["hi"] - b["lo"]) / 2 or 1e-9
        found.append({"index": i, "value": float(v), "expected": b["expected"], "lo": b["lo"], "hi": b["hi"],
                      "side": "above" if float(v) > b["hi"] else "below",
                      "deviations": round(abs(float(v) - b["expected"]) / (half / BAND_K), 1)})
    return found


def change_point(values: list[float | None]) -> dict | None:
    """The one place the LEVEL of the series changes, or None.

    {"index" (first period of the new level), "before", "after", "shift",
    "shift_pct", "p_value"}. Deterministic: the shuffles are seeded."""
    y = np.array([float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    n = len(y)
    if n < 2 * MIN_SEGMENT:
        return None

    def best(series: np.ndarray) -> tuple[float, int]:
        top, at = 0.0, -1
        total, csum = series.sum(), np.cumsum(series)
        for i in range(MIN_SEGMENT, len(series) - MIN_SEGMENT + 1):
            left, right = csum[i - 1] / i, (total - csum[i - 1]) / (len(series) - i)
            stat = abs(right - left) * math.sqrt(i * (len(series) - i) / len(series))
            if stat > top:
                top, at = stat, i
        return top, at

    stat, at = best(y)
    if at < 0:
        return None
    before, after = float(y[:at].mean()), float(y[at:].mean())
    base = abs(before) or abs(after) or 1.0
    if abs(after - before) / base < MIN_SHIFT:
        return None
    rng = np.random.default_rng(_SEED)
    beaten = sum(best(rng.permutation(y))[0] >= stat for _ in range(PERMUTATIONS))
    p = (beaten + 1) / (PERMUTATIONS + 1)
    if p > CHANGE_ALPHA:
        return None
    return {"index": int(at), "before": before, "after": after, "shift": after - before,
            "shift_pct": (after - before) / base * 100, "p_value": round(float(p), 4)}
