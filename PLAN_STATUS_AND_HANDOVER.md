# Datalytics vs SAS plan: delivery status and hand-over

- **Date:** 2026-09-25
- **Plan:** `SAS_GAP_ANALYSIS_AND_OUTPERFORMANCE_PLAN.md` (repo root). Section numbers and epic IDs (E01–E18) below are the plan's own.
- **Repo:** `data_analysis_dashboard_ai`. The app is in `AI_data_tool/data_analytics/`. `main` is at `990284b`.
- **Replaces, as the single current picture:** `SAS_GAP_SESSION_REPORT.md` and `UI_REFRESH_SESSION_REPORT.md` in this folder. Those stay as history; where they differ from this file, this file is current.

---

## 1. Where the program stands

| Measure | State |
|---|---|
| **Release blockers (plan §6)** | **All 8 closed.** |
| **Epics finished to their acceptance criteria** | **None fully.** E05, E06 and E07 are nearly there; each has a named remainder. |
| **Epics with delivered slices** | E01, E02, E03, E04, E05, E06, E07, E10, E11, E13 (foundations only), E15 |
| **Epics not started** | E08, E09 (beyond the restore fix), E12, E14, E16, E17, E18 |
| **Plan phase** | Phase 1 ("trustworthy foundation") is substantially done. Phase 2 ("complete the core journey") is in progress: the data journey (E05–E07) is well advanced; reporting (E08) and releases (E09) have not started. |
| **Git** | `origin/main` is at `e5e4ea0`. **26 commits are not pushed** (`569dbb0` … `990284b`). |
| **Tests at hand-over** | Frontend: 216 files, **2,819 tests pass**; `tsc` and `vite build` clean. Backend: **5,649 passed, 2 skipped, 0 failed**. |

### Status legend

- **Done**: meets the plan's acceptance criterion, with tests.
- **Partial**: a real slice is delivered and tested; the named remainder is not.
- **Not started**: no work in this program. The "already in the app" column says what existed before, per plan §4.

---

## 2. Release blockers (plan §6): all closed

All eight landed in `826784a` (inner-repo commit `3cd587c4`). Each has tests that fail on the old code.

| # | Blocker | What was wrong | What changed |
|---|---|---|---|
| 1 | Script tiles (P0) | A non-admin could run their own script-tile code through `/widget-data`. | Script execution is guarded server-side, for every entry point. |
| 2 | DirectQuery denied columns (P0) | Nested references were not checked; a `SELECT *` table leaked denied values. | Denied columns are passed into `run_direct_query` and are part of the cache key. |
| 3 | Authoring without read (P0) | A colleague could delete or re-model a dataset they could not read. | `require_dataset_read` runs first inside `require_dataset_capability`, and in dataflow writes. |
| 4 | Cross-surface isolation (P0) | A member could attach an unreadable dataset to their own report, and the "dashboard you can open" rung then opened it. | `_require_readable_datasets` in `reports.py`; creating from a template checks edit and view rights. |
| 5 | Migrations and readiness (P0) | A failed Alembic run still reported ready. | `/health/ready` returns 503 `migrations: failed`. |
| 6 | Production image (P0) | Only a dev image existed. | Dockerfile has dev and prod stages; prod runs non-root without reload (`docker-compose.prod.yml`); restore drill in `docs/BACKUP_AND_RECOVERY.md`. |
| 7 | Version restore (P1) | Restoring a snapshot broke widget links and bookmarks. | Snapshots store page and widget ids; restore remaps them. |
| 8 | Secrets and sessions (P1) | A weak `SECRET_KEY` was accepted in production; tokens survived a password reset. | Weak keys refused in production; tokens carry `iat`; `users.tokens_valid_after` (migration 0038) is set on reset. **Then** (`d9f8792`): the session is an httpOnly cookie with a CSRF header rule and a CSP. |

---

## 3. Epic overview

| Epic | Priority | Status | Delivered in this program (commits) | Main remainder |
|---|---|---|---|---|
| E01 Consistent security | P0 | Partial | Blockers 1–4; cross-org rules (`86cd678`); join privacy (`d76bf21`); cookie session + CSP (`d9f8792`) | One capability matrix document; a single negative suite across *every* surface; cache revocation tests |
| E02 Production baseline | P0 | Partial | Blockers 5–6; CORS order (`a867ba1`) | Upgrade/rollback rehearsal; replicas (shared storage, global quotas, durable scheduler) |
| E03 Typed capabilities | P0/P1 | Partial | Widget payload validation; formatting capabilities (`826784a`) | Versioned schemas, legacy-config migration, generated client types, connector capability declarations |
| E04 Numerical/query consistency | P0/P1 | Partial | 5 slices: cross-engine goldens, missing-category disclosure, ranking over source rows, year labels, Top-N on crosstabs (`826784a`, `a1961bd`) | Written evaluation order; measures on DirectQuery; wider non-additive fixtures |
| E05 Semantic contracts | P1 | **Nearly done** | Dependents + 409 on delete, rename with references, source-replacement guard + mapping UI, metric versions, same result in chart/AI/export/copilot (`ffca7c7`, `15c7e21`, `54c2824`, `b94e716`, `569dbb0`, `0739ecb`, `13f3d50`, `d7aae84`, `12eb7df`) | Stable field IDs (`FieldRef`); report-local overrides vs shared meaning |
| E06 Unified data workspace | P1 | **Nearly done** | Join privacy, fan-out/orphans/freshness preview, auto profile, next steps, saved view = prep pipeline, quality report, multi-database combine (`d76bf21`, `5d5fa42`, `a4841bd`, `73d3c07`, `30819bc`, `6e1dee0`, `69c6216`) | One catalog showing imported / live / materialized state; lineage view |
| E07 Certified ingestion | P1 | **Nearly done** | 9 commits `0c5cc6d` → `f63bde2` (see §4.7) | Persistent import queue with cancel and retry; a certified 2–3 connector set with a live driver test matrix |
| E08 Reliable reporting core | P1 | Not started | (Related: E04 slice 5, BUG-038 placeholders, chart restyle) | Whole epic |
| E09 Report releases/distribution | P1 | Not started | (Blocker 7 only) | Whole epic |
| E10 Bilingual accessible UX | P1/P2 | Partial | UI refresh Arabic/RTL pass (`6483a74`); one `<h1>` + skip link (`52f28b5`); explicit data timezone (`f63bde2`) | Task-level keyboard/screen-reader verification; Arabic PDF check; calendar choices |
| E11 Trustworthy conversational workflow | P1/P2 | Partial | Answer wording (`518f3fc`); measures in Ask AI and copilot (`569dbb0`, `13f3d50`); Ask AI redesign with add-to-dashboard and history (`c1a8d9b`); copilot redesign (`990284b`) | Held-out bilingual benchmark; evidence link per numerical claim; cost limits |
| E12 Usable automation | P1/P2 | Not started | — | Whole epic |
| E13 Reproducible predictive lifecycle | P2 | Foundations only | Train/validation/test split with stratification, balancing, encoding, feature selection, PCA as prep steps (`6e05b21`, `ab2c2d1`) | Model versions, model cards, promotion/rollback, batch scoring by version, drift |
| E14 Measured performance | P2 | Not started | — | Whole epic |
| E15 Geographic analytics | P2/P3 | Partial | Self-hosted vector-tile basemap (`33240e1`) | Lookup diagnostics, map/table parity tests, map exports, accessibility |
| E16 Embedding/extensions | P2/P3 | Not started | — | Whole epic |
| E17 Assisted migration | P1/P2 | Not started | — | Whole epic |
| E18 Customer validation | P0 onward | Not started | — | Whole epic (needs customer access) |

---

## 4. Epic detail: acceptance criteria against what was delivered

Each epic lists the plan's **minimum acceptance criteria** (plan §10) and whether each one is met.

### 4.1 E01: consistent security (P0) — Partial

| Acceptance criterion | Status | Evidence / remainder |
|---|---|---|
| Script boundary closed or feature disabled | **Done** | Blocker 1. |
| Denied fields never appear in DirectQuery results | **Done** | Blocker 2. |
| One capability rule for authoring and reading | **Done in code**; not written down | Blocker 3 made authoring require read. The plan also asks for **one documented capability matrix** (owner / admin / grantee / legacy / unowned); it has not been written. |
| Cross-surface isolation (imports, DirectQuery, previews, joins, downloads, AI, scoring, schedules, shares) | **Partial** | Blocker 4; joins can only reach readable datasets (`d76bf21`); prep-preview, join-check and analysis require read; security rules must sit inside one org (`86cd678`). **Remainder:** one negative suite that walks *every* surface with the same denied-field / row / tenant fixture. |
| Revocation and cache tests | **Partial** | Revoking a DatasetShare revokes access even via the grantee's own report (pinned). Cache invalidation on permission change is not tested as a suite. |
| No unresolved critical/high pilot findings | **Open** | No external security review has been done. |

Also delivered: session moved to an httpOnly cookie (SameSite=Lax, Secure in production), CSRF header rule for cookie writes, SSO without token in URL, CSP on the production nginx (`d9f8792`); per-org demo logins (`e5e4ea0`); every data import is audited (`c0cc078`); TLS modes for database connections (`565a567`).

### 4.2 E02: production baseline (P0) — Partial

| Acceptance criterion | Status | Evidence / remainder |
|---|---|---|
| Failed migration blocks readiness | **Done** | Blocker 5. |
| Reproducible, non-root production image | **Done** | Blocker 6. |
| Restore meets agreed RPO/RTO | **Partial** | A restore drill is documented (`docs/BACKUP_AND_RECOVERY.md`). No RPO/RTO has been agreed with the owner. |
| Clean install / upgrade / rollback rehearsal | **Not done** | |
| Restart loses no committed work; replica behaviour | **Not done** | Scheduler, caches and quotas are per-process; files are on local disk. |

Also delivered: CORS registered last, so a server error reaches the browser as itself, not as a "CORS error" (`a867ba1`).

### 4.3 E03: typed capabilities (P0/P1) — Partial

| Acceptance criterion | Status | Evidence / remainder |
|---|---|---|
| Unknown/invalid nested fields rejected | **Partial** | Widget configs are validated on save (`validate_widget_payload`). Not yet a versioned schema per widget type. |
| UI exposes only supported options | **Partial** | Formatting options a widget type cannot honour are refused (`FORMATTING_CAPABILITIES`), pinned to the frontend by a parity test. Widget roles are server-side (`REQUIRED_ROLES`), pinned the same way. |
| Legacy saved configs migrate | **Not done** | No versioned migration functions. |
| Contract tests for each declared option consumer | **Partial** | Parity tests exist for roles and formatting only. |

### 4.4 E04: numerical/query consistency (P0/P1) — Partial

| Acceptance criterion | Status | Evidence / remainder |
|---|---|---|
| Selected metrics match fixtures across engines | **Partial** | `tests/test_numeric_goldens.py`: hand-computed values agree on pandas, DuckDB and DirectQuery. |
| Unsupported cases give explicit errors | **Done for the found cases** | An unknown field is an `unknown_field` error, not a row count; DirectQuery refuses measures explicitly. |
| No silent semantic fallback | **Partial** | Fixed: blank categories now disclosed (`missing_category`, shown under charts in `a1961bd`); ranking computed over source rows, not the pushed-down page; Top/Bottom N with "All Other" on crosstabs and matrices; year labels. |
| Declared evaluation semantics (plan §9B) | **Not done** | The evaluation order (policy → prep → joins → row calcs → filters → aggregation → post-aggregation → ranking → formatting) is not yet written as a spec. |
| Measures on DirectQuery | **Not done** | `run_direct_query` has no `measures` parameter; the widget route refuses measures on DirectQuery (not reachable from the UI). |

### 4.5 E05: semantic contracts (P1) — Nearly done

| Acceptance criterion | Status | Evidence |
|---|---|---|
| Rename preserves bindings | **Done** | Renaming a measure or calculated column moves every reference in one transaction: widget configs, other expressions, alerts, hierarchies, common filters, the dataset filter and aggregates (`ffca7c7`). |
| Incompatible replacement blocked with actionable mappings | **Done** | A refresh (manual or scheduled) that would drop a column something uses is refused **before the file is written**; the 409 names the columns, their users and likely matches (`54c2824`). The refresh screen offers a mapping picker and "Refresh anyway" (`b94e716`). |
| One metric gives the same result in chart / AI / export | **Done** | Ask AI computes defined measures with their own formulas (`569dbb0`); the PDF and Excel digest compute what the dashboard shows (`0739ecb`); the copilot builds widgets on the defined measures (`13f3d50`); report parameters applied in one service for dashboard, PDF and digest (`d7aae84`). |
| Changes show affected consumers | **Done** | `GET /dependents`; deleting something in use returns 409 and the panels ask again, naming what uses it (`15c7e21`). |
| Metric versions | **Done** | A changed measure keeps its earlier formulas (last 20), with history and restore (`12eb7df`). |
| **Remainder** | Not done | Stable field IDs (`FieldRef`): identity is still by name, kept consistent by rewriting references. Report-local label/format overrides separate from the shared definition (plan §9A). |

### 4.6 E06: unified data workspace (P1) — Nearly done

| Acceptance criterion | Status | Evidence |
|---|---|---|
| Import → secured profile → composite join → saved view → report, with no manual payloads | **Done** | A new dataset opens with its profile already running (`a4841bd`); after "Save as new dataset" one click builds a dashboard (`73d3c07`); the saved view **is** the prep pipeline (owner's decision; the old DataView bundles are now called "settings templates" in the UI) (`30819bc`). |
| Preview shows fan-out, unmatched keys and freshness | **Done** | Every join preview shows fan-out, the other side's unmatched keys, and each dataset's last refresh (`5d5fa42`). |
| Secured (joins do not leak) | **Done** | A join can only reach a dataset you may read (`d76bf21`). |
| **Also delivered at the owner's request** | Done | Data quality report: missing values, duplicate rows, type problems, outliers, custom rules (`6e1dee0`). One dataset from tables in several databases, append or join, in one action (`69c6216`). |
| **Remainder** | Not done | One catalog view explaining imported / live / materialized state and freshness for all datasets (plan D04); a lineage view. |

### 4.7 E07: certified ingestion (P1) — Nearly done

| Acceptance criterion | Status | Evidence |
|---|---|---|
| No partial dataset masquerading as ready | **Done** | Table imports silently stopped at 100,000 rows; imports now honour `IMPORT_ROW_CAP` and refuse with the way forward (`0c5cc6d`). Uploads over the cap, with case-only duplicate headers or oversize, are refused at the door (`be26aab`). A multi-sheet workbook is never silently its first sheet (`e91b1cc`). Writes are atomic. |
| Per-item import outcome | **Done** | Each batch file gets its true outcome; append marks "created" only after the merged dataset exists; an unexpected failure is one file's error, not a 500 (`f2b050d`). |
| Duplicate handling | **Done** | The same bytes uploaded twice name the earlier dataset (advisory; only datasets the uploader can read) (`aa573cb`, migration 0039). Imports go to per-org paths, so a same-named import no longer overwrites another tenant's file (`0c5cc6d`). |
| File formats: CSV / Excel / Parquet | **Done** | CSV dialects (semicolons, tabs, decimal commas, BOM, Windows-1256 Arabic, Windows-1252) are canonicalized at upload (`47cddad`); Excel sheet selection, or one dataset per sheet in a batch (`e91b1cc`). |
| Timezone tests | **Done** | One policy: offset-carrying timestamps stored as wall-clock time in `DATA_TIMEZONE` (default UTC); incremental cursors keep their instant (`f63bde2`). |
| Auth / TLS / timeouts | **Done** | TLS modes (default, disable, require, verify-ca, verify-full) for Postgres- and MySQL-family connections; `SOURCE_STATEMENT_TIMEOUT_S` (default 900) on every source query. Checked live against the dev Postgres (`565a567`). |
| Import audit | **Done** | Upload, failed batch files, import, re-import and manual refresh are audited (`c0cc078`). |
| **Cancellation and retries; recoverable queue** | **Not done** | Imports still run inside the request. Needs a durable job record (the plan's `Job` contract), shared with E12. |
| **Driver auth/schema/types tests for a certified 2–3 connector set** | **Partial** | Unit-level connect-args tests for every family and a live check on Postgres. **Not done:** choosing the 2–3 customer connectors and a test matrix against real servers (types, schemas, auth). |

### 4.8 E08: reliable reporting core (P1) — Not started

- **Acceptance:** 15–20 object families pass role → configure → filter → save/reopen → export; a pivot fixture suite; no visible no-op controls.
- **Already in the app:** 74 widget types, crosstab/matrix with totals, display rules, slicers, containers, cross-filtering, drill, bookmarks.
- **Related work done:** Top-N "All Other" on crosstabs (E04); "Needs …" placeholders for unfinished hierarchy, map and model widgets (`fcfb3e1`); chart restyle and gallery (`6483a74`).

### 4.9 E09: report releases and distribution (P1) — Not started

- **Acceptance:** drafts do not alter released definitions; restore preserves dependencies; grants stay current; exports match viewer scope; edit conflicts visible.
- **Done:** version restore remaps page and widget ids (blocker 7). Report version history with restore existed before this program.
- **Not done:** the draft/published split, dependency manifest, conflict detection, export-fidelity tests.

### 4.10 E10: bilingual accessible UX (P1/P2) — Partial

- **Done:** a large Arabic/RTL pass with `en.ts`/`ar.ts` kept equal (`6483a74`); one `<h1>` per page and a skip link (`52f28b5`); the phone table scroll cue (`171d3eb`); test locale pinned so an Arabic-locale PC passes (`2890d60`); the data timezone is now explicit (`f63bde2`); Arabic CSV encodings read correctly (`47cddad`).
- **Not done:** keyboard and screen-reader completion of critical tasks as a suite; Arabic PDF and mixed-direction labels checked in real exports; calendar choices (e.g. fiscal, Hijri display).

### 4.11 E11: trustworthy conversational workflow (P1/P2) — Partial

- **Done:** answers name the dataset, format numbers, order groups, and do not suggest columns that do not exist (`518f3fc`); measures computed with their defined formulas in Ask AI and in the copilot (`569dbb0`, `13f3d50`); Ask AI redesign with results, history, composer and add-to-dashboard (`c1a8d9b`, other session); copilot launcher and chat redesign from Claude Design (`990284b`, other session). Column security is enforced in chat (earlier work).
- **Not done:** a held-out bilingual answer benchmark with targets; every numerical claim linked to its computed evidence; scored refusals and ambiguities; per-org AI cost limits.
- **Not verified live:** the answer wording (`518f3fc`) was never run against the real model, because the LLM endpoint was unreachable.

### 4.12 E12: usable automation (P1/P2) — Not started

- **Acceptance:** create / preview / run / review / cancel / retry from the UI; safe resume after restart; audit of inputs, outputs and approvals; no repeated effects from overlapping workers.
- **Already in the app:** dataflow APIs (no routed editor), the 7-step automation runner, schedules, alerts and deliveries with failure records.
- **Note:** the E07 import queue should share this epic's durable job design; build it once.

### 4.13 E13: reproducible predictive lifecycle (P2) — Foundations only

- **Done (owner's request, prep steps):** outlier handling, normalization, categorical encoding, date parts, feature selection, PCA, class balancing, train / validation / test split with stratification, duplicate handling with keep-first/last, fill forward/back/interpolate (`6e05b21`, `ab2c2d1`). Saved models already carry their columns and refuse a denied feature (earlier work).
- **Not done:** versioned training runs, model cards, promotion and rollback, batch scoring by model version, drift monitoring, GLM families, gradient boosting.

### 4.14 E14: measured performance (P2) — Not started

- **Already in the app:** DuckDB pushdown on by default; five `bench_*` scripts in `backend/scripts`.
- **Not done:** SLOs at 1/10/50 users, multi-worker fairness, cancellation that frees work.

### 4.15 E15: geographic analytics (P2/P3) — Partial

- **Done:** the maps can draw a self-hosted vector-tile basemap (TileServer GL `.pbf`), with a test fixture over Egypt (`33240e1`). Boundary sets existed before.
- **Owner action:** set the tile address in Admin → Maps: `http://192.168.50.208:8080/data/egypt_osm/{z}/{x}/{y}.pbf`.
- **Not done:** lookup diagnostics for unmatched names, map/table value parity tests, map exports, map accessibility.

### 4.16 E16 embedding/extensions, E17 assisted migration, E18 customer validation — Not started

- **E16:** embed and custom visuals exist; no supported SDK or versioned extension messages.
- **E17:** report packages exist; no SAS inventory mapping or reconciliation tooling.
- **E18:** no customer benchmark, persona discovery or pilot evidence yet. The plan puts this first in the dependency order; it needs customer access, not code.

---

## 5. Other work delivered (outside the epic structure)

| Item | Commit(s) |
|---|---|
| UI refresh phases 1–10: design system, charts, palettes, empty/loading states, QA report fixes (41 issues), Arabic pass | `6483a74` (UI session) |
| Hand-over tasks T1–T8 from the UI session (unhandled test errors, locale, headings, page size, cross-org rules, Ask AI wording, placeholders, same-named datasets) | `af63d1d` … `171d3eb` |
| Upload warns when a dataset name is taken; the Data tab shows the preview first on narrow screens | `19aefd8`, `b976adb` |
| Plan and application guide tracked; research folder ignored | `b7b2bef` |
| Login page redesign; Ask AI chat redesign; demo recording scripts | `c1a8d9b` (other session) |
| AI button redesign (copilot launcher and chat) | `990284b` (other session) |

---

## 6. Actions waiting on the owner

| # | Action | Why |
|---|---|---|
| 1 | **Push:** `git push origin main` | 26 commits are local only. |
| 2 | **Restart the backend** once | Migration 0039 (`datasets.content_sha256`) is applied by the startup `ALTER`; duplicate detection needs it on the dev database. |
| 3 | **Choose `DATA_TIMEZONE`** | Default is UTC. For Cairo wall-clock times on newly imported offset data, set `DATA_TIMEZONE=Africa/Cairo`. |
| 4 | **Check `SOURCE_STATEMENT_TIMEOUT_S`** | Default 900 s. An import that legitimately runs longer is now cancelled; raise it, or set 0 to turn it off. |
| 5 | **Set the tile server** in Admin → Maps | See §4.15. |
| 6 | **Run one live Ask AI question** when the LLM is reachable | The wording fixes (`518f3fc`) are pinned by tests but never seen live. |
| 7 | **Look at the phone Datasets table at 390 px** | The scroll cue (`171d3eb`) was not checked in a real browser. |
| 8 | **Choose the 2–3 connectors to certify** (E07) and the pilot scenario (E18) | Both are product decisions the plan leaves to you. |
| 9 | Housekeeping | `.git/index.lock.stale-from-claude-1790362878` (empty; safe to delete); `frontend/_ui_refresh_backup/` (ignored by git; delete when satisfied). |
| 10 | Optional | Reword the `c1a8d9b` commit message: it says "not reviewed or test-run", but that session did test it. Only while no other session is working. |

---

## 7. Recommended next steps, in the plan's dependency order

1. **Durable job layer** (plan §8 `Job` contract): one design for E07's import queue (cancel, retry, resume) and E12's automation. This closes E07 and unblocks E12 and E13.
2. **E01 close-out:** write the capability matrix; build the one cross-surface negative suite.
3. **E04 §9B:** write the evaluation order as a spec, then add measures to DirectQuery with parity goldens.
4. **E08 pivot suite and E09 draft/published split:** the start of phase 2's reporting half.
5. **E18 with the owner:** pick the pilot scenario and connectors; everything after phase 2 is gated on it.

---

## 8. Verification at hand-over

- **Frontend (at `990284b`):** 216 test files, **2,819 tests pass**; `tsc` clean; `vite build` succeeds.
- **Backend:** full suite at `990284b`: **5,649 passed, 2 skipped, 0 failed** (31 min 43 s). The process exits 1 afterwards only because the OpenTelemetry exporter logs an error at shutdown when no trace collector is running; no test is affected.
- **Every E05–E07 commit** was sabotage-checked: its new tests were run against the previous commit in a separate worktree (`D:/wt_x`) and fail there.
- **Live checks:** statement timeout cancelled `pg_sleep(3)` at 1.0 s on the dev Postgres; TLS `require` refused a server without TLS; the cookie session was verified in a real browser.

---

## 9. Rules for whoever continues (unchanged, keep following them)

1. Stage by explicit path; check `git diff --cached` first; never commit another session's files unless the owner says so.
2. Never switch branches or check out files in the shared tree. Sabotage checks run in a worktree (`git -c core.longpaths=true worktree add --detach D:/wt_x HEAD`), and **every step after `cd D:/wt_x` is chained with `&&`**: a failed `cd` once ran a checkout in the shared tree.
3. The repo is LF. The Edit tool can write CRLF on Windows: run `sed -i 's/\r$//'` on edited files, and check `git diff --stat` before committing.
4. Every `en.ts` key also goes in `ar.ts`.
5. Adding a backend test file or an Alembic revision changes the counts in `ARCHITECTURE.md` **and** `ARCHITECTURE.html`; the doc audit fails until both match.
6. In a batch endpoint, a rollback expires `current_user`; refresh it (and its `role`) before any capability check.
7. The backend runs with `--reload`: edits go live, and a mid-run edit can fail a running suite.
8. Pushing is the owner's call.
