# All-Layers Gap-Closure Pass

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Close the highest-value open gap in every layer of ARCHITECTURE_COMPARISON.md's recomputed "remaining gap" — Layer 3's retrieval substrate (the measured accuracy ceiling), Layer 2's telemetry + drift wire, Layer 5's forecast upgrade, Layer 6's page-type triggers, Layer 7's share-link pinning, plus the MCP client fix — then re-measure the agent and re-score the comparison a fourth time.

**Spec authority:** `AI_data_tool/ARCHITECTURE_COMPARISON.md` (third re-scoring — each task cites its row) + `docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md` (measurement appendices name the two semantics gaps tasks T1/T2 close).

**Baseline:** master `638b8fc`, 1934 backend + 717 frontend green. Agent measured: 48% completion / 75% value-verified / 32% clarification on the 25-question maps golden set.

## Global Constraints

Identical to the prior three SDD runs on this repo: Docker tests via PowerShell (`docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <args> -q --no-header -p no:warnings`); frontend `npx vitest run` locally; focused tests per task + full suites at checkpoints; BOM files (`models.py`, `main.py`, `config.py`) utf-8-sig; `_migrate` ALTER-IF-NOT-EXISTS for new columns on existing tables, plain create_all for new tables; `check_org` 404 convention; provenance ladder respected; additive only; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

**Deliberately OUT of this pass** (rulings, recorded up front): Valkey/Redis (new infra service — deployment decision, not code); embeddings/pgvector R.1–R.7 (the Qwen endpoint serves a chat model, no embedding API — infra-blocked; lexical retrieval via T3/T4 instead); rewriting `sql_expr.py` onto sqlglot (working security code, high-risk refactor, nothing broken); Layer 7 embeds (own project); real CI (repo has none — T13 ships the report tool + a documented gate script instead).

---

## Phase L3 — the measured accuracy ceiling

### Task T1: Canonical-source flags
**Comparison row:** Block B "canonical-source flags — cheapest single item with a measured wrong answer waiting on it."
- `SourceObject.is_canonical` Boolean (default false, server_default "0") + `_migrate` line.
- Review payload (`routers/metadata.py`) exposes it; `object_updates` accepts `{"is_canonical": bool}` (admin path that already exists).
- `agent/context.py`: `ObjectInfo` gains `is_canonical`; `render()` marks such objects `[CANONICAL — the source of truth for what it describes; prefer it over recomputing from raw tables]`.
- `agent/nodes/generate.py`: prompt instruction — a canonical object beats the base-table preference when both could answer.
- Frontend `SourceOverview.tsx`: a small "mark canonical" toggle per described object (admin), calling the existing confirm/object_updates API.
- Tests: model round-trip; render marks it; generate prompt contains the instruction; review API toggles it; cross-org 404 unchanged.

### Task T2: Enum value labels
**Comparison row:** L3 gap #2 — "`top_k` knows st_cd holds 1,2,3; the MEANING (3 = cancelled) is missing."
- `SourceColumn.enum_labels` JSON nullable ({raw value (stringified): label}) + `_migrate` line.
- Describe stage (opt-in LLM, `background=True`): for columns whose `ColumnStats.top_k` has ≤12 distinct values and no labels yet, one batched per-object call drafting labels from name+description+values; stored with `description_source`-style provenance semantics (never overwrite human edits — reuse the confirmed check pattern).
- Review UI: labels editable per column (columns tab), saved via `column_updates` (add `enum_labels` handling; human edit wins forever — mirror description_source=confirmed logic with a sibling `enum_labels_source`).
- `context.render()`: columns with labels render `st_cd (integer: 1=new, 2=paid, 3=cancelled)`.
- Tests: sync drafts labels only where eligible; confirmed labels survive resync (provenance test — the layer's core rule); render carries them; API round-trip.

### Task T3: Glossary + synonyms (incl. Arabic aliases)
**Comparison row:** L3 gap #3 — "'إجمالي المبيعات' and 'GMV' cannot resolve to the same metric."
- New table `glossary_terms(id, org_id, data_source_id nullable, term, definition, synonyms JSON list, maps_to_object nullable, maps_to_column nullable, created_at)` (create_all).
- Admin CRUD in `routers/metadata.py` (`GET/POST/DELETE /data-sources/{id}/glossary`), org-scoped 404s, term+synonyms non-empty validation.
- `agent/context.py`: `load_context` loads the source's terms; `SchemaContext.glossary_for(question)` — case-insensitive substring match of term/synonyms against the question (unicode-safe, works for Arabic); `render()` gains a "Glossary (terms from the question)" block listing matched term → definition → maps-to.
- `graph.py`: classify + generate both receive the glossary-enriched render (they already call `context.render()` — the enrichment needs the question, so add `render(question=...)` optional param; None keeps old output byte-identical).
- Tests: match incl. Arabic string; unmatched terms not rendered (prompt budget); maps_to surfaces; CRUD + org scoping; render(question=None) unchanged.

### Task T4: Join-path resolution
**Comparison row:** L3 gap #7 — "you have edges, not resolved paths."
- `agent/context.py`: `SchemaContext.join_path(from_table, to_table) -> list[JoinInfo] | None` — BFS over the confirmed/declared whitelist (no networkx; the graph is ≤hundreds of edges). `render()` unchanged (paths are computed, not dumped).
- `agent/nodes/generate.py`: when the question's glossary/table matching implies two tables with no direct edge, the graph (in `graph.py`, before generate) computes the path and appends `Join route: a.x = b.y THEN b.z = c.w` to the step question context. Keep minimal: a helper `suggest_join_route(context, tables)` used by graph.py when the plan step mentions ≥2 known table names.
- Tests: two-hop path found; no path → None; inferred-only edge never used in a path (F1); the route string reaches the generate prompt in a stubbed run.

## Phase L2 — engine hygiene

### Task T5: `query_runs` telemetry
**Comparison row:** L2 gap #7 — "the training signal for layer 4."
- New table `query_runs(id, org_id, source_kind ['directquery'|'import'|'agent'], data_source_id nullable, dataset_id nullable, sql_hash nullable, rows_returned, duration_ms, executor ['pushdown'|'pandas'|'duckdb'], cache_hit bool, created_at)` (create_all). No raw SQL stored (hash only — run records must not become a place values live).
- Write points: `direct_query.run_direct_query` (pushdown), the widget pandas path's main entry (one clean choke point — find it in `widget_data.py`), and `agent/executor.py` both executors. Fire-and-forget: a failure to log NEVER fails the query (try/except, log warning).
- Tests: each path writes one row with the right executor tag; logging failure doesn't break the query; no SQL text in the row.

### Task T6: Drift → cache invalidation
**Comparison row:** L2 gap #4 — "the drift signal exists; nothing subscribes."
- Cheapest correct mechanism: per-source **cache epoch**. `DataSource.cache_epoch` Integer default 0 + `_migrate`. The sync's drift stage, on `changed: true`, increments it (same transaction).
- Widget/DirectQuery cache keys (find `_widget_data_cache_get/set` + the frame-cache key builders) fold the epoch in — old entries become unreachable (LRU evicts them naturally).
- Tests: drift bump changes the key → stale entry not returned; no drift → keys stable; import datasets without a source unaffected.

## Phase L5 + misc backend

### Task T7: Forecast upgrade
**Comparison row:** L5 row #1 — hand-rolled smoothing → statsmodels (already pinned in requirements, unused for prediction).
- `shape_forecast` in `widget_data.py`: use `statsmodels.tsa.holtwinters.ExponentialSmoothing` (additive trend, seasonal if ≥2 full periods detectable) with the existing hand-rolled math as explicit fallback (short series, fit failure); add `lower`/`upper` naive confidence band (±1.96·residual std). Response shape stays backward-compatible (new keys additive).
- Tests: known series → statsmodels path taken (assert against a tolerance, not exact); 3-point series → fallback path; band keys present; existing forecast tests untouched/green.

### Task T8: MCP client reuse
**Comparison row:** "known wart, re-verified" — `mcp_server/server.py:23-28` builds a client per tool call.
- Module-level lazily-created `DatalyticsClient` (thread-safe once-init), reused across calls; close on process exit (atexit). Respect whatever auth/config `_client()` reads today.
- Tests: `mcp_server` tests if any exist (check `backend/tests` + `mcp_server/`); else a unit test asserting two tool invocations share one client object (monkeypatch the constructor, count).

### Task T9: `evals/report.py` + gate script
**Comparison row:** L4 "a library, not a gate."
- `evals/report.py`: takes a results JSON (the shape `evaluate()` returns + per-question rows), prints the per-intent table and exits non-zero if overall accuracy drops below a `--min-accuracy` threshold.
- `backend/run_eval_gate.ps1` (documented in `evals/README.md`, 20 lines): restart-backend → run the golden set → report — the manual gate until CI exists.
- Tests: report formatting + threshold exit codes (subprocess or function-level).

## Phase L6 — page-type triggers (frontend)

### Task T10: Popup overlay renderer
**Comparison row:** L6 verified gap A.
- View mode: navigating to a `page_type='popup'` page renders it as a centered modal overlay (dim backdrop, close button, Esc) over the CURRENT page instead of a tab switch; the tab strip never shows popup pages in view mode. Edit mode unchanged.
- Update `PagePropertiesPanel.tsx` popup desc if it hedges; update the UX Showcase seeder copy (`demo_content.py`) that honestly said "opens as a tab" → now true overlay (and its test pinning that copy).
- Tests: navigate-to-popup renders overlay not tab switch; Esc/close returns; non-popup unchanged.

### Task T11: Drillthrough trigger
**Comparison row:** L6 verified gap B (half of it).
- On charts in view mode: when the report has ≥1 `drillthrough` page, the existing datapoint click flow gains a "Drill through → <page>" affordance (context menu or modifier-click — match the existing interaction idiom found in the renderer); navigating carries the clicked dimension value as a page filter (reuse the existing filter-chip mechanism the drill flow already uses).
- Drillthrough pages hidden from the view-mode tab strip (reachable only by drill-through, per the page type's own description).
- Update `PagePropertiesPanel.tsx:18` to drop "(not yet triggerable)"; update UX Showcase copy + tests.
- Tests: drillthrough target reachable from a datapoint with the filter applied; page absent from tabs; reports without drillthrough pages unchanged.
(**Tooltip pages stay "(not yet triggerable)"** — hover-rendered live pages are a perf/UX project of their own; recorded, not attempted.)

## Phase L7

### Task T12: Share-link revision pinning
**Comparison row:** Tier 2 #7b — "a link you sent silently shows whatever the report became."
- `share_links` (find the real table/model name) gains `snapshot` JSON nullable + `pinned` bool default false + `_migrate` lines. On link creation with `pinned=true` (new optional API param, default false = today's behaviour), store the report's render-definition (pages+widgets config JSON — reuse whatever the report GET serializes).
- The shared-view endpoint serves from `snapshot` when present (data still live — the PIN is the layout/config, not the data; state this in a comment and the UI label "Layout pinned at share time").
- Frontend share dialog: a "Pin current layout" checkbox.
- Tests: pinned link unchanged after report edit; unpinned link follows edits; RLS/org behaviour of shared views untouched (their existing tests stay green).

## Phase final

### Task T13: Re-measure + fourth re-scoring + merge
- Seed 2-3 canonical flags + a handful of enum labels + 2 glossary terms on the live maps source (via the new APIs), restart, re-run the 25-question golden set (same method, fourth round): does the symbols question flip to correct? Completion/accuracy/clarification vs the 48/75/32 baseline. Append to the spec appendix.
- Full backend + frontend suites.
- Fourth re-scoring of ARCHITECTURE_COMPARISON.md (+HTML): L3 +T1-T4, L2 +T5-T6, L5 +T7, L6 +T10-T11, L7 +T12, misc; recompute overall.
- Merge to master (established fast-forward pattern).

## Batching (single implementer at a time, review each batch)
1. T1+T2 (catalog semantics, backend+small UI)
2. T3+T4 (glossary + paths)
3. T5+T6 (L2)
4. T7+T8+T9 (misc backend)
5. T10+T11 (frontend L6)
6. T12 (share pinning)
7. T13 (controller-led measurement + re-scoring)

## Verification
Per-task tests as specified; checkpoint full suites after batches 2, 4, 6; T13 is the end-to-end proof (live measurement + doc). The agent-accuracy claim of this whole pass is falsifiable by T13's numbers — report them whatever they are.
