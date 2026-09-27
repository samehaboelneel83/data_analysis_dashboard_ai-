# Datalytics — Development Session Handover

*Written 24 Sep 2026 at the end of a long Claude (Cowork) session. Everything here was checked against the repository when it was written; anything uncertain is marked **(uncertain)**. The code wins over this document wherever they disagree.*

---

## 0. Update: continuation session (24 Sep, Claude Code on the web)

This section is newer than everything below it. Where they disagree, this section is right.

**Git state:** the project is now on GitHub (`samehaboelneel83/data_analysis_dashboard_ai-`). `main` is a single "Initial commit" containing the whole workspace; the code is under `AI_data_tool/data_analytics/`. This session's work is on the branch **`claude/awesome-keller-qmxzls`** (pushed, no pull request opened). `masterplan/complete` and the commit hashes in §1 belong to the local Windows repository and do not exist on GitHub.

**Done this session (the three "next tasks" from §16):**
1. ✅ **ARCHITECTURE docs count:** now **212** frontend test files (211 plus the new `atlasLazy.test.ts`). `tests/test_architecture_doc.py` passes (35/35).
2. ✅ **Python security upgrade applied** in `backend/requirements.txt`: `fastapi==0.136.3`, `starlette==1.7.0` (now pinned explicitly), `python-multipart==0.0.31`, `python-jose[cryptography]==3.5.0`. Proof: two full backend sweeps on Python 3.12 (the Dockerfile's version), old pins against new, both **5,309 passed / 5 skipped / 3 failed**. The 3 failures are the same LLM-dependent `test_automation_runner.py` tests on both sides (the endpoint can't be reached from the cloud container). `pip-audit`: 46 advisories → 13 (setuptools 4, pyarrow 3, pytest 2, protobuf 2, ecdsa 2).
3. ✅ **Bundle performance:** the world atlas (~740 kB raw) had slipped back into the eager path. `chartRenderers/index.tsx` imported `GeoContourRenderer` statically; `ReportBuilder` imported `GeoMatchCheck` statically; `WidgetConfigPanel` used `useGeoMatch` directly. All three are lazy now (`GeoMatchLine.tsx` and `GeoMatchStatus.tsx` split out of `WidgetConfigPanel`). Static JS beyond the app shell: builder 1,939 → 1,159 kB raw (557 → 313 kB gzip), shared link 1,470 → 698 kB (434 → 192), embed 1,468 → 696 kB; the `WidgetRenderer` chunk 950 → 179 kB. `src/components/report/geo/atlasLazy.test.ts` walks the static import graph and fails with the import chain if this regresses. The only chunk still over Vite's 500 kB warning is `worldGeometry` (the atlas itself, loaded only with a map).
- Frontend after these changes: **212 files / 2,698 tests pass**; `tsc` 0 errors; `vite build` OK.

**Second round (same session):**
4. ✅ **The 2 unhandled errors in `ReportBuilder.test.tsx`** are fixed, and the full frontend suite now **exits 0** (212 files, 2,698 tests, 0 errors). One test was stale: with no widget selected, a field click now *builds a new chart*, but the test never mocked `addWidget`'s result, so the undo snapshot read `.layout` of undefined after the test had ended. It now asserts that behaviour. The other: jsdom has no `scrollIntoView`, now polyfilled in `src/test/setup.ts`.
5. ✅ **More Python advisories:** `pyarrow` 16.1.0 → **23.0.1** (clears CVE-2024-52338, code execution when reading untrusted IPC/Parquet, which matters because uploads are Parquet) and `setuptools` 75.6.0 → **80.10.2** (the newest that still ships `pkg_resources`). Full sweep: **5,309 passed / 5 skipped / 3 failed** (the same LLM tests). `pip-audit`: 13 → **4**.
6. ✅ **Route-walking tests work on any FastAPI version** (§13 low-priority 3): `backend/tests/_routes.py` flattens `_IncludedRouter`; 58 passed on FastAPI 0.136.3 **and** 0.141.1 (the old tests fail 4 on 0.141.1, and their admin sweep collected nothing). A new guard fails if the admin sweep ever finds no routes. **FastAPI ≥ 0.137 is no longer blocked**; it needs only the usual full sweep (§12's "stay on ≤ 0.136.x" rule is lifted).

**Remaining advisories and why they stay:**
- `protobuf` 4.25.9: OpenTelemetry 1.27's `opentelemetry-proto` requires `protobuf<5`. Fix = upgrade the OTel line (api/sdk/exporter plus the 0.4x instrumentation line) together, then sweep.
- `setuptools` PYSEC-2026-3447 (fix ≥ 83): ≥ 81 drops `pkg_resources`, which OTel 1.27's instrumentation imports. It falls with the same OTel upgrade.
- `ecdsa` 0.19.2: no fix exists. It is pulled in by python-jose, which uses the `cryptography` backend here, not ecdsa.
- `pytest` 8.2.2 (fix 9.0.3): test-only; pytest 9 is a major version and needs pytest-asyncio 0.23.7 checked with it.
- npm `pptxgenjs` → `image-size` (high): **not reachable in the app.** pptxgenjs's `browser` field maps `image-size` to `false`; it runs only under Node. The production bundle contains no `image-size` code. npm's "fix" is a downgrade to pptxgenjs 2.2.0; don't take it.
- npm `vite` 5 / `vitest` 2 / `esbuild` (critical/high, **dev server and test UI only**, not in the production bundle): needs vite 8 + vitest 5, both major. **Waiting on the user's go-ahead** (§15: major upgrades with behaviour risk are the user's call).

**User actions now needed:** rebuild the backend image (`docker compose build backend`) to pick up the new pins, and the frontend image as before. Merge `claude/awesome-keller-qmxzls` when you're happy with it.

**Next pending, in order:** (a) the OpenTelemetry upgrade that unlocks protobuf ≥ 5 and setuptools ≥ 83; (b) vite 8 / vitest 5 once the user agrees; (c) pytest 9; (d) optionally FastAPI 0.141 (sweep only); (e) the §13 low-priority items: the builder toolbar tap-target decision, and verifying the shared-link view on a real phone.

**Tip for a cloud session:** `node_modules/` and `dist/` are not in `.gitignore`. Add them to `.git/info/exclude` before `npm ci` so they never get committed.

---

## 1. Project overview

**Name:** Datalytics (`datalytics-frontend` 2.0.0 in `package.json`).
**Purpose:** a self-hostable analytics / BI platform. You connect or upload data, model it, and build interactive dashboards ("reports") with 74 widget types. It also offers an "Ask AI" natural-language assistant, automated insights, statistical analyses, predictive models, region maps, sharing (share links and embeds) and governance (row security, column security, sensitivity labels). SAS Visual Analytics is the explicit benchmark. `MASTER_PLAN.md` (in the parent folder) is the product plan this session implemented.

**Locations (on the user's Windows PC):**
- Plan and this handover: `D:\Omda 2025\projects\data_analysis_dashboard_ai\` (`MASTER_PLAN.md`, `SESSION_HANDOVER.md`)
- Code (git repo): `D:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics\`

**Technology stack:**
| Layer | Technology (version as pinned when this was written) |
|---|---|
| Frontend | React 18 + TypeScript, Vite 5, **React Router 7.18.4** (upgraded this session from 6.23), Recharts, d3-geo + topojson-client (maps), vitest 2 + Testing Library + jsdom, **axe-core 4.13** (dev dependency, added this session) |
| Backend | Python 3.10 (test venv), FastAPI **0.111.0** / Starlette 0.37.2 (see §10: a security upgrade was tested but **not applied**), Pydantic 2, SQLAlchemy async, Alembic, pandas 2.2.2, DuckDB (+ duckdb-engine 0.13.2), scikit-learn, scipy, statsmodels, pyarrow 16.1.0, python-jose 3.3.0, python-multipart 0.0.9, OpenTelemetry 1.27 |
| Data | PostgreSQL 16 (app metadata), uploaded CSV/Parquet files on disk, DuckDB for pre-aggregation and a metadata cache, Valkey (cache) |
| AI | An LLM at `settings.llm_base_url` (an OpenAI-compatible endpoint on the user's LAN); a separate `embeddings` service |
| Design system | "MCAIT" tokens: `frontend/src/styles/mcait/*.css` plus the product layer `frontend/src/styles/datalytics.css`, scoped by `data-product="datalytics"` on `<html>` and `data-theme="light|dark"` |

**Architecture (short):**
- **docker-compose.yml services:** `postgres` (host port **5433**→5432), `backend` (FastAPI, **8000**, `--reload`), `valkey`, `embeddings`, `frontend` (Vite dev server, host **3001**→3000), and `web` (nginx + built bundle, under a compose *profile*, for production).
- **Frontend container:** its `node_modules` are baked into the image. Only `src/`, `public/`, `package.json` (read-only), `vite.config.ts`, `tsconfig.json` and `index.html` are bind-mounted, so **new npm packages need an image rebuild**.
- **Backend layering** (`backend/tests/test_layer_conformance.py` enforces it): `services/` must not import FastAPI or `core/` capability modules; routers raise HTTP errors; widget errors use `core/widget_errors.widget_error(status, code, detail)` with codes from `services/error_codes.WIDGET_ERROR_CODES`.
- **One choke point for widget data:** `routers/widget_data._resolve_widget_data` is used by the builder, share links (`routers/shared.py`), embeds (`routers/embed.py`) and export. Anything enforced there holds on every surface.
- **Schema:** startup runs `create_all`, so new tables appear without a migration in dev; Alembic revisions exist for real deployments.

**Git state:**
- **Branch `masterplan/complete`** was created from `restyle/step-1-tokens` (the user's in-progress design-system branch). **There is no git remote**; nothing has been pushed.
- Commits on the branch, oldest first:
  1. `b42c3630` MASTER_PLAN complete: all phases and all 11 Part IV acceptance criteria (427 files)
  2. `38cc9ad4` Accessibility: axe WCAG 2.1 AA pass over the main pages
  3. `cd827313` Accessibility in the test suite, and a dark theme that passes AA
  4. `17bb14f5` Tap targets: 24px floor for small buttons and the lineage open link
  5. `077f0341` React Router 7: closes the open-redirect advisory (GHSA-wrjc-x8rr-h8h6)
- `git diff restyle/step-1-tokens masterplan/complete`: 441 files, +44,133 / −8,948 (169 added, 270 modified, 2 deleted).
- **(uncertain)** Commit `b42c3630` staged *all* uncommitted changes under `backend/app`, `backend/tests`, `backend/alembic`, `backend/boundary_packs`, `frontend/src` and `clients/python`. Some of that work predates the part of the session summarised here (for example Alembic 0030–0036, `services/automation_runner.py`, `services/knowledge.py`, `services/agent/*`). It was already in the working tree and was committed as-is.
- About 146 other changed files were **deliberately left uncommitted** because they are not plan work: `.env`, `backend/uploads/`, `frontend/dist/`, the MCAIT Design System folder, `docs/`, `scripts/`, course narration files and others. Do not commit `.env`.

---

## 2. Current objective

**Original requirement (the user's own words, lightly edited):** "start modifying my datalytics app based on this masterplan to make it all done, and when you finish any point or phase add a ✅ sign on it in the plan.md file." Later: "never stop until [you] achieve and succeed [in updating the] code to reach [the] full plan", and then "go with respect that we build an outstanding platform", followed by repeated "go ahead / go on / go on in loop".

**Current expected outcome:**
1. ✅ Every phase item in `MASTER_PLAN.md` implemented and marked ✅.
2. ✅ Every Part IV acceptance criterion (1–11) proven and marked ✅. The notes beside each one in the plan say how it was proven.
3. 🔄 **Ongoing quality loop:** audit → fix → test → commit, one area at a time (accessibility, phone width, dependency security, performance…). This loop was in progress when the session ended (§4 and §13).

**Acceptance criteria** (MASTER_PLAN Part IV, abridged; all marked ✅):
1. Home → rendered, filtered chart in ≤ 6 clicks, no dead ends.
2. Every edit, human or AI, is one named, reversible step; Ctrl+Z always answers.
3. Every result states its population (`rows_scanned` / `truncation`).
4. Summing a latitude, a year or an ID is impossible, and the refusal says why.
5. No disabled or empty control appears without its reason and its fix.
6. Models can be built, diagnosed, compared, saved and used to score on the canvas.
7. A dataset keyed by Egyptian governorates maps correctly first try.
8. A reader can answer "why am I seeing this?" from one pane, on a phone, offline.
9. "Last 30 days" is one click; a partial month never masquerades as a full one.
10. Every recommendation, insight and AI answer shows its evidence and its engine.
11. All of the above hold on the shared link and the embed.

**Constitution rules** (MASTER_PLAN Part I) that later work must keep: no silent refusal, no silent substitution, no aggregation without semantics, truncation as a first-class state, one disclosure vocabulary, accessible by construction, reproducible and explainable assistive output, every mutation one undo command, never destroy configuration to change a mode, and one naming function.

---

## 3. Work completed in this session

Unless noted, each item has unit or integration tests, and most were also exercised live against the running app through the browser.

### 3.1 Plan phases implemented (MASTER_PLAN Phases 6–7, follow-ups, Phase 4 EU pack)
| # | Change | Why | Main files | Tested |
|---|---|---|---|---|
| 6.4 | **Relative dates**: filter op `relative` (last N / this / previous / to-date / rolling, anchored on today or the latest date in the data), converted to `date_range`; a **partial last bucket** is flagged; the cache key carries `__today__` | "Last 30 days" plus honest partial periods | `backend/app/services/relative_dates.py`, `services/widget_data.py` (`_apply_filters`, `get_widget_data_from_df(flag_partial=…)`, `_today_for`), `routers/widget_data.py` (`_direct_query_relative_dates`), `routers/reports.py` (`_FILTER_OPS`), `frontend/src/lib/relativeDates.ts`, `components/report/RelativeDateEditor.tsx`, WidgetRenderer (chip, partial note, Why "Date windows"), bar/line renderers | yes, live |
| 6.6 | **Text analytics**: Arabic/English normalisation, light stemming, stop words, lexicon sentiment with negation, intensifiers and "but" shift; `text_sentiment` analysis; `text_topics` language, analyzer and per-topic tone; calc functions `SENTIMENT()` and `SENTIMENT_LABEL()` | Text columns were opaque | `services/text_lang.py`, `services/analysis/text_sentiment.py`, frontend `analysisResults`, calc catalogs | yes; demo feedback gave 55% coverage and 96% polar agreement |
| 6.5 | **Scoped measures**: `SCOPE()` / `ISINSCOPE()` resolved in the AST before evaluation | Level-aware measures | `services/measure_eval.py` (`_ScopeResolver`, `resolve_scope`), MeasuresPanel palette | yes |
| 6.2 | **Lattice (small multiples)** for bar, line, area, scatter, step and dot plot (max 8×8, 60 cells, shared domain); skipped on DuckDB, refused on DirectQuery | Trellis views | `services/widget_data.py` (`LATTICE_TYPES`, `shape_lattice`, `_lattice_domain`), `chartRenderers/LatticeRenderer.tsx`, config group "Lattice (small multiples)" | yes, live |
| 6.3 | **Animation** over a field (60 frames, chronological, shared domain) and a **brush** range selector | Play-through and range selection | `shape_animation`, `chartRenderers/AnimatedRenderer.tsx`, `axisOptions.brushProps`, WidgetRenderer brush chip | yes |
| 6.1 | **Cross-source mapping check**: `POST /relationships/check`; share links and embeds publish relationships | Cross-dataset filtering | `services/prep.py` (`mapping_match_report`), `routers/shared.py` (`published_relationships`), `embed.py`, ModelView, ReviewPane | yes |
| 7.1 | **Copilot edits are versioned and undoable** (`_bump_revision(..., via, note)`, version `meta`, "🤖" in history) | "Every edit, human or AI, undoable" | `routers/reports.py`, `report_copilot`, CopilotChat, ReportBuilder, VersionHistoryPane | yes |
| 7.2 | **Difference check** (count → binomial, avg → Welch, median → Mann-Whitney, sum → both; says when an effect is negligible yet significant) and an **Evidence chip** | Evidence behind "is this different?" | `analysis/inferential.difference_check`, `POST /api/v1/datasets/{id}/difference-check`, ViewerKit DifferenceDialog / EvidenceChip | yes |
| 7.3 | **Sensitivity labels and governance**: Public/Internal/Confidential/Restricted, derived through lineage and joins; classification floor; redaction on share links, embeds, CSV, PDF, packages and delivery; `POST /authz/decisions` (max 50) and an "access and why" explainer | Governed sharing | `services/sensitivity.py`, `routers/shared.py` (`sensitivity_gate`, `download_gate`), `core/capability.explain_capability`, `routers/authz.py`, datasets `/sensitivity`, AccessExplainer.tsx, DatasetSensitivity.tsx | yes |
| 7.4 | **Report review and publish gate**: high findings block publishing (409 `{message, findings}`), performance evaluation, org review settings | Quality before publishing | `services/report_review.py`, `routers/review.py`, model `OrgReviewSettings` + Alembic `0037_org_review_settings`, ReviewPane | yes |
| 7.5 | **Arabic/MENA formats**: tabular Hijri calendar (`hijri_month`, `hijri_year`), Arabic digits, MENA currencies with symbol position | Regional audience | `services/hijri.py`, `lib/arabicFormats.ts`, chartUtils, LanguageSwitcher | yes |
| 7.6 | **Semantic layer API** plus a Python client and notebook snippet | Governed programmatic access | `routers/semantic.py`, `clients/python/datalytics_client.py`, `NotebookSnippet.tsx` | yes |
| P1.4 | Cross-filter **selection history** (undo/redo of selections, 50 deep) | Reader undo | `CrossFilterContext.tsx`, FilterBar | yes |
| F-ups | Model **partitions**; per-model **ROC** in comparison; **carry filters** on a button action; **pop-up page** size picker and PDF export | Plan follow-ups | automated_prediction, `model_widgets.py`, ModelRenderer, CrossFilterContext.carryFiltersTo, PopupOverlay | yes |
| P4.2 | **EU NUTS-1 boundary pack** (123 regions, from Eurostat's Nuts2json on GitHub, because GISCO was blocked). It installs only with `{"accept_terms": true}`; the terms and required credit are shown first, and the credit "© EuroGeographics for the administrative boundaries" is drawn on every map (`geometry.x_attribution`) | Decided by the user: "add it with its terms shown" | `backend/boundary_packs/eu-nuts1.geojson` and `manifest.json` (attribution, terms, requires_acceptance), `services/boundary_sets.list_packs`, `routers/boundary_sets.install_boundary_pack`, `PackTermsConfirm.tsx` (used by BoundarySetPicker, AdminMaps and ReportBuilder), `worldGeometry.buildRegionSet` (`attribution`), `MapFrame.MapSvg` (`credit`), GeoChoropleth and GeoLayerStack | yes (8 backend pack tests, frontend tests) |

### 3.2 Acceptance-criteria proof pass (the "outstanding platform" work)
| Criterion | Problem found | Fix | Files |
|---|---|---|---|
| 1 | The empty page's "Add data" did nothing visible when the left panel was on Charts or More; a bar split by a second field could not filter the page and its tooltip lost series names; dual-axis charts could not filter; the dataset page was a dead end | `openDatasetPicker()` also switches to the Fields tab; split-bar `onClick`, tooltip names and selection dimming; `onClick` on the five dual-axis/comparative renderers; `handleClick` falls back to `cfg.roles.category` / `cfg.start`; **"+ Build a dashboard"** on the dataset page | `pages/ReportBuilder.tsx`, `chartRenderers/BarChartRenderer.tsx`, `DualAxis*Renderer.tsx`, `ComparativeTimeSeriesRenderer.tsx`, `SankeyChartRenderer.tsx`, `WidgetRenderer.tsx`, `pages/DatasetDetail.tsx`; test `chartRenderers/barSplitInteraction.test.tsx` |
| 2 | About 15 builder writes had no undo entry | Undo for charts made from a field, hierarchy or Suggest pane; add, delete (restores its widgets) and rename page; page properties; report filters; theme; classification; attach/detach data; hierarchy assignment; report display rules (coalesced); column-meta geography and measure/category (`setColumnMetaUndoable`); quick-calc measures; parameters. **Page ids alias** like widget ids (`pageIds = useRef(new IdAliases())`, `pid()`). `PATCH /reports/{id}` now accepts an explicit `dataset_id: null` | `pages/ReportBuilder.tsx`, `backend/app/routers/reports.py` (`update_report` uses `exclude_unset`; null is honoured only for `dataset_id`); tests in ReportBuilder.test and `tests/test_report_update_nulls.py` |
| 3 | No `rows_scanned`; the crosstab's `total` was its grid size; six shapers capped rows silently | `rows_scanned` stamped in `get_widget_data_from_df`, the DuckDB path and the `run_direct_query` wrapper; `_cut(frame, limit, unit)` adds truncation to dual-series, bubble, animated bubble, waterfall, box plot and xy-numeric; `_KEEPS_EVERY_GROUP` shapers state "nothing dropped"; TruncationNote gains units `categories` and `points` | `services/widget_data.py`, `services/direct_query.py`, `TruncationNote.tsx`; tests in `tests/test_widget_shapers.py` |
| 4 | The API happily summed `year` | **Server-side semantic veto** (422, code `semantic_veto`) in `_resolve_widget_data`; a one-click fix on the widget ("Use Maximum of year"); marking the column a measure overrides it | `services/semantic_guard.py` (`ARITHMETIC`, `SAFE_AGGREGATION`, `aggregation_refusal`, `config_refusal`), `services/error_codes.py`, `services/widget_data.sums_measure_by_default`, `WidgetBody.tsx` (`semanticFix`, `onApplyFix`); tests `tests/test_semantic_guard.py`, `components/report/semanticVeto.test.tsx`, and a share-link test in `tests/test_share_links.py` |
| 5 | 101 disabled controls gave no reason | 57 non-obvious ones gained a reason `title`; `ActionMenuItem.disabledReason`; the page-delete × is labelled | ~25 files (see §5) |
| 7 | Of 63 real governorate spellings, 57 matched | An exact **compact form** in the matcher (`compactRegionKey`, index key prefixed `~`; still never fuzzy) plus new pack aliases; the three spellings still missing from the installed Egypt set were **pinned** through the API | `components/report/geo/worldGeometry.ts`, `boundary_packs/egypt-governorates.geojson` |
| 9 | "Last 30 days" was several clicks deep | One-click presets on the dataset's date column (Last 7 / Last 30 days, Month / Year to date, Previous month); a second preset replaces the first, as one undo step | `pages/ReportBuilder.tsx` (`applyDatePreset`, `dateColumnOf`) |
| 10 | Ask AI answers never named their engine | An `answerSource()` line under every assistant answer; the source-design dialog names the AI model | `components/chat/ChatPane.tsx`, `components/review/SuggestFromSourceDialog.tsx`; test `components/chat/answerSource.test.ts` |
| 11 | — | Shown to hold by construction, plus a share-link test | `tests/test_share_links.py` |

### 3.3 Other fixes found during the full test sweeps
- `services/suggest_dataset_dashboard._probe` counted metadata keys as rows (a 3-bar chart reported "5 rows"). It now uses `rows`, excluding `_RESULT_METADATA`.
- Security: **model scoring now drops the caller's denied columns** (`routers/prediction_models.py` `score_model`). `routers/semantic.py` was reviewed and registered in `tests/test_rls_base_frame_choke_point.py`.
- Four guard tests were reading files that had moved: the renderer dispatch (now `WidgetBody.tsx`), the calc palette (`calcColumns/catalog.ts`), grid `COLS` (`pages/reportBuilder/grid.ts`), and the frontend test count.
- The 10 long-failing frontend map-click tests: the maps were never drawn because jsdom gives tiles no size. Fixed with the test helper `src/test/measuredTiles.ts` (`withMeasuredTiles()`).
- TypeScript is now at **0 errors** (it was 4): `CopilotChat.test`, `MapFrame` `dir` typing, and the `worldGeometry` `GeoFittable` type.
- The demo now covers **all 74 widget types**: a new "Demo — Models" report and a contour map. The seed fits and saves a real `PredictionModel` ("Demo — Revenue model") for the scoring widget.
- ARCHITECTURE.md and ARCHITECTURE.html counts and tables were updated (81 tables, 29 routers, 74 widget types, 25 aggregations, 37 revisions, the semantic veto).

### 3.4 Accessibility, phone and security (after the plan)
- **axe WCAG 2.1 AA browser audit** on 14 pages. Fixed contrast on the rail section labels, dataset badges and the active builder tab. The opened-reports strip became real navigation (it was a tablist holding close buttons). The lineage graph's 74 nested links moved out of the node buttons. Admin → Users now shows "Loading roles…" instead of a false "Create a role first" while roles load.
- **axe in the test suite:** `frontend/src/test/axe.ts` (`axeViolations(node, alsoDisable?)`, contrast and region rules off under jsdom), a self-test in `src/test/axe.test.tsx`, and checks on 11 surfaces.
- **Dark theme:** status colours (success, warning, danger, info) now have dark values; new `--mc-danger-fg`; 29 hard-coded white-on-accent texts use `--mc-accent-fg`; `:where(a){color:var(--accent)}`.
- **Phone width (390px):** no page scrolls sideways; `.btn-sm` has a 24px minimum (WCAG 2.5.8); the lineage open link is 24px.
- **Dependency security:** React Router upgraded to 7.18.4, which closes GHSA-wrjc-x8rr-h8h6 (open redirect). The Python upgrade was **tested, not applied** (see §10).

---

## 4. Current project state

### ✅ Completed
- Every MASTER_PLAN phase item and all 11 Part IV acceptance criteria are marked ✅. The notes under Part IV and the "Quality pass (24 Sep)" block record how each was proven.
- Frontend: the full vitest suite passes (about 2,670 tests; the last full run was after the React Router 7 upgrade), `tsc --noEmit` shows 0 errors, and `vite build` succeeds.
- Backend: a full sweep of about 5,300 tests (382 modules) passed except for environment-only cases (§10), on the current pins (FastAPI 0.111).
- The accessibility, dark-theme, phone and React Router work described in §3.4 is committed.

### 🟡 Partially completed
- **Python dependency security upgrade.** It was tested in a *copy* of the test environment (`$HOME/venv2` in the Cowork VM, which is not part of the project) and **not written to `backend/requirements.txt`**. Candidate set: `fastapi==0.136.3`, `starlette==1.7.0`, `python-multipart==0.0.31`, `python-jose[cryptography]==3.5.0`. The backend sweep with exactly this set had reached **batch 00 of 32 (194/194 passed)** when the session ended. An earlier sweep with FastAPI 0.141.1 got through batch 14 cleanly except route introspection (below).
- **Quality loop:** accessibility, phone width and npm security are done. Performance (bundle size) is the next planned area; `vite build` warns that some chunks exceed 500 KB. Not started.

### ❌ Not completed
- The dev-only npm advisories (vite 5 → 8, vitest 2 → 5, esbuild) need major upgrades; not attempted.
- `pptxgenjs` → `image-size` (high; denial of service in the browser's own PPTX export only): npm's "fix" is a downgrade, so not applied.
- Python pyarrow 16 → 23, protobuf 4 → 5/6, pytest 8 → 9 and setuptools advisories: not attempted.
- The report builder's dense toolbar (theme swatches, open-report tabs and their ×) is still under the 24px tap-target size. It is desktop authoring UI; left for the user to decide.
- Nothing is pushed (no remote configured).

### ⚠️ Known problems
- **FastAPI ≥ 0.137 changes routing internals:** `app.routes` holds `_IncludedRouter` wrappers, not flattened `APIRoute`s. Three test files (`test_admin_endpoints_require_admin.py`, `test_router_reachability.py`, `test_frontend_constant_mirrors.py`) iterate `app.routes` and fail or check nothing. **0.136.3 is the newest version that still flattens.** No production code iterates `app.routes`.
- `tests/test_architecture_doc.py` expects "**211** files" (frontend test files) but ARCHITECTURE.md/.html still say **210**, because `src/test/axe.test.tsx` was added after the docs were updated. Fix both documents: `~2,800 tests across 211 files` and `~2,800 tests · 211 files`.
- The user's running containers are **not rebuilt**. The frontend container still has React Router 6 and no axe-core. Both work (App.tsx has no future flags now; v6 only prints warnings), but container tests need a rebuild.
- `passlib` prints `AttributeError: module 'bcrypt' has no attribute '__about__'` at import. This is a known passlib/bcrypt version warning, pre-existing and harmless.

### 🔧 Temporary workarounds
- **Backend tests in the Cowork VM** need `UPLOAD_DIR` and `DUCKDB_CACHE_PATH` pointed at a writable folder, because the defaults are under `/app` (§11).
- **Cowork-VM deletes:** the connected folder forbids `rm` unless the user approves delete access for the session. Files were *moved* into `data_analytics/_to_delete/` instead of being deleted (stale git index locks, commit helper scripts, vitest timestamp files, `ModelView.test.tsx.tmp`).
- **git from the Cowork VM:** git leaves `.git/index.lock` behind when it cannot unlink files. Use `GIT_OPTIONAL_LOCKS=0` for read-only commands; commits worked after the user granted delete access for the session.
- **Demo test artifacts** are gathered in the workspace folder "Test leftovers (safe to delete)" instead of being deleted (§7).

---

## 5. Files changed

The full list: `git diff --name-status restyle/step-1-tokens masterplan/complete` (441 files). The table covers the files that matter for continuing the work. Paths are relative to `data_analytics/`. Status: **A** added, **M** modified, **D** deleted.

| File | Change | Status | Important notes |
|---|---|---|---|
| `../MASTER_PLAN.md` (parent folder, not in git) | ✅ marks and proof notes on every item; "Quality pass (24 Sep)" block | M | The source of truth for scope |
| `../SESSION_HANDOVER.md` (not in git) | This document | A | |
| `backend/app/services/semantic_guard.py` | Veto rules: `ARITHMETIC`, `SAFE_AGGREGATION`, `aggregation_refusal`, `config_refusal` | A (mirrors `frontend/src/lib/semanticGuard.ts`) | Keep both halves' rules identical |
| `backend/app/routers/widget_data.py` | Veto in `_resolve_widget_data`; relative dates for DirectQuery | M | The one path every surface uses |
| `backend/app/services/widget_data.py` | `rows_scanned`, `_cut`, `_KEEPS_EVERY_GROUP`, `sums_measure_by_default`, lattice/animation shapers, relative-date filters, partial-period flag, crosstab population | M | Very large module; read around the function you change |
| `backend/app/services/direct_query.py` | `rows_scanned` in the `run_direct_query` wrapper and paths | M | |
| `backend/app/services/error_codes.py` | `semantic_veto` code | M | |
| `backend/app/routers/reports.py` | `update_report` null-`dataset_id` semantics; revision `via`/`note`; version meta; `relative` filter op | M | |
| `backend/app/routers/review.py`, `services/report_review.py` | Review, publish gate, performance evaluation, org settings | A | |
| `backend/app/routers/authz.py` | `POST /authz/decisions` | A | |
| `backend/app/routers/semantic.py` | Semantic API | A | Registered in the RLS choke-point test |
| `backend/app/services/sensitivity.py` | Labels, lineage, redaction | A | Services must not import FastAPI; `download_gate` lives in `routers/shared.py` |
| `backend/app/routers/prediction_models.py` | Scoring drops denied columns | M | |
| `backend/app/routers/boundary_sets.py`, `services/boundary_sets.py` | Pack terms and acceptance; attribution | M | |
| `backend/boundary_packs/*` | Egypt, US, Saudi, UAE, EU NUTS-1 packs plus `manifest.json` | A | EU pack: `requires_acceptance: true` |
| `backend/app/services/suggest_dataset_dashboard.py` | `_probe` row count fix | M | |
| `backend/app/services/demo_content.py` | "Demo — Models" report, contour map, `_seed_demo_model` | M | Seeding writes a `PredictionModel` |
| `backend/app/services/relative_dates.py`, `text_lang.py`, `hijri.py`, `analysis/text_sentiment.py`, `model_widgets.py` | Phase 6/7 features | A | |
| `backend/alembic/versions/0037_org_review_settings.py` | `OrgReviewSettings` table | A | 0030–0036 are also new on this branch (origin uncertain, §1) |
| `backend/tests/test_semantic_guard.py`, `test_report_update_nulls.py`, `test_widget_shapers.py`, `test_share_links.py`, `test_demo_reports.py`, `test_rls_base_frame_choke_point.py`, `test_calc_date_stats_functions.py`, `test_report_composer.py`, `test_demo_directquery.py` | New or updated tests | A/M | |
| `ARCHITECTURE.md`, `ARCHITECTURE.html` | Counts and tables updated | M | Frontend test-file count must become 211 (§4) |
| `frontend/package.json`, `package-lock.json` | `axe-core ^4.13.0` (dev); `react-router-dom ^7.18.4` | M | Lockfile committed with LF line endings |
| `frontend/src/App.tsx` | Removed `BrowserRouter` future flags (RR7) | M | |
| `frontend/src/pages/ReportBuilder.tsx` | Undo everywhere, `pageIds`/`pid`, `openDatasetPicker`, date presets, pack terms, a11y fixes, opened-reports nav | M | ~3,500 lines; read before editing |
| `frontend/src/pages/reportBuilder/undo.ts` | `UndoStack`, `IdAliases`, `useUndoStack` | A | Command log, not snapshots |
| `frontend/src/components/report/WidgetBody.tsx` | Widget-type dispatch (moved here from WidgetRenderer); `semanticFix`, `onApplyFix` | A | Backend tests parse this file |
| `frontend/src/components/report/WidgetRenderer.tsx` | Click-column fallback, truncation note, fix dispatch | M | |
| `frontend/src/components/report/chartRenderers/*` | Split-bar and dual-axis filtering, Lattice, Animated, Model, Contour, LayerStack renderers | A/M | |
| `frontend/src/components/report/geo/worldGeometry.ts`, `MapFrame.tsx` | `compactRegionKey`, `attribution`/`credit`, `GeoFittable` | M/A | Matching must stay exact, never fuzzy |
| `frontend/src/components/report/PackTermsConfirm.tsx` | Terms panel | A | |
| `frontend/src/components/report/TruncationNote.tsx` | Units `categories`/`points` | A | |
| `frontend/src/components/chat/ChatPane.tsx` | `answerSource()` provenance line | M | |
| `frontend/src/components/ActionMenu.tsx` | `disabledReason` | M | |
| `frontend/src/pages/Lineage.tsx` | Link moved out of the node button; 24px target | M | |
| `frontend/src/pages/DatasetDetail.tsx` | "+ Build a dashboard" | M | |
| `frontend/src/pages/admin/AdminUsers.tsx` | Loading-aware disabled reason | M | |
| `frontend/src/index.css` | Rail label contrast, badge mix, `:where(a)`, `.btn-sm` 24px, `.btn-danger` fg | M | |
| `frontend/src/styles/datalytics.css`, `styles/mcait/colors.css` | Dark status colours, `--mc-danger-fg` | M | The user's design-system files: change them sparingly |
| `frontend/src/test/axe.ts`, `axe.test.tsx`, `measuredTiles.ts` | Test helpers | A | |
| `frontend/src/pages/Dataflows.tsx`, `Dataflows.test.tsx` | Deleted | D | **(uncertain)** Already missing from the working tree before the session's commit; nothing imports it. Recover with `git show restyle/step-1-tokens:frontend/src/pages/Dataflows.tsx` if needed |
| `clients/python/datalytics_client.py`, `README.md` | Python client for the semantic API | A | |

---

## 6. Important code and implementation details

**Semantic veto (criterion 4).** In `backend/app/services/semantic_guard.py`:
```python
non_additive_kind(column) -> 'coordinate' | 'identifier' | 'year' | None   # classified by NAME
ARITHMETIC = {"coordinate": {"sum"}, "identifier": {"sum","avg","mean","average","median","stddev","variance"},
              "year": {"sum","avg","mean","average"}}
SAFE_AGGREGATION = {"coordinate": "avg", "identifier": "countd", "year": "max"}
config_refusal(config, column_meta, *, sums_by_default: bool) -> {"column","aggregation","safe","message"} | None
```
- `routers/widget_data._resolve_widget_data` raises `widget_error(422, "semantic_veto", message)`.
- A missing aggregation counts as `sum` only when `services/widget_data.sums_measure_by_default(widget_type)` is true, meaning the shaper is in `_SUMS_BY_DEFAULT`. In this app, `scatter` *does* aggregate (it uses `shape_series`).
- `column_meta[col].role == "measure"` overrides the veto.
- On the frontend, `WidgetBody.semanticFix(cfg)` builds `{patch: {aggregation|aggregation2: safe}, label}`, and the author gets a button that dispatches `PATCH_WIDGET_EVENT`, which is undoable.

**Population and truncation (criterion 3).**
- Every result dict carries `rows_scanned`. `get_widget_data_from_df` defaults it to `total`. The crosstab sets it explicitly, because its `total` is its grid size, which the renderer relies on. The DuckDB path and `run_direct_query` overwrite it with the real source row count.
- `_cut(frame, limit, unit) -> (frame.head(limit), {"applied","shown","of","limit","reason":"limit","unit"})`.

**Undo (criterion 2).**
- `pages/reportBuilder/undo.ts` is a command log. `UndoCommand = {label, undo, redo, coalesceKey?}`; entries sharing a `coalesceKey` within 1.5 s merge; the limit is 100.
- `IdAliases` maps old → new ids when undo recreates something. ReportBuilder keeps `widgetIds` **and** `pageIds`. **Always resolve ids when a command runs** (`widgetIds.current.resolve(id)`, `pid(pageId)`), never when it is recorded.
- Undoing a page delete recreates the page, then its widgets, and registers both aliases.

**Region matching (criterion 7).**
- `worldGeometry.buildRegionSet` indexes each key property under three keys: lowercase, `normalise()`d, and `'~' + compactRegionKey(value)`. `matchRegion` tries them in that order.
- `compactRegionKey` strips one administrative word (governorate/province/prefecture/emirate/region, and Arabic محافظة/إمارة/منطقة) and removes spaces, hyphens, apostrophes, dots and tatweel. Still exact matching; never fuzzy.

**Boundary pack terms.**
- Manifest entries may carry `attribution`, `terms` and `requires_acceptance`.
- `POST /boundary-sets/packs/{id}/install` refuses (400) without the body `{"accept_terms": true}` when acceptance is required. It audits `boundary_pack.accept_terms` and stores `geometry["x_attribution"]`, which the frontend draws through `MapSvg credit`.

**Date presets.** `ReportBuilder.applyDatePreset(id)` adds a report common filter `{column: <first datetime column>, op: "relative", value: {..preset.spec, anchor: "data_max"}}` and replaces an existing relative filter on that column. The whole swap is one undo entry.

**Ask AI provenance.** `ChatPane.answerSource(msg)` returns one of: proposals → "Proposed by the AI model…"; analysis → "The AI chose the test; the result was computed…"; no query → "AI reply: no data was queried"; catalog-only → "…from the data catalog"; otherwise → "AI answer from N queries on your data (R rows)…".

**Accessibility test helper.** `src/test/axe.ts` exports `axeViolations(node, alsoDisable = [])`, which returns readable violation lines with `color-contrast` and `region` disabled. **axe uses timers:** a file that calls `vi.useFakeTimers()` must call `vi.useRealTimers()` before using it.

**Theming tokens.** Text on an accent fill uses `var(--mc-accent-fg)`; text on a danger fill uses `var(--mc-danger-fg, #fff)`. Never hard-code `#fff` on `var(--accent)`, because the dark theme's accent is light.

**`PATCH /reports/{id}` semantics.** Only fields that are set are applied. An explicit `null` clears `dataset_id`; `null` on any other field is ignored.

---

## 7. Database changes

**Schema:**
- **New table `org_review_settings`** (Alembic `0037_org_review_settings`, `down_revision = "0036_org_map_settings"`). Columns: `id` PK; `org_id` FK → organizations (CASCADE, unique, indexed); `publish_gate` bool (default false); `updated_by` FK → users (SET NULL); `updated_at`. It controls whether high review findings block publishing.
- Revisions `0030`–`0036` (automation runs, report origin, automation run record, dataset column provenance, source column target, page layout mode, org map settings) are also new on this branch. **(uncertain)** They may predate the summarised part of the session.
- No stored procedures or views. Dev startup runs `create_all`; deployments run `alembic upgrade head`.

**JSON conventions (no schema change):**
- `datasets.column_meta["__sensitivity__"]` holds a dataset's own label; `column_meta[col].role` holds `"measure"` / `"geography"` and `boundary_set_id`.
- `boundary_sets.geometry` carries the foreign members `x_pins` (value → feature index) and `x_attribution` (required credit).
- `report_versions` snapshots carry `meta: {via, note}` (`via` = `"copilot"` for AI edits).

**Seed data:** the demo seed (`POST /api/v1/demo/seed`, or `scripts/demo_up.ps1`) now also fits and inserts a `prediction_models` row "Demo — Revenue model" and creates the report "Demo — Models". Reseeding **replaces** the demo datasets and reports.

**Live database state the user should know about.** These are test artifacts created while verifying the work; none has been deleted:
- The workspace folder **"Test leftovers (safe to delete)"** (workspace node id 160) holds reports 198–201 (UI Test 1–4), 203 ("Untitled dashboard", made while testing the first-chart path) and the old "What stands out…" reports 164, 165, 173, 174, 175 and 183. Some of those summed latitudes or years and now show the semantic-veto refusal.
- Saved model **"Category model (test)"** (id 5) on the Demo — Sales dataset (id 120).
- Report 202 "Sales overview" contains test widgets (for example widget 2182, a linear regression); its `partition` reference was removed.
- The `_Partition_` prep step was **removed** from dataset 120 (reverting a test change). Its other prep steps (`drop_duplicates`, `fill_nulls` on country) were left alone; their origin is uncertain.
- The installed "Egypt governorates" boundary set got three pins: Qaliubiya → Qalyubia, Gharbiya → Gharbia, Marsa Matruh → Matrouh.
- Report 199's lattice test setting was reverted.
- QA reports 191–194 were left untouched; it's unclear whether they are test material.

**Pending database work:** none required. The user will delete the test artifacts above.

---

## 8. APIs and integrations

All routes are under `/api/v1` unless noted. Authentication is a Bearer JWT; the SPA keeps it in `localStorage["datalytics_token"]`. Share links are anonymous (`/api/v1/shared/{token}/…`); embeds use a host-signed JWT.

**Endpoints added or changed in this session:**

| Method | Path | Purpose / contract |
|---|---|---|
| POST | `/datasets/{id}/widget-data` | Now **422 `{detail, code:"semantic_veto"}`** for arithmetic on a year, coordinate or id. Every result carries `rows_scanned` and (for capping shapers) `truncation{applied,shown,of,limit,reason,unit}` |
| POST | `/shared/{token}/widget-data/{widget_id}` | Same contract as above, through the same code path |
| PATCH | `/reports/{id}` | Explicit `"dataset_id": null` clears the primary dataset; other nulls are ignored |
| POST | `/relationships/check` | Cross-source mapping match report |
| POST | `/datasets/{id}/difference-check` | Statistical difference check (test, p, effect size and label) |
| GET/PUT | `/datasets/{id}/sensitivity` | Sensitivity label (own and effective, with reasons) |
| POST | `/authz/decisions` | Batched capability decisions with reasons (max 50) |
| GET | `/reports/{id}/review` | Review findings |
| POST | `/reports/{id}/evaluate-performance` | Per-widget timing |
| GET/PUT | `/review-settings` | Org publish gate |
| GET | `/semantic/datasets` | Semantic-layer catalogue |
| POST | `/semantic/query` | Governed query (RLS, column security, export policy "api") |
| GET | `/semantic/datasets/{id}/rows` | Governed rows (json or csv) |
| GET | `/boundary-sets/packs` | Now includes `attribution`, `terms`, `requires_acceptance` |
| POST | `/boundary-sets/packs/{id}/install` | Body `{"accept_terms": true}` is required for packs with `requires_acceptance` (400 otherwise) |
| PUT | `/boundary-sets/{id}/pins` | Replaces all pins `{pins:{value: featureIndex}}` (read and merge first) |
| GET/PUT | `/map-settings` | Org basemap tiles |
| POST/DELETE | `/demo/seed` | Seed or unseed the demo (no UI button; `scripts/demo_up.ps1` calls it) |

- **Publishing** now returns **409 `{message, findings}`** when the org publish gate is on and high findings exist.
- **External services:**
  - The LLM is at `llm_base_url`; `backend/app/core/config.py` defaults it to a private LAN address. Ask AI, the copilot and the automation chain's narration depend on it.
  - The embeddings service (a compose service).
  - Eurostat's Nuts2json data on GitHub was the one-time source for the EU pack. GISCO itself was blocked by proxy policy.
  - The accessibility audits loaded axe from cdnjs in the browser; the test suite uses the npm package.
- **Frontend API client:** `frontend/src/services/api.ts` (`reportsApi`, `boundarySetsApi.installPack(packId, acceptTerms=false)`, `widgetDataApi.query`, etc.). Tests that mock `services/api` with a factory must include every export the component uses.

---

## 9. Configuration and environment

- **Root `.env`** variable *names*: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `SECRET_KEY`, `ALLOWED_ORIGINS`, `ENV`, `MAX_UPLOAD_MB`, `VITE_API_URL`. Values: `<SECRET>` placeholders; never commit `.env`.
- **Backend settings** (`backend/app/core/config.py`): `upload_dir` (default `/app/uploads`), `duckdb_cache_path` (default `/app/uploads/metadata_cache.duckdb`), `llm_base_url`. Environment variables override them (`UPLOAD_DIR`, `DUCKDB_CACHE_PATH`, …).
- **Ports and URLs:** frontend dev `http://localhost:3001`, API `http://localhost:8000` (`/api/v1`, health at `/health`), Postgres on host port `5433`.
- **Browser storage keys:** `datalytics_token`, `theme` (`light|dark`), `rail-expanded`, `datalytics:builder-left-tab`, `datalytics:open-reports` (sessionStorage), `datalytics:popup-size`.
- **Credentials:** a normal admin login is needed to use the app. `scripts/demo_up.ps1` has an `-AdminPassword` parameter (use `<ADMIN_PASSWORD>`). The AI assistant never typed passwords.

---

## 10. Errors and problems (unresolved)

1. **Python security upgrade not applied yet**
   - **Problem:** `pip-audit -r backend/requirements.txt` reports 46 advisories in 8 packages. The ones that matter for production: python-multipart 0.0.9 (DoS and path traversal), starlette 0.37.2 (multipart, Host header, path validation and more), and python-jose 3.3.0 (algorithm confusion, DoS). Others: pyarrow 16.1.0, protobuf 4.25.9, ecdsa 0.19.2 (no fix), setuptools 75.6.0, pytest 8.2.2.
   - **Tried:** FastAPI **0.141.1** (+ Starlette 1.7.0, Pydantic 2.13.5). Batches 00–14 passed except `test_frontend_constant_mirrors` (2 failures), because in FastAPI ≥ 0.137 `app.routes` contains `_IncludedRouter` wrappers. **Do not use ≥ 0.137 without first rewriting the three route-walking tests.**
   - **Current candidate:** `fastapi==0.136.3`, `starlette==1.7.0`, `python-multipart==0.0.31`, `python-jose[cryptography]==3.5.0`. The three route-walking test files pass (57 tests), and full-sweep batch 00 passed 194/194. **The remaining 31 batches have not been run.**
   - **Next:** run the full backend sweep on this set (§11). If green, update `backend/requirements.txt`, rebuild the backend image, re-run `pip-audit`, and commit.
2. **ARCHITECTURE docs frontend-test-file count:** the docs say 210; the code has 211. Update both documents (§4).
3. **Automation-runner tests (3) and the LLM**
   - **Problem:** in the Cowork VM, `test_automation_runner.py` tests `test_the_rest_of_the_chain_still_walks_to_done`, `test_the_shipped_chain_runs_end_to_end_unmonkeypatched` and `test_a_completed_run_leaves_nothing_on_disk` fail with `LLM endpoint error: HTTP 403: Connection blocked by network allowlist` (the run ends `needs_review`).
   - **Cause:** these tests call the live LLM. Environment-only; they should pass on the user's machine with the LLM reachable **(unverified there)**.
4. **Dev-only npm advisories:** vite 5 → 8 and vitest 2 → 5 (critical/high dev-server and test-UI advisories), and esbuild. These need major upgrades; not attempted. Risk: config changes.
5. **Report builder tap targets under 24px** (theme swatches 18px, open-report tab ×): a design decision for the user.
6. **Edit-mode dimming** (0.5 opacity) of widgets hidden from readers or inside tab containers fails contrast checks. This is intentional author-only UI, and a test pins it. Not a bug unless the user decides otherwise.

---

## 11. Testing

**Commands (from the repo root):**
```bash
# Frontend (on the host, or in the container after `docker compose build frontend`)
cd frontend
npx vitest run                               # whole suite (~2,670 tests)
npx vitest run src/pages/ReportBuilder.test.tsx -t "undo step"   # a focused run
npx tsc --noEmit -p tsconfig.json            # must stay at 0 errors
npx vite build                               # production build (warns: chunks > 500 KB)

# Backend
cd backend
UPLOAD_DIR=<writable dir> DUCKDB_CACHE_PATH=<writable dir>/metadata_cache.duckdb \
  PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q            # ~5,300 tests
python -m pytest -q tests/test_semantic_guard.py tests/test_widget_shapers.py  # focused
python -m pip_audit -r requirements.txt                                        # dependency advisories
```
- **How this session ran them (Cowork VM specifics).** Frontend: `rsync` `frontend/src` into a scratch copy (`$HOME/fe`) with Linux `node_modules`, then `node node_modules/vitest/vitest.mjs run …` with `ESBUILD_BINARY_PATH` set. Backend: a Linux venv (`$HOME/venv`), 12 test files per batch to fit a 3-minute limit, with the two environment variables above.
- **Results at the end of the session:**
  - Frontend: all pass; tsc 0 errors; build OK.
  - Backend (current pins): all pass except the environment-only failures in §10.3.
  - axe: 11 surfaces clean in tests. Browser audit: 14 pages clean in light and dark, except the intentional edit-mode dimming and one transient fade.
  - Phone (390px): no horizontal overflow on 8 pages.
- **Known to work live** (checked in the user's Chrome against the running stack): the first-chart path (6 clicks, or 4 from a dataset), page-delete undo restoring widgets, the semantic veto (API 422 plus fix button), `rows_scanned` on the crosstab, date presets, Egypt matching (63/63 on a fresh install; the installed set via pins), the EU pack refusal without terms, and the Ask AI provenance line.
- **Still needs testing:**
  1. The full backend sweep on the candidate Python upgrade.
  2. The automation-runner tests with the LLM reachable.
  3. Container tests after rebuilding the images (`axe-core`, React Router 7).
  4. The shared-link reader view on a real phone (a new share link was not minted because that would publish data).
  5. Performance/bundle work, once done.

---

## 12. Decisions and constraints (do NOT violate)

**Working rules from the user:**
- **Never delete** the user's files or app data without explicit approval. The user asked to be told about deletions and to do them himself. Move files to `data_analytics/_to_delete/` instead.
- **Never type passwords** or secrets into anything. Never commit `.env`.
- **Commit only when asked.** Work goes on the branch `masterplan/complete`. Commit messages end with the attribution lines already used on the branch. No remote exists; don't push unless one is added and the user asks.
- **Mark progress in `MASTER_PLAN.md`** with ✅ and a short "how it was proven" note.

**Architecture and code rules:**
- Keep the layer rules (`tests/test_layer_conformance.py`): services must not import FastAPI or `core/capability`; widget errors go through `widget_error()` with registered codes.
- **Enforce data rules in `_resolve_widget_data`**, so they hold for the builder, share links, embeds, export and the API alike.
- **Region matching stays exact** (never fuzzy): painting data onto the wrong region is worse than leaving it unmatched.
- **Every builder mutation needs an undo entry.** Resolve widget and page ids when the command *runs* (`IdAliases`).
- **Every result states its population** (`rows_scanned`) and any cut (`truncation`). A disabled control always gets a reason.
- The **semantic guard's** backend and frontend rules must stay identical (`semantic_guard.py` ↔ `lib/semanticGuard.ts`).
- **API contracts:** keep `total` meaning what each renderer expects (the crosstab's `total` is its grid size). Add new fields rather than changing old ones.
- **Design system** (`styles/mcait/*`, `styles/datalytics.css`) is the user's in-progress restyle. Fix usages (which token an element uses) before changing token values; add a missing dark value only when it is clearly missing.
- **Theming:** text on an accent fill uses `--mc-accent-fg`; on a danger fill, `--mc-danger-fg`. No hard-coded `#fff`.
- **FastAPI:** stay on ≤ **0.136.x** unless the route-walking tests are rewritten for `_IncludedRouter`.
- **Dependencies:** npm packages must be added in `frontend/package.json` and `package-lock.json` (keep the lockfile's **LF** line endings); the frontend container then needs a rebuild. Keep React 18 and Python 3.10 compatibility (the test venv's Python is 3.10; the container's Python is **(uncertain)**).
- The **EU NUTS-1 pack must never install without explicit acceptance**, and its credit must stay visible on every map using it.
- **Assistive output** (AI and insights) must always show its evidence and its engine.

---

## 13. Pending tasks

### High priority
1. Finish the **Python security upgrade**: run the full backend sweep with `fastapi==0.136.3`, `starlette==1.7.0`, `python-multipart==0.0.31`, `python-jose[cryptography]==3.5.0`. If green, update `backend/requirements.txt`, commit, and tell the user to rebuild the backend image.
2. Fix the **ARCHITECTURE.md/.html frontend test-file count** (210 → 211) so `test_architecture_doc.py` passes. Commit.
3. **User actions** (remind; do not do them): rebuild the containers (`docker compose build frontend backend`, then `docker compose up -d`); delete the "Test leftovers (safe to delete)" dashboards and folder, model id 5, and `_to_delete/`; reload the demo (`.\scripts\demo_up.ps1 -SkipBuild`).

### Medium priority
1. **Performance:** `vite build` reports chunks over 500 KB. Analyse the bundle, code-split heavy routes (builder, maps, models, PPTX export) with `React.lazy`/dynamic import, and measure before and after.
2. **Dev-tooling upgrade** (vite 8, vitest 5, esbuild) to clear the critical/high dev-only advisories. Needs care with config and the test setup.
3. Other Python advisories (pyarrow, protobuf, setuptools, pytest) after the high-priority set.
4. Verify the shared-link reader view on a phone using a link the user creates.

### Low priority
1. Ask the user whether the report builder's compact toolbar should meet the 24px tap-target size.
2. Replace or pin `pptxgenjs` so its `image-size` advisory is resolved (npm's suggested fix is a downgrade).
3. Consider rewriting the route-walking tests to be FastAPI-version-agnostic (flatten `_IncludedRouter` through `effective_route_contexts`, or use `app.openapi()`), unblocking FastAPI ≥ 0.137.

---

## 14. Recommended next step

1. Open the repo, check out `masterplan/complete`, and confirm `git log --oneline -5` shows `077f0341` at the top. Check that `git status` doesn't show `.git/index.lock` problems.
2. Fix the ARCHITECTURE docs count (210 → 211) and run `python -m pytest -q tests/test_architecture_doc.py`.
3. In a **separate virtualenv**, install `backend/requirements.txt`, then `fastapi==0.136.3 starlette==1.7.0 python-multipart==0.0.31 "python-jose[cryptography]==3.5.0"`. Run the **whole** backend suite with `UPLOAD_DIR` and `DUCKDB_CACHE_PATH` set. If the only failures are the three LLM-dependent automation-runner tests, update `requirements.txt` with those four pins, run `pip-audit` again, and commit on the branch. Otherwise investigate the failures without jumping to FastAPI ≥ 0.137.

---

## 15. Continuation instructions for the next AI assistant

- Read `MASTER_PLAN.md` (Parts I and IV especially) and this handover, then **inspect the actual files** before changing anything. The code is the authority; this document may be stale or wrong in places marked uncertain.
- **Continue from the current implementation.** Every plan item is built. Don't rebuild completed features; extend or fix them.
- **Preserve the architecture and the decisions in §12:** single widget-data choke point, layer rules, exact region matching, undo for every mutation, disclosure of population and truncation, reasons on disabled controls, theming tokens.
- **Verify assumptions** by running the relevant tests (and `tsc`) before and after each change. Keep TypeScript at 0 errors and the suites green; add a regression test for every bug fixed.
- **Don't repeat approaches that failed:**
  - FastAPI ≥ 0.137 without adapting the route tests.
  - Running backend tests with `/app` paths in a non-container environment.
  - Assuming `npm install` in the host reaches the frontend container.
  - Committing the lockfile with CRLF line endings.
  - Relying on screenshots of a hidden browser tab (widgets load lazily only when visible). Use DOM or API checks instead.
- **Never delete** the user's data or files; never type secrets; commit only on request; don't push without a remote and a request.
- **Ask the user only** for genuine decisions: design changes to the builder toolbar, anything destructive, major dependency upgrades with behaviour risk, or scope beyond the plan.
- After finishing a unit of work: update `MASTER_PLAN.md` (✅ plus a proof note), commit on `masterplan/complete` with the established attribution trailer, and report briefly.

---

## 16. Copy/paste starter prompt

```
You are continuing an existing development session. First read the handover below, then inspect the actual project files to verify the current state. Do not assume the handover is more authoritative than the code. Continue from the current implementation and complete the next pending task.

Project: Datalytics, a self-hostable analytics/BI platform (React 18 + TypeScript + Vite + React Router 7 frontend; FastAPI + pandas + DuckDB + SQLAlchemy/Alembic + PostgreSQL backend; docker compose: frontend :3001, backend :8000, postgres :5433).
Code: D:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics (git branch `masterplan/complete`, no remote).
Plan: D:\Omda 2025\projects\data_analysis_dashboard_ai\MASTER_PLAN.md: every phase and all 11 Part IV acceptance criteria are done and marked ✅.
Full handover: D:\Omda 2025\projects\data_analysis_dashboard_ai\SESSION_HANDOVER.md. Read it first, especially §4 (state), §10 (open problems), §12 (constraints) and §13 (pending tasks).

Next tasks, in order:
1) Fix ARCHITECTURE.md and ARCHITECTURE.html: the frontend test-file count must be 211 (tests/test_architecture_doc.py).
2) Finish the Python security upgrade in a separate venv: fastapi==0.136.3, starlette==1.7.0, python-multipart==0.0.31, python-jose[cryptography]==3.5.0. Do NOT use FastAPI >= 0.137 (app.routes becomes _IncludedRouter wrappers and three route-walking tests break). Run the full backend suite with UPLOAD_DIR and DUCKDB_CACHE_PATH set to writable paths; the three automation-runner tests need the LLM and may fail offline. If green, update backend/requirements.txt and commit.
3) Then performance: code-split the frontend chunks over 500 KB and measure before and after.

Rules: never delete the user's files or data (move to _to_delete/ and tell the user); never type or commit secrets; commit only when asked, on masterplan/complete; keep tsc at 0 errors and all suites green; add a regression test for every fix; update MASTER_PLAN.md with ✅ and a proof note; ask the user only for genuine decisions.
```
