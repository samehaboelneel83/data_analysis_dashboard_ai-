# Discovery engine — a domain-neutral platform that knows what is worth analysing

Date: 2026-10-10 · Branch: `emad` · **Phase 0 (§K) and the phase 1 slice (§L) built and tested 2026-10-11, uncommitted. Phases 2–6 are not started.**
Builds on [../suggestions/PLAN.md](../suggestions/PLAN.md) (stored column classification, shared gate, neutral vocabulary — built the same day, uncommitted).

Scope set by the owner: the engine, not the screens ("do not care about UI/UX"). The reference screenshots are read as **a list of things the platform must be able to suggest** (§4).

How to read this: every statement about the code is marked **[verified]** (read in the repository on 2026-10-10, with the file) or **[assumed]**. Recommendations are not marked; they are the rest.

---

## A. Current-state assessment

### A1. What exists (verified)

**Data access**
- 45+ connector specs in `services/connectors.py` (`_ALL_SPECS`): PostgreSQL-wire ×16, MySQL-wire ×11, SQL Server, Oracle, SQLite, DuckDB file, ClickHouse, Access, warehouses (Snowflake, BigQuery, Databricks, Trino — URL-only, import-only), generic SQLAlchemy/ODBC/API. **No Athena.** No ClickHouse/Snowflake/BigQuery driver is pinned in `requirements.txt`; the operator installs it.
- Upload formats (`services/ingest.py: SUPPORTED`): CSV, XLSX, XLS, JSON, Parquet, XML, Access containers.
- Two dataset modes. **Import**: a CSV on disk plus a Parquet sidecar, read whole into pandas through `frame_cache.get_frame` (process-local LRU, 8 frames / 1.5 GB, every hit a deep copy). **DirectQuery**: `services/direct_query.py` pushes down GROUP BY for a fixed set of widget types, count series, paged tables and KPI re-measure; histogram and correlation matrix are pushed down on PostgreSQL only; everything else falls back to `SELECT *` with a random sample above a cap (10,000 rows to draw, `analysis_row_cap = 250,000` to analyse).
- DuckDB is already in the path: `services/duck_agg.py` aggregates the Parquet sidecar before pandas is touched (`widget_duckdb_pushdown = True`), for plain series widgets without preparation steps or calculated columns.
- Multi-table: `SourceRelationship` (declared / inferred / confirmed, with cardinality), FK inference by sample overlap (`metadata/infer_keys.py`), `services/query_builder.py` with joins, sub-queries and recursive CTEs.
- Security in the query path: row rules and hidden columns (`core/rls.py`, fail-closed), read-only SQL enforcement by parsing (`services/sql_safety.py`, sqlglot), `QueryRun` log, audit log, per-organisation quotas, statement timeouts (server-side on PostgreSQL; MySQL read timeout; **none on SQL Server or Oracle**).

**Analyses** — one catalogue already exists: `services/analysis/registry.py` (`AnalysisSpec`: name, description, JSON-schema parameters, result kind, lazy handler), served at `GET /analysis/registry`, run by `POST /datasets/{id}/analysis/run`.

| Family | Present | Library |
|---|---|---|
| Profiling | numeric stats, categorical top values, date ranges and gaps; quality report (missing, duplicates, numbers stored as text, placeholder codes, whitespace, author rules) | pandas, scipy |
| Statistics | group comparison (Welch t / ANOVA + effect size), chi-square, correlation with p-value, OLS, logistic GLM, mixed model, Cox survival, pairwise post-hoc with FDR | scipy, statsmodels |
| Discovery | six insight detectors + rates and gradients (`services/insights.py`), key influencers, relative importance (`services/explain.py`), association rules (own apriori, `analysis/patterns.py`) | pandas |
| ML | k-means segmentation with silhouette, shallow decision tree, automated prediction bake-off (dummy / linear / tree / forest on a holdout), stored models with scoring and PSI drift (`analysis/model_store.py`) | scikit-learn |
| Time | forecast with 95% interval (AutoETS → Holt-Winters → linear), forecast-vs-goal, goal seek, forecast scenario (what-if on factors) | statsforecast, statsmodels |
| Anomaly | univariate: IQR, IsolationForest, ECOD | pyod |
| Text | TF-IDF + NMF topics, lexicon sentiment, Arabic-aware | scikit-learn |
| Graph | degree / closeness / betweenness inside the `network` widget | numpy |

**Widgets** — 75 types (basic, two-measure, matrix, tables, 10 map types, flow/graph, 6 hierarchy, 7 model widgets, controls).

**Suggestion machinery** — five engines (browser heuristics, insights → widgets, dataset designer + analyst panel, connection designer, guided setup), now sharing: the stored column classification (`services/column_classes.py`, read through `services/semantic_guard.py`), one refusal gate (`services/suggest_gate.py`), a deterministic one-sentence reader of any drawn result (`services/readback.py: takeaway`), server-side feedback (`SuggestionFeedback`), and a probe that draws every suggestion on the secured rows before offering it.

**Background work** — durable jobs in the database (`services/jobs.py`: lease, heartbeat, cooperative cancel, retry; handlers include `suggest_jobs`), a refresh scheduler, an automation loop. In-process asyncio; no external queue.

**LLM** — every call goes through `services/llm.py` (`LLMClient.complete_json` with schema enforcement, never raises, returns `None` when off); endpoint routing by weight and strength (`services/llm_endpoints.py`); per-organisation token metering.

### A2. What is missing or weak (verified)

1. **No single description of what a widget needs.** Five parallel tables: `frontend/src/types/report.ts` (roles, optional roles, which roles are numeric/date), `services/widget_roles.py` (required roles only), `widget_data.SHAPERS`, `suggest_dataset_dashboard.WIDGET_GUIDE` (prose for the model; no entry for 5 types), the browser renderer map. None records minimum rows, cost, supported back-ends or whether a model is needed. Each analysis keeps its own `MIN_ROWS` constant in its own file.
2. **Nothing about a dataset is remembered between requests.** `DatasetColumn.stats` is written as `{}` at every creation site and never filled. `build_profile` and `generate_insights` recompute on the full frame on every call; there is no result cache for profile or insights. The PostgreSQL statistics readers (`metadata/profile.py: from_pg_stats_row`, `build_profile_sql`) **have no caller** outside tests; connection profiling uses a 1,000-row sample.
3. **Large data is bounded by memory, not by design.** Import data is a whole pandas frame, deep-copied per request, in a cache that is per worker process. The DirectQuery fallback is `SELECT *` with `ORDER BY RANDOM()` — a full scan and no column pruning.
4. **Methods the reference screenshots need and the platform does not have:** time-series anomaly with an expected band; change-point detection; model-agnostic feature importance (SHAP or permutation); a 2-D projection of clusters (PCA exists only as a preparation step); multivariate anomaly; cohort/retention; Pareto; radar; scatter-plot matrix; KPI with sparkline and change against the previous period; per-column validity profile (valid / mistyped / string lengths / patterns); a rule network for association rules (rules and the generic network widget both exist, unconnected); Monte-Carlo simulation; any optimisation or solver link; a summary of a whole dashboard.
5. **The LLM is mandatory in places and unguarded in others.**
   - Ask AI **fails** without a model (`agent/nodes/classify.py` has no fallback; `graph.py` ends the run). The page copilot returns HTTP 502.
   - The per-connection switch `allow_llm_sampling` is honoured only by metadata sync and the guided setup. Ask AI, the copilot, the analyst panel, both designers, `source_brief`, `widget_review`, insights narration and `column_classes.model_hints` ignore it.
   - `guided_setup/health.py: model_rules` sends `df.head(5)` — five raw rows — to the model; its caller (`routers/guided_setup.py`, the data-check route) takes a client with no gate.
   - **No prompt-injection defence**: cell values, column descriptions and top values are placed in prompts without delimiting or a "this is data" instruction. Protection today is on the output side only (schema, enum re-check, SQL validation, number guards).
   - `model_hints` opens no usage meter of its own.
   - No prompt caching, no batching beyond 40 columns per describe call.
6. **Domain vocabulary remains outside the files cleaned on 2026-10-10** — see A3.
7. **Limits not enforced everywhere:** no per-job wall-clock timeout; quotas are per organisation, not per person; benchmarks exist as manual scripts (`backend/scripts/bench_*.py`) and are not run in CI.

### A3. Domain-specific code still present (verified by search; Arabic-only literals and three files not opened — `query_builder.py`, `measure_eval.py`, `direct_query.py`)

| Severity | Where | What |
|---|---|---|
| High — logic | `services/source_brief.py` `_ITEM_NAME` (commodity, product, sku…), `_SIZE_WORDS` (`orders`), `_TOTAL_VALUES` ("both sexes") | word lists from a prices/food-security database |
| High — logic | `services/metadata/infer_semantic.py` `_NAME_SEMANTICS`, `_CONTINUOUS_NAME` (price, revenue, sales, salary, wage, profit…) | catalog-level type guessing by trade nouns |
| High — logic | `services/analyst_panel.py` `_TITLE_AGG` ("headcount" → distinct count) | HR word |
| High — prompts | `services/agent/nodes/classify.py` (~20 few-shot lines: customers, revenue by region, call types, "قسم المبيعات"), `copilot.py` (16), `followup.py` (14), `generate.py` (3), `clarify.py` (1) | Ask AI examples from four sample databases |
| High — prompts | `services/analyst_panel.py` lens briefs ("pay, tenure and size per department", "same department, same title, same hiring year", "pay by title, by gender") | the "equity" lens is an HR analysis written as a general one |
| High — prompts | `services/source_brief.py` `BRIEF_SYSTEM` / `DESIGN_SYSTEM` (subsidies, commodity × month, share of poor people, inflation of staples) | connection designer |
| Medium | `services/agent/validate.py` `_COUNTING` (traffic, busiest), `services/pii.py` `_PLACE_WORDS` (store, branch, warehouse, plant), `frontend/src/pages/Dataflows.tsx` (default name `headcount`, regex with `hire`), two prompt examples in the designers | |
| Low | placeholders and tooltips in ~8 components | examples shown to the user, not logic |

---

## B. Target architecture

No new service and no new database. Four additions to what exists, each replacing duplication rather than adding a layer.

```
                         ┌────────────────────────── stored once per dataset ──────────────────────────┐
 source / file ──► PROFILE STORE ─────────────────────────────────────────────────────────────────────┤
                   column classes (exists) · column statistics · table shape · relationships · freshness│
                         └───────────────────────────────────────┬──────────────────────────────────────┘
                                                                 │ read, never rescanned
 CAPABILITY REGISTRY  ──────────────►  DISCOVERY  ◄──────────────┘
 one record per widget and analysis:    1. candidates   (registry × profile, no data touched)
 needs · minimum data · cost tier ·     2. fit          (prerequisites, refusals — deterministic)
 back-ends · evidence function ·        3. evidence     (cheap first; pushed down or sampled)
 output · llm: none|optional|required   4. rank + dedupe (measured terms only)
                                        5. card         (structured; sentence from readback)
                                                     │
                 ┌───────────────────────────────────┼───────────────────────────────────┐
                 ▼ tier 0-1: in the request          ▼ tier 2: a job (services/jobs.py)   ▼ optional
            existing probe + gate              deep analyses, cancellable, cached     LLM: wording, intent,
            (suggest_gate, widget_data)        by profile version                     unfamiliar names, follow-ups
                                                     │
                                              FEEDBACK (exists) ─► ranking weights
```

**Component responsibilities**

| Component | Is it new? | Responsibility |
|---|---|---|
| **Profile store** | Fills what exists: `DatasetColumn.stats`, `ColumnStats`, `column_meta` | Everything the engine needs to know about a dataset without touching rows again. Versioned by the data's fingerprint (file mtime+size, or the connection's `cache_epoch`). |
| **Capability registry** | Extends `services/analysis/registry.py`; absorbs `REQUIRED_ROLES`, `WIDGET_GUIDE`, the `_NEEDS_*` sets and the scattered `MIN_ROWS` | The single declaration of what each widget and analysis needs, costs and returns. Exported to the browser as JSON so `report.ts` stops being a hand-kept copy. |
| **Discovery** | New module, `services/discovery/`, ~4 files. The five engines call it instead of each generating candidates their own way | Candidates → fit → evidence → rank → cards. |
| **Evidence cache** | New table, small | Result of an evidence function, keyed by (dataset, profile version, capability, parameters, reader's row-rule fingerprint). |

**LLM-independent operation.** Stages 1–5 run with no model. A model, when present and permitted, is called at three named points only (§F), each with a deterministic result already in hand.

**Synchronous vs asynchronous**

| Stage | When | Budget |
|---|---|---|
| Profile | at import / sync / refresh, as a job; never in a user request | — |
| Candidates + fit (tier 0) | in the request | no data read; target < 100 ms **[to be measured]** |
| Cheap evidence (tier 1) | in the request, concurrent, pushed down or on the stored sample | a fixed time budget; what is not finished becomes a job |
| Deep evidence (tier 2: models, rule mining, forecasts across many series) | a job; cards appear as they finish | per-job wall-clock limit (new), cancellable through the existing checkpoint |

The response is **progressive**: tier-0/1 cards immediately, a job id for the rest; the browser polls the existing jobs API.

---

## C. Recommendation engine design

### C1. The capability record

One Python dataclass, the superset of today's `AnalysisSpec`. Fields exist only where something reads them.

```
name, family (chart | profile | statistic | model | forecast | anomaly | pattern | scenario | optimisation)
optional_backend: an extra library that gives a richer variant when installed (e.g. shap); the built-in one is always present
needs:      roles with the classes each accepts
            (e.g. measure: number in {amount,count}; group: category, 2..50 values; when: date)
minimum:    rows, groups, periods, events per group — whichever apply
structure:  none | relationship | coordinates | parent-child | repeated-entity | transactions
cost:       tier 0 (profile only) | 1 (one aggregate) | 2 (fit a model / scan pairs)
backends:   frame | duckdb | sql:<families>     ← what the evidence function can run on
evidence:   "module:function" → {strength, effect, n, p?, note}   (None for a plain chart)
draws:      widget types that can show the result, in preference order
answers:    question kinds it serves (how many · compare · trend · relate · explain · predict · unusual · what-if · where)
llm:        none | optional | required
claim:      observation | association | prediction | hypothesis   ← printed on the card
```

`claim` is how "do not present correlation as causation" is enforced mechanically: wording templates are chosen by it, and a model may not upgrade it.

### C2. Lifecycle

| # | Stage | Uses | Notes |
|---|---|---|---|
| 1 | Dataset discovery | catalog (exists) | |
| 2 | Schema + metadata | `SourceColumn`, `DatasetColumn` | |
| 3 | Semantic roles | `column_classes` (exists) | values → neutral vocabulary → model once → author |
| 4 | Profile | **profile store** | computed once, as a job |
| 5 | Opportunity discovery | registry × profile | a pure function; no rows read |
| 6 | Candidate generation | each capability's `needs` matched against columns | bounded: at most N column combinations per capability, chosen by profile statistics (variance, cardinality, missingness), not all pairs |
| 7 | Fit / prerequisites | `minimum`, `structure`, hidden columns, personal data, `eligible_for_suggestion` | deterministic refusals with a reason (kept for "why not?") |
| 8 | Evidence | capability's evidence function | tier 1 inline, tier 2 as a job |
| 9 | Cost + feasibility | `cost`, row count, back-end | decides inline vs job vs not at all |
| 10 | Rank + dedupe | §C3 | signature dedupe exists (`suggestionTakeaway.signature`); move it server-side |
| 11 | Card | §E | sentence from `readback.takeaway`; model optional |
| 12 | Execute | existing widget-data and analysis-run routes | unchanged |
| 13 | Verify | `suggest_gate.says_nothing` + the probe (exist) | a card whose result says nothing is withdrawn, not shown |
| 14 | Feedback | `SuggestionFeedback` (exists) | |
| 15 | Follow-ups | registry `answers` graph | "after a trend → what explains it → which segment → forecast"; deterministic table of next steps per result kind |

### C3. Ranking — separate measures, no universal score

Five quantities are kept apart and shown apart:

| Quantity | Meaning | Source | Measurable today? |
|---|---|---|---|
| **Fit** | the data satisfies the capability's needs | stage 7 | yes — boolean; a failed fit is never ranked |
| **Evidence** | how strongly the data shows something | effect size (Cramér's V, η², \|r\|, rate gap, standardized change) with the p-value corrected across everything tested in the scan (FDR already used in `inferential.correct_p_values`) | yes for capabilities with an evidence function |
| **Relevance** | closeness to what the person asked for | token overlap between the stated goal / dashboard title and the columns' names, labels and descriptions; +model intent when available | partly (today: "matches X in the report description") |
| **Novelty** | not already on the page, not a restatement of another card | signature + same-columns-same-claim | yes |
| **Cost** | tier and estimated time | registry + row count | tier yes; time needs benchmarks |

Initial ordering (deliberately simple, every term measured):

```
order key = ( has_goal_match,            # relevance first when a goal exists
              evidence_band,              # strong / moderate / weak — bands, not decimals
              -cost_tier,                 # cheaper first within a band
              feedback_bias )             # kinds this person adds rise; kinds they dismiss sink
then: diversify — at most K per family and per column
```

Plain charts with no evidence function (a count by category) are not ranked against findings; they fill a fixed "basics" quota, as the baseline suggestions do today.

**Testing the ranker without a model:** a labelled suite (§H) with planted effects and planted non-effects; metrics are precision@5, the share of planted effects found, and the false-discovery rate on the null datasets. Feedback tunes only `feedback_bias` and the diversity quota — never the evidence measure.

---

## D. Capability catalogue — what the reference screenshots require

Status: **have** (exists, needs only a registry record) · **wire** (parts exist, need connecting) · **new** (method or shaper to write).
LLM: N = not needed · O = optional (wording only).

| # | Seen in the references | Discovery condition (generic) | Method | Status | LLM | Cost | Effort |
|---|---|---|---|---|---|---|---|
| 1 | **Column profile card** (valid / unique / invalid / mistyped / missing, string lengths, patterns, distinct, value bars) | any column | counts by parsed type against the column's majority type; length min/max; shape patterns (`A9-999` style masks) | **wire**: `data_quality.quality_report`, `metadata/profile.py`, `analytics.py` hold most; add mistyped count, length range, mask inference | N | 0–1 | S |
| 2 | **Row count by date + data delay** | a date column the profile marks as "when the record began" | count per period; delay = now − latest value | **wire**: count series is pushed down; freshness exists as pipeline health, not as a result | N | 1 | S |
| 3 | **KPI with sparkline and change vs previous period** | a measure + a start date with ≥ 2 comparable periods | value, previous comparable period, series for the sparkline; thin/partial periods excluded (rule already in `insights._trends`) | **new** shaper + renderer option (sparkline component exists for crosstab rows) | N | 1 | S |
| 4 | **Anomaly band** (expected range, flagged points) | a measure over ≥ ~30 periods | seasonal decomposition or the forecast model's in-sample interval; points outside flagged | **new** (reuses `shape_forecast` machinery and `statsforecast`) | N | 2 | M |
| 5 | **Forecast with confidence, "compare to past"** | a measure over ≥ 2 seasons | AutoETS → fallbacks (exists) | **have** | N | 2 | — |
| 6 | **Key influencers / top segments** | an outcome or a measure marked worth explaining + candidate factors | group lift vs baseline (exists) | **have** as an analysis; **wire** as a widget type | N | 2 | S |
| 7 | **Feature importance (SHAP-style) + per-feature spread** | a target + ≥ 3 predictors, rows ≥ minimum | permutation importance on the automated-prediction winner (scikit-learn, already installed); SHAP only if the dependency is accepted (§I-4) | **new** | N | 2 | M |
| 8 | **Clusters with a 2-D projection** | ≥ 3 quantities | k-means (exists) + PCA to two components for the scatter | **wire**: add projection to `shape_model_cluster` | N | 2 | S |
| 9 | **Cluster × attribute bubble matrix, radar of cluster profiles** | after #8 | centroid table drawn as bubble matrix / radar | **new** radar renderer; bubble matrix via existing heatmap/bubble | N | 1 | S |
| 10 | **Association rules: network + table (support, confidence, lift)** | a transaction shape: a repeated-entity key with a category per row, or several yes/no columns | apriori (exists) | **wire**: feed rules to the existing `network` widget; **new** detection of the transaction shape | N | 2 | S–M |
| 11 | **Correlation heatmap, distributions, box plots, scatter grid** | ≥ 3 quantities | exists; scatter-plot matrix = small multiples of `numeric_series` | **have**; SPLOM **new** (S) | N | 1 | S |
| 12 | **Channel mix, share of total, donut, treemap, Pareto** | a category 2–30 values + an additive measure | exists; Pareto = sorted bars + cumulative share, flagged when the top ~20% carry ~80% | **have**; Pareto **new** (S) | N | 1 | S |
| 13 | **Geographic heat / point / choropleth** | stored `geo_level` (exists) | exists for countries and coordinates | **have**; regions and cities need a gazetteer (§I-6) | N | 1 | — / M |
| 14 | **Anomaly table with impact and confidence; "unusual spike detected", contributing factors** | #4 finds a point → explain it | contribution analysis: change of the measure between the anomalous period and its baseline, split by each category (largest contributors) | **new** — the "why did it change" step; reuses `decomposition` + insights | O | 2 | M |
| 15 | **Scenario simulation: named scenarios, outcome distributions, P(loss)** | a fitted relationship (regression or forecast scenario) + ranges for inputs | Monte-Carlo over the model's parameter and residual uncertainty; seeded, reproducible | **new**; `forecast_scenario` and `goal_seek` are the base | N | 2 | L |
| 16 | **Dashboard key takeaways** | a page with drawn widgets | run `readback.takeaway` over each widget's result, group by claim, order by evidence | **wire** (deterministic); model may rewrite into a paragraph under the existing digit guard | O | 1 | S |
| 17 | **Service/health style: gauges, thresholds, status tiles, incident list** | a measure with a stored direction + a threshold or target column; a status-like outcome | exists (gauge, KPI, alerts) | **have** | N | 1 | — |
| 18 | **Change point** ("what changed significantly") | a measure over time | PELT / binary segmentation on the period series (own implementation or `ruptures`, §I-4) | **new** | N | 2 | M |
| 19 | **Cohort retention** | an entity key + a first-seen date + repeated activity | cohort by first period × periods since | **new** | N | 1–2 | M |
| 20 | **Multi-table consistency** | a declared relationship | orphan rate, cardinality as measured vs declared | **wire**: `meaning.measure_links` measures this | N | 1 | S |
| 21 | **Optimisation opportunity** | see §D2 | hand-off | **new**, last | O | — | L |

### D2. Optimisation — only when a decision problem is actually present

No solver exists in this repository **[verified]**, and **there is no Problem Solver platform yet** (owner, 2026-10-10). So this capability stops at recognising a decision problem and writing it down as a problem specification; nothing is solved or sent anywhere until such a platform exists. An optimisation card is offered only when the data shows the *structure* of a decision, never because numbers exist:

- a **resource table**: rows are options (things), with a cost-like amount and a benefit-like amount, and a capacity or budget stated by the user or present as a column → knapsack / allocation;
- an **assignment shape**: two entity sets joined by a table carrying a cost or a distance → assignment / transport;
- a **fitted response model** (from #15) with controllable inputs the user marks → maximise the predicted outcome under ranges.

The card collects what is missing (objective direction, which columns are decisions, constraints) through a structured form; nothing is inferred silently. Output: a problem specification document (objective, decision columns, constraints, data references) in a neutral, versioned JSON shape owned by this platform, so a future solver — built here or elsewhere — can consume it. No solver dependency is added now.

---

## E. Card contract (no interface design)

The only "UX" decision this plan makes is the shape of what the engine returns. Presentation is free to change.

```json
{
  "id": "sig:…",                         "capability": "anomaly_band",
  "family": "anomaly",                    "claim": "observation",
  "title": "…",                           "sentence": "… (from readback, with its numbers)",
  "why": {"reason": "fit|evidence|goal|follow_up", "detail": "…"},
  "fields": ["col_a", "col_b"],
  "evidence": {"band": "strong", "effect": 0.31, "effect_kind": "rate_gap", "n": 62662, "p_adj": 0.0004},
  "limits": ["sampled 250,000 of 4.1M rows", "last period excluded: partial"],
  "cost": {"tier": 2, "state": "ready|running|queued", "job_id": 812},
  "action": {"kind": "add_widget|run_analysis|open", "widget_type": "…", "config": {…}},
  "next": ["explain_change", "segment", "forecast"],
  "source": "deterministic|model_assisted"
}
```

`evidence`, `limits` and `claim` are never written by a model.

---

## F. LLM strategy

| Mode | What runs | When |
|---|---|---|
| **1 Deterministic** | everything in §C; cards worded by `readback` templates | no model configured, model down, AI not permitted for the connection, or budget spent |
| **2 Hybrid (default when a model is permitted)** | mode 1, plus the model at three points | |
| **3 Assisted** | mode 2, plus multi-step planning in Ask AI | opt-in per organisation |

**The three model points in mode 2**

| Use | Why a model | Deterministic alternative | Cost / latency | Validation | Privacy | When off |
|---|---|---|---|---|---|---|
| **Column kinds** (built: `column_classes.model_hints`) | names in any language and field | values + neutral vocabulary | one call per dataset, ever | schema + kind enum; a measurement word is not overruled | names, ranges, descriptions; no rows; hidden columns withheld | values + vocabulary |
| **Goal → intent** (what the person asked for, as question kinds + columns) | free text in any language | token overlap with column names and labels | one call per request for suggestions | schema; columns checked against the dataset | the person's sentence + column names | token overlap |
| **Wording** (one call for the whole card list, not per card) | readable titles in the reader's language | `readback` templates (already translated EN/AR) | one batched call | digit guard (exists in `insights.narrate_findings`, `guided_setup.answer.honest_text`): every number must appear in the evidence; `claim` may not be upgraded | computed sentences only, no rows | templates |

**Rules that follow from A2-5 (to fix regardless of this plan)**

1. One gate, `ai_allowed(source, user, feature)`, consulted by **every** call site; today `allow_llm_sampling` is honoured by two features out of ~25 call sites.
2. Raw rows never go to a model: `health.model_rules` sends value *shapes* and ranges instead of `head(5)`; Ask AI's explain step is the one place result rows are sent, and it must pass the same gate and the personal-data mask.
3. Untrusted text (cell values, descriptions, top values) is wrapped in a delimited data block with a fixed instruction that it is data; values are length-capped (exists) and stripped of control sequences. Output-side checks stay.
4. Ask AI degrades instead of failing: with no model, a question is matched to registry capabilities by the same token-overlap intent and answered with cards ("here is what can be computed about X").
5. Metering covers `model_hints`.
6. Caching: answers keyed by (model, prompt hash) already exist for the analyst panel (7 days); reuse that store for intent and wording, keyed additionally by profile version. Prompt-prefix caching: the system prompt and the registry block are byte-stable and first — usable where the endpoint supports it **[the deployed vLLM endpoints' support is unverified]**.
7. Routing: intent and wording are `light` in the existing `FEATURE_WEIGHT` table.

---

## G. Implementation roadmap

Sized relative to each other (S ≈ days, M ≈ a week or two, L ≈ several weeks). Each phase leaves the product working.

### Phase 0 — finish neutrality and close the AI gaps (S–M)
- Remove the word lists and reword the prompts of table A3 (`source_brief.py`, `infer_semantic.py`, `analyst_panel.py`, `agent/nodes/*.py`, `agent/validate.py`, `Dataflows.tsx`). The "equity" lens becomes "compare like with like": same groups, same level, different outcome — no pay, no gender.
- `ai_allowed` gate at every call site; `model_rules` stops sending rows; delimited data blocks; `model_hints` metered.
- "Allow AI" for uploaded datasets: a dataset-level switch with an organisation default (`Dataset` gains the field; connection datasets keep inheriting `DataSource.allow_llm_sampling`); `ai_allowed` reads whichever applies.
- Ask AI without a model: instead of ending the run as failed, match the question's words to columns and to the analysis catalogue and answer with what can be computed (until phase 1 exists: the catalogue entries whose required columns the dataset has; after phase 1: discovery cards).
- A test that fails when a listed trade noun appears in a logic constant or a prompt string of `services/` (a denylist read from one file; comments and tests exempt).
- **Accept:** the existing suites pass; the three guided-setup scenarios and the Ask AI benchmark (`docs/ASK_BENCHMARK.md`, `scripts/bench_ask.py`) do not regress; with `allow_llm_sampling = False` no request reaches a model (asserted with a client that fails on call).
- **Risk:** Ask AI few-shot examples carry accuracy; rewording must be measured on the benchmark, not assumed.

### Phase 1 — the smallest vertical slice: profile store + registry + one endpoint (M)
- **Profile store:** fill `DatasetColumn.stats` at import/refresh/sync (job): count, missing, distinct, min/max, quantiles, top values, length range, parsed-type counts, date median and span, period cadence. Import: DuckDB over the Parquet sidecar. PostgreSQL connections: call the existing unused `pg_stats` readers first, sample second. Add a dataset-level `profile_version`.
- **Registry:** extend `AnalysisSpec` to the record of §C1; register the existing analyses and the ~40 proposable widget types; generate `REQUIRED_ROLES`, `WIDGET_GUIDE` and `usable_widgets` from it; export JSON; the test that re-derives roles from TypeScript flips direction.
- **Discovery:** `services/discovery/{candidates,fit,rank,cards}.py`; `GET /datasets/{id}/opportunities?goal=` returning cards for tiers 0–1 only, built from what already exists (insights findings, baselines, gate, readback).
- The builder's Suggest pane and "Suggest dashboards" (no-goal path) call it; the other doors unchanged.
- **Files:** `services/analysis/registry.py`, `services/widget_roles.py`, `services/suggest_dataset_dashboard.py`, `services/dataset_refresh.py`, `services/metadata/profile.py`, `routers/datasets.py`, `routers/reports.py`, new `services/discovery/`, one migration (`profile_version`, evidence cache).
- **Accept:** same dataset → same cards from both doors; opening a dataset's suggestions a second time reads no rows for tier 0 (asserted by counting frame loads); time to first card recorded on the benchmark suite (no target claimed before measuring).
- **Risk:** the registry must not become a second copy — the generated tables are the proof.

### Phase 2 — cheap capabilities from the references (M)
#1 column profile, #2 count by date + delay, #3 KPI with sparkline and change, #8 cluster projection, #10 rule network + transaction-shape detection, #11 scatter matrix, #12 Pareto, #16 page takeaways, #20 relationship consistency.
**Accept:** each has a registry record, an evidence function with a planted-effect test and a null test, and appears as a card only when its condition holds.

### Phase 3 — time and explanation (M–L)
#4 anomaly band, #18 change point, #14 contribution ("why did it change"), #6 key influencers as a widget, #7 permutation importance; the follow-up table (stage 15). Tier-2 jobs with a wall-clock limit and the evidence cache.
**Accept:** on series with a planted level shift and a planted spike, both are found and dated within one period; on white noise nothing is reported at the corrected level.

### Phase 4 — large data (M–L, benchmark-led)
Evidence functions get a `duckdb` or `sql` implementation where the benchmark shows the frame path is the cost: group-by evidence (rates, standouts), histograms, correlation, count series. DirectQuery fallback gains column pruning and `TABLESAMPLE` where the family supports it (already used by metadata sampling). Frame cache: measure the deep-copy cost before changing it.
**Accept:** defined after phase 1's measurements; no numeric target is asserted here.

### Phase 5 — scenarios, cohorts, decision problems (L)
#15 simulation, #19 cohorts, #21 recognising a decision problem and writing its specification (no solver; see §D2).

### Phase 6 — one engine everywhere (M)
The guided setup's designer, the analyst panel and the connection designer become callers of discovery with a goal; the model picks among validated cards instead of inventing widgets. This is the "one literal engine" left open in the suggestions plan.

---

## H. Benchmark and quality plan

**Datasets** (synthetic generators under `qa/fixtures/`, seeded, with the truth recorded beside each; plus the real ones already loaded locally for a sanity pass)

| Shape | Planted truth |
|---|---|
| small numeric (1k) / large numeric (5M) | two correlated pairs, one non-linear |
| high-cardinality categorical (100k values) | nothing — must not produce bar charts of 100k bars |
| daily series, 3 years | trend, weekly season, one spike, one level shift |
| transactions (entity × item) | three item sets with lift |
| three related tables with a base/event link | a rate that differs by group while counts follow size |
| coordinates + regions | a spatial cluster |
| imbalanced outcome (2%) | two real factors, one leak (a column that is the outcome renamed) |
| sparse, 60% missing | — |
| pure noise | nothing — the null test |
| names that say nothing (`c1…c40`), Arabic names | same truths as above |
| misleading correlation (two series sharing a trend) | must be labelled association, flagged as trend-driven |
| free text with instructions inside ("ignore previous…") | must not change any output |

**Metrics**

| Metric | How |
|---|---|
| precision@5, recall of planted truths | against the recorded truth |
| false-discovery rate | cards with evidence on the noise datasets |
| redundancy | cards sharing a signature or the same columns + claim |
| time to first card; time to all tier-1 cards; peak memory | extend `scripts/bench_common.py` |
| rows read on a repeat request | counter on frame loads / queries |
| correctness | each evidence function against a reference computation (scipy / statsmodels) |
| mode-1 parity | the same suite with the model disabled; mode 2 may only add wording |
| model cost | tokens per dataset opened (target: classification once + ≤ 2 calls per suggestion request — to be confirmed by measurement) |
| acceptance | add rate and dismiss rate per capability from `SuggestionFeedback` |

Baselines: today's engines on the same suite, recorded before phase 1 starts. Regression: the suite runs in CI at the small sizes; the large sizes are a manual script like the existing `bench_*`.

---

## I. Architecture decisions

| # | Decision | Chosen | Alternatives | Why / trade-off |
|---|---|---|---|---|
| 1 | Where intelligence lives | deterministic engine; model at three named points | model-first planning | reliability, cost, works offline; the model cannot invent a finding it does not compute |
| 2 | Registry | extend the existing `AnalysisSpec` to widgets | a new plugin framework; keep five tables | one table already exists and is served to the agent; a framework is abstraction before need |
| 3 | Compute for profile and evidence | DuckDB over the existing Parquet sidecar for imports; source SQL for live data | add ClickHouse as an analytical store; Spark | DuckDB is already installed and in the widget path; ClickHouse is a *source* connector here, and nothing measured yet justifies a second store. Revisit only if phase 4 benchmarks show imports beyond the 2M-row cap are a real need |
| 4 | New dependencies | **decided:** built-in equivalents are the default (permutation importance, PCA, own change-point). `shap` and a change-point library are **optional extras**: detected at start-up, declared in the registry as an alternative back-end of the same capability, never required | add them as hard requirements | must run fully offline (`docs/OFFLINE_DEPLOYMENT.md`); an installation without the extras loses nothing but the richer variant |
| 5 | Optimisation | **decided:** recognise the decision problem and produce a specification only; no solver, no external call | embed a solver now | there is no Problem Solver platform yet; building against one would be building against nothing |
| 6 | Maps for regions/cities | **open** — needs a gazetteer with coordinates | built-in world admin-1 set; organisation's own list (`boundary_sets.py` exists) | size and licensing of a built-in set vs the work of an own list |
| 7 | Background execution | the existing jobs table | Celery / an external queue | durable, cancellable, already operated; revisit if tier-2 volume outgrows `WORKER_CONCURRENCY = 2` |
| 8 | Confidence | five separate quantities, evidence in bands | one 0–100 score | a single number would mix "the chart fits" with "the effect is real" |
| 9 | Domain packs | optional registry records + vocabulary files loaded per organisation, never imported by the core | words in the core | keeps the neutrality test meaningful; a pack can name "headcount" for an HR organisation without the core knowing the word |

**Owner's decisions (2026-10-10)**

| Question | Decision | Effect on the plan |
|---|---|---|
| Problem Solver platform | It does not exist yet | #21 ends at a problem specification (§D2); phase 5 carries no solver work |
| SHAP / change-point libraries | Built-in equivalents by default; the libraries are optional extras | decision 4; the registry gains an "optional back-end" field so a capability can use an extra when it is installed |
| Ask AI with no model | Stays visible and answers with what the platform can compute without AI | phase 0, step 5 below; the answer is a list of discovery cards matched to the question's words |
| "Allow AI" for uploaded files | Yes — the same permission applies | phase 0: the switch moves from "per connection" to "per data origin": a dataset built from a connection inherits the connection's; an uploaded dataset carries its own, with an organisation default |
| Import limit (2,000,000 rows) | Keep it for standard imports until there are benchmark results; treat file imports and live analytical queries as different paths | phase 4 measures both separately; no change to `import_row_cap` before that; larger data is served through live connections with push-down |

**Still to settle (not blocking phase 0)**
1. Maps for regions and cities: a built-in boundary set, or the organisation's own list only (decision 6).
2. The default of the "Allow AI" switch for a newly uploaded file (the plan assumes: the organisation's setting, on unless an administrator turns it off).

---

## J. Immediate next steps (after review — not started)

Phase 0, in this order:

1. Record baselines: run `scripts/bench_ask.py` and the existing suggestion tests; save the outputs beside this plan.
2. Add `ai_allowed(dataset_or_source, user, feature)` — covering uploaded datasets through the new dataset-level switch; route the ~25 call sites of part A2-5 through it; test with a client that raises on any call.
3. `health.model_rules`: replace `df.head(5)` with per-column shapes and ranges; keep `verify_rule` unchanged.
4. Add the delimited data block helper to `services/llm.py`; use it wherever values or descriptions enter a prompt.
5. Ask AI with no model answers with what can be computed, instead of failing.
6. Neutralise table A3, file by file, re-running the Ask AI benchmark after `classify.py`, `generate.py`, `copilot.py`, `followup.py`.
7. Add the denylist test for trade nouns in logic constants and prompt strings.
8. Review, then phase 1.

---

## K. Phase 0 — what was built (2026-10-11)

| Step | Done | Where |
|---|---|---|
| One "Allow AI" answer for every feature | The refusal lives inside the model client: once a request learns its data is not allowed, every model call made in that request returns nothing, whichever feature makes it | `services/llm.py` (`deny_ai`, checked in `LLMClient.complete`), `services/ai_policy.py` |
| Wired where a request learns its data | Ask AI, page copilot, insights, column explain, "Ask AI again", both dataset designers and the analyst panel (through `suggest_inputs.prepare`), builder suggestions, connection designer, every guided-setup step, automations, background jobs (reset per job) | `routers/{agent,datasets,reports,report_copilot,metadata,guided_setup}.py`, `services/{suggest_inputs,automation_runner,jobs,column_classes}.py` |
| Uploaded files have the switch | `Dataset.allow_ai` (unset = follow the connection, or the installation default `ai_for_uploads_default = True`); read and write routes; a control in the dataset header; audited | `models.py`, migration `0064`, `routers/datasets.py` (`/datasets/{id}/allow-ai`), `components/DatasetAllowAi.tsx` |
| A dataset cannot switch on what its connection switched off | yes; a dataset saying no always wins | `ai_policy.dataset_allows` |
| No raw rows to the model in the data check | names, kinds, ranges and category labels only; a column of many different texts is described by its shape | `guided_setup/health.py` |
| Untrusted text | a fixed rule added to the system message of **every** call; values, rows and measured facts fenced as data in the designers, the analyst panel, the guided setup, the connection designer, Ask AI's written answer and the column classifier; a value cannot close its own fence | `llm.DATA_RULE`, `llm.data_block` |
| Ask AI without a model | answers with the columns the question points at and the analyses the data supports, in plain words, saying no AI was used — instead of failing | `services/agent/without_model.py`, `agent/graph.py` |
| Column classification is metered | under the request's meter, or its own | `column_classes.model_hints` |
| Remaining trade vocabulary removed | Ask AI examples (classify, copilot, follow-up, SQL writer, clarify), connection designer lists and prompts, catalog type guessing, analyst-panel lens briefs, counting words, place words, dataflow defaults, analysis catalogue descriptions | table A3's files |
| "What a value is a value of" read from shape | the column with at least as many distinct values as the unit column, instead of a list of trade nouns | `source_brief._item_columns` |
| A test that keeps it so | scans the engine's strings (word lists, regexes, prompts) for one field's nouns; comments and tests are exempt | `tests/test_domain_neutral.py` |

**Measured**

* Tests: 2,350 backend tests in the 118 related files and all 4,341 frontend tests pass; type check clean.
* Ask AI benchmark (26 questions, English and Arabic), run before and after the examples were reworded on the same day and model: identical — 9 of 10 answers right in each language, no ungrounded answer, the same three cases failing in both runs (recorded in `docs/ASK_BENCHMARK.md`). A scorer defect found on the way (a typographic apostrophe in "can’t" was not read as a refusal) was fixed.
* Live, on an uploaded dataset: with the switch on, Ask AI answers through the model; with it off, the same question is answered in 0.0 s without one, "Ask AI again" is refused, and insights still come back with their template wording.

**Behaviour change to know about.** A connection whose "Allow AI" is off now has AI off in *every* feature for the datasets built from it — that is the point — where before only the catalog sync and the guided setup obeyed. On this installation three connections are off ("Demo — Live SQLite" ×2, "QA Conn 1125").

**Not done in phase 0**

* `POST /analysis/narrate` rewords a finding the browser already holds; it carries no dataset, so it is not tied to a dataset's switch (it sends computed sentences only).
* Ask AI's SQL writer receives the schema (names, descriptions, value labels) inside its system prompt; the every-call rule covers it, but it is not fenced as a block, to avoid changing a prompt the benchmark depends on without need.
* The page copilot still needs a model: with AI off it now says so (409) instead of failing (502); it has no no-model mode.
* Low-severity items of A3 (example placeholders and two tooltips in the interface).
* Statement timeouts for SQL Server and Oracle, a per-job time limit and per-person quotas (A2-7) belong to later phases.
* Three Ask AI benchmark cases fail before and after; they are existing weaknesses, not addressed here.

---

## L. Phase 1 — the vertical slice that was built (2026-10-11)

| Piece | What exists | Where |
|---|---|---|
| **Stored profile** | Per column: kind, count, missing, distinct; a number's range, mean, spread and quantiles; a text's length range and — for a category only — its labels; a date's range, median and the months it covers; how much of a text column is really numbers. For the table: rows, exact duplicates, structure. Written to `DatasetColumn.stats` (no longer `{}`) and `column_meta["__profile__"]`, versioned by the file's size and write time (a day, for a live source) | `services/discovery/profile.py` |
| Who may write it | Only a read with no row rule and no hidden column. A restricted reader gets hidden columns removed and, under a row rule, no value-level figure | `profile.for_reader`, `profile.ensure` |
| **Capability registry** | 91 records: every proposable widget (66) and every catalogued analysis (25), each with the column kinds it needs, its smallest data, structure, cost tier, kind of claim, the question it answers, and `llm: none`. The designer's structure requirements moved here and are imported back; minimums are held equal to each analysis module's own by a test | `services/discovery/capabilities.py`; `GET /datasets/capabilities/registry` |
| **Discovery** | Column kinds from the stored profile and the stored classification → fit with a plain-words reason → cards. Tier 0: what the data supports, with the columns each analysis would use. Tier 1: what the insight detectors found, each drawn and gated as before, with its evidence in bands. Ranked by goal match, evidence band, cost; at most four per family; nothing twice | `services/discovery/engine.py`; `GET /datasets/{id}/opportunities?goal=&depth=&limit=&fresh=` |
| Card contract (§E) | as designed; `evidence` is present only where a detector found something, an association card carries "not that one causes the other", and there is no single confidence | `engine._card`, `OpportunityCard` in `frontend/src/services/api.ts` |
| Cache | the reader's cards for 15 minutes, keyed by data version, goal, the reader's row rule and hidden columns, and the column classification | existing cache back-end (not a new table — simpler than the plan's) |

**Measured on this machine (one process, local Postgres and Valkey; a single run each, not a benchmark)**

| Dataset | Rows | First request (profile + evidence) | What it supports, from the store | Repeat |
|---|---|---|---|---|
| price history (import) | 621,835 | 7.4 s | 0.01 s | 0.01 s once cached |
| staff snapshot (import) | 240,124 | 1.4 s | 0.01 s | 0.01 s |
| the same table, live connection | 240,124 | 6.0 s | 0.01 s | 0.01 s once cached |
| shipments (import) | 64,420 | 2.0 s | 0.01 s | 0.01 s |
| listings (upload) | 14,269 | 0.6 s | 0.01 s | 0.01 s |
| sales (upload) | 2,000 | 0.2 s | 0.01 s | 0.01 s |
| Arabic-named indicators | 574 | 3.8 s (includes the one-time column classification by the model) | 0.01 s | 0.07 s |

**Tests:** 27 new (profile, registry, kinds and fit, evidence, ranking, endpoint incl. hidden columns and another organisation); 1,974 backend tests in the related files pass. Two defects found by these tests and fixed in the insights engine: a true/false column was admitted as a measure, and crashed the outlier and trend detectors.

**Differences from the plan, and what phase 1 did not do**

1. **One of the two existing doors is switched over (2026-10-11): the builder's Suggest pane** now reads `GET /reports/{id}/opportunities` — the discovery engine with the report's name as the goal — and shows the new addable cards (a forecast, groups of similar rows, values that appear together, rules that separate an outcome) beside the findings; a card's limits ("not that one causes the other") are shown in its details. "Suggest dashboards" on a dataset is **not** switched yet. Originally: The builder's Suggest pane and "Suggest dashboards" still call their own routes. The new endpoint reuses the same detectors, gate and probe underneath, so the evidence cards are the same findings — but "one request, same cards from both doors" is not true yet, and the interface shows none of the new analysis cards.
2. **The profile is measured on first use, not by a job at import**, and with pandas on the frame the request already loaded — not DuckDB over the Parquet file. The first request on the largest dataset took 7.4 s; that is the cost to move into a background job (phase 4).
3. **`depth=1` still reads the rows** (the insight detectors run on the frame); only its result is cached. "No row read" holds for `depth=0`.
4. **The registry reads roles and menu text from where they were**, rather than generating them; the browser's `report.ts` is still hand-kept. The single source for *requirements* is the registry; roles remain in `widget_roles.py`.
5. **The PostgreSQL statistics readers are still unused** (connection-level profiling was not touched).
6. **Feedback does not yet move the ranking** on the server: dismissed suggestions are remembered per browser signature, and that signature is computed in the browser.
7. **Rows per group, events per predictor** and similar minimums are declared but cannot be checked before the data is read; they are enforced by each analysis when it runs.
8. No benchmark suite (§H) yet: the planted-effect and noise checks exist as unit tests only.

### Loop log (after §L)

* **2026-10-11 — Suggest pane on the discovery engine.** `routers/reports.py` (`/reports/{id}/opportunities`), `services/api.ts` (`suggestApi.forReport` maps addable cards), `SuggestionsPane.tsx` (limits line), forecasts filed under Trend. Checked in the browser on the shipments dashboard: 18 ideas, the four new kinds present. Found and fixed on the way: a date stored as text was profiled as labels (the profile now reads the platform's own type for the column), and the "start date" rule preferred a finish date whose median ran early — in the discovery engine **and** in the insights engine's `order_event_dates`. Tests: 30 discovery tests, 1,942 report-component tests pass.
* **2026-10-11 — a leak closed in phase 1's own work.** The stored profile had been written to `DatasetColumn.stats` and `column_meta`, which every dataset payload returns: a reader under a row rule would have received the ranges and labels of rows they may not see. It now lives in its own table (`dataset_profiles`, migration `0065`) that nothing serialises and is read only through `profile.for_reader`. A test asserts the dataset payload carries no profile figure. (This replaces "fill `DatasetColumn.stats`" in §G phase 1.)
* **2026-10-11 — phase 2, #1 and #2: the column profile card and data delay.** Per column: valid / unique / non-unique / invalid / mistyped / missing with shares, the most and least common value, text length range, the shape values share (`AA-9999`), distinct count; for a date, how old its newest value is. `GET /datasets/{id}/profile`. Three profile cards join discovery at tier 0 (no row read): values that are not what their column mostly holds, exact copies of rows, data that has stopped arriving. Checked on three real datasets (a tracking number's pattern found; 104 duplicate rows in the call records; listings 115 days old). Tests: 38 discovery tests; related suites pass.
* **Not done for these two:** no screen shows the profile card yet (the API and its types exist); the date-typed check for text columns (a text column that is mostly dates) is not implemented — only numbers stored as text are detected.
* **2026-10-11 — phase 2, #3: KPI with its history.** A KPI with `sparkline_date` returns, beside its unchanged headline, the same number per period (grain chosen from the span: day → year), the last complete period against the one before, and the change — computed by the KPI's own shaper on the same rows and filters, with the period the data stops inside left out (`widget_data.kpi_trend`). The card draws the change and a sparkline; which way is good comes from the column's stored direction (`trend_good`), and with none the change has no colour. Discovery offers every headline number with its history when the table has a start date covering three periods or more. Checked live on two imported datasets and a live connection. Tests: 6 server, 3 browser.
* **Not done for #3:** a KPI on a live connection that is answered by a pushed-down query does not get a trend when that path is taken (the one checked here went through the frame); "compare with the same period last year" is not offered — only the previous period.
* **2026-10-11 — phase 2, #8: clusters as a picture.** `analysis/segment.py` now places every row on the two directions along which the rows differ most (principal components of the standardised variables — scikit-learn, already installed) and returns up to 1,200 points with their group, the group centres, and for each axis its share of the variation and the variables that weigh most on it. The cluster widget gains a "Picture" tab (only when a projection came back); discovery's "Groups of similar rows" card opens it. Deterministic (same data, same picture). Live: shipments → 4 groups, 1,200 of 10,000 sampled rows drawn, 17 s; sales → 2 groups, 6 s. Tests: 4 server, 1 browser.
* **Not done for #8:** the time is the existing search for the number of groups (2 to 8, each scored), unchanged — on large data this card belongs in a background job (phase 3's tier-2 jobs); radar and the cluster × attribute bubble matrix (#9) are not built.
* **2026-10-11 — phase 2, #10: what occurs together in the same group, and the rules as a network.** `analysis/patterns.py`: `basket_rules(df, group, thing)` for a table with one row per (group, thing) — support, confidence both ways, lift, same thresholds as the row-wise rules — and `rules_network(rows)` (values as nodes, rules as edges). The rules widget takes `basket` + `item`, and both kinds of rules now carry a network; the widget has a "Network" tab (values on a circle, a thicker line further above chance, and the line "together more often than chance is not one causing the other"). Discovery recognises the shape from the stored figures — an identifier that repeats with few values seen once, and a column naming things (5 to 200 values) — and offers "What occurs together in the same ⟨group⟩". Tests: 5 for baskets and network, 3 for the shape, 1 browser. Live: five of the real datasets were recognised; after it offered a *year* as a group key on three of them, a year is now excluded (and tested).
* **Not done for #10:** the shape is not verified before the card is offered (that each group holds several things is only known when the widget runs — it then refuses in plain words); groups of more than 60 things are left out; the plain trade word list in a refusal of the rules widget was reworded, but `model_widgets.py` is not yet covered by the neutrality test.
* **2026-10-11 — phase 2, #12: Pareto.** A new insights detector — "3 of 12 ⟨category⟩ values carry 80% of ⟨measure⟩" — for a number that adds up, a category of six groups or more, a total of one sign, when at most 35% of the groups reach 80% (and at least two do: one group carrying everything is already the standout finding). Drawn by the existing bar-and-line chart in a new `pareto` mode: groups from the largest down, the line the running share of the whole taken over all groups before any cut; the result states how many groups reach 80%. Tests: 6. On the five real datasets checked it fired only on the call records, where it restated the standout — which is what led to the "at least two" rule; none of the others is that concentrated.
* **Not done for #12:** no real dataset here shows a genuine Pareto, so it is verified on planted data only; the 80% line is not drawn as a reference line on the chart.
* **2026-10-11 — phase 2, #16: a page's key takeaways, without a model.** `GET /reports/{id}/pages/{pid}/takeaways`: every data widget on the page is computed as the reader sees it (the same resolver the page and the export use — row rules, hidden columns, plus the report's own filters), its result is read back into one sentence with its own numbers (`readback.takeaway`), a KPI with history adds how its last period compares, and the sentences come back in reading order — headline, over time, comparison, spread, where, together — at most twelve (`services/discovery/takeaways.py`). Each line carries its sentence as a translation key too. Checked on four pages of two real dashboards, one Arabic: 0.2–1.1 s per page, no widget silent. Tests: 4.
* **Not done for #16:** no screen shows them yet (the API and its types exist); the optional model rewrite into a paragraph is not wired; a percentage column reads "17.7", without its sign; tables and lists are skipped; the route has no test of its own (the service does) — it was exercised live only.
* **2026-10-11 — browser check of #3, #8, #10, #12.** A scratch dashboard ("Discovery check (scratch)", on the shipments dataset) with the five new widget variants, opened in the browser: both KPIs show the change and a sparkline (a falling late rate is green, because lower is better for that column; the shipment count has no stored direction and no colour); the Pareto chart draws descending bars with a rising "Cumulative share (%)" line; the cluster widget's Picture tab draws 1,200 points and two centres and names what each axis is made of; the rules widget's Network tab draws 12 values joined by 46 lines. No error on the page. The scratch dashboard was left in place.
* **2026-10-11 — the takeaways and the profile card are on screen.** (a) The reader's assistant panel on a dashboard has a **Summary** tab: the page's takeaways under their sections, each with its chart's title, in the reader's language where the server sent a translation key, and the line "No AI wrote this" (`pages/reportBuilder/PageTakeaways.tsx`, `ViewAssist.tsx`). Seen in the browser on the shipments dashboard. (b) Opening a column in a dataset's **Columns** tab shows its profile facts — valid, missing, mistyped, different values, seen only once, most and least common, length, the shape of its values, how old the newest date is (`ColumnMeaningPanel.tsx`). Seen in the browser on three columns (a tracking number's shape `AA999999AA`; a status column's most and least common value; a date 10 days old). Tests: 2 + 1 browser tests; 486 in the affected suites.
* **Not done:** the profile facts are English only; the Summary tab is in view mode only (not in the editor's panel); a reader who cannot open a column's row (no edit rights) does not reach the facts.
* **2026-10-11 — phase 2, #20: are the links between tables consistent.** `GET /setup/{source_id}/meaning/link-checks`: for every measured link of a connection (declared or inferred) — how many rows of the child point at a value that is not in the parent (orphans, which silently drop out of every joined figure), how many carry no value at all (not orphans, reported apart), how many parents have children — counted on the database as the reader, problems first, each with one plain sentence (`guided_setup/meaning.py`: `link_check`, `link_checks`). Live on two real connections: the courier database's seven links are all consistent (0.5 s); the marketplace database has two links with a few orphans (3 rows and 1 row), found in 1.1 s. Tests: 4.
* **Not done for #20:** no screen shows it; it is not a discovery card (it is about a connection, and discovery cards are per dataset); the counts for a link do not apply row rules beyond what the existing link measurement does.
* **Decision — #11 scatter-plot matrix is deferred.** A new widget type has to be added in five places that are kept in step by hand (§A2-1), for a view the correlation matrix plus the pair-by-pair "do these two move together" cards already cover. It should wait until the registry generates those five tables (phase 6).
* **Phase 2 status:** done — #1 profile card, #2 data delay, #3 KPI with history, #8 cluster picture, #10 baskets and rule network, #12 Pareto, #16 page takeaways, #20 link consistency. Deferred — #11 scatter matrix, #9 radar / bubble matrix. Open from phase 1 — "Suggest dashboards" on a dataset still uses its own route.
* **Next:** phase 3 (anomaly band, change points, "why did it change", key influencers as a widget, feature importance) — or first switch "Suggest dashboards" over. The owner has not chosen; the loop will take the switch-over first, as it closes phase 1.

## M. Phase 3 — time and explanation: what was built (2026-10-11)

* **#13 anomaly band and change point.** `analysis/timeline.py` (expected range from the series' own history — trailing median and spread, or the same position in earlier cycles once four cycles exist; one seeded permutation test for a level shift). A line, area or step chart with `anomaly_band` / `change_point` returns `lo` / `hi` / `expected` per period, the periods outside, and the shift (`widget_data.read_timeline`); the renderer draws the range, the dots and the marker. Two insight detectors (`anomaly`, `change_point`) offer the chart. The period the data stops inside is never judged; a series of more than 1,000 points (raw rows, not periods) is not judged at all. Tests: 20.
* **#14 "why did it change".** `analysis/change_drivers.py`, catalogued as `explain_change`: the last complete period against the one before (or two named periods), the difference split by every usable category, each value with its change and — for a total or a count — its share of the change. Categories are ranked by how much of the movement sits in one value. Where a category's values moved three times more than the total did, they cancel: no shares are printed and the category is listed last, marked as offsetting. An average gets each value's own change and its share of rows, never a share of the change. Every result says it shows where the change sits, not what caused it. Discovery offers it for a table with a number, a date and a category, and as the follow-up to a trend or an anomaly. Tests: 8. Live on shipments: 0.1 s; the rise sits in one service type.
* **#15 key influencers as a widget.** `model_influencers` (`model_widgets.shape_model_influencers`): outcome, optional value of interest, optional columns to look in; re-fitted under the page's filters like every model widget; each group with its rate (or average), how many times the usual that is, and its rows. Registered in the five hand-kept places plus the demo. Discovery's "What goes with ⟨outcome⟩" card now adds this widget. Tests: 5 server, 1 browser. Live on shipments: same-day service is late 1.8× as often as usual.
* **#16 feature importance.** `automated_prediction.permutation_importance`: for the winning model, the fall in the held-back score when one column is shuffled (five times, seeded; a text column's encoded pieces shuffled together), with the spread, and a flag for falls not clear of shuffling noise. Only when the winner beats guessing. Shown under the comparison. Tests: 3. Live: 1.4 s on 50,000 rows.

**Not done in phase 3**
* SHAP is not wired, even as an optional extra — permutation importance is the only method. Per-row explanations ("why this row") do not exist.
* No change-point library is used or offered as an optional extra; the built-in test finds **one** shift per series, not several.
* Weekly data with under four years of history has no yearly season, so a peak that returns every year is flagged every year (24 of 137 weeks flagged on the shipments data, several of them the same weeks each year).
* "Why did it change" has no chart of its own (it is an analysis result), reads one category at a time (no combinations of two categories), and its result text is English only. The mix effect for an average is stated, not decomposed.
* The influencers widget does not read column classification (shapers are not given it), so it relies on the analysis' own rules for what is a usable column.
* Tier-2 background jobs were not built: every phase-3 analysis runs in the request. All were fast on the data checked; the cluster card (17 s) is still the slow one.
* Browser: the new widgets were verified through the API and by component tests. The scratch dashboard page stayed on "Loading…" in the automated browser pane, so they were **not** seen drawn on a live page.
* Two demo tests (`test_demo_reports` — widget-type coverage) cannot run inside the backend container (they read the browser's type file); their expectations were updated by hand.

## N. Second reference set (15 screenshots, 2026-10-11) — what each asks of the engine

Read as "be able to suggest views like these", as with the first set. Capability, not layout.

| # | What the screenshot shows | Have | Missing to suggest it |
|---|---|---|---|
| 1 | Activity by weekday × hour (heat grid) | `heatmap`; date parts down to `hour_of_day` | a **weekday** date part; the rule "a timestamp with times of day → weekday × hour"; time-zone choice |
| 2 | Lines per year over months; year × month heat grid; peak / off-peak ratio | `comparative_time_series`, `heatmap` | a **month-of-year** part so years overlay; a "busy periods vs the rest" ratio derived from the data (no named seasons) |
| 3 | Timeline with notes at turning points | change point, anomalies (phase 3) | notes on the chart at those points, written from the finding |
| 4 | Number with change against the previous period or the same period a year back; period presets | KPI with history (previous period) | **same period last year**; a page-level "compare with" setting |
| 5 | Year over year | as 2 | as 2 |
| 6 | Status board: counts per stage, share on time, map of counts, sparklines | KPI with history, rates, maps | stage / funnel reading from a status column + two dates; "at risk" needs a rule the data states (promised vs actual date) |
| 7 | Tile board: progress to a target, top sources by share, this period vs last by month | `gauge`, bars | **target** per number (stored on the column, never guessed); paired bars period vs period |
| 8 | Week × role grid of surplus / shortfall, coloured by sign | `heatmap` | two-number difference (capacity − demand) as a derived measure; diverging colour around zero |
| 9 | Two groups' rate with uncertainty; lift and chance of being better | `compare_groups` | an **experiment reading**: two-group rate difference, interval, lift, and a plain verdict; needs a column that marks the groups |
| 10 | Two scenarios side by side | `forecast_scenario` | side-by-side comparison of two parameter sets over the same widgets (phase 5) |
| 11 | Actual vs plan table with Δ and Δ%; bridge from plan to actual | `waterfall`, `matrix` | **two-measure variance** (actual vs reference) and the bridge by category — the same arithmetic as `explain_change`, between two columns instead of two periods |
| 12 | Counts by severity over time; counts with change | grouped bars, KPI with history | ordered-category colouring from the stored order |
| 13 | Area scoring on a map grid with a question answered in text | `map_density`, Ask AI | grid scoring from several layers (out of scope until a scoring rule is stated by the user) |
| 14 | Scenario bars with a second-axis line | `dual_axis_bar_line`, scenarios | as 10 |
| 15 | Pass / warn / fail donuts; counts over time; freshness, volume, schema change | profile cards, data delay, link checks | a **data-health page** assembled from those cards; volume-over-time and schema-change detection between profile versions |

**Grouped into work (proposed order):**
1. *Calendar reading* (1, 2, 5): weekday and month-of-year date parts; discovery cards "by weekday and hour", "each year over the months", "year × month grid". Small, no new widget type.
2. *Period comparison* (4, 7, 12): same period last year on a KPI; paired period bars.
3. *Variance against a reference* (11, 8): actual vs a second number — table with Δ / Δ% and the bridge; diverging grid.
4. *Two-group experiment reading* (9).
5. *Data-health page* (15) from what phases 1–2 already measure, plus volume and schema change.
6. *Notes on a timeline* (3).
7. *Targets* (7) — needs a place to store a target; *scenarios side by side* (10, 14) and *stage boards* (6) stay in phase 5; *grid scoring* (13) is not planned.

## O. §N-1 calendar reading — what was built (2026-10-11)

* **Two date parts.** `weekday` (`1 Mon` … `7 Sun`, Monday first — ISO 8601, not one region's week) and `month_of_year` (`01 Jan` … `12 Dec`), beside the existing `hour_of_day`. Labels carry the position first so an axis sorted as text is in calendar order, and are mapped from the number so they never depend on the server's locale. Offered in the chart panel's "Group dates by" (English and Arabic). A click on such a label filters by it like any other date bucket.
* **One date on both sides of a chart.** `dimension2_granularity` (`widget_data.second_grain`): the second field cut into date parts becomes a column of its own before the chart is shaped, so the same date can be weekday down and hour across, or month along with a line per year. Grids show every position of a cycle (7 days, 24 hours, 12 months), empty where there are no rows. For "each year over the months" the months before the data begins and after it stops are emptied rather than drawn as 0. Pushed-down queries are not used for these charts (the rows are read).
* **What the profile now keeps for a date:** years, days, hours of the day seen, and the share of values that carry a time of day (`profile.SCHEMA = 4`; profiles are re-measured on next use).
* **Three discovery cards**, from the stored figures alone, for the date the records begin on:
  * *⟨number⟩ by weekday and hour* (grid) — at least 28 days, at least half the values timed, at least 6 hours of the day seen.
  * *Each year of ⟨number⟩ over the months* (one line per year) — 2 to 6 years, 13 months or more.
  * *⟨number⟩ by year and month* (grid) — 2 years or more.
  With no number that adds up, rows are counted. They appear in a dashboard's Suggest list as well as on the dataset.
* **Checked:** 11 tests (`tests/test_calendar_reading.py`, with a planted Thursday-morning habit that the grid finds). On five real datasets every offered card drew, in 0.03–0.35 s; a 24-year table got the grid and no 24-line chart (which is where the 6-line cap came from). In the browser on the scratch dashboard: all ten widgets drew — the two grids, the per-year lines, the influencers widget and the read line among them.

**Not done**
* Weekday and month names are English on the chart whatever the reader's language (only the panel option is translated).
* The chart panel has no control for the second field's date part; it is set by the suggestion (or by hand in the config) and survives edits.
* No time zone: hours are as stored. The reference's time-zone picker is not built.
* Cards are offered, not evidenced: nothing checks that a weekday or a month actually differs from the others before offering (a detector for "this weekday is consistently higher" would make it a finding).
* The "busy periods against the rest" ratio from the reference is not built.
* The number chosen is the first one classified as adding up, as on every other card — on a listings table that was a room count.
* Seen while checking phase 3 in the browser: a long line in a narrow tile opens on a window with a slider, so unusual periods and the shift marker outside the window are not visible until the reader slides. Unchanged.
* Year over year uses calendar years only (no fiscal or Hijri year on the second field in the cards, though `second_grain` accepts any supported part).

## P. §N-2 period comparison — what was built (2026-10-11)

* **A number against the same period a year before.** A KPI with history now returns `year_ago` (period, value, change, change %) beside the unchanged comparison with the previous period, whenever the history reaches that far — for day, week, month and quarter periods (`widget_data.kpi_trend`, `_year_before`). The card shows it as a second line ("▲ 12.0% vs 2025-09"), coloured by the same stored direction as the first. Nothing to configure: discovery's "number with its history" cards get it by themselves.
* **The last two years, month against month.** A fourth calendar card: paired bars per month of the year, the latest year beside the one before. The two years are counted back from the newest date in the data (a relative filter anchored on the data, so the card does not go stale), and the months that have not happened yet are empty.
* **Checked:** 3 server tests for the year-before comparison (a planted December peak: +150% on November, +20% on last December), 1 for the paired bars, 2 browser tests; live on three real datasets.

**Not done**
* No page-level "compare with" switch and no period presets (7 / 30 / 60 days, month or year to date) as in the reference — the comparison is per number.
* Week 53 and 29 February have no year-before and show none; a year period has only its previous year.
* The year-before line is English ("vs"), and the paired bars use calendar years only.
* A number against a **target** or a **forecast** (the reference's "vs forecast") is not built — that is §N-3 / §N-7.

## Q. §N-3 one number against another — what was built (2026-10-11)

* **First, a fix to §P:** in the year-against-year charts the month the data stops inside is now left out (and the result says so, `partial_period.dropped`), by the same "unfinished" test a KPI's history uses — twelve days of December are no longer set beside all of last December.
* **Where two numbers differ** — analysis `explain_variance` (`analysis/change_drivers.py`): one column against another on the same rows, totals and the difference, split by every usable category with each value's difference, its % of the yardstick and its share of the whole difference. Same rules as "why did it change": no shares where the parts cancel; an average gets no shares; rows holding only one of the two numbers are in neither total, and counted.
* **The bridge** — a waterfall with `bridge_from`: starts at the yardstick's total, one step per category (largest difference first, eight steps, the rest gathered into "All other"), arrives at the number's total; totals drawn grey. Carries the table behind it (`variance`: every category with both numbers, Δ and Δ%). Refused in plain words for an average. Rows with no category are a step of their own, so it always arrives.
* **The grid of the difference** — a heat grid with `difference_of`: each cell is one number minus the other; coloured by sign around zero, surpluses shown with "+".
* **When it is offered:** two numbers that add up, recorded in the **same unit**, whose averages are within 1.5× of each other, plus a category (and a date for the grid). Three cards per pair, at most two pairs. The data does not say which of the two is the yardstick, and every card says so.
* **Checked:** 11 server tests (a planted 30% shortfall in one group), 1 browser test, related suites pass.

**Not done**
* **No real dataset here has such a pair**, so it is verified on planted data only. The first size rule (3×) did fire on the shipments data — a fee against the price of the parcel, which is not a comparison anyone means — and that is why the rule is now 1.5×. A pair is still offered on unit and size alone: nothing checks that the two move together row by row.
* The variance table rides on the bridge's result; no widget shows it as a table yet.
* Numbers with no recorded unit are never paired, even if they plainly are a plan and its actual: the unit has to be classified (by the model once, or by the author).
* The bridge splits by one category; the grid is by month only.
* "Against a target" as a single stored value (not a column) is still §N-7.

## R. §N-4 two groups, one outcome — what was built (2026-10-11)

* **The reading** — analysis `compare_two_groups` (`analysis/two_groups.py`): a column that marks two groups and an outcome. A two-valued outcome (or a named value) is compared as a rate, a number as an average. It returns each group's figure and rows, the difference with its 95% range, the lift over the group set against, the chance the other group is really higher (seeded draws: the same data gives the same answer), a p-value, a curve per group of where its true value probably lies, and one verdict in words — *higher*, *lower*, or *not clear yet* (below a 95% chance either way).
* **What it always says:** if rows were not put in their groups at random, this is a difference between two kinds of rows, not the effect of the group. It cannot know which, so the claim on the card is "association".
* **Refusals in plain words:** more or fewer than two groups; a group under 30 rows. A caveat when one side of a rate has fewer than 5 rows, and when an outcome with more than two values had its rarest value counted.
* **When it is offered:** a column whose stored counts show exactly two values of 30 rows or more each (not a date, not a key), against the outcome that matters — or, with none, the first number. At most two cards.
* **Result view:** verdict first, then each group, both curves on one axis, the difference with its range, lift, chance.
* **Checked:** 7 server tests (a planted 10.5% → 14.2% difference is called; an identical pair is "not clear yet"), 1 browser test. On the real datasets it was offered 13 times (distinct column pairs) and the six run all returned: five "not clear yet", one clear (the price of two body types — a difference between two kinds of rows, as the caveat says).

**Not done**
* No widget: it is an analysis result, not a tile on a dashboard; the reference's row of experiment cards (several at once, each with a status) does not exist.
* Exactly two groups. Several variants against one baseline, with the correction that needs, is not built.
* It is offered for any two-valued column — nothing knows which column, if any, marks an experiment. On descriptive data most readings are honest "not clear yet" or a difference between kinds of rows.
* No "how many more rows until this is clear" (the power side), and no guard against reading the result repeatedly while rows are still arriving.
* An outcome that never occurs in one group reads as a lift of −100%; the caveat about small counts is the only flag.
* Result text is English only.

## S. §N-5 health checks — what was built (2026-10-11)

* **Seven checks, read off the stored profile** (`services/discovery/health.py`), each *passed*, *worth a look* or *failed*, with one sentence and the columns it concerns:
  * **Still arriving** — the newest date against the usual gap between days that hold records (a yearly table is not late after two months). Worth a look at most: nothing knows whether the data was meant to keep arriving.
  * **Rows per month** — the last complete month against the range its own history made likely (the same band the anomaly line uses); a month at half the expected or less fails. Carries the last 36 months of counts.
  * **Columns changed** — columns gone, columns holding another kind of value, columns added, since the last time the *data* was different.
  * **Values present** — empty columns, columns more than half empty (fail), columns missing 5% or more (worth a look).
  * **Values of the right kind**, **columns that vary**, **no copied rows**.
* **What the profile now keeps** (`profile.SCHEMA = 5`): rows per month for a date; and, when the data changes, what the columns were before (`previous`). Both are withheld as the reader's rights require — a hidden column is not named in `previous`, and a reader under a row rule gets no month-by-month volume and no dates.
* **`GET /datasets/{id}/health`** and a **Health checks** panel on a dataset's Overview: the summary line (n passed · n worth a look · n failed), problems first, the rest behind "Show details", the months as bars. English and Arabic labels.
* **Checked:** 7 server tests (each check with a planted fault; the reader's restrictions; the carry-over of the previous columns), 3 browser tests. Live on five real datasets in 0.0–0.7 s, and seen in the browser on the listings dataset (one failed, two worth a look, four behind details).

**Not done**
* The check sentences come from the server in English; only the panel's own labels are translated.
* "Columns changed" has only been exercised by test — no real dataset here changed between two measurements. A dataset rebuilt under a new id has no history.
* Link consistency (§phase 2 #20) is not on this panel: it is about a connection, and the panel is per dataset.
* No history of health over time (the reference's test-result charts by day), no alert when a check starts failing — the platform's existing rule alerts are separate and untouched.
* The older "What you should know" panel (guided setup findings) is still shown on the Columns and Rules tabs; the two are not merged.
* For a live connection the profile is good for a day, so the checks are as of the day's first reading.
* Volume is per calendar month only; a daily or hourly feed that stops for a day inside the month is caught by "Still arriving", not by volume.

## T. §N-6 notes on a timeline — what was built (2026-10-11)

* **The notes** (`widget_data.timeline_notes`): a read line (`anomaly_band` / `change_point`) now carries up to four sentences pinned to their periods — where the level changed ("From 2024-W44 the level rose: about 50,916 before, 86,761 since (+70%)") and the periods furthest outside what their history made likely ("2024-W45: 117,334, where its history made at most 67,288 likely"). In time order, numbered. Written from the figures: what happened and when, never why, and no model.
* **On the chart:** a numbered pin on each of those periods and the sentences under the chart; an author can turn them off (`timeline_notes: false`).
* **A fix to phase 3 found in the browser:** a read line now shows its whole history instead of opening on a sliding window — the shipments line shows all 24 of its marked weeks and the shift, where it showed 2 and no shift.
* **Checked:** 2 server tests, 3 browser tests; seen in the browser on the scratch dashboard (4 notes, 4 pins, 24 dots).

**Not done**
* The sentences are English only, and are not yet part of a page's Summary (takeaways).
* A note cannot be written or edited by the author — the reference's free-text annotations are not built; these are the engine's own.
* Four notes at most, chosen by size alone; periods that return every year (a seasonal peak) still take up notes — see §M on yearly seasons in weekly data.
* Without the sliding window, a line of several hundred periods in a narrow tile has crowded axis labels.

## U. §N-7 a number against its target — what was built (2026-10-11)

* **Where a target lives:** on the column, set by the author — `column_meta[col].target` and `target_period` (each month / quarter / year, or absent for "everything shown"). Read only through `semantic_guard.target_of`. Nothing proposes one: not the engine, not a model.
* **Setting it:** the Columns tab's panel for a number has a **Target** field and, once set, what it is for.
* **Reading it** (`widget_data.kpi_target`): a KPI with `target_value` returns how far along it is (%), what is left, and whether it is met — at or above the target, or at or below it where lower is better. A target for a period is set against the **last complete period of that size**, never against the total of everything shown; with no history of that size, the target comes back as not applied, with the reason.
* **On the card:** "84% of 1,000" with a thin bar, green when met; the reason in words when not applied.
* **Offered:** discovery's headline-number cards carry the stored target (and ask for the history a period target needs). The limits line says the target is the stored one.
* **Checked:** 7 server tests, 2 browser tests. Live through the API on the shipments data (a monthly target read against September 2026; a whole target at 91%).

**Not done**
* The target is copied into the widget when it is suggested; changing the column's target later does not update widgets already on a page.
* Only the headline number reads it. The gauge has its own older `target_value`; bars and lines do not draw a target line from the stored value.
* One target per column — not per category (a target per branch), not per named period (this year's against last year's), and not a forecast.
* Setting a target was not exercised on a real dataset (it would have changed the owner's data); the field is covered by the type check only, with no browser test of its own.
* The card's "of" is English only.

## V. §N scenarios side by side — what was built (2026-10-11)

* **The analysis** — `compare_scenarios` (`analysis/compare_scenarios.py`): two to four named what-ifs, each a set of factor moves, run through the same fitted model as `forecast_scenario` and set beside the projection with nothing moved — a table (total, difference and % against nothing moved, whether it leaves the observed range), the projection period by period for every scenario, and which ends highest and by how much. Nothing new is fitted and nothing is optimised: each scenario is exactly the single what-if's answer.
* **Warnings:** said once when shared; a scenario that goes outside anything observed carries its own name. When the model explains under 30% of the variation that is said first, before any total.
* **Refused in plain words:** fewer than two or more than four; two with one name; one that moves nothing (that is the baseline, always shown); too little history.
* **Offered:** for a date and two numbers with eleven months or more — the first number that adds up, with the next number 10% higher and 10% lower. Claim: hypothesis.
* **Result view:** which ends higher first, then the table, the period-by-period figures behind "Show details".
* **Checked:** 5 server tests (each scenario equals the single what-if; +10% and −10% mirror), 1 browser test. Run on five real datasets.

**Not done**
* **On real data the default card is mechanical.** It pairs the first two numbers: on shipments the fee "follows" weight at 0.99 because both are monthly totals that rise with the number of rows; on listings it offered bathrooms against bedrooms; two were offered where the model explains 3–5% (now flagged first, but still offered). Nothing checks, before offering, that the factor is something a person can move or that the fit is worth reading.
* No chart: the period-by-period figures are a table. No widget, so two scenarios cannot sit on a dashboard, and the reference's two maps side by side are not built.
* The reader cannot name and edit scenarios on screen — the parameters come from the card, the analysis page's generic form, or Ask.
* No optimisation ("which mix is best under a limit"), as §D2 of the plan decided: only when a decision problem is actually stated.
* Result text is English only.

## W. §N stage boards — what was built (2026-10-11)

* **The analysis** — `stage_board` (`analysis/stage_board.py`): a column that says where each row stands, the date it began, and optionally the date it finished and the date it was due. Per stage: rows and share, how many are still going, how long those have usually been going and the oldest; overall and per stage, what finished on time and what is overdue.
* **Three rules, all read from the data:** a row is *open* when it has no finish date (no list of "closed" words); it was *on time* when it finished by the end of the day it was due; it is *overdue* when it is open and its due date is before the **newest date in the data** — never the clock, so a file loaded last month is not all overdue.
* **Order of stages:** the order stored for the column when it has one; otherwise from the stage holding the most open rows.
* **Offered** when the stored figures show the shape: a date that is empty on some rows (0.5%–95%) as the finish, another complete date after the start as the due date, and a category of 3 to 12 values as the stage — one with a stored order or marked as an outcome first.
* **Result view:** rows / still going / overdue / finished on time, then a row per stage.
* **Checked:** 8 server tests, 1 browser test. On real data: three distinct boards offered across 60 datasets. The express-shipments data read 76.5% on time and 188 of 211 open rows overdue; the marketplace orders read 92.1% on time.
* **Found on real data and fixed:** a due *date* was compared with a finish *time*, so a row finished at 15:00 on its due day counted as late (21% on time became 76.5%).

**Not done**
* **Which column is the stage is a guess when nothing is stored:** on one shipments dataset it picked the region instead of the status. The card says so and the parameter can be changed; a check that the stage column actually separates open rows from finished ones would fix it and is not built.
* A row that ended without a finish date (lost, cancelled) counts as still going, and as overdue. Said in the result; not solved.
* No tile, no map of counts, no sparklines per stage — the reference's board is one screen; this is one analysis result plus the KPI, map and line widgets that already exist separately.
* No time *in* a stage (that needs a row per change of stage, which these tables do not have): the age is since the row began.
* Result text is English only.

## X. Second reference set — status (2026-10-11)

Every group proposed in §N is built except the one never planned (grid scoring, #13): §O calendar reading, §P period comparison, §Q one number against another, §R two groups, §S health checks, §T timeline notes, §U targets, §V scenarios, §W stage boards. Each section lists what it does not do.

**What repeats across those lists — the honest state of the engine:**
1. **Offering is still mostly by shape, not by evidence.** Calendar, two-number, two-group, scenario and stage cards are offered when the table *could* support them; only the insight detectors (trend, anomaly, Pareto, …) check the rows first. On real data several of these cards were mechanical (scenarios, two groups) or picked the wrong column (stage). A cheap evidence pass per card kind is the single most valuable next step.
2. **New results are analysis results, not tiles**: why-did-it-change, two numbers, two groups, scenarios and stages cannot sit on a dashboard.
3. **Sentences written by the server are English only**; panel labels are translated.
4. **Nothing runs in the background**: phase 3's tier-2 jobs were not built; everything was fast on the data here, which is not large.
5. **Phases 4 (large data, benchmark-led) and 6 (one engine everywhere — "Suggest dashboards" on a dataset still uses its own route) have not been started.**

## Y. §X-1 a look at the rows before a card is offered — what was built (2026-10-11)

`services/discovery/evidence.py`, run whenever the rows are in hand (depth 1 — every Suggest list): each card that tier 0 offers by the table's shape is checked on the reader's rows and is **kept with what was found**, **kept as it was**, or **withheld with the reason** (returned as `withheld`, so "why was this not suggested" has an answer). A check that fails for any reason leaves its card untouched.

| Card | The check | Withheld when |
|---|---|---|
| weekday × hour grid | spread of an average weekday and of the hours | every day and hour is about the same |
| each year over months / year × month / two-year bars | the same month against its own year's average, across years | never (kept without evidence when the year is flat) |
| one number against another (three cards) | the two move together **row by row** (correlation ≥ 0.5) | they do not — one is not a yardstick for the other |
| two groups | the reading itself | "not clear yet" |
| scenarios | evidence for the factor, a fit worth reading, and the two linked row by row | no link, or linked only because busier periods hold more of everything |
| stage board | which category best separates rows still going from finished ones — **and that column becomes the stage** | no column separates them |
| why did it change | the latest month's move against a usual month's | never (evidence from 2× the usual) |

The sentence of what was found is the card's `found` (and what the Suggest pane shows): "Nov runs +86% against its year's average month and Feb −22%, year after year"; "status separates the 784 rows still going from the finished ones".

* **Checked:** 9 tests, each with a planted case and its absence. On seven real datasets: the shipments board now takes `status` where the shape had picked the region; the fee-against-weight and fee-against-days scenarios are withheld as volume only; a two-group card with no clear difference is withheld; the yearly cards carry the real season (November); 0.1–3 s per dataset in all.
* **Found and fixed on the way:** a weekday that is +2% was announced as the finding when the real pattern was the hours — the sentence now leads with what is large.

**Not done**
* No screen lists what was withheld (the API returns it).
* The checks are on a sample of 200,000 rows at most; the seasonal check needs each month seen in two years.
* A scenario on two columns that are linked row by row but that nobody can move (rooms of a listing) is still offered: nothing knows what a lever is.
* The yearly cards share one sentence (three cards, one finding); ranking keeps at most a few per family.
* Tier 0 (`depth=0`, no rows read) still offers by shape alone — that is what tier 0 is.
* The `found` sentences are English only.

## Z. §X-3 the engine's sentences in the reader's language — what was built (2026-10-11)

The existing mechanism (`readback.Said`: the English sentence plus its key and pieces; the browser says `rb.<key>` from its own catalogue, and anything unknown falls back to English) now carries three more families of sentences — 82 catalogue entries in English and Arabic:

* **What a look at the rows found**, and why a card was withheld (`evidence.py`: `found_i18n`, `reason_i18n`) — shown in the Suggest pane. Day and month names inside a sentence are keys of their own.
* **Notes on a timeline** (`text_i18n`) — under a read line on a dashboard.
* **Health checks**: every title and sentence (`title_i18n`, `sentence_i18n`), including the lists ("… and 2 more").

* **Checked:** a server test that every key exists in both catalogues and that the English catalogue reproduces the server's sentence exactly, for notes, health checks and findings (4 tests; they need the browser's catalogue files and were run with those copied beside the server); a browser test of Arabic rendering with nested pieces (2). Seen in the browser in Arabic on the listings dataset's health panel, then switched back to English.

**Not done — still English whatever the language**
* Card **titles**, **sentences** and **limits** of every discovery card (as before phase 3: only the takeaway line was ever translated).
* Analysis results and their views: why-did-it-change, two numbers, two groups, scenarios, stage board, feature importance — both the server's warnings and the labels in the result views.
* The column profile facts (phase 2), the KPI card's "of" and "vs", weekday and month labels on chart axes, and the Target field's labels.
* Column and value names are shown as stored, in any language.
* Numbers inside sentences use Western digits.
* The four catalogue tests are skipped wherever the browser's files are not beside the server (the server's own container).

## AA. §X-3 continued — the cards in the reader's language (2026-10-11)

* **Every card the engine offers by shape now carries its own words as key + pieces**: title, description, each limits line and the reason (`title_i18n`, `sentence_i18n`, `limits_i18n`, `why.detail_i18n`) — 80 more catalogue entries in English and Arabic (`rb.card.*`). That covers the analysis cards (forecast, why-did-it-change, scenarios, influencers, rules, prediction, groups of rows, baskets, text), the profile cards (mistyped values, copied rows, data delay), the calendar cards, one-number-against-another, the stage board, two groups, and the lines added for history and targets.
* **The Suggest pane says them in the reader's language** (title, reason, limits, and the description when there is no finding to lead with); a widget added from an Arabic pane gets its Arabic title.
* **Checked:** two more server tests — every card produced on four planted tables reads the same from the English catalogue and has its key in Arabic, and every key in the source is in both catalogues; no card offered by shape goes out without keys. 34 catalogue tests pass with the browser's files beside the server. Related suites: 698 server, 4,221 browser (one unrelated export-dialog test failed once under the full run and passed when run alone).

**Still English whatever the language**
* Cards that come from the **insight detectors** keep their English titles (their takeaway line was already translated); so do the names of columns and values.
* The **analysis page as a whole**: every result view (about twenty, the five added here among them) and the warnings the analyses return. This predates the discovery work and is the largest remaining piece.
* The column profile facts, "of" / "vs" on the headline-number card, weekday and month labels on chart axes, the Target field.
* Not seen in the browser in Arabic this time: verified by tests and the type check only.

## AB. §X-3 continued — the five new result views in the reader's language (2026-10-11)

* **Views:** why-did-it-change / one number against another, two groups, scenarios side by side, the stage board, and the feature-importance block now take every label from the catalogue (`res.*`, 39 entries each language); numbers stay as they are and are kept left-to-right inside a right-to-left page.
* **What the analyses say:** their warnings, the two-group verdict, the weak-fit line and the importance note travel as key + pieces beside the English (`meta.warnings_i18n`, `sentence_i18n`, `caveats_i18n`, `importance_note_i18n`; `rb.an.*`, 18 entries each language). A verdict that starts with a group's name no longer has a capital forced onto that name (`readbackText.sayText`).
* **Checked:** a server test runs each analysis in the cases that produce each warning and compares it with the English catalogue exactly, and requires the Arabic key (35 catalogue tests with the browser's files beside the server); a browser test renders the stage board in Arabic. Suites: 496 server (related files), 4,222 browser, type check clean.

**Still English whatever the language**
* The **older result views** on the analysis page (about fifteen: forecast, regression, decision tree, clusters, the statistical tests, text topics and tone, the single what-if, the prediction comparison apart from its importance block) and the warnings those analyses return — including the single what-if's warnings that the scenario comparison passes through.
* The name a scenario is given by the suggestion card ("⟨factor⟩ +10%") is data, shown as written.
* Insight-detector card titles; column profile facts; "of" / "vs" on the headline-number card; weekday and month labels on chart axes; the Target field.
* Not opened in the browser in Arabic: verified by tests.

## AC. §X-2 analysis results as tiles — what was built (2026-10-11)

* **One new widget type, `analysis_result`** (`model_widgets.shape_analysis_result`): `config.analysis` names an analysis and `config.params` are its parameters. Five analyses can be tiles — why-did-it-change, one number against another, two groups, the stage board, scenarios side by side (`TILE_ANALYSES`): each is quick and has a result view of its own. The tile draws **the same view** the Analysis tab does (`AnalysisResultRenderer` → `ResultFor`), so there is one view per result, in both languages.
* **It lives with the page:** it is run on the rows the page shows, after the widget's and the page's filters, like every model widget beside it.
* **What it cannot draw is said in words, never an error:** no analysis chosen; an analysis that is not a tile; a refusal by the analysis itself (three groups, a missing column).
* **How it is offered:** the cards of those five analyses carry `tile` — the widget and the parameters the card ended up with after the look at the rows — and a dashboard's Suggest list adds the tile. The card is still an analysis to run on the dataset page.
* **Registered** in the hand-kept places (roles, browser types, renderer, gallery, labels in both languages) and in the demo. Not proposable by the chart designers: it only arrives through its analysis' card.
* **Checked:** 5 server tests, 3 browser tests; related suites pass (the two demo tests that read the browser's type file cannot run in the server's container, as before). In the browser on the scratch dashboard: the stage board (62,662 rows, 784 still going, 78.9% on time) and why-COD-changed drawn as tiles.

**Not done**
* No panel to choose the analysis or edit its parameters on a tile: it is added from Suggest (or by config). A tile dropped from the gallery says it has no analysis yet.
* Not tiles: feature importance / prediction comparison and the older analyses (slow, or no compact view).
* The tile does not read column classification (shapers are not given it), so a stored stage order is not applied on a tile — the analysis falls back to its own ordering.
* The result views were designed for a page, not a small tile: they scroll inside it rather than adapt.
* No export of the tile to PDF / slides was checked.

## AD. Phase 6, first step — "Suggest dashboards" takes the engine's findings (2026-10-11)

**What phase 6 said, and what was done instead.** The plan was for the dashboard designers to become callers of discovery. Read closely, the dataset's "Suggest dashboards" is not a thin route: it is the analyst panel — several lenses, derived fields, every idea drawn, a gate, a selection by what was drawn, pages with filters, a detail and a quality page — with its own tests and reviews behind it. Replacing it with the discovery engine would have thrown that away. So the engine was made one of its **sources**, which is the part of "one engine" that adds something:

* `discovery.engine.candidates(df, type_map, column_meta)` — the cards kept **with evidence** after the look at the rows (a weekly rhythm, a season, two numbers that move together), one per finding, as the widget that draws each.
* The panel (`suggest_inputs.panel`, used with and without a goal, and by the background job) adds them to its ideas. They pass the **same** gate, are drawn, and are selected or not like any other idea. One that is chosen keeps the engine's own sentence as its takeaway ("Oct runs +112% against its year's average month…"), with its translation key, instead of the generic reading of the chart.
* They are computed on the data's own columns, not on the fields the panel derives for drawing.
* **Checked:** 1 new test; the panel and suggestion suites pass (371). Live, no goal: shipments (7 pages, 41 widgets, the weekday × hour grid chosen), marketplace orders (the grid and the year-over-months line), listings (the year-over-months line); 1–8 s as before.
* **Fixed on the way:** "falls between 00:00 and 24:00" was said when the busy hours were not one stretch of the day.

**Not done**
* The model lenses still invent their own widgets; they do not pick among validated cards (the other half of phase 6).
* The guided setup's designer and the connection designer are untouched.
* Analysis tiles are not offered to the panel: its gate does not know the type, and it scores ideas by what a chart drew.
* Whether a discovery chart is chosen is the panel's selection; nothing reserves it a place.
* On a failure the discovery ideas are skipped silently (logged), and the panel proceeds without them.

## AE. §X-4 slow analyses in the background — what was built (2026-10-11)

* **A job for an analysis** (`services/analysis_jobs.py`, kind `analysis.run`, on the platform's existing job runner): runs as the person who queued it, checked again when it runs; reads the same secured frame the request reads (row rules, hidden columns, preparation steps); stores the same envelope the request returns. The analysis' own refusal becomes the job's error, in its own words.
* **When it is queued** (`POST /datasets/{id}/analysis/run`, new `background`): `true` queues it; `"auto"` — what the browser now sends — queues only an analysis the registry marks as slow (cost tier 2: groups of similar rows, the prediction comparison, influencers, rules, the tree) **on a table of 100,000 rows or more**; absent or `false` runs in the request exactly as before.
* **The browser waits for it** (`analysisCatalogueApi.run`): a queued answer is followed by asking about the job every 1.5 s, and the call resolves with the result — or rejects with the same shape of refusal — so every caller's own "working" state covers both without change.
* **Checked:** 5 server tests (same answer queued as in the request; a quick analysis is not queued; a hidden column and an analysis' refusal fail the job with a reason; one skipped for want of a second-organisation user in the fixture), 3 browser tests. Live: "groups of similar rows" on the 64,000-row shipments queued explicitly, finished in 20 s; with `"auto"` the same call runs in the request, the table being under the threshold.

**Not done**
* The 100,000-row threshold is a guess: no table here is large enough to have measured where a request becomes too long (that is phase 4's benchmark).
* The person is not told it moved to the background, cannot leave and find it again, and cannot cancel it from the screen — the call offers `onQueued` and the job can be cancelled through the jobs API, but no screen uses either yet.
* Only the generic analysis route. The slow **widgets** (the cluster tile's 17 s) and the dedicated routes (`/segment`, `/key-influencers`, `/association-rules`) still run in the request.
* A discovery card's `cost.state` is still always "ready": the cards do not start or track jobs.
* One attempt, no retry: a job that fails is asked for again by the person.

## AF. Phase 4, first step — a benchmark, and what it changed (2026-10-11)

**`backend/scripts/bench_discovery.py`** builds one made-up table per size in memory (a timed start date, a finish date empty on the newest rows, a due date, four categories, a two-valued flag, an outcome, five numbers, an identifier) and times each step once, with nothing cached. Seconds, on the development machine:

| step | 100,000 | 500,000 | 2,000,000 |
|---|---:|---:|---:|
| profile (measured once per version of the data) | 0.34 | 1.0 | 1.3 |
| cards from the stored profile (no row read) | 0.0 | 0.0 | 0.0 |
| insight detectors | 0.26 | 1.1 | 4.16 |
| look at the rows for the shape cards | 0.22 | 0.35 | 0.49 |
| why did it change | 0.06 | 0.22 | 0.91 |
| one number against another | 0.05 | 0.26 | 1.0 |
| two groups | 0.02 | 0.08 | 0.37 |
| stage board | 0.02 | 0.08 | 0.39 |
| scenarios side by side | 0.03 | 0.13 | 0.6 |
| groups of similar rows | 4.0 | 3.95 | 4.01 |
| what goes with an outcome | 0.03 | 0.04 | 0.07 |
| values that appear together | 0.17 | 0.87 | 1.51 |
| rules that separate an outcome | 0.18 | 0.59 | 2.02 |
| prediction comparison + importance | 2.41 | 3.89 | 5.64 |
| line by week, read (band, shift, notes) | 0.07 | 0.25 | 0.95 |
| weekday × hour grid | 0.19 | 0.94 | 3.77 |
| headline number with history | 0.18 | 0.85 | 3.39 |
| bridge between two numbers | 0.01 | 0.06 | 0.21 |
| influencers tile | 0.03 | 0.07 | 0.16 |
| cluster tile | 4.0 | 4.02 | 4.04 |

**What it found, and what was changed**
* **"Groups of similar rows" took 24–26 s at every size — and 12 s on 5,000 rows.** Not the data: the numeric library's 24 threads fighting over a problem that needs one. The same fit took 5 s on 24 threads and 0.03 s on one. The search now runs on one thread (`segment.py`, `threadpool_limits`): **26 s → 4 s, the answer identical** (compared field by field on the benchmark table). This is the cluster card and the cluster tile that every earlier section listed as "17–26 s, belongs in a background job".
* **Nothing else is slow.** The slowest steps at 2,000,000 rows are the prediction comparison (5.6 s), the insight detectors (4.2 s) and two calendar widgets (3.4–3.8 s). The slow analyses sample before they fit, so they barely grow.
* **So the background threshold was wrong.** §AE queued slow analyses from 100,000 rows; on these measurements the request is fine past a million. `BACKGROUND_ROWS` is now 1,000,000, kept as room for a slower host.
* **For the owner's open question on the 2,000,000-row import limit (§I):** at that size, in memory, the engine's own steps are 0–6 s each.

**What this benchmark does not measure**
* Reading the rows: loading 2,000,000 rows from a file or a database, row rules and preparation steps are outside it — the steps start from a frame already in memory. Nor memory under several readers at once.
* One machine, one run per step, one made-up table shape (14 columns). A wide table, long text, or many high-cardinality categories would move the profile and the detectors.
* Live connections (pushed-down queries) and the widgets that go through them.
* Whether the other model fits (the tree, the prediction comparison) have the same thread problem: at 0.2–5.6 s they were not looked into.

## AG. Import performance — a reproducible baseline, and the limits as settings (2026-10-11)

**`backend/scripts/bench_import.py`** — each size in a fresh process, on the seeded twenty-column table the other benchmarks use; best of two runs. On the development machine (65 GB, no container limit):

| rows | file MB | parse CSV s | write copy s | cold load s | in memory MB | peak MB | types s | profile s | first chart s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 250,000 | 48.3 | 0.295 | 0.652 | 0.138 | 166.8 | 682.8 | 0.077 | 1.084 | 0.023 |
| 1,000,000 | 193.4 | 1.207 | 2.233 | 0.502 | 667.1 | 2233.9 | 0.317 | 1.088 | 0.028 |
| 2,000,000 | 386.7 | 2.361 | 4.33 | 0.932 | 1334.2 | 4302.4 | 0.616 | 1.082 | 0.034 |
| 4,000,000 | 773.5 | 4.439 | 8.64 | 1.505 | 2668.3 | 8439.9 | 1.315 | 1.148 | 0.043 |

* **Memory is the limit, not time.** Everything scales in a straight line; a cold load of 4,000,000 rows is 1.5 s. The process peaks at about **2.1 GB per million rows** of this table (the parse and the copy held at once), and a loaded dataset stays at about 0.67 GB per million.
* **The safe limit is worked out, not asserted**, from three rules the script takes as arguments: how many people read large datasets at once (`--readers`, 3), what share of the machine imports may take (`--memory-share`, 0.5), and the longest acceptable cold load (`--max-load-s`, 10). On this host: at least 4,000,000 rows fits. On an 8 GB host with the same rules the answer would be about 600,000 (4 GB ÷ 3 readers ÷ 2.1 GB per million).
* **The import limit itself was not changed** (2,000,000; `import_row_cap`, already an administrator's setting). The owner's rule was "keep it until there are benchmark results": here they are, for this machine. It should be run on the host that will carry the data before the limit is raised there.

**Made configurable** (Admin → Settings; each also an environment variable):
* `analysis_background_rows` (1,000,000) — from how many rows a slow analysis is queued; 0 = never by size.
* `discovery_sample_rows` (200,000) — rows a dataset is measured on for its profile and for the look before a suggestion.
* `model_fit_threads` (1) — threads for the cluster search; 0 = the library's own choice.
* Found missing while doing this: two settings added in phase 0 (`classify_columns_with_model`, `ai_for_uploads_default`) had never been put on the Settings page, which the page's own test requires. They are there now.

**Not done**
* One table shape. A wide table or long text columns weigh more per row; the script takes no `--columns` yet.
* Peak memory is of one process doing everything in turn — an upper figure for an upload, a generous one for a reader.
* Database imports (a query pulled over the wire) are not timed; neither is a refresh.
* Two tests in `test_app_settings.py` fail in this container because its environment configures a list of model endpoints; they are about the model endpoint, not these settings, and were not investigated further.

## AH. One source for AI-designed dashboards — the model chooses among validated charts (2026-10-11)

**The setting:** `suggest_ai_selection` (Admin → Settings → AI model), default **cards**.
* **cards** — the model is shown the charts the platform has already built, validated and drawn on the data (statistics engine, discovery engine, derived fields, standard series), each with the sentence of what it shows, and answers with **ids from that list**. It cannot put a chart on the page that the platform did not make. Two model calls per dashboard: reading the person's goal into questions, and choosing.
* **free** — as before 2026-10-11: the model proposes its own charts, lens by lens; each is then checked and drawn.
* **both** — its proposals join the validated set, and it also chooses among everything that survived.

**How it works** (`analyst_panel.pick_cards`, `run_panel`): what was chosen is valued above anything not chosen, in the model's order, and is placed on the "Your questions" page; the rest of the dashboard is the platform's own selection, as it is with no model. An id outside the list is dropped. A model that fails costs the choice, not the dashboard. The goal and the list are fenced as data. With a goal, the quick "Suggest dashboards" now goes this way too instead of through the quick designer that invented charts.

* **Checked:** 7 tests with a stand-in model (never asked to propose in cards mode; invented ids dropped; free and both as described; nothing asked without a goal; a failure harmless; fencing). The older tests of the free pipeline now say so explicitly. Suites: 527 pass. **Live, with the real model**, on the shipments data and a goal about late deliveries: 55 s, 38 charts drawn, 12 chosen, **0 invented**, eight pages.

**Not done**
* The **guided setup's designer** and the **connection designer** (suggesting before a dataset exists) are untouched: they still design in their own way. Without a goal the guided setup already takes the platform's own selection.
* The reason shown under a chosen chart is the model's few words ("answers Q2 by…"); the chart's own sentence is measured, the reason is not.
* 55 s is almost all the model reading the goal and choosing; nothing was done to shorten it.
* The default changed from free to cards: an install that preferred the model's own charts sets `free`.
* Analysis tiles are still not in the set the model chooses from.

## AI. Localization, independently — an inventory with a ratchet (2026-10-11)

* **`docs/i18n/INVENTORY.md`**: every file that still holds reader-visible English, with its count — **769 literals in 81 files** after this step (802 before), by area and by file, with a suggested order.
* **`frontend/src/test/strings.inventory.test.ts`** + `i18nBaseline.json`: a file may not exceed its recorded number, a file not listed must have none, and a file that improved must be re-recorded. So localization proceeds file by file, independently of everything else, and cannot slide back. The baseline file is the configuration (`ignore`, `files`).
* **Migrated in this step:** the first half of the analysis result views — goal seek, factor bars, "what moves it", the statistical tests' figures, the decision tree, the prediction comparison (26 entries in each language; that file went from 66 to 33).
* **Checked:** the whole browser suite passes (4,383 tests, 354 files), type check clean.

**Not done**
* 769 literals remain; the largest are the column panel (78), the dataset page (66), the workspace tree (54), alerts (42), the command palette (39).
* The second half of the analysis result views: text topics, tone, the single what-if.
* Server-written English outside the scanner's reach (the older analyses' warnings, insight-detector card titles, profile facts).

## AJ. Localization, continued — the result views and the widget body (2026-10-11)

* **Every analysis result view is now translated** (`components/analysis/analysisResults.tsx`, 66 → 0): the second half — text topics, tone, the single what-if — with language names and the tone words in the reader's language (60 more entries each language since §AI).
* **The dashboard widget body** (`components/report/WidgetBody.tsx`, 27 → 1): slicer search and text filter, table and list footers ("Showing 6 of 3,576 rows"), truncation notes, the KPI's "of" and "vs", the regions a screen reader names. The one left is the label of a suggested fix, built in a plain function.
* **Inventory: 710 literals in 80 files** (802 in 81 at the start). `docs/i18n/INVENTORY.md` is regenerated, with what is done and the order for the rest.
* **Checked:** the whole browser suite (4,383 tests) passes; an added test renders an older view (the prediction comparison) in Arabic.

**Not done**
* 710 literals remain; the largest: the column panel (78), the dataset page (66), the workspace tree (54), alerts (42), the command palette (39).
* Server-written English outside the scanner's reach, as listed in §AI.
* Not opened in the browser in Arabic this time.

## AK. Localization, continued — the Columns tab (2026-10-11)

* `components/dataset/ColumnMeaningPanel.tsx` (78 → 0): what a column is treated as and why, how it is summarised, what kind of number it is, which way is good, its target and what the target is for, the order of its values, outcome, place, the "ask AI again" button, every tooltip and saved-message — and the **profile facts** (valid, missing, mistyped, most and least common, length, shape, newest value), which were English however they were listed before. 122 entries in each language; the option lists now hold values only and take their words from the catalogue.
* **Inventory: 632 literals in 79 files.** Whole browser suite passes (4,384).
* Not opened in the browser in Arabic.

## AL. Localization, continued — the dataset page (2026-10-11)

* `pages/DatasetDetail.tsx` (66 → 1): every toast, the refresh and schedule controls, the statistics tables and date summaries, cluster results, pinning a finding, the outlier inspector, the derived-dataset bar, the data tab's notes and empty states (66 entries each language).
* **A neutrality fix on the way:** the filter box's example was a hard-coded Arabic expression about one profession and its pay. It is now a neutral example in both languages (`status == 'open' AND amount > 20000`).
* **Inventory: 567 literals in 79 files** (802 at the start). Whole browser suite passes (4,384).
* Not opened in the browser in Arabic.

## AM. Localization, continued — everything drawn on a dashboard (2026-10-11)

* **35 dashboard components** (`components/report/**`, 128 → 6): every chart renderer's empty state ("Configure widget to see data", "No data."), the names a screen reader announces for maps and charts, the notes about rows not placed on a map or groups not shown, pop-up and tooltip pages, the row-limit note, the box plot's and vector plot's hover text — and the **forecast's goal sentence** in its four cases (expected by a period; already reached; possible only at the optimistic edge; not within the horizon), each as a whole sentence per direction so neither language bends a verb into a template. 107 entries in each language.
* What is left there is example text (an e-mail address, a portal name) and two fragments of longer sentences.
* **Inventory: 445 literals in 48 files** (802 in 81 at the start). Whole browser suite passes (4,384), type check clean.
* Done with a small edit tool that applies exact replacements and adds the translator to each component that now uses it; every file was type-checked and the suite run afterwards.
* Not opened in the browser in Arabic.

## AN. Localization, continued — workspaces and sharing (2026-10-11)

* `WorkspaceTree.tsx` (54 → 0), `FolderShareDialog.tsx` (36 → 0), `DatasetShareDialog.tsx` (14 → 0): creating, renaming, publishing, restricting and deleting folders; every menu item, badge and confirmation; who a folder or dataset is shared with and at what level (93 entries each language).
* `CommandPalette.tsx` (39 → 0): it was already translated through keys; the English written beside each key is what a search typed in English matches, and those lines now say so. One page that had no key got one.
* **A neutrality fix on the way:** the examples in the "new folder" and "new dashboard" boxes named one department and one kind of figure; they are now "Team reports" and "Monthly overview".
* **Inventory: 302 literals in 44 files** (802 in 81 at the start). Whole browser suite passes (4,384), type check clean.
* Not opened in the browser in Arabic.

## AO. Localization, continued — alerts, aggregates, data quality, schema changes (2026-10-11)

* `AlertsPanel.tsx` (42 → 3), `AggregatesPanel.tsx` (30 → 1), `DataQualityPanel.tsx` (17 → 1), `SchemaBreakDialog.tsx` (13 → 0): creating an alert (what to watch, direction, percentage, how often), the function hints in its expression box, building an aggregate (grain, measures, refresh), the data-quality report and its rule results, and the "source changed" dialog (97 entries each language). What is left in them is code: an expression, an address, a column name.
* **A neutrality fix on the way:** the alert form's examples named one kind of figure and one table's column ("Revenue fell below target", `SUM(revenue)`, `COUNT(emp_no)`); they are now "A total fell below its limit", `SUM(amount)`, `COUNT(id)`.
* **Inventory: 205 literals in 43 files** (802 in 81 at the start). Whole browser suite passes (4,384), type check clean.
* Not opened in the browser in Arabic.

## AP. Localization, continued — the query builder and its canvas (2026-10-11)

* `QueryBuilderDialog.tsx` (34 → 1), `QueryCanvas.tsx` (20 → 0): the saved/updated messages, every picker's empty choice, adding joins, columns and group conditions, sort direction, the row-limit note, the function list, the notes about hand-edited SQL, and on the canvas the five join types with their explanations, the join-in-progress banner and every name a screen reader announces (56 entries each language).
* SQL words (`WHERE`, `SQL`) and the generated column names (`__level`, `__path`, `__root_id`) stay as they are in both languages — they are code.
* The join types' English stays in the exported list (other code reads it); the screen shows them through keys by join kind.
* **Inventory: 152 literals in 42 files** (802 in 81 at the start). Whole browser suite passes (4,384), type check clean.
* Not opened in the browser in Arabic.

## AQ. Localization, continued — suggesting from a connection, the join graph, upload, the shared page (2026-10-11)

* `SuggestFromSourceDialog.tsx` (20 → 0), `JoinGraph.tsx` (9 → 0), `pages/Upload.tsx` (14 → 0), `pages/SharedReport.tsx` (9 → 0), `DashboardProposals.tsx` (9 → 5): the "suggest a dashboard" dialog from a connection, the join graph's notes and counts, every upload message (duplicates, partial and total failures, sheets, Access files), the read-only shared page, and the buttons under a proposal in chat (64 entries each language; a few existing keys reused).
* **A neutrality fix on the way:** the suggest dialog's examples named two professions and one kind of workplace; they are now "a team lead, a manager, me" and "where things slow down, and when" (the test's sample input changed with them).
* **Left as it is:** the five headings of the proposal brief in chat follow the language the *answer* was written in, not the screen's language — they already have both languages in the file; moving them to the catalogue would make an Arabic brief show English headings on an English screen.
* **Inventory: 96 literals in 38 files** (802 in 81 at the start). Whole browser suite: 4,382 of 4,384 on the first run; the two failures were tests reading the old wording (one fixed in the test, one by keeping the original English sentence), and the affected suites pass after that (370 tests). The whole suite was not run a second time.
* Not opened in the browser in Arabic.

## AR. Localization, continued — the smaller screens (2026-10-11)

* `StatisticsPanel` (8 → 0), `NotebookSnippet` (7 → 0), `DynamicPinCard` (6 → 0), `EvidencePopover` (6 → 0), `ErrorBoundary` (6 → 0), `SchemaBrowser` (6 → 0), `EmbeddedReport` (5 → 0), `DatasetPickerDialog` (4 → 0): running an analysis, the "use in Python" dialog, a pinned finding's states, the evidence behind a proposed join, the "something went wrong" card, browsing a connection, the embedded page, and choosing a dataset — including its headings and default title, which the scanner had not counted (53 entries each language).
* The error card became a small function component inside the same file, so it can read the reader's language; the boundary itself is unchanged.
* The scanner now also accepts the mark written as a markup comment (`{/* i18n-ok */}`), so a code sample inside markup can be marked where it stands. Three lines marked earlier stopped counting because of this.
* **Inventory: 46 literals in 30 files** (802 in 81 at the start). Whole browser suite passes (4,384), type check clean.
* Not opened in the browser in Arabic.

## AS. Localization — the inventory reaches zero (2026-10-11)

* The last 30 files (46 → 0). Translated: the digits choice in the language switcher, sync progress, the chat history's names for screen readers, lineage ("extract", "Open …"), the home list, "Scanning for insights…", "· live" beside a dataset's name, the description written on a suggested dashboard, the bell's dot, the loading and signing-in pages, the suggestion list of the SQL box, the breakdown widget's two prompts, and the "use Average of …" fix offered when an aggregation makes no sense (23 new entries each language).
* Two sentences that were split between a key and a trailing English fragment are whole now (`cr.firstNodes`, `dd.correctionsAll`).
* Marked as not prose (`i18n-ok`): example addresses, expressions and SQL, a key name, the wordmark, "Ctrl K", "Excel", a CSS block, and the five brief headings in chat that follow the answer's language rather than the screen's.
* **A neutrality fix on the way:** three example placeholders named a kind of customer or company; they are now `my-portal`, `https://app.example.com`, `name@example.com`.
* **Inventory: 0 literals in 0 files** (802 in 81 at the start). Any new hard-coded English in a `.tsx` file now fails `strings.inventory.test.ts`. Whole browser suite passes (4,384), type check clean.
* **Not done:** nothing translated in §AJ–§AS has been opened in the browser in Arabic. The scanner does not see server-written English (older analyses' warnings, insight-detector card titles, column profile facts) or text built in `.ts` helpers.

## AT. Neutrality — the interface's examples, and a test that keeps them so (2026-10-11)

* The low-severity items of table A3 (left open in §K) are done. Eleven examples shown to the user named one field of work or one city — a glossary term and its rule, the Columns tab's roll-up tip, the calculated-column name and expression, a measure type's description, a legend title, the new-dashboard goal, the query builder's dataset name, the alerts empty state, the guided setup's focus, an address in the embed sample. Each now speaks of records, groups, amounts and totals, in both languages.
* An unused catalogue entry ("headcount") was deleted.
* `frontend/src/test/neutralCatalogue.test.ts` reads every string of the catalogues and the builder's label map and fails on a trade noun or place name (the same word list as `backend/tests/test_domain_neutral.py`, plus a short Arabic list). Two entries are allowed, with the reason beside them: a time-zone example and an optional map pack's description.
* The same check, run once by hand over the backend modules the engine test does not list, found only personal-data patterns and the time-zone example.
* Whole browser suite passes (4,385), type check clean; the engine neutrality test and the catalogue-parity tests pass.
* **Left on purpose, as before** (docs/suggestions/PLAN.md §7): field-specific ordered scales are recognised when the data holds them; a tree is found through *parent / manager / supervisor / reports to*; accounting words are money words; personal-data detection keeps its lists; the currency list and the map packs include one country's entries among others.
* **Not done:** the Arabic word list in the new test is short and leaves out «عميل» (also the word for a software client), so an Arabic-only example about customers would pass.

## AU. Closing the gaps, 1 — Arabic on screen, and the English the server still wrote (2026-10-11)

**Looked at in the browser, in Arabic** (signed in as the seeded admin): the home page, datasets, upload, Ask AI, insights, automations, dashboards, connections, lineage, glossary, dataflows, migration, one dataset's six tabs, one dashboard of 14 widgets, and twelve admin and monitoring pages. Method: on each page, every visible text, title, placeholder and screen-reader name that contains an English phrase and no Arabic was listed. Names of the person's own things (datasets, dashboards, connections) are theirs and stay as written.

What that found, and what was done:

| Found on screen | Cause | Done |
|---|---|---|
| Six settings with English labels and help | settings added in §AE–§AH without catalogue entries | entries added; a test now fails when a setting has no label in both languages (`test_app_settings.py`) |
| Lineage badges ("Extracted from…", "N active steps…", "Never refreshed", "3h ago") | text built inside a function call, which the scanner of §AI does not read | translated; the age uses the shared `formatTimeAgo` |
| Footnotes under results: statistical tests, model comparison, what-if, sentiment, clustering, the model widget's leak warning | written by the server as plain English | each is now a keyed sentence (`readback._s`, 45 keys under `rb.st.*`, `rb.ap.*`, `rb.fs.*`, `rb.ts.*`, `rb.sg.*`, `rb.mw.*`), carried beside the English (`caveats_i18n`, `warnings_i18n`) and said from the catalogue by one component (`components/analysis/SaidItems.tsx`) in every result view, the what-if dialog, saved models and the model widget |
| "Overall rate", "strongest lift", "score" in the model widget; "Cumulative share (%)" on a Pareto | names the shapers write | translated where they are drawn |

* A named scenario's "goes outside anything observed" keeps its key through the comparison of scenarios.
* Tests: two new ones — every such sentence has a key in both catalogues with the same pieces; a statistical result's footnotes render from the catalogue to exactly what the server wrote. Whole browser suite passes (4,385).
* **A defect found on the way:** a statistics scan with exactly one tested finding carried no adjusted p-value (`insights._apply_multiple_comparison_correction` returned early), which a test had been failing on since an earlier change to the scan. A family of one now reports its own value.

**Not done, and why**
* **Layout was not judged by eye.** The browser pane available here renders the page too small to read; the check was of text, not of spacing, truncation or mirrored layout.
* The **headline sentence of a statistical test** ("Statistically significant difference in … with a small effect") and its "size of the gap" sentence are still English: they are composed from several clauses and need their own keys.
* **Insight-detector card titles** and **column profile facts** are still English from the server.
* Text **stored when it was written** stays in that language: a guided-setup run's findings and AI-written pages, a job's or an alert's last status and error, a suggested dashboard's description.
* Pages not opened: the report builder's side panels and dialogs, the guided setup's steps, connection review, sharing dialogs, the print view.

## AV. Closing the gaps, 2 — the guided setup's designer can choose among ready charts (2026-10-11)

* New setting **`setup_ai_selection`** (Admin → Settings → AI model): `free` (default) · `cards` · `both`, the same three ways as `suggest_ai_selection` has for "Suggest dashboards", on its own switch.
* **cards:** the platform builds its own charts for the rows the person asked about — the statistics engine's, the discovery engine's, the standard series, and the *plain charts of the data's shape* (how many, per group, over time; each yes/no column's share; each number rolled up the way the platform already rolls it up) — up to 130. The model answers with pages of **ids from that list**, a question id for each, and may give each chart a title and a reason in the person's language. It cannot change a chart or add one (`answer.validated_cards`, `standard_cards`, `pick_pages`). Every chosen chart still goes through the designer's gate.
* **both:** it chooses first; the designer's existing repair round then designs only for the questions no ready chart answered.
* If choosing returns nothing in `cards`, the flow falls back to the platform's own selection, as it does with no model.

**Measured live** (real model, one request of five questions in Arabic about the returned part of a 64,420-row table):

| Mode | Time | Pages | Questions answered | Note |
|---|---|---|---|---|
| free | 66 s | 3 | 5 of 5 | each chart filtered to the returned rows where the question needed it |
| both | 108 s | 2–3 | 5 of 5 | |
| cards, found charts only | 20 s | 2 | 2 of 5 | |
| cards, with the plain charts | 25 s | 2 | 3 of 5 | one of the three answered "which area has most returns" with a count of **all** rows per area |

**Why the default is `free`.** A question about a *part* of the rows needs a filter on a value, and no ready-made chart carries one; in `cards` such a question is left unanswered or, worse, matched to a chart of everything. In `free` each chart is still drawn and judged on the rows before it is offered, so nothing unchecked reaches the page in any mode. The setting is there for an installation that prefers speed and a closed menu.

* Tests: 7 (a page holds only charts from the list; invented, repeated and non-numeric ids dropped; a failure is harmless; the list and request are fenced; the plain charts never use an identifier, a personal column or a column that may not be shown; the switch is its own).

**Not done**
* The **connection designer** (suggesting before a dataset exists) is unchanged, on purpose: until it has written a query there are no rows and so no ready charts to choose from; the query itself must come from the model; and its charts are already judged on the rows the query returns. Choosing among ready charts built on the query's result is possible as a later step; it was not built or measured.
* Ready charts filtered to one value (the missing piece above) were not generated.
* "Change this page" in the guided setup (a person's own typed request) still designs freely in every mode.
* `cards` and `both` were measured once each, on one request.

## AW. Closing the gaps, 3 — AI switched off (2026-10-11)

* **Page copilot.** With "Allow AI" off for the data it no longer refuses (409). It answers in plain words that the page was not changed, names the columns the typed words point at, and lists up to five charts the platform has already built and checked on this data for those columns, each of which can be added from Suggest (`services/copilot_without_model.py`; reply carries `without_ai` and `suggestions`). When the model is on but does not answer, the reply is still the 502 it was: a test and the builder depend on telling the two apart.
* **Ask AI's SQL writer.** The catalogue it is shown (table and column names, descriptions, value labels, glossary) is now fenced as data like every other piece of the person's own text.
* Tests: 3 for the no-AI answer; the copilot's "AI is off" test now expects the answer instead of the refusal.
* **Not done:** the no-AI answers of Ask AI and the copilot are written in English only. The copilot's suggestions are listed in words; the chat does not yet draw them as buttons.

## AX. Closing the gaps, 4 — limits (2026-10-11)

| Limit | Setting | Default | How |
|---|---|---|---|
| A query on **SQL Server** | `source_statement_timeout_s` (existing) | 900 s | pymssql: the driver's query timeout; pyodbc: set on each new connection |
| A query on **Oracle** | same | 900 s | python-oracledb: `call_timeout` on each new connection |
| One **background job** | `job_time_limit_s` (new) | 7,200 s | past it the job ends as failed with a plain sentence and the worker is free; 0 = none |
| **AI tokens per person per day** | `ai_tokens_per_user_per_day` (new) | 0 = off | the tighter of this and the organisation's budget binds; the refusal says "your own AI budget"; scheduled work is charged to the organisation only |

* Tests: 5 for the two database families (arguments, and the attribute set on a stand-in connection; the engine runs the hook on every new connection), 1 for the job limit, 3 for the per-person budget.
* **Not verified against real servers:** no SQL Server or Oracle database is available here. The driver attributes are the documented ones; the behaviour on a live server was not observed.
* A job stopped by the limit has its coroutine cancelled; work it had handed to a thread (a model fit, a blocking driver call) runs to its own end in the background.
* **A fixture fixed on the way:** two Ask AI budget tests had been failing since "Allow AI" became one switch (§K) — their connection had it off, so no model was asked and nothing was metered. The fixture now allows AI.

## AY. Phase 5 — cohorts, how sure a what-if is, and a decision written down (2026-10-11)

The three capabilities of §G phase 5 (§D-19, §D-15, §D-21). Each is offered only when the table has the shape for it.

### Who comes back (`cohort_retention`)

* For a table where the same identifier appears on many rows over time. Each one's **cohort** is the period of its first row; it **came back** in a later period when it has at least one row there; **retention** is the share of a cohort seen again *k* periods after its first. Day, week, month, quarter or year; up to 12 periods; the newest 24 cohorts.
* A cohort that has not lived through a period yet has an **empty** cell there, never a zero. A cohort of fewer than 20 is flagged. The last row is all cohorts together, weighted by size, counted only over the cohorts that reached each period.
* **Offered** when a key repeats — at least 30 different values, more than 1.5 rows each — beside a date; a column of names with no fixed shape is not taken for an identifier. A look at the rows keeps the card only if there are at least three cohorts, and says what it found ("x% are seen again the month after their first…").
* Analysis tab: "Who comes back?". As a tile on a dashboard: yes.

### How sure a what-if is (`simulate_scenarios`)

* The what-if model of `forecast_scenario`, run 2,000 times with its **coefficients** drawn from their estimated distribution and **each period's noise** drawn from the size of the fit's misses. For each scenario's total over the horizon: the middle, where 9 runs in 10 fall, where the middle half falls, the **chance of ending below doing nothing**, and — given a floor — the chance of ending below it.
* The **same draws** for every scenario and the baseline (they differ by what was moved, not by luck), and a **fixed seed** (the same data gives the same answer every time).
* One number is enough to ask: "move each factor by 10%" makes an up and a down scenario; named scenarios are accepted too.
* It carries every warning of the what-if it rests on (association, not intervention; a scenario outside anything observed is named), and says first when the model explains little.
* **Offered** beside "scenarios side by side", under the same look at the rows: withheld when the factor and the number rise together only because busier periods hold more of everything.
* Analysis tab: "How sure is a what-if?". As a tile: yes.

### A decision to set up (`discovery/decision.py`)

* **Recognised by shape, from the stored profile:**
  * *a choice among options* — one row per option (a key that never repeats), at least two amounts that add up, 5 to 5,000 rows, and **no date column**: a dated row is something that happened, not an option;
  * *a matching of two sets* — two columns whose pairs fill at least half of the grid (every one of the first against every one of the second), with a number per pair, and no date column.
* **Nothing is inferred about roles.** The person says which amount to make as large or as small as possible, which is limited and by how much (or how many options may be chosen); for a matching, how often each side may be used. That is checked on the rows — each row really one option, each pair really once, the limit above zero and not excluding everything, six of one side cannot each be matched to five of the other one-to-one — and refused in plain words when it cannot be a decision.
* **What comes back** is a document, `schema: datalytics.decision-problem/1`: objective (direction, column), decisions (one per row, in or out), constraints, the columns involved, and checks worth knowing (a limit that rules nothing out; rows with no value; pairs missing from the grid). It holds no row of the data. It is **not solved, stored or sent anywhere**; the person may download it.
* A reader under a row rule is offered nothing ("one row per option" is not true of a part of the table); a hidden column cannot be named.
* Routes: `GET /datasets/{id}/decision-problems`, `POST /datasets/{id}/decision-problems/specification`. Analysis tab: "Is there a decision to set up?" — what was written is said in plain words first; the document is behind "Show details".

### Checked

* Tests: 31 on the server (cohorts counted by hand on a case of four; retention recovers the rate put in; a second row in a month changes nothing; the simulation's middle is the single what-if's total within 1%, a factor that really moves the number leaves under 1% chance of ending below doing nothing, a factor that does nothing lands between 5% and 95%, identical on a second run; a decision is recognised, refused for a dated table, for a repeated key, for too few options, for a sparse grid; the specification says exactly what was said; the routes as a reader, with a hidden column, across organisations) and 6 in the browser (the two result views; the decision form sends exactly what was chosen and shows the reason when refused).
* **Live, on the 64,420-row shipments table:** no decision is offered (every row is dated) and no cohort card (it has no repeating identifier, only names) — as intended. Run by hand on the names column: 311 of them, 9.9% seen again the month after their first, 0.2 s. The simulation by hand on fee against weight: 0.2 s, 0% and 100% chance of ending below doing nothing — and the engine had **withheld** that card, because the two are linked only by volume. Seen in the browser in Arabic: the three new questions on the Analysis tab and the "no such shape" answer.

### Not done

* No table in this installation has the shape of a decision or a repeating identifier, so those two were checked live only in the negative; their positive cases are the tests.
* The third decision shape of §D2 (**maximise a fitted response model** under ranges) is not written down as a specification: it needs the simulation's model exposed as an objective, which was not built.
* The simulation draws from what the model estimates about itself; it does not widen for a model that is wrong in form (a curve fitted as a line). It says so.
* The decision card appears in the engine's card list, but only the Analysis tab opens its form: the builder's suggestion pane shows charts only.
* Refusals of the three (and of every analysis) are written by the server in English.
* The analysis names in the Analysis tab's own list ("cohort retention") are the registry's English names, as for every analysis; five common form labels were translated on the way.

## AZ. Closing the gaps, 5 — the three failing Ask AI cases (2026-10-11)

The benchmark (26 questions, English and Arabic, `docs/ASK_BENCHMARK.md`) had three cases failing before and after phase 0. Each was looked at:

| Case | What was wrong | Done | Now |
|---|---|---|---|
| "By how much did A's total exceed B's?" (English) | sent to a significance test between all groups; the answer was a p-value and a gap of averages | a question that asks *by how much*, *how much more*, or *the difference between* is an amount, not a test (`classify.settle_intent`, English and Arabic wording) | passes |
| A column the data does not have, asked in Arabic | the answer declined correctly; the **scorer** did not recognise "this data does not contain…" | scorer's refusal wording extended, English and Arabic | passes |
| Average of a percentage column, asked in Arabic | the dataset has a **defined measure** "Margin % (on totals)"; the Arabic wording is read as naming it (9.98%), as the platform's own rule for defined measures says, while the English wording is read as the column and averaged (19.01%), which the benchmark expects | a prompt line preferring the stored column was tried and **removed** — it contradicted the defined-measure rule and changed nothing | **still fails**; which answer is right is the owner's call |

* Run three times today: morning (three fail), with only the schema fenced (the same three fail — the fence changed nothing measurable), and after these changes: **25 of 26**; English 10 of 10 answers, Arabic 9 of 10; refusals 3 of 3 in both; no ungrounded answer. All targets met.
* Tests: three routing cases and two refusal phrasings added.
* **Not done:** the Arabic average is left as it is: it follows the dataset's own defined measure. Either the benchmark case should expect the measure in both languages, or the question should name the column; that is a decision, not a fix.

## BA. The whole backend suite, run end to end (2026-10-11)

Until now only the suites near each change had been run. The whole suite (7,862 tests, 24 minutes in the container) was run once after §AU–§AZ: **7,811 passed, 25 failed, 25 errors.** Every one was looked at.

| What failed | Why | Done |
|---|---|---|
| 43 of the 50: the architecture documents, the capability matrix, the demo reports, the live-query demo, the evaluation order | they read files outside the container (`docs/`, `frontend/src`, `ARCHITECTURE.*`) | run again with those files supplied: all pass except the count check below |
| Counts in `ARCHITECTURE.md` and `.html` (tables, widget types, migrations, backend test modules, frontend test files) | the documents had not followed the code | updated in both: 96 tables, 77 widget types, 65 revisions, 516 test modules, 356 test files |
| New data routes missing from the cross-surface security inventory | eight routes added since phase 0 were never listed | **opportunities, column profile, health and decision problems now go through the harness** — another organisation and a colleague without access get 404; a reader with a hidden column and a row rule gets neither; all pass. The specification, Allow AI, column lineage and "classify again" are listed with the reason each returns no row |
| A service importing the web framework | the background analysis job caught the router's HTTP error by its class | caught by its shape instead; the layer rule holds |
| A column marked as an identifier still entered correlations | `is_quantity` read the name only, not the stored role | **a real defect, fixed**: the person's own word for the column counts |
| "salary is averaged", "pay findings are about averages", and "IMSI and LAC stay out of correlations" | these tests expected the platform to know one field's column names, which phase 0 removed on purpose | the tests now give the columns their stored classification, under which the same behaviour holds; one line asserts that the bare name decides nothing |
| The classifier's Arabic example | the test looked for the example that phase 0 replaced with a neutral one | test updated |
| Two settings tests, one model-endpoint test | they read the container's own list of model servers | the tests now set that list aside; they pass |

* After the fixes, every affected suite was run again (1,173 tests) and the document tests with their files (107): all pass. The whole suite was **not** run a second time end to end.
* Whole browser suite: 4,391 pass; type check clean.
* **Afterwards:** the two settings tests and the model-endpoint test that failed only in this container now set aside the machine's own list of model servers, and pass. Nothing in the backend suite is known to fail.
