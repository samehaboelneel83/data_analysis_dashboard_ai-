# UX + ETL + Security Pass

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Make the product easy to drive (right-panel usability, navigation, codeless expressions, PowerBuilder-style query builder), add a rich ETL surface (extract formats, a visual transform pipeline, full/incremental loads, lineage), and harden data/application security for design time and sharing time — with self-serve user/org parameters so non-admins can build "my data" views.

**Authority:** the user's requests of 2026-08-26 (usability, query builder graph⇄script, ETL E/T/L + lineage, security in/out of the org, easy RLS + auto user/org parameters) + the survey of the same date (facts below are verified, cited file:line where load-bearing).

**Baseline:** master (2095 backend + 739 frontend green). Branch: `ux-etl-security`.

## Global Constraints

Same machinery as every prior pass: backend tests in Docker via PowerShell (`docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <args> -q --no-header -p no:warnings`); frontend `npx vitest run` + `npx tsc --noEmit` local; focused tests per batch, full suites at checkpoints (after batches 4, 8, 12); BOM files (models.py/main.py/config.py) utf-8-sig; `_migrate` ALTER-IF-NOT-EXISTS for new columns; `check_org` 404 convention; additive — no existing test weakened; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. **No new DnD library** — click-to-insert (proven in CalcColumns) + the codebase's native mouse-event convention. Frontend styling follows each file's existing idiom.

**Ruled out up front:** unstructured extraction (emails/web — own project); reverse-parsing SQL into the graphical query model (script mode is honest one-way); real CI (no remote exists).

---

## Phase A — navigation & context

### A1: Context links & breadcrumb
Survey facts: no path from report→dataset→source except the Lineage page; `DatasetDetail.tsx:680` links only to generic `/connections`; CommandPalette indexes pages/reports/datasets but not connections.
- ReportBuilder header gains a compact breadcrumb: report name ▸ dataset name(s) (link `/datasets/:id`) ▸ source name (link `/connections` — or the review page `/connections/:id/review` when the dataset has `data_source_id`).
- DatasetDetail links to its specific connection.
- CommandPalette adds connections to its index.
- Tests: breadcrumb renders with links for a source-backed dataset and degrades (no source link) for uploads; palette finds a connection by name.

### A2: Right-panel object bar + reset
Survey facts: selection routing is a ternary at `ReportBuilder.tsx:2275-2288` (widget → WidgetConfigPanel else page → PagePropertiesPanel); panel scroll is never reset on selection change; accordion open-state is global via localStorage (`ExpandableGroup.tsx:34`).
- A slim header atop the right panel (default mode): shows the selected object ("Widget: <title or type>" / "Page: <name>"), an ✕ that clears widget selection (falls back to page), and a "Report settings" link that opens the parameters mode.
- Panel content scrolls to top whenever the selected object identity changes.
- Per-widget-type most-relevant group auto-opens: when selection changes to a widget whose type grants Formatting/etc., ensure "Fields" is visible (scroll top achieves this) — implement as: selection change collapses nothing but scrolls top (keep localStorage behaviour; do NOT fight it).
- Tests: header shows widget title; ✕ deselects; scroll container's scrollTop set to 0 on selection change (jsdom: assert the ref call).

## Phase B — config panels

### B1: Widget panel search + Actions group
Survey facts: `WidgetConfigPanel.tsx` (1602 lines) accordion of 8 groups + a flat always-visible block; button actions buried in the flat block at :767-811 gated on `wt==='button'`.
- A filter box at the top of the panel: typing narrows visible groups/fields by label match (case-insensitive; matching groups force-open while filtering; clearing restores).
- Button action config moves into a named **"Actions"** ExpandableGroup (same fields, same state keys — a relocation, not a rewrite), open by default for buttons.
- Tests: filter narrows to matching group; clearing restores; Actions group renders for buttons with the existing action fields; non-buttons don't show it.

### B2: Page panel sections + actions summary
Survey facts: `PagePropertiesPanel.tsx` (186 lines) is a flat form; page-type radios at :130-142.
- Restructure into the same ExpandableGroup idiom: Identity (name/title), Layout (size), Behaviour (page type + interactions), Prompt, Visibility. Preserve all state keys.
- New "Actions on this page" list: widgets on the active page whose config has an `action`, one row each ("Button 'X' → navigate: Page 2"), click selects that widget (reuses the existing selection setter).
- Tests: groups render; actions list shows a button's action and clicking selects it; empty state hidden.

## Phase C + S0 — codeless expressions + system parameters

### C1: Shared ExpressionBuilder
Survey facts: the best UX already exists in `CalcColumnsPanel.tsx` `BuilderModal` :299-643 (3-pane Attributes/Functions/Operators click-to-insert, live Test); `MeasuresPanel.tsx` has a sibling copy; the dataset filter (`DatasetDetail.tsx:521-529`) is a bare textarea.
- Extract `components/expr/ExpressionBuilder.tsx` from BuilderModal: props {columns, functionsCatalog, value, onChange, onTest(expr)→result, extraPaletteGroups?}. CalcColumns and Measures both consume it (dedupe — behaviour identical, their tests keep passing). Dataset filter upgrades from textarea to the builder (modal or inline, following DatasetDetail's idiom).
- Tests: existing CalcColumns/Measures tests green unchanged; dataset filter opens the builder, insert works, Test round-trips.

### S0: System parameters (user + org), non-admin useful
Backend facts: `core/rls.py` expands `USEREMAIL()/USERID()/USER()` via `apply_user_context(expr, *, email, user_id)`; widget filter expressions evaluate via `widget_data.apply_filter_expr`; report parameters exist (ReportBuilder parameters mode :2174-2248).
- Backend: add `ORGID()`/`ORGNAME()` tokens to `apply_user_context` (needs org name — extend the signature; find every caller and pass org info; org name from the caller's loaded Organization). Widget/report filter evaluation paths must expand user tokens for the VIEWING user before evaluation — locate where widget filter expressions/`default_filter_expr` are evaluated per-request and ensure `apply_user_context` runs there for the requesting user (it may only run for RLS today — this is the change that makes the tokens usable in ordinary author filters). Narrowing-only by construction (they're just literals after expansion).
- Frontend: the ExpressionBuilder palette gains a "System" group: Current user email/id, Current organization id/name → inserts the tokens. Parameters panel shows a read-only "System" section listing them.
- Tests: backend — a widget filter `owner == USEREMAIL()` returns only the caller's rows for two different users (the key test); ORGID/ORGNAME expand. Frontend — palette inserts tokens.

### C2: Codeless mode
- A structured mode inside ExpressionBuilder (toggle "Simple | Advanced"): rows of [column ▾] [operator ▾] [value|column|parameter ▾] joined by AND/OR, plus a function row type ([function ▾] with argument slots). Compiles to the text expression (generalizing `DisplayRulesPanel.compileCondition` :70-126). Text is source of truth: switching Simple→Advanced always works; Advanced→Simple only when the expression was builder-generated (tracked marker) else offer "start over in Simple".
- Tests: row edits compile to expected expressions incl. system parameters; round-trip for builder-generated; hand-written expression → Simple shows the honest fallback.

### S0b: Codeless RLS rule builder
Facts: Row security admin UI exists (admin nav); rules are per role+dataset `filter_expr` text; Layer-1 semantic types mark email columns (`dataset_columns.semantic_type`).
- In the Row Security admin page: "New rule" flows codelessly — pick dataset → column picker **pre-suggesting email/user-ish columns** (semantic_type email, or name matching user/email/owner) with a "restrict by current user?" hint → match target: Current user email / Current user id / Current org / literal per role → generates `col == USEREMAIL()` etc. Text view remains for advanced.
- Tests: suggestion surfaces email-typed column; generated expression correct; saved rule round-trips.

## Phase S1 — kill RLS post-filtering (the architecture-flagged flaw)

Facts: `widget_data.apply_rls_filter` (:2015) post-filters result frames; the agent's dataset mode already does it right (base-frame filtering pre-registration); many call sites (routers/widget_data.py:113,222,253, analysis.py, datasets.py, prep.py:348, alerts/delivery).
- Restructure so RLS filters the BASE frame before any aggregation/shaping in every import-path pipeline: the frame-load choke points (frame_cache/load_file → prep → shape) apply `apply_user_context`-expanded RLS immediately after load, and `apply_rls_filter` on RESULTS is deleted (or reduced to the base-frame helper). Audit each call site; keep fail-closed semantics (broken expression → zero rows).
- Tests: an aggregate over an RLS-filtered dataset equals the aggregate of only-permitted rows (value-pinning, the TestPoliciesBind pattern); the old post-filter function no longer exists on result paths (structural pin); every existing RLS test green.

## Phase D — query builder

### D1: Persist the query model
Facts: `QueryBuilderDialog.create()` :102-112 sends only compiled SQL (`dataSourcesApi.import`); `query_builder.py` compiles a validated JSON model; builder datasets can't be re-edited.
- Backend: `Dataset.query_model` JSON nullable + `_migrate`; import endpoint accepts optional `query_model`, stores it; expose in dataset GET.
- Frontend: dialog sends the model; DatasetDetail shows "Edit query" for datasets with a model → reopens the dialog pre-loaded; re-import updates data + model (full reload semantics).
- Tests: round-trip create→reopen→model intact; re-import replaces rows.

### D2: Graphical ⇄ script switch
- The SQL preview becomes a tabbed pane: "Design" (existing) | "SQL". SQL tab: editable textarea seeded from the compiled SQL. Editing switches the dialog to script mode: Design tab greys with "Manual SQL — return to Design regenerates from the model and discards manual edits" (explicit button + confirm). Script-mode create() sends sql only (no model → not re-editable visually; the dialog says so).
- Tests: edit → script mode; revert regenerates; create in script mode sends no model.

### D3: Canvas column picking (PowerBuilder feel)
Facts: `QueryCanvas.tsx` draws draggable table boxes, join edges by column clicks, join-type cycling; columns config lives in form rows below.
- Table-box columns get checkboxes: checking adds to the output columns (default aggregation none), synced two-way with the rows below; a per-column badge cycles aggregation (none→sum→avg→count…—reuse the dialog's list); WHERE rows gain a "builder" button opening the shared codeless builder scoped to the picked tables' columns.
- Tests: checkbox syncs to columns rows both directions; badge cycles; builder inserts a filter.

## Phase F — ETL

### F1: XML extraction
Facts: `analytics.py:12-15` SUPPORTED = csv/xlsx/xls/json (+parquet). Add `.xml` via `pd.read_xml` (lxml — check availability in image; if absent add to requirements + rebuild test image). Upload UI accept-list updated.
- Tests: an XML fixture uploads and parses; unsupported extension message unchanged.

### F2: Transform pipeline editor
Facts: engine exists — `prep.py` fail-soft ordered steps: replace, rename, retype, split, filter_rows, remove_columns, aggregate (+ joins via aux_frames); no `sort` step; steps stored on the dataset (find the field — grep prep_steps_of). There is SOME existing prep UI on DatasetDetail (verify what exists before building).
- Engine: add `sort` (columns + directions) and `dedupe` (subset columns, keep first) step kinds, same fail-soft style + tests.
- UI: a "Pipeline" section on DatasetDetail: step cards in order (icon, summary line), add-step menu (all kinds), edit in place (per-kind mini-forms; filter/computed use the shared ExpressionBuilder), reorder via up/down buttons (no DnD lib), remove. **Live preview**: after any change, a preview strip per step: row count in→out + a 5-row sample of the final result (server endpoint that applies steps 1..k — check if a prep preview endpoint exists; add one that takes steps and returns per-step counts + final sample, RLS-filtered per S2).
- Tests: engine sort/dedupe; preview endpoint per-step counts under RLS; UI cards add/reorder/remove/edit + preview renders.

### F3: Load modes (drive the watermarks)
Facts: `Watermark` model exists (dataset_id, strategy full|incremental, cursor_column, cursor_value) — never driven; datasets import via file or source SQL; a scheduler exists (alerts/delivery services + schedule mode in reports — find the actual job runner).
- Backend: refresh service for source-backed datasets — `refresh_dataset(id, mode)`: full = re-run stored query_model/SQL replacing rows; incremental = append rows where cursor_column > cursor_value, update watermark (transactional; wrong-config falls back to full with a warning). Refresh history: reuse `query_runs` (source_kind='refresh') + last_refreshed_at on Dataset (+_migrate). Endpoint `POST /datasets/{id}/refresh` (admin or owner), config endpoints for strategy/cursor_column.
- Frontend: DatasetDetail "Load" section: strategy picker (cursor column dropdown for incremental), Refresh now, last refresh + history line.
- Tests: full replaces; incremental appends only new rows + advances cursor; bad cursor column falls back full with warning; org scoping.

### F4: Lineage shows ETL
Facts: `/lineage/graph` endpoint (datasets.py:765) + clickable Lineage page.
- Graph payload gains per-dataset: step_count, load strategy, last_refreshed_at, staleness bucket; source→dataset edges labelled "extract"; dataset nodes badge transform count (click → DatasetDetail pipeline section anchor); freshness coloring (fresh <24h / stale / never).
- Tests: payload fields; page renders badges/colors (existing lineage tests stay green).

## Phase S3-S5 — sharing + tenant hardening

### S3: In-org sharing identity + snapshot edge case
Facts: `routers/shared.py:48` comment — shared views resolve RLS via the CREATOR; `PageRoleVisibility` cascade edge case parked (deleted page after pinning loses restriction).
- Authenticated in-org viewers of a shared report get RLS resolved as THEMSELVES (guest/anonymous keeps creator semantics — that's the feature); audit report-view paths for viewer-identity correctness.
- Snapshot edge case: pinned snapshots store the page's role-visibility list AT PIN TIME inside the snapshot; serving filters restricted normal pages for role-holding viewers from the snapshot copy (guests: normal-only unchanged).
- Tests: two users same org different roles see different rows via the same in-org share; pinned snapshot of a role-restricted page stays restricted after the live page is deleted.

### S4: Tenant boundary — guest link controls
Facts: share links exist with pinned/snapshot; expiry/revocation unknown (verify); export policy admin exists; no per-link access log.
- Share dialog states plainly: "Guest viewers see data with YOUR data permissions." Per-link: expiry date (nullable), revoke (delete exists? verify — else add revoked flag), and an access log table (share_link_id, ts, ip hash, user_agent trunc) written on guest render (fire-and-forget, query_log pattern); a per-link access count/last-access in the dialog.
- Export policy: verify it gates guest-view export routes; close gaps found.
- Tests: expired link 404s; revoked link 404s; access rows written; export policy respected on guest paths.

### S5: App/tenant hardening
- Rate limiting: per-user token bucket middleware on auth'd routes + stricter per-link bucket on guest routes (in-process, per-worker honest limits — no Valkey; settings-tunable; 429 with Retry-After). Exempt health.
- enc:v1→v2 migration: startup task re-encrypts any `enc:v1:` secrets to v2 (idempotent, logged count).
- Audit trail: `admin_audit` table (org, actor, action, target, ts, detail hash-safe) written on security-relevant mutations (RLS rules, row policies, share create/revoke, export policy, API keys); admin page lists it read-only (the existing "audit log must not be editable" principle).
- Tests: 429 after N requests; v1 secret migrates on startup; audit rows on rule create; audit list admin-gated.

## Phase E — close out
Full backend + frontend suites; live smoke of the headline surfaces (breadcrumb, pipeline preview, query builder reopen, guest link expiry); comparison doc re-score (+HTML); merge to master.

## Batching
1: A1+A2 · 2: B1+B2 · 3: C1+S0 · 4: C2+S0b (checkpoint) · 5: S1 · 6: D1+D2 · 7: D3 · 8: F1+F3 (checkpoint) · 9: F2 · 10: F4 · 11: S3+S4 · 12: S5 (checkpoint) · E.

---

## Addendum (2026-08-26, user request mid-execution)

Three new requirements arrived while Batch 6 was in flight. They extend, not replace, the existing sequence: run as **Batch 13 (S0c + SH1)** and **Batch 14 (U1)** after Batch 12, before Phase E.

### Task S0c: Auto-injected RLS rules from user/org parameters

Builds on S0b's codeless builder and S0's system parameters. Goal: admins get RLS conditions **auto-generated** from auto-filled user/org parameters, then can modify them.

**Files:** backend `routers/admin.py` (or the RLS rules router found by grep), `models.py` (RowPolicy gains `auto_generated` BOOLEAN default false via `_migrate` ALTER-IF-NOT-EXISTS; BOM preserved); frontend `AdminRowSecurityRules.tsx`.

- Backend endpoint `POST /admin/rls-rules/auto-generate` body `{dataset_id}` (org-scoped, admin-only): scans the dataset's columns; for each column with `semantic_type == 'email'` or name matching `/user|email|owner/i` proposes `` `col` == USEREMAIL() ``; for name matching `/org|tenant|company/i` proposes `` `col` == ORGID() `` (numeric-ish) or `` `col` == ORGNAME() `` (text). Returns proposals; `{apply: true}` creates them as normal rules with `auto_generated=true`, skipping any column that already has a rule (idempotent — re-running never duplicates).
- Admin UI: "Auto-generate rules" button on the Row-security page (dataset picked) → shows proposals with checkboxes → apply. Auto-generated rules render with an "auto" badge; editing one through the existing edit flow clears `auto_generated` (so a later re-run does not clobber the admin's modification — assert this in a test).
- Tests: proposal correctness per column type; idempotency; edit-clears-flag; generated rules actually filter via the base-frame path.

### Task SH1: Dataset sharing to another user

**Files:** backend `models.py` (+`DatasetShare`: id, dataset_id FK, user_id FK, created_at, unique(dataset_id,user_id); `_migrate` CREATE-IF-NOT-EXISTS; BOM), datasets router; frontend `DatasetDetail.tsx` share dialog.

- Grep the existing report-sharing pattern first and mirror its shape (in-org user share, not guest links).
- API: `GET/POST/DELETE /datasets/{id}/shares` — owner (or admin) only manages shares; share target must be a user in the same org (404-never-403 discipline per repo convention). Shared users get READ access: dataset appears in their list (flagged `shared: true`), preview/columns/widget-building work; update/delete/re-import/share-management stay owner-only.
- RLS still applies to the shared viewer with THEIR identity (base-frame path already does this — add a test proving a shared user sees their own row subset, not the owner's).
- Frontend: Share dialog on DatasetDetail (user picker from org users endpoint), shared-with list with remove; datasets list shows a shared badge.
- Tests: cross-org share rejected 404; shared user can read but not mutate; unshare revokes; RLS-per-viewer test above.

### Task U1: Pop-up action menus as an alternative to icons, app-wide

- New shared component `frontend/src/components/ActionMenu.tsx`: a "⋯" trigger button opening a popup menu of labeled actions (text + optional icon), keyboard accessible (Escape closes, arrow navigation, focus return), closes on outside click, positioned to stay in viewport.
- Adopt it at every icon-cluster site found by grep (at minimum: dataset list row actions, report list row actions, widget header actions in ReportBuilder, admin table rows). Icons stay; the menu is the alternative — same handlers, no behavior change.
- Tests: ActionMenu unit tests (open/close/keyboard/outside-click); one adoption-site test per surface asserting menu items fire the same handlers as the icons.

**Batching update:** 13: S0c+SH1 · 14: U1 · then Phase E (E's full-suite + smoke covers the addendum too).
