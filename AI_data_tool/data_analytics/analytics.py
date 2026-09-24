"""
Analytics Service — type detection, descriptive stats, outlier detection,
categorical analysis, datetime analysis, correlation.
"""
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
from scipy.stats import chi2_contingency
from pathlib import Path


SUPPORTED = {".csv": pd.read_csv, ".xlsx": pd.read_excel,
             ".xls": pd.read_excel, ".json": pd.read_json, ".parquet": pd.read_parquet}


def load_file(path: str) -> pd.DataFrame:
    p = Path(path)
    reader = SUPPORTED.get(p.suffix.lower())
    if not reader:
        raise ValueError(f"Unsupported file type: {p.suffix}")
    return reader(p)


def _safe(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)): return None if np.isnan(v) else float(v)
    if isinstance(v, float) and np.isnan(v): return None
    return v


def detect_types(df: pd.DataFrame) -> dict[str, str]:
    type_map = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            type_map[col] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(s):
            type_map[col] = "datetime"
        else:
            try:
                parsed = pd.to_datetime(s, infer_datetime_format=True)
                if parsed.notna().sum() / max(len(s), 1) > 0.8:
                    df[col] = parsed
                    type_map[col] = "datetime"
                    continue
            except Exception:
                pass
            ratio = s.nunique() / max(len(s.dropna()), 1)
            type_map[col] = "categorical" if (ratio < 0.5 or s.nunique() <= 30) else "text"
    return type_map


def analyze_numeric(df: pd.DataFrame, cols: list[str]) -> dict:
    if not cols:
        return {}
    result = {"columns": {}}
    for col in cols:
        s = df[col].dropna()
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
        corr = df[cols].corr(method="pearson").round(4)
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


def analyze_datetime(df: pd.DataFrame, cols: list[str]) -> dict:
    if not cols:
        return {}
    result = {"columns": {}}
    for col in cols:
        s = df[col].dropna().sort_values()
        diffs = s.diff().dropna()
        info = {
            "min": str(s.min()), "max": str(s.max()),
            "range_days": int((s.max()-s.min()).days),
            "n_values": int(len(s)), "n_unique": int(s.nunique()),
            "gaps_over_7d": int((diffs > pd.Timedelta(days=7)).sum()),
        }
        if s.dt.month.nunique() > 1:
            monthly = s.dt.to_period("M").value_counts().sort_index()
            info["monthly_counts"] = [{"period": str(k), "count": int(v)} for k,v in monthly.items()]
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
