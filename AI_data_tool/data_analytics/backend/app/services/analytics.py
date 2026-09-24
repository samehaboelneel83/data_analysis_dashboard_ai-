"""
Analytics Service - descriptive stats, outlier detection, categorical
analysis, datetime analysis, correlation.

Layer 5. Reading a file and typing its columns used to live here too; that half
is now `ingest.py` (layer 2), and is re-exported below for the call sites that
still import it from this module.
"""
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
from scipy.stats import chi2_contingency
from pathlib import Path

# ── ingestion, moved to ingest.py ─────────────────────────────────────────────
# `SUPPORTED`, `load_file` and `detect_types` are layer-2 ingestion concerns and
# now live in ingest.py. They are re-exported here under their original names
# because eighteen call sites import them from this module; new code should
# import from `.ingest` directly.
from .ingest import SUPPORTED, detect_types, load_file  # noqa: F401,E402


def _safe(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)): return None if np.isnan(v) else float(v)
    if isinstance(v, float) and np.isnan(v): return None
    return v


def _numeric_series(s: pd.Series) -> pd.Series:
    """Drop nulls and coerce booleans to 0/1.

    pandas reports is_numeric_dtype(bool) as True, so detect_types files a
    boolean column under "numeric" -- but numpy refuses to compute a percentile
    over booleans ("numpy boolean subtract ... is not supported"), which turns
    a whole dataset's analysis into a 500.

    Cast rather than skip: the statistics are then genuinely useful, since the
    mean of a 0/1 column is the proportion that are true. Object-dtype columns
    holding True/False/None (how a Postgres boolean arrives) are covered too.
    """
    s = s.dropna()
    if pd.api.types.is_bool_dtype(s):
        return s.astype("int8")
    if s.dtype == object and len(s) and all(isinstance(v, bool) for v in s):
        return s.astype("int8")
    return s


def analyze_numeric(df: pd.DataFrame, cols: list[str]) -> dict:
    if not cols:
        return {}
    result = {"columns": {}}
    for col in cols:
        s = _numeric_series(df[col])
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        outliers = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
        result["columns"][col] = {
            "count": _safe(s.count()), "mean": _safe(s.mean()), "std": _safe(s.std()),
            "min": _safe(s.min()), "p5": _safe(s.quantile(.05)), "p25": _safe(q1),
            "median": _safe(s.median()), "p75": _safe(q3), "p95": _safe(s.quantile(.95)),
            "max": _safe(s.max()), "sum": _safe(s.sum()), "variance": _safe(s.var()),
            "skew": _safe(s.skew()), "kurtosis": _safe(s.kurtosis()),
            "iqr_outliers": outliers,
            "missing_pct": round(df[col].isnull().mean() * 100, 2),
            "cv": _safe(s.std() / s.mean()) if s.mean() != 0 else None,
        }
    if len(cols) >= 2:
        corr = df[cols].apply(_numeric_series).corr(method="pearson").round(4)
        result["correlation"] = {c: {r: _safe(corr.loc[c, r]) for r in corr.columns} for c in corr.index}
    return result


def analyze_categorical(df: pd.DataFrame, cols: list[str], top_n: int = 15) -> dict:
    if not cols:
        return {}
    result = {"columns": {}, "chi2_tests": []}
    for col in cols:
        s = df[col]
        vc = s.value_counts(dropna=False).head(top_n)
        probs = s.value_counts(normalize=True).values
        entropy = float(-np.sum(probs * np.log2(probs + 1e-12)))
        result["columns"][col] = {
            "top_values": [{"value": str(k), "count": int(v), "pct": round(int(v)/max(len(s),1)*100,2)} for k,v in vc.items()],
            "n_unique": int(s.nunique()), "entropy": round(entropy, 4),
            "missing_pct": round(s.isnull().mean()*100, 2),
            "mode": str(s.mode().iloc[0]) if len(s.mode()) else None,
        }
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            ct = pd.crosstab(df[cols[i]], df[cols[j]])
            if ct.size == 0: continue
            chi2, p, dof, _ = chi2_contingency(ct)
            result["chi2_tests"].append({
                "col_a": cols[i], "col_b": cols[j],
                "chi2": round(float(chi2),4), "p_value": round(float(p),6),
                "dof": int(dof), "significant": bool(p < 0.05),
            })
    return result


_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def analyze_datetime(df: pd.DataFrame, cols: list[str]) -> dict:
    """Profile date/datetime columns: range, density over time, weekday shape,
    and whether the column carries times at all.

    Coerces its own input: CSV-loaded frames carry dates as STRINGS, and this
    function used to work only because detect_types happened to convert columns
    in place before it ran -- a side-effect dependency that made every direct
    caller crash with `str - str`. Coercion here makes the function correct on
    the frame it is actually given.
    """
    if not cols:
        return {}
    result = {"columns": {}}
    for col in cols:
        raw = df[col]
        s = pd.to_datetime(raw, errors="coerce").dropna().sort_values()
        if s.empty:
            result["columns"][col] = {"note": "no parseable date values"}
            continue
        diffs = s.diff().dropna()
        weekday = s.dt.dayofweek.value_counts()
        # date vs datetime: a column whose every value sits at midnight carries
        # dates; any nonzero time-of-day makes it a true datetime.
        has_time = bool(((s.dt.hour != 0) | (s.dt.minute != 0) | (s.dt.second != 0)).any())
        info = {
            "min": str(s.min()), "max": str(s.max()),
            "range_days": int((s.max() - s.min()).days),
            "n_values": int(len(s)), "n_unique": int(s.nunique()),
            "missing_pct": round(float(raw.isna().mean() * 100)
                                 + float((len(raw.dropna()) - len(s)) / max(len(raw), 1) * 100), 2),
            "gaps_over_7d": int((diffs > pd.Timedelta(days=7)).sum()),
            "granularity": "datetime" if has_time else "date",
            "weekday_counts": [{"day": _WEEKDAYS[i], "count": int(weekday.get(i, 0))}
                               for i in range(7)],
        }
        if has_time:
            hourly = s.dt.hour.value_counts()
            info["hour_counts"] = [{"hour": h, "count": int(hourly.get(h, 0))} for h in range(24)]
        if s.dt.to_period("M").nunique() > 1:
            monthly = s.dt.to_period("M").value_counts().sort_index()
            info["monthly_counts"] = [{"period": str(k), "count": int(v)} for k, v in monthly.items()]
            busiest = monthly.idxmax()
            info["busiest_period"] = {"period": str(busiest), "count": int(monthly.max())}
        result["columns"][col] = info
    return result


def run_full_analysis(df: pd.DataFrame) -> dict:
    type_map = detect_types(df)
    num_cols = [c for c,t in type_map.items() if t == "numeric"]
    cat_cols = [c for c,t in type_map.items() if t == "categorical"]
    dt_cols  = [c for c,t in type_map.items() if t == "datetime"]
    return {
        "type_map":    type_map,
        "numeric":     analyze_numeric(df, num_cols),
        "categorical": analyze_categorical(df, cat_cols),
        "datetime":    analyze_datetime(df, dt_cols),
        "overview": {
            "rows": len(df), "cols": len(df.columns),
            "missing_pct": round(df.isnull().mean().mean()*100, 2),
            "type_counts": pd.Series(type_map).value_counts().to_dict(),
        },
    }
