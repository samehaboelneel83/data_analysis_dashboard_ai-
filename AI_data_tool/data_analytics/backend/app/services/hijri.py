"""Hijri dates for time axes (Phase 7.5, Arabic formats).

The TABULAR (arithmetic, "Kuwaiti") Islamic calendar: deterministic and
offline, which a chart needs -- the same date always lands in the same bucket.
Official Umm al-Qura dates follow moon sighting and can differ by a day at a
month boundary; the axis says "tabular Hijri" so nobody reads it as the
official calendar.

Labels are `1448-03` -- year and zero-padded month -- so they sort as text
(which is how every chart orders categories); the client names the month.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MONTHS_AR = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة",
             "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"]
MONTHS_EN = ["Muharram", "Safar", "Rabiʿ I", "Rabiʿ II", "Jumada I", "Jumada II",
             "Rajab", "Shaʿban", "Ramadan", "Shawwal", "Dhu al-Qaʿda", "Dhu al-Hijja"]


def _jdn(dt: pd.Series) -> np.ndarray:
    """Julian day number of each (naive) date."""
    return (dt.dt.normalize().astype("int64") // 86_400_000_000_000 + 2440588).to_numpy()


def to_hijri(dt: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(year, month, day) arrays; NaT rows come back as -1."""
    valid = dt.notna().to_numpy()
    jd = np.where(valid, _jdn(dt.fillna(pd.Timestamp("2000-01-01"))), 2451545)
    l = jd - 1948440 + 10632
    n = (l - 1) // 10631
    l = l - 10631 * n + 354
    j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
    l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l) // 709
    d = l - (709 * m) // 24
    y = 30 * n + j - 30
    return (np.where(valid, y, -1), np.where(valid, m, -1), np.where(valid, d, -1))


def hijri_label(dt: pd.Series, granularity: str) -> pd.Series:
    y, m, _ = to_hijri(dt)
    if granularity == "hijri_year":
        out = pd.Series([str(v) if v > 0 else None for v in y], index=dt.index, dtype=object)
    else:
        out = pd.Series([f"{a}-{b:02d}" if a > 0 else None for a, b in zip(y, m)], index=dt.index, dtype=object)
    return out
