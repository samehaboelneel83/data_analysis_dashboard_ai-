# Tier 5 — Analysis Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Close Layer 5's remaining gaps: uniform `AnalysisResult` contract, scikit-learn segmentation with automatic k, StatsForecast forecasting, PyOD anomaly detection, and the `registry.py` tool catalogue — plus the parked `_run_alembic` self-heal (load-bearing for air-gapped ops).

**Deployment constraint (binding):** production is air-gapped. All ML deps resolve at image build; no model downloads at runtime (verify none of the chosen libraries phone home or lazy-download — StatsForecast/sklearn/PyOD are pure-compute, but ASSERT it: no network calls in the analysis paths).

## Global Constraints

- models.py / main.py / config.py BOM utf-8-sig — preserve.
- No schema changes expected; if one appears, alembic revision chained on 0008 (id ≤32) + `_migrate` parity.
- Existing API response shapes must not break the frontend: the contract wraps internally; response models evolve additively (new fields OK, removals/renames NOT, unless the task also updates every frontend consumer + tests in the same batch).
- Docker pytest from PowerShell ONLY: `docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <paths> -q --no-header -p no:warnings`. Rebuild the test image after requirements changes; escalate to the controller if a build fails (registry flakes happen — retry with `--pull=false` first).
- TDD; deterministic tests (fixed seeds for ML — `random_state`/seed every stochastic call); commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- New heavy deps allowed this tier: `scikit-learn`, `statsforecast`, `pyod` — pinned, mutually compatible with the numpy/pandas pins already present (CHECK the resolver: statsforecast pulls numba/llvmlite — verify the pinned numpy is in numba's supported range BEFORE committing to versions; if numba's ceiling conflicts with the repo's numpy, ledger-escalate rather than bumping numpy silently).

### Task A1: Uniform AnalysisResult contract + alembic self-heal

**Files:** new `backend/app/services/analysis_contract.py`; adapt the analysis services/router (grep `routers/analysis.py` + the services it calls — inventory every distinct result shape first and LIST them in your report); `backend/app/main.py` (`_run_alembic` self-heal); tests.

- Contract dataclass/TypedDict: `kind` (str), `columns` (list[{name, dtype}]), `rows` (list[dict], `_safe`-cleaned), `meta` (dict: params used, method, timings), `warnings` (list[str]). One helper `as_response(result)` producing the CURRENT wire shape per endpoint (backward-compat adapter) plus the new uniform envelope under a `result` key added ADDITIVELY where the frontend can migrate later. Every analysis service returns the contract internally; the router adapts.
- Self-heal: in `_run_alembic`, when `upgrade head` fails AND the failure is a DuplicateTable/DuplicateColumn class error, verify head-equivalence cheaply (every table name in `Base.metadata` exists) and then `stamp head` with a loud WARNING log naming the drift; any other failure keeps today's log-and-continue. Tests: simulated drift (create_all'd DB + version pinned behind) self-heals to head on next boot; a genuinely broken revision (non-duplicate error) does NOT stamp.

### Task A2: segment — clustering with automatic k

**Files:** requirements (+scikit-learn pinned); new `backend/app/services/analysis/segment.py` (or the pattern the analysis services dir uses — mirror it); router endpoint (grep how existing analysis endpoints register: same auth/org/RLS discipline — analysis runs on the RLS-filtered base frame like everything else); frontend surface where analysis results render (grep the analysis UI) gains a Segment option.

- KMeans over selected numeric columns (standardized), k chosen by silhouette score over k=2..min(8, n//10) (documented), `random_state=42`; result: per-row cluster labels + per-cluster centroid summary rows + silhouette in meta; graceful 400 on <2 usable numeric columns or too few rows. Optionally upgrade `shape_geo_clusters` call sites — ONLY if trivially compatible; else leave and note.
- Tests: value-pinned on a synthetic 3-blob fixture (k found == 3, labels stable with seed); RLS pin (restricted user segments only their rows); degenerate inputs 400.

### Task A3: forecast (StatsForecast) + anomaly (PyOD)

**Files:** requirements (+statsforecast, +pyod, pinned per the numba caveat above); the existing `shape_forecast` (services/widget_data.py ~1114) gains a `method` option: `ets` (default, NEW — StatsForecast AutoETS) vs `simple` (the existing hand-rolled smoothing, kept as fallback and for parity tests); anomaly: the existing IQR path (grep `iqr`/anomaly in analysis services) gains PyOD detectors (`iforest` default, `ecod` option) behind the SAME endpoint with a `detector` param defaulting to the CURRENT behavior (`iqr`) so nothing changes silently.
- StatsForecast usage: fit per-series on the shaped frame, horizon from the existing param, confidence intervals into the result (additive fields). Import LAZILY inside the method branch (numba import cost ~seconds — never pay it at app startup; test asserts `statsforecast` not in sys.modules after boot).
- Tests: deterministic seeds; ets on a seasonal synthetic series beats `simple` on MAE (value-pinned tolerance, fixed data); intervals present and ordered (lo≤point≤hi); pyod iforest flags the planted outliers on a synthetic fixture, iqr path byte-identical to before; lazy-import pin.

### Task A4: registry.py — analysis tool catalogue

**Files:** new `backend/app/services/analysis/registry.py`; wire into the agent context/prompt (grep where the agent learns capabilities — likely a static prompt section) and expose `GET /analysis/registry` (org-authenticated).
- Registry: machine-readable list of analysis capabilities — name, description, params schema (JSON-schema-ish dict), result kind — POPULATED FROM the actual services (segment, forecast methods, anomaly detectors, existing analyses inventoried in A1). Single source of truth: each analysis module registers itself; the endpoint and the agent prompt section render from the same registry. Agent prompt: a compact "Analyses available:" block (budget-aware — reuse the render budget discipline; cap the block, it's small anyway).
- Tests: registry contains segment/forecast/anomaly with correct param schemas; endpoint authenticated; prompt block renders and stays under its cap; adding a fake registered analysis appears everywhere (single-source test).

**Batching:** B1: A1 · B2: A2 · B3: A3 · B4: A4 · final review + image rebuilds (test + live) + merge.
