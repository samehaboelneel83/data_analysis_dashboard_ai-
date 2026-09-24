"""A1: uniform internal contract for analysis services.

Every analysis service (today: the descriptive `run_full_analysis` profile;
tier-5 adds segment/forecast/anomaly on top) should build one of these
internally, then the router adapts it to the wire response via
`as_response`. The adapter's job is to keep every EXISTING response byte-
identical while additively attaching the uniform envelope under a `result`
key, so the frontend can migrate to it incrementally without a breaking
change today.

Fields (per the tier-5 plan):
  kind:     str -- the analysis kind, e.g. "full_profile", "segment".
  columns:  list[{"name": str, "dtype": str}] -- the columns the analysis
            ran over, where that concept applies.
  rows:     list[dict] -- row-oriented results (e.g. per-row cluster labels,
            per-point forecast values); `_safe`-cleaned of numpy scalars.
            Empty for analyses (like the current descriptive profile) whose
            output isn't naturally row-shaped -- their detail lives in meta.
  meta:     dict -- params used, method, timings, and (for non-row-shaped
            analyses) the full detail payload under meta["detail"].
  warnings: list[str] -- non-fatal notices surfaced to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np


@dataclass
class AnalysisContract:
    kind: str
    columns: list[dict[str, str]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return safe_clean(asdict(self))


def safe_clean(value: Any) -> Any:
    """Recursively convert numpy scalar types (and NaN floats) to native
    Python so the envelope is always JSON-safe, regardless of what the
    underlying analysis service left behind."""
    if isinstance(value, dict):
        return {k: safe_clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_clean(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def full_profile_to_contract(analysis: dict[str, Any]) -> AnalysisContract:
    """Wrap the existing `run_full_analysis` output (type_map/numeric/
    categorical/datetime/overview[/sampled/total_rows/sample_size]) into the
    uniform contract. This analysis is descriptive/nested rather than
    row-oriented, so `rows` stays empty and the full breakdown lives under
    `meta["detail"]` -- the legacy dict itself is left completely untouched
    for the byte-preserved wire response."""
    type_map = analysis.get("type_map", {}) or {}
    columns = [{"name": name, "dtype": dtype} for name, dtype in type_map.items()]

    detail = {k: v for k, v in analysis.items() if k != "type_map"}
    meta: dict[str, Any] = {
        "method": "full_profile",
        "params": {},
        "detail": detail,
    }
    if "sampled" in analysis:
        meta["params"]["sampled"] = analysis["sampled"]
    if "total_rows" in analysis:
        meta["params"]["total_rows"] = analysis["total_rows"]
    if "sample_size" in analysis:
        meta["params"]["sample_size"] = analysis["sample_size"]

    return AnalysisContract(kind="full_profile", columns=columns, rows=[], meta=meta, warnings=[])


def as_response(analysis: dict[str, Any]) -> dict[str, Any]:
    """Backward-compat adapter for the `/datasets/{id}/analysis` endpoints.

    Returns the ORIGINAL wire dict, byte-for-byte, with one additional key:
    `result`, carrying the uniform AnalysisContract envelope. Existing
    frontend consumers reading the legacy top-level keys are unaffected;
    new consumers can read `result` instead.
    """
    contract = full_profile_to_contract(analysis)
    return {**analysis, "result": contract.to_dict()}
