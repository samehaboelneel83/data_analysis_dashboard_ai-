# Datalytics — MAIN branch: Exhaustive UI Journey & Evaluation

| | |
|---|---|
| **Code under test** | **`main` @ `0cb8f48`** (14 Oct 2026, "Merge pull request #23 from samehaboelneel83/emad"), freshly cloned. App code was not changed. |
| **Date** | 14 Oct 2026 |
| **Where it ran** | Cloud workspace only: Postgres 16, FastAPI backend (Python 3.12 as in the Dockerfile), Vite frontend, a fresh database, the demo seed (6 datasets, 8 dashboards) and all dev accounts. The courier database `nile_express` came from `qa/fixtures/generate_logistics_db.py`. |
| **How** | 11 evaluator agents ran in two waves, each with its own headless Chromium, clicking by visible text like a user. Every screenshot was looked at before it was evaluated. The 57 `high` cases of `qa/TEST_PLAN.md` were also run formally. |
| **Viewports / modes** | Desktop 1440×900, tablet 820×1180, phone 390×844; light + dark; English + Arabic (RTL) |
| **Accounts** | Super admin, org admin, global analyst, EMEA analyst (row and column restricted), Contoso and Northwind admins and analysts, a new non-admin "reader" for sharing, a logged-out guest |
| **Not available here** | No LLM/embedding service (AI answers fail, so failure handling was evaluated), no `online_retail` / `nyc_taxi` databases (the cloud cannot download them; the courier database was used instead), no SSO identity provider, no download contents in headless mode |

> **How to read this file.** Sections 1–6 are the evaluation summary. Section 7 holds the complete per-screen notes for every area: the screenshot, what it shows, whether it works, issues by severity, UX notes, console errors and a 1–5 score. Screenshot links point to `screenshots/<area>/…` inside the zip.

---

> **Fix status — 15 Oct 2026.** The findings below describe `main` @ `0cb8f48` as tested on 14 Oct and are kept as recorded. Since then, on branch `s_mostafa`:
> - **Fixed:**
>   - #2, guest links on map dashboards (`16a84654`)
>   - #1, the `init.sql` schema gap (`62a54a56`): it turned out worse on this code, because the backend would not start on such a database
>   - two Critical admin-security issues found while tracing the code for the fix plan (`55c6ac61`): an org admin could edit or delete the platform admin, and could become a platform admin by registering an upper-case copy of its email
> - **Browser QA re-run of the 57 high cases on the fixed branch:** 46 pass / 4 fail / 7 blocked (was 45 / 4 / 8). The only change is SHARE-02 → pass.
> - Details, tests and remaining risks: `TODO_PLAN.md` → *Progress*, and `qa_rerun_2026-10-15/REPORT.md`.

## 1. Executive summary

**Overall score: 3.5 / 5.** Datalytics on main is a broad, ambitious BI product. Its core paths and most of its new features work, and the visual design is calm and consistent. What holds it back is a Critical guest-link defect, a handful of security gaps in sharing and admin, AI features that don't fail fast when the model is down, and a long tail of edge-case bugs.

**What works well:**
- **Ask AI handles an outage honestly:** a "model server unreachable" banner, a paused composer, a no-AI fallback answer and a Stop button.
- **Publishing and sharing:**
  - drafts vs published versions with "Go back to version N"
  - Archive with counts, and nothing leaks afterwards
  - Hand over, a server-enforced approval-before-publish flow, and guest links off by default
- **Templates and suggestions:** every template produced a usable dashboard, and suggested dashboards without AI built 47 charts in about 8 seconds.
- **Guided setup on a real Postgres database:** it found 7 of 9 deliberately planted data problems, with exact counts and one-click fixes.
- **Security core:** org isolation and EMEA row/column security hold everywhere tested, including templates and exports.
- **Shell:** command palette, dark mode, Arabic/RTL, a setup checklist for new orgs, and Profile ("About you").

**What holds it back:**
- **A Critical bug:** guest links fail whenever a dashboard has a map. (A database first built from `init.sql` also can't load demo content; see #1, which is High, not Critical.)
- **Security gaps:**
  - "No downloads" shares can be bypassed through Print/PowerPoint.
  - An org admin is shown Edit/Delete on the platform super admin.
  - Org-chart row security (MYSCOPE) can't be saved.
- **Broken new code:**
  - Guided setup's "Warn me on every refresh" always fails because of a bad import.
  - Charts render only after scrolling, so Present mode is empty.
- **Edge-case bugs:** admin validation, a stale-results race in Insights, unsafe cell editing, inconsistent number formats and several broken chart types.

### Scorecard

| Area | Screens | Screenshots | Score /5 | High | Medium |
|---|---|---|---|---|---|
| A — Shell, login, home, global UI | 45 | 88 | **3.8** | 0 | 5 |
| B — Data: datasets, glossary, upload, connections, guided setup, dataflows, lineage, migration | 54 | 215 | **3.5** | 11 | 32 |
| C — Dashboards & report builder (incl. chart types) | 60 | 149 | **3.3** | 12 | 25 |
| D — Ask AI, Insights, automations, monitoring | 22 | 66 | **3.2** | 4 | 18 |
| E — Admin, platform, roles & access | 30 | 111 | **3.4** | 7 | 17 |
| F — Templates, suggested dashboards, publishing & sharing | 54 | 163 | **3.7** | 3 | 14 |
| QA plan (57 `high` cases) | 57 | 40 | 45 pass · 4 fail · 8 blocked | | |
| **Total** | **265 + 57 QA cases** | **832** | **3.5** | | |

High and Medium counts are the tags in the per-screen notes; one problem can be tagged on more than one screen. Section 2 lists the unique issues.

### Automated tests

| Suite | Result |
|---|---|
| Frontend Vitest | **389 files, 4,689 passed** |
| Frontend TypeScript (`tsc --noEmit`) | clean |
| Backend pytest (Python 3.12) | **8,564 passed, 4 skipped, 1 failed** |
| Schema check: a database built from `init.sql` reaches the ORM schema | **fails: 8 columns missing** (High #1) |

**The one failing backend test:** `tests/test_widget_roles.py::TestParityWithTheFrontend::test_the_spec_file_was_actually_read` expects 75 frontend chart types, but the frontend has 77. The other 131 parity checks pass, so only the hard-coded count is stale, but it leaves CI red.

**Environment notes:**
- The backend needs **Python 3.12**: the code uses 3.12-only f-string syntax and won't import on 3.11. The Dockerfile already uses 3.12, so this only matters for anyone running it outside Docker.
- The backend tests and the live app both default to the same DuckDB cache file (`/app/uploads/metadata_cache.duckdb`). Running pytest next to a live backend on one machine locks it, which briefly stalled connection syncs during this run. Once the app was given its own file, sync and guided setup worked.

---

## 2. Top issues (consolidated, ranked)

| # | Severity | Area | Issue | Evidence | Suggested fix |
|---|---|---|---|---|---|
| 1 | **High** *(corrected from Critical, 15 Oct)* · ✅ **fixed** `62a54a56` | Install | A database first created from `postgres/init.sql` gets its tables from that file, then is stamped at Alembic head. 8 columns are never added (`datasets.aggregate_of_dataset_id`, `datasets.aggregate_spec`, `reports.origin`, `report_pages.background_url`, `dataset_columns.source_column_id`, `analysis_results.run_id/params/created_by`), so **"Load demo content" fails with HTTP 500**. *Correction:* since commit `5ffbb917`, `docker-compose.yml` no longer mounts `init.sql`, so a normal fresh Docker install is **not** affected. This still breaks developer volumes created before that commit, and anyone loading `init.sql` by hand as README / `first-stop.md` describe. | schema check above | Add the 8 columns to `_migrate` in `app/main.py`, or update `init.sql` |
| 2 | **Critical** · ✅ **fixed** `16a84654` | Sharing | **Guest links bounce to the login page whenever the dashboard has a map.** The map tile calls the authenticated `/api/v1/map-settings`, gets a 401, and the global redirect fires. The shared payload itself returns 200. | F2-55 | Serve map settings in the shared payload, or mark the call `quiet401`; make `/shared` immune to the global 401 redirect |
| 3 | **High** | Sharing | **"No downloads" can be bypassed.** A reader whose share has *May download* off still opens the print view and uses *Print / Save as PDF* and *Download PowerPoint* (built in the browser, no server check). | F-95, F-96 | Gate the print route and PPTX on the share's download right, server-side |
| 4 | **High** | Admin | An **org admin is shown Edit and Delete on the platform super admin** (`admin@datalytics.local`). Server-side enforcement was not tried, to protect the shared session. | E-111 | Hide super admins from org lists; refuse PUT/DELETE unless the caller is a super admin |
| 5 | **High** | Security | **Org-chart row security can't be used.** Quick setup builds `region in MYSCOPE()`, and saving fails with "name 'MYSCOPE' is not defined", because rule validation fills in the user tokens but never MYSCOPE (`admin.py` `_validate_filter_expr` → `core/rls.apply_user_context`). Verified in code. | E-28 | Expand MYSCOPE() with placeholder values during validation |
| 6 | **High** | Data | **Guided setup "Warn me on every refresh" always returns 500.** `routers/guided_setup.py:1577` imports `DataCheckIn` from `app.schemas.schemas`, but it is defined in `routers/datasets.py`. Verified in code. | B2 notes | Fix the import |
| 7 | **High** | Data | **Guided setup hides errors and makes broken widgets.** "Read the database now" swallows every error (`UnderstandStep.tsx:93`), and server errors from sync aren't shown. 6 of the 17 generated widgets fail with "'late_pct_vs_promised' is not a column or measure". | B-104/120, B2 | Show errors; validate generated widgets against the dataset |
| 8 | **High** · ◐ *case-duplicate emails fixed `55c6ac61`; the rest open* | Admin | New users **default to the Admin role**. `not-an-email` with password `x`, case-duplicate emails, duplicate role names and a **quota of -3** are all accepted. Roles have **no permission matrix**. | E-02, E-03, E-77, E-15 | Server-side validation; least-privilege default; capability toggles |
| 9 | **High** | Dashboards | **Charts render only after a scroll**, so Present mode shows "Loading…" on every tile. | C-55, C-57, C-74 | Render tiles already in the viewport on mount; render eagerly in Present |
| 10 | **High** | Insights | **Stale results race:** switching datasets quickly shows Sales findings under Metrics/Routes. | D-30 | Ignore late responses (dataset id / AbortController) |
| 11 | **High** | Data | **Removing the last filter leaves the grid filtered**, and **Edit cells keys rows by the non-unique `date`**, so one edit rewrites many rows. | B-15, B-16 | Re-query on filter change; unique key and an "N rows will change" warning |
| 12 | **High** | Builder | **Stale widget selection after a page add or switch** sends PATCHes for widgets not on the page (404 and an uncaught error). The dataset chosen in the Create dialog doesn't appear until reload. | C-07, C-14, C-15 | Clear selection on page change; invalidate after create |
| 13 | **High** | Dashboards | **Broken chart types:** word cloud blank, scatter with empty axes (one measure only), Sankey without labels; treemap, sunburst and box-plot labels overflow or are unreadable. Map data roles accept any field type. | C-20, C-24, C-25, C-26/27/30, C4 notes | Fix the renderers; type-check roles; add empty-state text |
| 14 | **High** | Data | **Multi-sheet XLSX upload has no sheet picker.** The message is hidden under Technical details. | B-81 | Read `detail.sheets` and show a picker |
| 15 | **High** | AI | **No fail-fast when the model is unreachable.** Suggest dashboards with AI spins for over 2 minutes, an automation run hung on "Build the report" for over 8 minutes, Ask AI suggestion cards still send while "paused", and the data check took about 7 minutes. | F-14, D-58, D-07, B2 | Check model health first; time out every AI step |
| 16 | **High** | Insights | **"Pin finding" goes nowhere:** no Pinned section and no unpin. | D-36 | Ship a Pinned section or remove the action |
| 17 | **High** | Data | **Dataflow from a seeded dataset fails with a silent 403**, even for the super admin. | B-122 | Show the reason; filter the source list |
| 18 | **High** | Demos | **Seeded dashboards wrong:** World Sales Map has a "Needs Latitude · Longitude" tile. "Can I trust this data?" and the "What is in the data" template show row counts as **"$ 2,000"**. | C-54, C-65, F-63 | Fix the seed configs; don't apply currency to count() |
| 19 | **High** | Admin | **Connection rules (Ask AI):** the Postgres connection lists no tables, expressions aren't validated, and changes aren't audited. | E-36/38 | Load tables from metadata; validate; audit |
| 20 | Medium | Sharing | **Team shares don't appear under My team** for a team member. **Restore** brings an archived dashboard back **Published**, not as a draft. The **org-wide approval switch** and publish-to-everyone are one click with no confirmation. New person shares default to **Can edit**. | F-92, F2-33, F2-41, F2-04, F-79 | Resolve team shares; restore to draft; confirmations; default to Can view |
| 21 | Medium | Security | **EMEA traces of `cost`:** measure formulas show `SUM(revenue) - SUM(cost)`, the dataset says "13 columns / 2,000 rows" (true: 12 / 514), and one tile shows the raw "name 'cost' is not defined" error (QA SEC-02). Rows and values themselves are correctly hidden. | E-92/93/96 | Compute counts after RLS/CLS; hide dependent formulas; friendly tile message |
| 22 | Medium | Dashboards | **Number formats:** tables, crosstabs and matrix show raw 2221091.66, bar + line and dual-axis line sum percentages ("12000%"), and KPI/gauge values clip. | C-32, C-35/41, C-58, C3 notes | One shared formatter; average percentages |
| 23 | Medium | Shell | **Deep link lost after login.** The notifications popover won't close (Escape or navigation), the Home stat cards are cramped on phone, and the model picker shows raw "ConnectTimeout" with no per-user "AI off". | A-08, A-20, A-68, A-19 | `state.from`; standard popover dismissal; 2×2 grid |
| 24 | Medium | QA plan | **DASH-04:** Create with an empty name makes "Untitled dashboard". **INS-02:** View full scan lands empty. **MAP-02:** density bubbles show overlapping numbers. | QA REPORT | Require a name; reuse the scan; one label per bubble |
| 25 | Low | Tests | A stale chart-type count (75 vs 77) fails one backend test; the test suite and the app share the default DuckDB cache path. | pytest log | Update the count; give tests their own cache path |

---

## 3. Cross-cutting themes

1. **AI-dependent features don't fail fast.** Ask AI handles an outage well, but Suggest dashboards, automations, data checks and AI descriptions still wait minutes against a model the header already reports as unreachable. Check model health once and gate everything on it.
2. **Silent failures:** guided setup swallows errors, the dataflow 403 says nothing, and Copy reports "Copied" even when it failed.
3. **Access controls aren't enforced at every exit.** The print and PPTX paths ignore "No downloads", guest links depend on an authenticated call, and an org admin is offered super-admin edits. Every exit (print, PPTX, CSV, widget export, guest, embed) should go through one server-side check.
4. **State consistency:** stale insights, stale grids, stale selection after page changes, counts that don't refresh after fixes, team shares not resolved.
5. **Formatting goes through more than one path:** currency on counts, raw table numbers, summed percentages, Western digits in Arabic.
6. **Admin hygiene:** input validation, safe defaults and a role permission matrix are missing.
7. **Responsive design** is good for the shell and lists but weak for the builder (unusable at 820px), monitoring tables and KPI tiles on phones.

## 4. Strengths

- **Ask AI degrades honestly:** banner, paused composer, no-AI fallback and Stop.
- **The publishing model** is well thought out: plain-language confirmations, server-enforced approval, and readers locked out immediately on archive or removal.
- **Templates and no-AI suggestions:** fast and sensible dashboards from statistics alone.
- **Guided setup "Check & discover"** found 420 duplicates, 904 padded names, 1,309 unweighed parcels, empty and constant columns and 38 negative fees, with exact counts and one-click fixes that become dataset steps.
- **Org isolation and EMEA row/column security** hold everywhere tested, including templates and exports.
- **Broad automated test coverage:** about 4,700 frontend and 8,500 backend tests.
- **The shell:**
  - an excellent login and the command palette
  - thorough dark mode and RTL mirroring
  - accessibility basics: skip link, focus rings and labelled icons
  - a setup checklist for new orgs

## 5. Role × capability matrix

The full matrix is in section E's notes. In short:
- **Super admin:** sees everything, including Platform.
- **Org admins:** see Admin and Monitoring for their own org. They are, however, shown Edit/Delete on the super admin (#4).
- **Analysts:** see Data, Sources and Analyse. Upload and Connections can't be restricted (#8).
- **EMEA:** only Europe rows and no `cost` values, but its counts and formulas leak (#21).
- **Contoso and Northwind:** get "not found" for Default-org content.
- **Forbidden admin and platform URLs** redirect silently to Home, with no "no access" page.

## 6. Coverage, limits and leftovers

- **Covered:**
  - every rail destination (31), every admin and platform page, all seeded dashboards and datasets
  - templates, suggestions, publishing and sharing steps 1–9 of `qa/NEW_FEATURES_TEST_GUIDE.md`, guided setup on a real Postgres database
  - 33 of 77 chart types, 9 accounts, 3 viewports, light/dark, EN/AR, and the 57-case QA plan
- **Not covered or blocked:**
  - every AI answer (no model)
  - `online_retail` / `nyc_taxi` (guide §4, large data), because the cloud can't download them
  - guide §7.10–7.12: the reader row rule, My dashboards filters, Favourites, Reports sent, Arabic Share dialog. The headless driver kept dropping the page after account switches.
  - 44 of the 77 chart types: maps other than Point Map, the models group, controls/containers and some hierarchy charts. At about 70 s per screenshot on the shared 2-core machine, there wasn't time for all of them.
  - successful SSO; download contents; native confirm dialogs (auto-cancelled)
  - a few actions on seeded content were skipped on purpose
- **Load caveat:** a 2-core machine running several browsers made pages take 10–60 s. Evaluators retried timing misses and didn't count them as bugs.
- **Test data left in the cloud database only** (named "QA …"): datasets (including from `nile_express`), dashboards, glossary term, data check, dataflow, users, roles, team, org, API key, connector, conversation, automation runs. Platform settings changed during tests were switched back off. Nothing was written to your computer or to the app code, and nothing was pushed to GitHub.

---

## 7. Detailed per-screen notes

Each area follows. Screenshot names link to the image in this package. Where an area has helper notes (B2, C3, C4, F2), they follow the main notes for that area.


---

## QA report

**Build / branch:** MAIN, commit 0cb8f48 (/home/claude/main_repo/AI_data_tool/data_analytics)
**App URL:** http://127.0.0.1:3001
**Browser:** headless Chromium (puppeteer driver, port 9400)
**Viewport:** 1440×900 + 390×844 for MOB-01/02
**Seeded:** yes (fresh seed; other QA agents worked in parallel on the same instance, so their "QA B/F …" items are visible)
**Login used for most cases:** ADMIN admin@datalytics.local (GLOBAL / EMEA for SEC, EMEA for NAV-04/AUTH-07)
**Date:** 2026-10-14, 19:00–20:05 EEST
**Tester:** Claude (agent) — all `high` cases (57)

### Summary

| | Count |
|---|---|
| Total run | 57 of 57 |
| Passed | 45 |
| Failed | 4 |
| Blocked / skipped | 8 blocked |

**Top issues** (worst first):

1. SEC-02 — EMEA user sees the raw error "Unknown column or function in measure expression: name 'cost' is not defined" on the Margin % by region tile, so column-level security shows up as a broken tile.
2. DASH-04 — the "Create a dashboard" dialog lets you click Create with an empty name; an "Untitled dashboard" is created with no name-required message.
3. INS-02 — "View full scan →" lands on Analysis > Insights with an empty panel and only a "Generate insights" button.
4. MAP-02 — Origin density bubbles print two overlapping numbers per bubble (e.g. "34" over "37"), so the counts are hard to read.
5. (visual, not a case fail) Demo — Sales Overview: small tiles cut off their content (gauge value, second KPI value, "Average margin % by product" squashed). On /ask, suggestion chips still submit while the model is offline and spin past 60 s.

**Notes for the next run** (flakes, missing seed, AI model down):

- No LLM: Ask AI and the page copilot disable the input with "The model server isn't reachable, so new questions are paused." That blocks ASK-02/03/04/06, SEC-03 and BUILD-10/11. Suggestion chips on /ask still submit and hang ("Analyzing… / Still working") past 60 s.
- Guest (sign-in-free) share links are switched off at platform level, so SHARE-02 is blocked. Headless Chromium has no clipboard, so Copy link shows "Couldn't copy the link".
- The machine was heavily loaded (2 CPUs, 4 Chromium instances + pytest): each screenshot took about 70 s (MOB-01/02 have no screenshots for that reason).
- The driver's click by text sometimes hit a wrapper element (e.g. "Ask about this data" opened "Use in Python"), so I clicked by coordinates in those cases.
- MAP-04 resized a seeded widget, which I restored with Undo (status shows Saved). A "changed in another session" banner appeared because other agents were using the same seeded report.
- Items created: dataset "Qa sample" (UP-02, suggested name kept), dashboards "QA Dashboard 01" (/reports/15) and "QA Untitled leftover" (/reports/13, the stray dashboard from DASH-04). Not deleted.

---

### Results

| Test ID | Result | What actually happened | Console errors | Notes |
|---|---|---|---|---|
| AUTH-01 | pass | Empty submit stays on /login; inline "Enter your email address." / "Enter your password." | none (only expected 401 /auth/me when logged out) | shot AUTH-01 is pre-click (shots very slow under load) |
| AUTH-02 | pass | "Enter a full email address, like name@company.com."; stays on /login | none (401 /auth/me expected) |  |
| AUTH-03 | pass | "That email and password don't match. Check them and try again."; stays on /login | 401 POST /auth/login (expected) |  |
| AUTH-04 | pass | Same message as AUTH-03; not signed in | 401 POST /auth/login (expected) |  |
| AUTH-05 | pass | Lands on / "Good evening, Admin"; rail Home/Ask AI/Datasets/...; account menu "admin" top right | none | shot HOME-01 |
| AUTH-06 | pass | Logged out, /reports -> /login (after the 401 /auth/me check); signed in, /reports shows the dashboard list (DASH-01) | 401 GET /auth/me (expected when logged out) |  |
| AUTH-07 | pass | Account menu (demo-emea) > Log out -> /login; opening / again ends on /login, Home not shown | 401 GET /auth/me (expected) |  |
| NAV-01 | pass | Rail Home, Ask AI, Datasets, Lineage, Upload, Connections, Dashboards, Insights each load their own page (/, /ask, /datasets, /lineage, /upload, /connections, /reports, /insights); active item highlighted (seen in shots) | none |  |
| NAV-04 | pass | EMEA rail: Home, Ask AI, Data, Data sources, Analyse only — no Monitoring/Admin/Platform. Direct /admin/users redirects to / | none |  |
| NAV-05 | pass | Rail shows MONITORING (Refresh & jobs, Deliveries, Activity), ADMIN (13), PLATFORM -> Organizations | none | shot HOME-01 |
| HOME-01 | pass | KPI tiles (12 dashboards, 6 datasets, 1 connection), quick actions, "Continue where you left off" cards, Dashboards list, Recent activity. AI box says "The AI is offline right now" | none | shot HOME-01 |
| HOME-02 | pass | Clicked "Headline numbers" card -> /reports/11, dashboard viewer with KPIs, filters, scatter | none |  |
| HOME-03 | pass | Clicked "Demo — Routes" in Datasets section -> /datasets/5 detail | 404 GET /datasets/5/analysis (x2; no analysis yet, page renders fine) |  |
| DS-01 | pass | All 6 demo datasets listed by name incl. Demo — Sales (2,000 rows); filters + sort; no Try again | none |  |
| DS-02 | pass | Title "Demo — Sales", tabs Overview / Columns 13 / Data 2,000 / Analysis / Rules & alerts 1 / Models; "Ask about this data" visible | none | Tab names differ from plan (no "Meaning"/"Alerts"/"Aggregates"; Aggregates is shown only for DirectQuery datasets by design) — plan text is outdated |
| DS-03 | pass | Data tab: table with 16 columns, rows 1–100 of 2,000, pager, horizontal scroll | none | shot DS-03 |
| DS-04 | pass | fx columns profit, days_month_to_date (and another agent's "QA B calc") appear in Data tab header with values | none |  |
| DS-09 | pass | "Ask about this data" -> /ask?dataset=1, "Asking about Demo — Sales", suggestions; banner "model server isn't reachable" | none | Driver text-click hit a wrapper and opened "Use in Python"; clicked the link itself |
| UP-01 | pass | With no file there is no Import/submit control at all — only "Browse files" + drop zone; step labels Review/Import are not clickable; stays on /upload | none | shot UP-01. Plan's "message to select a file" is not shown because submit is impossible (design changed) |
| UP-02 | pass | `upload qa_sample.csv` -> Review with preview (region, country, revenue, units, date; 5 rows), suggested name "Qa sample"; Import dataset -> "Dataset imported / Qa sample is ready to use"; Open dataset -> /datasets/7, Data tab shows region, country, revenue, units, date | 404 GET /datasets/7/analysis (no analysis yet) | shots UP-02, UP-02b. Success is an in-page panel, not a toast; dataset detail opens via "Open dataset" rather than automatically. Created dataset "Qa sample" |
| ASK-01 | pass | /ask with no dataset: "Step 1 Choose your data" picker (6 datasets + 1 connection); question box and Send disabled — cannot send without scope | none |  |
| ASK-02 | blocked | No LLM: question textarea + Send disabled, "The model server isn't reachable, so new questions are paused." Could not send "hi" | none | shot ASK-02 |
| ASK-03 | blocked | No LLM: input disabled (same as ASK-02) | none |  |
| ASK-04 | blocked | No LLM: input disabled; the suggestion chip "Total revenue by region" still submits and spins "Analyzing your data… / Still working" past 60 s with no error | none | shot ASK-04. Minor: suggestion chips bypass the paused state and hang instead of failing fast |
| ASK-06 | blocked | No LLM: input disabled, could not send | none |  |
| DASH-01 | pass | /reports lists 12 seeded dashboards by name (Demo — Sales Overview, World Sales Map, Use case — …, UX Showcase…), folders, filters | none |  |
| DASH-03 | pass | Demo — Sales Overview opens /reports/1; widgets load (KPIs $8,632,597 / 402,108 / 19.0%, Revenue by region bars, Monthly revenue line) | none | shots DASH-03, DASH-03b. Visual: small tiles clip content (Revenue against target gauge value cut off, "Revenue, cost and units" 2nd value cut, "Average margin % by product" squashed to unreadable); tile hover toolbars (eye/expand/image) float over neighbouring tile titles |
| DASH-04 | fail | "New dashboard" now opens a "Create a dashboard" dialog (Blank/Template/With AI, Dashboard name, Dataset, Folder) but Create is enabled with an empty name and creates "Untitled dashboard" (/reports/13) — no name-required message | none | shots DASH-04a, DASH-04. Stray dashboard renamed "QA Untitled leftover" |
| DASH-05 | pass | Dialog: name "QA Dashboard 01", Dataset Demo — Sales, Create -> /reports/15?edit=1, empty editable canvas "Design this page", Demo — Sales attached | none | list card checked below |
| BUILD-01 | pass | Empty canvas "Design this page", left panel Insert/Fields/Templates with fields, right Properties panel, Edit mode active | none | shot BUILD-01 |
| BUILD-02 | pass | Insert > Bar adds "Bar Chart" with sample/"Needs Dimension"; clicking field region then revenue binds Dimension=region, Measure=revenue; 4 bars render (2.22M, 2.2M, 2.2M, 2.01M) | none | shots BUILD-02b, BUILD-02. Title editable via Format > Widget title |
| BUILD-03 | pass | Insert > KPI + revenue -> "$ 8,632,597 revenue" (Sum); renamed to "QA Total revenue" | none | shot BUILD-03 |
| BUILD-04 | pass | Clicked Europe bar on Demo — Sales Overview: chip "region = Europe", tiles show "1 filter", Total revenue $2,199,377, Units 101,764, Region slicer only Europe; Reset filters restores $8,632,597 | none | shot BUILD-04. Cosmetic: selected bar's value label is white on light green (unreadable) |
| BUILD-06 | pass | Layout menu lists Executive (default), KPI board, 2×2, Split, Spotlight, Comparison, Detail, Three-up, Free layout; Executive put KPI on top full width, bar below; no overlap, no big empty band | none | shot BUILD-06 |
| BUILD-07 | pass | `drag` KPI handle onto Bar chart: they swapped (Bar on top, KPI below), both kept usable size | none | shot BUILD-07 |
| BUILD-08 | pass | `drag` Bar chart resize handle to top-left: stops at col 1–4 × row 1–4 (~230×245 px); bars and axis still visible | none | shot BUILD-08. Cosmetic: value labels thin out to 2 of 4 at that size |
| BUILD-10 | blocked | No LLM: page copilot ("Ask AI · QA Dashboard 01 · Page 1") opens with suggestions, but input + send are disabled: "The model server isn't reachable, so new questions are paused." Clean state, no crash | none | shot BUILD-10 |
| BUILD-11 | blocked | No LLM: same disabled copilot input | none |  |
| MAP-01 | pass | Shipping routes tile: full world (Americas to Australia/Japan), route arcs visible, Asia not cut off | none | shot MAP-01 |
| MAP-02 | fail | Origin density: bubbles fully inside the tile, but each bubble prints two overlapping numbers (bold cluster count over a faint second value, e.g. "34" over "37", "1" over "31", "2" over "28"), so the counts are hard to read | none | shots MAP-02, MAP-02-zoom (same after waiting 4 s, not an animation) |
| MAP-03 | pass | Routes as a network: London, Tokyo, Sydney, Los Angeles (plus Frankfurt, New York, Dubai, Singapore, Sao Paulo, Johannesburg) labels fully inside tile | none | shot MAP-03. Minor: "Sao Paulo"/"Johannesburg" labels sit on the edges |
| MAP-04 | pass | Edit mode: `drag` of Shipping routes resize handle to half width -> tile became col 1–7, map refit to the smaller tile with whole world visible, no clipping; undo restored the seeded size | none | shots MAP-04b, MAP-04d. A "This report was changed in another session — Reload" banner appeared (other testers on the same seeded report) |
| INS-01 | pass | /insights: Dataset picker lists 6 datasets; picking Demo — Sales shows "Scanning for insights…" then TOP INSIGHTS (outliers in margin_pct/profit, units 2025-01 spike) with histograms | none | shot INS-01 (scan took ~15 s under load) |
| CONN-01 | pass | /connections lists "Demo — Live SQLite" (SQLite) and another tester's "QA B Nile Express" (PostgreSQL, Connected) with Test/Browse/Query builder actions; Imports section | none |  |
| CONN-02 | pass | New connection > PostgreSQL > Next > Create connection with empty fields: "Connection name is required", "Host is required", "Database is required"; drawer stays open; toast "Fill in Connection name, Host, Database first" | none | shot CONN-02. Cosmetic: the toast overlaps the Create/Test/Cancel buttons at the bottom of the drawer |
| LIN-01 | pass | Graph: Sources (3) -> Datasets (10) -> Reports (21) columns with edges (extract/reads); Graph/List toggle, filters, Export as PNG | none | shot LIN-01. Cosmetic: opens at 53% zoom so node labels are ~7 px and unreadable without zooming |
| SEC-01 | pass | GLOBAL on "Use case — Regional performance review" (/reports/8, View only): 4 regions, Revenue $8,632,597, Margin % by region (cost-based) 10.94/10.55/10.08/8.21 for Europe/APAC/NA/LatAm | none | shot SEC-01 |
| SEC-03 | blocked | No LLM: Ask AI input disabled for EMEA too ("model server isn't reachable") | none |  |
| ADM-01 | pass | /admin/users lists admin@datalytics.local (Platform Admin), admin@example.invalid, demo-emea, demo-global (+ another tester's qa.f.reader) | none | Contoso/Northwind accounts not listed here (other orgs) — expected |
| ADM-02 | pass | New User > Create empty: "Email is required" toast; with email only: "Password is required for a new user"; nothing created | none | shot ADM-02. Minor: errors are toasts only, no inline field highlighting |
| SHARE-01 | pass | Share "QA Dashboard 01" dialog (People / Publishing / Embed / Schedule): link http://127.0.0.1:3001/reports/15?page=31 shown with Copy link. Copy link showed toast "Couldn't copy the link" — expected in headless Chromium without clipboard permission, so copy not verifiable here | none | shot SHARE-01. Guest links: "Links that open without signing in are switched off for this platform" |
| SHARE-02 | blocked | No guest/share token can be created: platform has sign-in-free links switched off ("Share it with named people, a role or a team instead"). Not changing the platform setting (shared env) | none |  |
| MOB-01 | pass | 390×844: login form fits, Sign In button full width (308×44 px, tappable), signed in to / | none | no screenshot (time) |
| MOB-02 | pass | 390×844: "Open navigation" opens the drawer; tapping Dashboards goes to /reports and the drawer closes; reopened drawer closes on Escape | none | no screenshot (time) |
| MOB-03 | pass | 390×844, Demo — World Sales Map: widgets stack one per row and the canvas scrolls; the choropleth shows the whole world with nothing clipped. Minor: the toolbar overflows to the right ("Subscr…" cut off), and the floating AI button covers the corner of the map | none | shot MOB-03 |

---

### Failures in detail

#### DASH-04
- **Page:** /reports → New dashboard
- **Account:** ADMIN
- **Steps:** Click "New dashboard"; leave "Dashboard name" empty (placeholder "Untitled dashboard"); click Create.
- **Expected:** Create disabled, or a "name is required" message.
- **Actual:** Create is enabled; "Untitled dashboard" is created (/reports/13?pick=data) and the data picker opens.
- **Screenshot:** QA/shots/[DASH-04a](screenshots/QA/DASH-04a.png), QA/shots/[DASH-04](screenshots/QA/DASH-04.png)
- **Console:** none
- **Network:** no failed requests

#### SEC-02
- **Page:** Use case — Regional performance review (/reports/8)
- **Account:** EMEA demo-emea@example.invalid
- **Steps:** Log in as EMEA and open the report.
- **Expected:** Europe only, `cost` removed cleanly, totals smaller than for GLOBAL.
- **Actual:** Europe only and smaller totals ($2,199,377 vs $8,632,597), which is correct. But the "Margin % by region" tile shows "Unknown column or function in measure expression: name 'cost' is not defined".
- **Screenshot:** QA/shots/[SEC-02](screenshots/QA/SEC-02.png) (GLOBAL for contrast: QA/shots/[SEC-01](screenshots/QA/SEC-01.png))
- **Console:** 404 GET /api/v1/datasets/1/analysis
- **Network:** as above

#### INS-02
- **Page:** /insights → View full scan
- **Account:** ADMIN
- **Steps:** Pick Demo — Sales, wait for Top insights, click "View full scan →".
- **Expected:** The dataset page's Insights section with the longer list.
- **Actual:** /datasets/1#insights opens on the Analysis tab with "What stands out? Insights" selected, but the panel is empty except for "Generate insights".
- **Screenshot:** QA/shots/[INS-02](screenshots/QA/INS-02.png)
- **Console:** none
- **Network:** no failed requests

#### MAP-02
- **Page:** Demo — World Sales Map (/reports/5), tile "Origin density"
- **Account:** ADMIN
- **Steps:** Scroll to Origin density and wait.
- **Expected:** Bubbles inside the tile, counts readable.
- **Actual:** The bubbles are inside the tile, but each one shows two overlapping numbers (a bold count over a faint second value), so the counts are hard to read.
- **Screenshot:** QA/shots/[MAP-02](screenshots/QA/MAP-02.png), QA/shots/[MAP-02-zoom](screenshots/QA/MAP-02-zoom.png)
- **Console:** none
- **Network:** no failed requests

---

### Sign-off

- Short run (auth → maps → RLS → mobile) complete? yes
- Full plan complete? no — high cases only, all 57 run
- Safe to demo to a user? With caveats: avoid the EMEA view of the Regional performance review, the "View full scan" link and the Origin density labels.


---

## A — Shell, authentication, home & global UI
Coverage: ~45 distinct screens/states / 80+ screenshots. Accounts: admin@datalytics.local, analyst@contoso.invalid, demo-emea@example.invalid (blank capture). Viewports: 1440×900, 820×1180, 390×844. Note: machine heavily loaded (30–60 s per command).

### A-01 — Login page (`/login`)
- Screenshot: [A-01-login](screenshots/A_shell/A-01-login.png)
- What it shows: split layout, form left (Email, Password with eye toggle, Sign In, OR, Sign in with SSO, "ask your workspace admin"), illustration right; EN switcher + dark-mode toggle top.
- Works: ✅
- Issues: [Low] 401 GET /api/v1/auth/me logged as console error twice on load
- Console: 2× 401 /auth/me
- Score: 5

### A-02 — Login, empty submit
- Screenshot: [A-02-login-empty](screenshots/A_shell/A-02-login-empty.png)
- Works: ✅ inline errors "Enter your email address." / "Enter your password." red borders, no request sent.
- Issues: None
- Score: 5

### A-03 — Login, invalid email
- Screenshot: [A-03-login-invalid-email](screenshots/A_shell/A-03-login-invalid-email.png)
- Works: ✅ "Enter a full email address, like name@company.com."
- Issues: None
- Score: 5

### A-04 / A-05 — Wrong password / unknown user
- Screenshots: [A-04-login-wrong-password](screenshots/A_shell/A-04-login-wrong-password.png), [A-05-login-unknown-user](screenshots/A_shell/A-05-login-unknown-user.png)
- Works: ✅ identical banner "That email and password don't match. Check them and try again." for both (no account enumeration); password field focused and selected for retry.
- Issues: [Cosmetic] the decorative "Revenue" number on the right panel changes between renders (2,480,000 → 2,291,463) — animated, fine, but noticeable.
- Console: 401 POST /auth/login (expected)
- Score: 5

### A-06 — Sign in with SSO (no email / no IdP)
- Screenshot: (capture timed out under load; text verified)
- Works: ✅ with email filled it shows "No single sign-on is configured for that email"; with empty email asks for email first.
- Issues: None
- Score: 4

### A-07 — /sso/callback with no params (`/sso/callback`)
- Screenshot: [A-07-sso-callback-noparams](screenshots/A_shell/A-07-sso-callback-noparams.png)
- What it shows: blank white page (the "Signing in…" text did not render in the capture), then replace('/') → /login with no message.
- Works: ⚠️
- Issues: [Low] Failed/empty SSO round-trip silently lands on the plain login page; [Low] blank white flash during the hop.
- Score: 2

### A-08 — Deep link while logged out (`/reports/1`, `/datasets`, `/reports`)
- Screenshots: [A-08-deeplink-after-login](screenshots/A_shell/A-08-deeplink-after-login.png) (login form), [A-08-deeplink-lands-home](screenshots/A_shell/A-08-deeplink-lands-home.png), [A-08b-protected-loading](screenshots/A_shell/A-08b-protected-loading.png)
- Works: ❌ after signing in you land on `/`, not the requested page. Code: ProtectedRoute still `<Navigate to="/login" replace />` without `state.from`; Login does `window.location.replace('/')`.
- Issues: [Medium] Deep-link target lost after login. [Medium] Protected routes show bare "Loading…" text top-left on an empty page during auth bootstrap.
- Console: 2× 401 /auth/me
- Score: 2

### A-09 — Home, admin (`/`)
- Screenshots: [A-09-home](screenshots/A_shell/A-09-home.png), [A-09b-home-full](screenshots/A_shell/A-09b-home-full.png), [A-10-home-dashboards-section](screenshots/A_shell/A-10-home-dashboards-section.png), A-11/A-12-home-datasets-section
- What it shows: date + "Good evening, Admin", ask box disabled ("The AI is offline right now" / red "New questions are paused while the model server is unreachable"), 4 stat cards (Dashboards 21 "0 published · 11 draf…", Datasets 8 / 14,910 rows, Connections 2 PostgreSQL · SQLite, Last data update 11 minutes ago "Scheduled refreshe…"), 4 quick actions, "Continue setting up" (guided-setup resume row with Continue), "Continue where you left off" (4 thumbnails), Dashboards (21) with All/Mine tabs + Recent/Name sort + grid/list toggle, Recent activity, Refresh & jobs empty state, Datasets (8) table with row hover actions (Preview / Build a dashboard / Ask AI).
- Works: ✅ polished redesign; AI-offline state is clear and honest.
- Issues:
  - [Low] Stat-card subtitles truncated with ellipsis at 1440 px: "0 published · 11 draf…", "Scheduled refreshe…".
  - [Low] Stat says "0 published" while a card in the grid shows the "Everyone" badge (Demo — World Sales Map, shared by F) — terminology mismatch between "published" and shared-to-Everyone.
  - [Low] Brief asked for All/Mine/Recent tabs: only All/Mine exist; "Recent" is a sort dropdown (Recent / Name A–Z) — fine, but the sort button label shows the current value without a "Sort:" prefix.
  - [Cosmetic] Datasets "Freshness" shows grey dot "Uploaded" for files — not really a freshness value.
- Console: none
- Score: 4

### A-13/A-14 — Home Dashboards tabs & sort
- Screenshots: [A-13-home-dash-mine](screenshots/A_shell/A-13-home-dash-mine.png), [A-14-home-dash-sort](screenshots/A_shell/A-14-home-dash-sort.png)
- Works: ✅ Mine filters to own dashboards; sort menu Recent / Name (A–Z).
- Issues: None
- Score: 4

### A-15 — Home dashboard card ⋯ menu
- Screenshot: [A-15-home-card-menu](screenshots/A_shell/A-15-home-card-menu.png)
- What it shows: hover reveals Open + share icon + ⋯; menu: Rename, Copy link, Export as PDF, Delete (red).
- Works: ✅ (not executed Delete on seeded content)
- Issues: [Cosmetic] the hover overlay covers the card title ("QA Dashb…") while the menu is open.
- Score: 4

### A-16 — Account menu
- Screenshot: [A-16-account-menu](screenshots/A_shell/A-16-account-menu.png)
- What it shows: email, "Platform Admin · Default Organization", Always show details, My profile, Log out.
- Works: ✅ — Profile now exists.
- Issues: [Low] no change-password / preferences entry ("ask your workspace admin" only).
- Score: 4

### A-17/A-18 — My profile + About you (`/profile`)
- Screenshots: [A-17-profile](screenshots/A_shell/A-17-profile.png), [A-18a-profile-typed](screenshots/A_shell/A-18a-profile-typed.png), [A-18-profile-saved](screenshots/A_shell/A-18-profile-saved.png)
- What it shows: read-only Email/Role/Organization ("set by an administrator"), collapsible "About you — nothing saved yet" textarea, Save (disabled until changed), help text.
- Works: ✅ typed "QA A: I am a QA tester checking revenue and delivery KPIs weekly.", Save → header changes to "About you — saved on your profile"; persists after reload.
- Issues: [Low] No toast/confirmation besides the small grey header suffix; [Low] Save button stays very faint (disabled styling) right after saving, easy to miss state; [Cosmetic] page uses only ~55% width, a lot of empty space.
- Console: none
- Score: 4

### A-19 — Top-bar AI model picker ("Default")
- Screenshot: [A-19-model-picker](screenshots/A_shell/A-19-model-picker.png)
- What it shows: red dot status; popover: "What does this change?" disclosure, Auto ("No model is reachable"), Default ✓ DEFAULT "ConnectTimeout", Check again, Manage models link, "Your choice applies to your own AI requests on this browser."
- Works: ✅
- Issues: [Low] Raw exception name "ConnectTimeout" shown to users — humanize ("Model server not responding"). [Low] No explicit "AI off" option visible though the guide says "Turn AI off (the model picker in the top bar)".
- Score: 3

### A-20 — Notifications bell
- Screenshot: [A-20-notifications](screenshots/A_shell/A-20-notifications.png)
- Works: ⚠️ empty state "Nothing yet — alerts, delivery problems and comments land here."
- Issues: [Medium] The panel does not close on Escape, and stays open over the page even after opening the command palette and navigating to a dashboard (see A-22, A-23).
- Score: 3

### A-21/A-22 — Command palette (Ctrl K)
- Screenshots: [A-21-command-palette](screenshots/A_shell/A-21-command-palette.png), [A-22-palette-search](screenshots/A_shell/A-22-palette-search.png)
- Works: ✅ Ctrl K opens; "demo" groups Dashboards / Datasets with type tags, keyboard hint footer.
- Issues: None (besides bell overlay above)
- Score: 5

### A-23 — Open dashboard from palette (`/reports/1`)
- Screenshot: [A-23-palette-open-dashboard](screenshots/A_shell/A-23-palette-open-dashboard.png)
- Works: ✅ opens in VIEW mode with "Edit" button, footer "Saved".
- Issues: [Low] Every widget shows its floating hover toolbar (eye/expand/image) at once, overlapping widget titles/values (e.g. "Units sold" second KPI value hidden, gauge value cut "8,632,597"); [Medium] notifications panel still open over it.
- Score: 3

### A-24..A-27 — Left rail: groups, Admin expanded, collapse «
- Screenshots: [A-24-rail-admin-expanded](screenshots/A_shell/A-24-rail-admin-expanded.png), [A-25-rail-admin-scrolled](screenshots/A_shell/A-25-rail-admin-scrolled.png), [A-26-rail-groups-collapsed](screenshots/A_shell/A-26-rail-groups-collapsed.png), [A-27-rail-collapsed](screenshots/A_shell/A-27-rail-collapsed.png), [A-27b-rail-collapsed-hover](screenshots/A_shell/A-27b-rail-collapsed-hover.png)
- What it shows: groups DATA(4) / DATA SOURCES(2) / ANALYSE(6) / MONITORING(3) / ADMIN(13) / PLATFORM(2); collapsed groups show count badges + chevron; « collapses to an icon rail with group dividers; "Right to left" pinned at the bottom.
- Works: ✅ each group toggles; ADMIN collapsed by default; icon rail keeps active highlight.
- Issues: [Low] Rail header (logo + «) still scrolls away when the nav is scrolled with ADMIN expanded (A-25: top of rail starts at "Templates"). [Low] Collapsed icon rail has no visible tooltip on hover in the capture (A-27b) — icons only, no labels; titles rely on aria-label.
- Score: 4

### A-28..A-58 — First view of every rail destination (31 routes)
- Screenshots: [A-28-dest-ask](screenshots/A_shell/A-28-dest-ask.png) … [A-40-dest-migration](screenshots/A_shell/A-40-dest-migration.png), [A-41-dest-monitoring-jobs](screenshots/A_shell/A-41-dest-monitoring-jobs.png) … [A-58-dest-platform-settings](screenshots/A_shell/A-58-dest-platform-settings.png)
- Works: ✅ all 31 routes render with correct breadcrumb (Section › Page) and active rail item; zero console errors / failed API calls.
- Observations:
  - Ask AI (A-28): Step 1 "Choose your data" picker + History panel; ask box disabled "Complete step 1 first". Good.
  - Datasets (A-29): summary bar, filters, side preview. Lineage graph, Glossary (connection picker, "No terms yet"), Dataflows, Upload (3-step), Connections (2 incl. "Continue setup · step 1 of 4"), Dashboards (views/folders), My dashboards (tabs All/Made by me/Shared with me/My team/Favourites/Recently opened/Reports sent), Templates gallery, Insights, Automations, Migration — all consistent.
  - Admin/Platform pages (A-44..A-58) consistent cards/tables.
- Issues:
  - [Low] Dataflows/Insights/Automations/Migration use native `<select>` and native "Choose Files" input (A-32, A-38, A-40) — visually inconsistent with the custom selects elsewhere.
  - [Low] Platform settings exposes the internal LLM endpoint address `http://10.125.18.189:8000/v1` and model name — fine for super admin, but Admin › Settings (A-44) also renders the Platform section to the same user, duplicating Platform settings.
  - [Cosmetic] Migration (A-40) page uses ~50% width; most of the canvas empty.
  - [Low] Calendar (A-55): "Save" button enabled-looking but faint/disabled with no hint why.
- Console: none
- Score: 4

### A-59/A-60 — Arabic (Home, Datasets)
- Screenshots: [A-59-home-arabic](screenshots/A_shell/A-59-home-arabic.png), [A-60-datasets-arabic](screenshots/A_shell/A-60-datasets-arabic.png)
- Works: ✅ full RTL mirroring, rail on the right, translated greeting "مساء الخير، Admin", stats, quick actions, Datasets table and filters translated.
- Issues:
  - [Low] Digits remain Western in tables/KPIs (11, 146,093, 64,420).
  - [Low] Mixed-direction truncation: source column "...nts من مبنية", "...eSQL · مباشر" — English segments clipped at the wrong end.
  - [Low] Dataset descriptions stay English (user content, acceptable).
  - [Cosmetic] stat subtitle "...11 مسودة · 0 منشورة" truncated.
- Console: none
- Score: 4

### A-61 — "Right to left" toggle in English
- Screenshots: [A-61-rtl-english](screenshots/A_shell/A-61-rtl-english.png), [A-61b-ltr-restored](screenshots/A_shell/A-61b-ltr-restored.png)
- Works: ✅ mirrors layout; toggles back.
- Issues: [Low] In English RTL, punctuation is bidi-reordered: "Admin ,Good evening", "minutes ago 3", "rows 146,093", "...Search" — expected for forced RTL on English text, but looks broken; consider `dir="auto"` on text nodes or hide this toggle for LTR languages. [Low] After toggling, the rail scroll position jumps (rail starts at "Templates").
- Score: 3

### A-62..A-64 — Dark mode (Home, Datasets, Dashboard)
- Screenshots: [A-62-home-dark](screenshots/A_shell/A-62-home-dark.png), [A-63-dataset-dark](screenshots/A_shell/A-63-dataset-dark.png), [A-64-dashboard-dark](screenshots/A_shell/A-64-dashboard-dark.png)
- Works: ✅ good contrast, consistent tokens; charts adapt.
- Issues: [Low] Dashboard "Live embed" widget is a bright white box in dark mode (A-64). [Cosmetic] Divider widget navy box fine. Same overlapping widget hover toolbars as A-23.
- Score: 4

### A-65 — 404 (`/no-such-page`)
- Screenshot: [A-65-404](screenshots/A_shell/A-65-404.png)
- Works: ✅ "This page does not exist — Nothing lives at /no-such-page." + Home / Datasets / Dashboards buttons.
- Issues: [Low] Top-bar breadcrumb says "Home" on the 404 page (should say "Page not found").
- Score: 4

### A-66 — /embed with no params
- Screenshot: [A-66-embed-noparams](screenshots/A_shell/A-66-embed-noparams.png)
- Works: ⚠️ centered grey line "This embed link is missing its token." on blank page.
- Issues: [Cosmetic] No icon/branding/help; acceptable for an embed context.
- Score: 3

### A-67 — Home quick actions & Continue setting up
- Screenshot: [A-67-home-continue-setup](screenshots/A_shell/A-67-home-continue-setup.png)
- Works: ✅ New dashboard → /reports (list, not a blank canvas as the subtitle "Start from a blank canvas" promises); Upload data → /upload; New connection → /connections (list, not the new-connection form); Ask AI → /ask; Continue → /setup/2.
- Issues: [Low] "New dashboard — Start from a blank canvas" lands on the Dashboards list instead of creating/opening a blank dashboard; "New connection — Connect a database" lands on the list instead of the add dialog. One extra click each and mismatched promise.
- Score: 3

### A-68..A-72 — Phone 390×844 (home, drawer, datasets, dashboard, account menu)
- Screenshots: [A-68-phone-home](screenshots/A_shell/A-68-phone-home.png), [A-69-phone-drawer](screenshots/A_shell/A-69-phone-drawer.png), [A-70-phone-datasets](screenshots/A_shell/A-70-phone-datasets.png), [A-71-phone-dashboard](screenshots/A_shell/A-71-phone-dashboard.png), [A-72-phone-account-menu](screenshots/A_shell/A-72-phone-account-menu.png)
- Works: ✅ hamburger drawer with scrim; top bar compacts to icons; breadcrumb hidden; dashboard stacks widgets one per row; Edit not visible but toolbar scrolls.
- Issues:
  - [Medium] Home stat cards stay 4-across at 390 px: labels clipped ("Dashboar", "Connectio"), values wrap ("5 / minutes / ago"), subtitles "0 publi…", "Sched…". Should be 2×2.
  - [Low] Ask box placeholder truncated "The AI is offline right".
  - [Low] Quick-action subtitles truncated ("Start from a blank…", "Ask in plain…").
  - [Low] Dashboard toolbar overflows (Subscribe cut "Subsci", Edit off-screen) and filter bar "No filters app" clipped (A-71).
  - [Low] Datasets table on phone shows only Name + truncated Source; Rows/Freshness off-screen, horizontal scroll inside card.
- Score: 3

### A-73..A-77 — Tablet 820×1180
- Screenshots: [A-73-tablet-home](screenshots/A_shell/A-73-tablet-home.png), [A-74-tablet-drawer](screenshots/A_shell/A-74-tablet-drawer.png), [A-75-tablet-datasets](screenshots/A_shell/A-75-tablet-datasets.png), [A-76-tablet-dashboard](screenshots/A_shell/A-76-tablet-dashboard.png), [A-77-tablet-account-menu](screenshots/A_shell/A-77-tablet-account-menu.png)
- Works: ✅ rail becomes drawer; Home 4 stat cards in a row fit; datasets table fits with preview panel hidden; dashboard view shows 4-column grid.
- Issues: [Low] Dashboard view at tablet: KPI titles truncated ("Revenue agains", "Average margi", "Revenue, cost a") and widget hover toolbars overlap the numbers ("8,632,597" hidden in gauge). - Score: 4

### A-78/A-79 — Logout and login at tablet/phone
- Screenshots: [A-78-tablet-login-after-logout](screenshots/A_shell/A-78-tablet-login-after-logout.png), [A-79-phone-login](screenshots/A_shell/A-79-phone-login.png)
- Works: ✅ Log out → /login; login layout stacks illustration above form on narrow screens.
- Issues: [Low] On phone, the decorative illustration takes the first ~180 px before the form; consider hiding it < 600px.
- Score: 4

### A-80..A-82 — Keyboard / a11y spot checks
- Screenshots: [A-80-login-tab-focus](screenshots/A_shell/A-80-login-tab-focus.png), [A-82-after-skip-focus](screenshots/A_shell/A-82-after-skip-focus.png) (A-81 skip-link capture came out blank under load and was removed)
- Works: ✅ login Tab order is Language → Dark-mode toggle → Email → Password → Show password → Sign In → SSO; focus ring is clearly visible (2px green outline, A-80). App shell has a "Skip to content" link as the first focusable element (seen in the page text and button list on every app page).
- Issues: [Low] On login the first two Tab stops are the language and theme toggles, before Email. The Email field has no autofocus. [Low] I could not visually confirm the skip link's focus styling because of load (the capture was blank).
- Score: 4

### A-83 — Home, empty org (analyst@contoso.invalid)
- Screenshot: [A-83-home-contoso-analyst-empty](screenshots/A_shell/A-83-home-contoso-analyst-empty.png)
- What it shows: "Welcome to Datalytics, Analyst" with "Your workspace is ready. Three steps to your first insight."; ask box "Connect data first to ask questions"; stats at 0 with "None yet"; a GET STARTED "Set up your workspace" checklist (0 of 3 complete) with 1 Connect data (Upload data / New connection buttons), 2 Build a dashboard, 3 Ask AI, plus an illustration; then an empty "Continue where you left off" state.
- Works: ✅ This is a very good onboarding experience. - Issues: None seen.
- Score: 5

### A-84 — Home, demo-emea@example.invalid
- Screenshot: [A-84-home-demo-emea](screenshots/A_shell/A-84-home-demo-emea.png) (blank: the capture timed out under heavy machine load at 20:04)
- Works: not verified. Login succeeded (URL `/`), but the page had not rendered when the time box ended.
- Score: n/a

### Area summary
- Score (avg): about 3.8 / 5.
The redesigned Home has good stats, quick actions, guided-setup resume, dashboard tabs and card menus, and a first-class empty-org onboarding checklist. Profile with "About you" saves and persists. The model picker is honest about the offline AI. The command palette, dark mode and Arabic RTL all work well. All 31 rail destinations render with correct breadcrumbs and no console errors. The remaining issues are mostly carry-overs: the deep-link return after login, the bare "Loading…" during the auth bootstrap, the silent SSO failure, the rail header scrolling away, and Arabic digits. The new issues are minor UI ones: the notifications popover won't close, Home stat cards are cramped on phone, the quick actions don't do what their subtitles promise, the dashboard view's hover toolbars overlap values, and a raw "ConnectTimeout" is shown in the model picker. The environment was extremely slow (load average about 10, 30–60 s per command), which cost coverage.

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| A-08 | Medium | Login after deep link | Requested URL is lost; always lands on Home | Pass `state.from` from ProtectedRoute and navigate there after login (same-origin path only) |
| A-20 | Medium | Notifications bell | Popover ignores Escape and stays open across Ctrl K and route changes | Close on Escape, outside click and route change |
| A-68 | Medium | Home on phone | 4 stat cards side by side at 390 px; labels and values clipped or wrapped | 2×2 grid under 600 px |
| A-08b | Medium | Protected routes | Bare "Loading…" text during the auth bootstrap | Branded spinner or app-shell skeleton |
| A-23 | Low | Dashboard view | Every widget's hover toolbar is visible at once and overlaps titles and values (also at tablet) | Show the toolbar only on hover or focus of that widget |
| A-67 | Low | Home quick actions | "New dashboard — Start from a blank canvas" and "New connection" open lists, not the create flows | Deep-link to the create dialog or a blank dashboard |
| A-19 | Low | Model picker | Raw exception "ConnectTimeout"; no visible "AI off" option although the guide mentions one | Humanize the error; add an explicit Off choice or explain where it is |
| A-07 | Low | /sso/callback | Blank page, then a silent login page | Show "Single sign-on did not complete" |
| A-25 | Low | Rail | Header scrolls away with long nav | Sticky header and footer |
| A-59 | Low | Arabic | Western digits; mixed-direction truncation | Shared number formatter; `<bdi>`/`dir=auto` on names |
| A-65 | Low | 404 | Breadcrumb says "Home" | Show "Page not found" |
| A-09 | Low | Home stats | Subtitles truncated at 1440 ("0 published · 11 draf…"); "0 published" while a card is shared to Everyone | Allow wrapping; align the published/shared terms |

- Strengths:
  - Clear, non-enumerating login errors and good inline validation; visible focus ring.
  - Redesigned Home with guided-setup resume and a strong empty-org onboarding.
  - Profile "About you" is simple and persists.
  - The AI-offline state is communicated everywhere (Home ask box, model picker).
  - Command palette with grouped results and keyboard hints; Ctrl K works.
  - Arabic and RTL mirroring is thorough; dark mode is consistent.
  - The 404 page has useful exits; all routes have breadcrumbs; zero console errors inside the app.
- Not covered / blocked:
  - demo-emea Home: the capture was blank under load at the time box.
  - Skip-link focus visual: the capture was blank.
  - Home card ⋯ actions Rename, Copy link, Export PDF and Delete were not executed (seeded content).
  - The quota validation part of - The A-06 SSO screenshot timed out (text verified).
  - The machine load (pytest + 4 Chromiums) caused many 30 s navigation timeouts.


---

## B — Data: datasets, glossary, upload, connections, dataflows, lineage, migration
Coverage: ~40 screens / 152 screenshots (B-01 … B-152). Account: admin@datalytics.local. Viewports 1440x900 and 390x844. Environment was heavily loaded (load avg ~10 on 2 CPUs); first driver calls timed out until a new page was opened.
Note: environment was heavily loaded (load avg ~10 on 2 CPUs); first driver commands timed out / "Not attached to an active page" until a newpage.

### B-01 — Datasets list   (`/datasets`)
- Screenshot: [B-01-datasets-list](screenshots/B_data/B-01-datasets-list.png)
- What it shows: summary strip (6 datasets, 5 uploaded / 1 live, 14,900 rows, 278.2 KB), filters (Source, Status, Sensitivity label, Mine only, Certified only), sort dropdown, table + right preview panel with columns and first rows.
- Works: ✅ list renders; preview panel updates on row click.
- Issues: [Low] No text search box on the list (only 6 items; no search box visible). [Cosmetic] Freshness truncated "Uploaded 9 minute…" in a wide table with spare space in Dashboards column.
- UX notes: Preview panel is a good addition. Sort is a dropdown (Recently updated / Name / Most rows), headers are not clickable.
- Console: 401 /auth/me during login only (pre-login, expected)
- Score: 4

### B-02 — Row menu on last row   (`/datasets`)
- Screenshot: [B-02-row-menu-last](screenshots/B_data/B-02-row-menu-last.png)
- What it shows: ⋯ menu with "Suggest dashboards" and "Delete dataset", opens downward below last row, fully visible.
- Works: ✅ Not clipped.
- Issues: [Low] no Rename in the row menu.
- Console: none
- Score: 4

### B-03/04/05 — Sort, Source filter, bulk select   (`/datasets`)
- Screenshots: [B-03-sort-menu](screenshots/B_data/B-03-sort-menu.png), [B-04-filter-live](screenshots/B_data/B-04-filter-live.png), [B-05-bulk-select](screenshots/B_data/B-05-bulk-select.png)
- Works: ✅ Source=Live shows 1 of 6; Sort Name re-orders alphabetically; selecting 2 rows shows a "2 datasets selected" bar with Delete selected / Clear selection; header checkbox shows indeterminate.
- Issues: [Cosmetic] after choosing a filter the native sort select shows a focus outline overlapping its own chevron (B-04 top-right).
- Console: none
- Score: 4

### B-06..09 — Demo — Sales › Overview   (`/datasets/1`)
- Screenshots: [B-06-sales-overview](screenshots/B_data/B-06-sales-overview.png), [B-07-sales-overview-lower](screenshots/B_data/B-07-sales-overview-lower.png), [B-08-sales-profiled](screenshots/B_data/B-08-sales-profiled.png), [B-09-sales-insights](screenshots/B_data/B-09-sales-insights.png)
- What it shows: header (Uploaded file, Not certified, sensitivity select, "AI: follow the default" select, Ask about this data, Use in Python, Share, ⋯, Build a dashboard), tabs Overview/Columns/Data/Analysis/Rules & alerts/Models; KPI tiles; "Ready to use" checklist (Fresh, Complete, Checks, Certified); Columns at a glance (needs "Profile the columns"); Used by (7 dashboards + 1 alert); Where it comes from mini-lineage; Insights; Recent activity.
- Works: ✅ Profile the columns fills the table with sparklines/top values. ⚠️ Generate insights shows "Scanning…" and stays (no LLM needed? still spinning after 4 s).
- Issues: [Medium] Console: GET /api/v1/datasets/1/analysis returns 404 four times on load (unhandled missing resource). [Cosmetic] KPI strip: "Models 1" tile wraps to its own second row leaving 3/4 of the row empty. [Low] Columns at a glance shows only 6 of 13 columns with no "show more" except the "All 13 columns" link.
- Console: 4x 404 GET /api/v1/datasets/1/analysis
- Score: 4

### B-10/11 — Demo — Sales › Columns   (`/datasets/1` Columns tab)
- Screenshots: [B-10-sales-columns](screenshots/B_data/B-10-sales-columns.png), [B-11-sales-columns-lower](screenshots/B_data/B-11-sales-columns-lower.png)
- What it shows: "What you should know about this data" (outliers in 4 columns; 51 rows negative revenue + "Leave those rows out" action), column search, type chips, "0 of 13 described", Ask AI again, Hidden columns, table with description, distribution, empty %, summary, "Use as" role select; Detailed statistics collapsible.
- Works: ✅ renders well; plain-language data warnings are a strong new feature.
- Issues: [Low] "year" detected as NUM (and NUM CAT on Overview) but "Use as: Dimension" — ok; target summary uses 574.53 – 16,786.32 while revenue uses "$" formatting — inconsistent currency formatting between similar money columns. [Cosmetic] "$ -12,012" — minus after currency symbol with space.
- Console: none
- Score: 4

### B-12..15 — Demo — Sales › Data grid + filters   (`/datasets/1` Data tab)
- Screenshots: [B-12-sales-data-grid](screenshots/B_data/B-12-sales-data-grid.png), [B-13-filter-panel](screenshots/B_data/B-13-filter-panel.png), [B-14-filter-applied](screenshots/B_data/B-14-filter-applied.png), [B-15-filter-removed](screenshots/B_data/B-15-filter-removed.png)
- What it shows: toolbar Filter / Row filter / ƒx Column / Group & bin / Measures / Steps, Search rows, Edit cells; grid with typed headers, sortable; paging 100 rows.
- Works: ✅ filter region == Europe → "Rows 1–100 of 514 (filtered from 2,000)" and a removable chip. ❌ Removing the filter with × leaves the panel saying "No filters" but the grid shows only Europe rows and footer still "of 514 (filtered from 2,000)".
- Issues: [High] removing the last filter does not reload the grid.
- Console: none
- Score: 3

### B-16/17 — Data › Edit cells   (`/datasets/1`)
- Screenshots: [B-16-edit-cells](screenshots/B_data/B-16-edit-cells.png), [B-17-edit-cell-active](screenshots/B_data/B-17-edit-cell-active.png)
- What it shows: "Editing cells" toggle, "Rows identified by [date]" key picker, explanation "Corrections are saved as a prep step… Every row sharing the key value is corrected."; clicking a cell opens an inline editor.
- Works: ⚠️ Inline editing works; key still defaults to `date` (non-unique: 633 distinct dates over 2,000 rows). The helper text now warns that every row sharing the key is corrected, but there is no "N rows will change" count and no unique-key default.
- Issues: [High] but still risky: default key is the non-unique `date`; a single edit silently rewrites every row with that date. Default should be a unique column or a row id.
- Console: none
- Score: 3

### B-18..22 — Data › Calculated columns, add "QA B calc"   (`/datasets/1`)
- Screenshots: [B-18-calc-column-dialog](screenshots/B_data/B-18-calc-column-dialog.png), [B-19-calc-add-form](screenshots/B_data/B-19-calc-add-form.png), [B-20-calc-formula-mode](screenshots/B_data/B-20-calc-formula-mode.png), [B-21-calc-test](screenshots/B_data/B-21-calc-test.png), [B-22-calc-saved](screenshots/B_data/B-22-calc-saved.png)
- What it shows: panel listing profit / days_month_to_date, Duplicate a column, Custom functions; "+ Add" opens a guided chooser (Calculate from two columns, Group numbers into bands, Label rows by conditions, Combine text, Part of a date, Clean text, Write a formula myself) with a format select; formula mode opens a full ƒx Expression Builder (attributes, functions, operators, Simple/Advanced).
- Works: ✅ Created "QA B calc" = revenue / units; Test then Save Column; appears in list and as a new grid column. Values are now rounded (71.96, 80.18, 62.38).
- Issues: [Low] Test result is not visibly shown in the builder after pressing ▶ Test (no preview row in view at 1440x900; footer stays the same). [Cosmetic] Edit/delete icons (✏ ×) on calc rows are tiny low-contrast glyphs.
- UX notes: the guided "what do you want to make" chooser is a big step up for non-technical users.
- Console: none
- Score: 4

### B-23/24 — Data › Group & bin, Measures   (`/datasets/1`)
- Screenshots: [B-23-group-bin](screenshots/B_data/B-23-group-bin.png), [B-24-measures](screenshots/B_data/B-24-measures.png)
- What it shows: Group & bin with source column picker and explanation; Measures list ("Margin % (on totals)" and "Margin %", identical formulas) with + Add measure.
- Works: ✅ panels open/close via toggle buttons.
- Issues: [Low] Two seeded measures have the same formula with different names (confusing demo content).
- Console: none
- Score: 4

### B-25..29 — Data › Steps (pipeline)   (`/datasets/1`)
- Screenshots: [B-25-steps-panel](screenshots/B_data/B-25-steps-panel.png), [B-26-add-step-menu](screenshots/B_data/B-26-add-step-menu.png), [B-27-add-step-after-esc](screenshots/B_data/B-27-add-step-after-esc.png), [B-28-add-step-after-outside](screenshots/B_data/B-28-add-step-after-outside.png), [B-29-step-filter-rows-form](screenshots/B_data/B-29-step-filter-rows-form.png)
- What it shows: PIPELINE empty state "No transform steps yet", "+ Add step" menu (Filter rows, Sort, Remove duplicates, Aggregate, Rename column, Change type, Split column, Trim whitespace, Change case). Filter rows step shows Simple/Advanced condition builder, row count 2,000→2,000, "Save as this dataset's view" and "Save as new dataset…", and a preview table.
- Works: ⚠️ Step form works. The Add step menu still cannot be dismissed with Esc or an outside click (B-28 identical to B-26); only choosing an item closes it.
- Issues: [Medium] (menu not dismissible). [Low] Step preview table wraps dates ("2024-\n06-17") and product names in narrow columns and shows raw unformatted numbers (3,382.2 vs grid's "$ 3,382"); preview clipped on the right (margi…) with no visible horizontal scroll hint. [Low] Step buttons "move up/move down/disable/delete" are tiny icon-only controls (↑ ↓ ● ×).
- Console: none
- Score: 3

### B-30/31 — Analysis tab   (`/datasets/1`)
- Screenshots: [B-30-sales-analysis](screenshots/B_data/B-30-sales-analysis.png), [B-31-analysis-insights](screenshots/B_data/B-31-analysis-insights.png)
- What it shows: left "What do you want to find out?" question list (26 analyses grouped Explain/Compare/Find patterns/Predict and plan/Read text); right: Key influencers for revenue (baseline, effect bars, small-group tags, skipped-column notes). Insights: summary + OUTLIER IMPACT / ANOMALY cards with histograms.
- Works: ✅ Key influencers ran instantly; Insights generated after a few seconds (no LLM needed).
- Issues: [Medium] Outlier/Anomaly cards now draw a histogram, but the second OUTLIER IMPACT card ("85 outlying rows move the average profit") still has an empty body (no chart) leaving a large blank tile. [Low] Overview's "Generate insights" button stayed "Scanning…" (B-09) while the Analysis › Insights version completed — inconsistent.
- Console: none
- Score: 4

### B-32..38 — Rules & alerts incl. NEW data checks   (`/datasets/1`)
- Screenshots: [B-32-sales-rules](screenshots/B_data/B-32-sales-rules.png), [B-33-add-rule-form](screenshots/B_data/B-33-add-rule-form.png), [B-34-check-allowed-values](screenshots/B_data/B-34-check-allowed-values.png), [B-35-check-added](screenshots/B_data/B-35-check-added.png), [B-36-check-run](screenshots/B_data/B-36-check-run.png), [B-37-quality-report](screenshots/B_data/B-37-quality-report.png), [B-38-quality-report-result](screenshots/B_data/B-38-quality-report-result.png)
- What it shows: data warnings, Quality rules (+ Rule → "Add a check": No blanks, Unique values, Only allowed values, Row count range, Rows must not fall sharply, A rule, Values exist in another dataset, Columns stay the same; If it fails: Keep the previous data / Only warn), Run now, one-off quality report, Alerts (seeded "Demo — margin below target"), Freshness.
- Works: ✅ Added "region is one of: Europe, Asia Pacific, North America, Latin America" (Warn); Run now → "Checked 2,000 rows · All pass" with green tick. One-off "Check data quality" → 2,000 × 13, 0% empty, 0 duplicates, 4 columns with outliers.
- Issues: [Low] The "Add a check" form gives no hint that allowed values are comma-separated beyond the placeholder "open, closed"; check name can't be set. [Low] Quality-report says revenue "84 outliers" while Columns tab says 51 negative revenue rows & Overview says outliers in revenue — different counting methods, unexplained. [Cosmetic] Overview "Checks: No saved checks yet" wording vs "Rules" tab name vs "+ Rule" button vs "Add a check" form title — four names for one concept.
- UX notes: Nice, clear new feature; the "Keep the previous data" (block) vs "Only warn" choice is well explained.
- Console: none
- Score: 4

### B-39..44 — Models, ⋯ menu, Share, Use in Python, Ask about this data   (`/datasets/1`, `/ask?dataset=1`)
- Screenshots: [B-39-sales-models](screenshots/B_data/B-39-sales-models.png), [B-40-more-actions-menu](screenshots/B_data/B-40-more-actions-menu.png), [B-41-share-dialog](screenshots/B_data/B-41-share-dialog.png), [B-42-use-in-python](screenshots/B_data/B-42-use-in-python.png), [B-43-ask-about-data](screenshots/B_data/B-43-ask-about-data.png), [B-44-ask-answer-no-llm](screenshots/B_data/B-44-ask-answer-no-llm.png)
- What it shows: Models: Train a model + seeded "Demo — Revenue model v1 Champion" (R² 0.342, random forest). ⋯ menu: Certify, Re-run analysis. Share dialog (Person/Role/Org unit, View/Edit, who can already open it). Python snippet modal. Ask about this data → /ask?dataset=1 with dataset preselected and 6 suggested questions; "The model server isn't reachable, so new questions are paused." input disabled.
- Works: ✅ all open. Ask handles no-LLM gracefully (clear red line, disabled input) — good.
- Issues: [Medium] Ask: after attempting to type and pressing Enter, the page reset to "Step 1 Choose your data" with the dataset de-selected (B-44) and the whole page got text-selected (Ctrl+A in disabled box selected the page) — the preselected dataset was lost. [Low] Python snippet: code line clipped at right edge ("# Settings → API keys;" cut) with no horizontal scroll indicator. [Low] Share dialog says "Anyone who can open its 9 dashboards" while Overview "Used by" lists 7 dashboards — inconsistent counts. [Low] Header "Ask about this data" link was hard to hit: first two clicks didn't navigate (needed a fresh load) — possibly overlay from the sensitivity select.
- Console: none
- Score: 4

### B-45..54 — Demo — Live Orders (DirectQuery) — all tabs   (`/datasets/6`)
- Screenshots: [B-45-dq-overview](screenshots/B_data/B-45-dq-overview.png), [B-46-dq-data](screenshots/B_data/B-46-dq-data.png), [B-47-dq-filter-panel](screenshots/B_data/B-47-dq-filter-panel.png), [B-48-dq-calc-panel](screenshots/B_data/B-48-dq-calc-panel.png), [B-49-dq-aggregates](screenshots/B_data/B-49-dq-aggregates.png), [B-50-dq-rules](screenshots/B_data/B-50-dq-rules.png), [B-51-dq-columns](screenshots/B_data/B-51-dq-columns.png), [B-52-dq-analysis](screenshots/B_data/B-52-dq-analysis.png), [B-53-dq-models](screenshots/B_data/B-53-dq-models.png), [B-54-dq-more-menu](screenshots/B_data/B-54-dq-more-menu.png)
- Differences vs import: badge "Live (DirectQuery)", "AI: follow the connection" + "AI: not allowed" text, extra Aggregates tab (GROUP BY at source, grain/measures), no Use in Python, no Steps button, no Edit cells; Size "—"; Freshness "Not applicable — queried live"; ⋯ menu Certify / Run analysis.
- Works: ✅ Data tab now shows an info bar "Showing the first 100 rows live from the source. Filtering, sorting, search, and calculated columns aren't supported yet for DirectQuery previews." Analysis (key influencers on quantity over 12,000 rows) works. Models explains 250k-row training cap.
- Issues: [Medium] the limitation is now explained, but Filter / Row filter / ƒx Column / Group & bin / Search rows / sort arrows are still enabled and open full editors (B-47, B-48) that do nothing. [Medium] Rows still reshuffle: page 1 first row was order 1615, after Next→Prev it is 9687 (no stable ORDER BY). [Medium] Rules & alerts for DirectQuery has no Quality rules / data checks section at all (only Alerts + Freshness) — the new data checks are unavailable for live datasets with no explanation. [Low] "AI: follow the connection" select next to bold "AI: not allowed" reads as contradictory.
- Console: none
- Score: 3

### B-55..60 — Other demo datasets (Metrics, Projects, Feedback, Routes)   (`/datasets/2..5`)
- Screenshots: [B-55-dataset-2-overview](screenshots/B_data/B-55-dataset-2-overview.png), [B-56-dataset-3-overview](screenshots/B_data/B-56-dataset-3-overview.png), [B-57-dataset-4-overview](screenshots/B_data/B-57-dataset-4-overview.png), [B-58-dataset-5-overview](screenshots/B_data/B-58-dataset-5-overview.png), [B-59-routes-data](screenshots/B_data/B-59-routes-data.png), [B-60-feedback-columns](screenshots/B_data/B-60-feedback-columns.png)
- What it shows: same 6-tab layout as Sales (Overview, Columns, Data, Analysis, Rules & alerts 0, Models); no Aggregates tab (import). Routes Data shows GEO-tagged lat/lon columns rounded sensibly (49.55, -0.701, 0.167). Feedback Columns tab warns "61 rows look the same as other rows… Remove the copies"; text columns show no distribution/summary.
- Works: ✅ All open; Routes coordinates are rounded.
- Issues: [Medium] Every dataset detail load fires GET /api/v1/datasets/{id}/analysis → 404 (twice per page). [Low] Feedback: text columns (comment/sentiment/topic) show empty Distribution and Summary cells — no top-values for TXT here though Sales shows them for TXT (because Sales was profiled). [Low] Routes: the lat/lon rounding is inconsistent (0.167 / -0.0516 / 9.1 — significant-digit rounding gives different dp per row).
- Console: 404 GET /api/v1/datasets/{2,3,4,5}/analysis
- Score: 4

### B-61..66 — NEW Glossary   (`/glossary`)
- Screenshots: [B-61-glossary-list](screenshots/B_data/B-61-glossary-list.png), [B-62-glossary-add-term](screenshots/B_data/B-62-glossary-add-term.png), [B-63-glossary-empty-save](screenshots/B_data/B-63-glossary-empty-save.png), [B-64-glossary-filled](screenshots/B_data/B-64-glossary-filled.png), [B-65-glossary-term-saved](screenshots/B_data/B-65-glossary-term-saved.png), [B-66-glossary-always-toggled](screenshots/B_data/B-66-glossary-always-toggled.png)
- What it shows: page intro, Connection selector (only "Demo — Live SQLite"), Business terms card with empty state; Add a term form: Term, What it means, Also called (comma separated, Arabic placeholder), Table (optional), Column (optional), Rule the AI must follow, "Apply to every question" checkbox.
- Works: ✅ Empty Save → "A term needs a name" (toast only). Created "QA B term" (aliases incl. Arabic "طلب كبير", maps to orders.amount, rule amount > 1000) → table row; Always checkbox toggles and persists after reload.
- Issues: [Medium] Glossary is scoped to connections only — uploaded datasets (e.g. Demo — Sales) cannot get terms, and there is no way to link a term to a dataset column from the dataset's Columns tab. [Low] Table/Column are free text, not pickers from the connection schema — typos are not validated (I typed orders.amount; nothing checked it exists). [Low] Empty-save validation only in a toast; field not highlighted. [Low] No edit for an existing term (only the inline rule box, Always checkbox and delete icon).
- UX notes: Clear purpose text. The page is wide-open with a lot of unused space below the single card.
- Console: none
- Score: 3

### B-67..79 — Upload: page, empty name, qa_sample.csv, qa_sample_2.csv, .txt error   (`/upload`)
- Screenshots: [B-67-upload-page](screenshots/B_data/B-67-upload-page.png), [B-68-upload-review](screenshots/B_data/B-68-upload-review.png), [B-69-upload-empty-name](screenshots/B_data/B-69-upload-empty-name.png), [B-70-upload-empty-name-submit](screenshots/B_data/B-70-upload-empty-name-submit.png), [B-71-upload-type-click](screenshots/B_data/B-71-upload-type-click.png), [B-72-upload-progress](screenshots/B_data/B-72-upload-progress.png), [B-73-upload-result](screenshots/B_data/B-73-upload-result.png), [B-74-upload-opened](screenshots/B_data/B-74-upload-opened.png), [B-75-upload-sample2-review](screenshots/B_data/B-75-upload-sample2-review.png), [B-76-upload-add-txt](screenshots/B_data/B-76-upload-add-txt.png), [B-77-upload-txt-preview](screenshots/B_data/B-77-upload-txt-preview.png), [B-78-upload-txt-only](screenshots/B_data/B-78-upload-txt-only.png), [B-79-upload-txt-result](screenshots/B_data/B-79-upload-txt-result.png)
- What it shows: 3-step stepper (Choose files → Review → Import), drop zone (CSV, XLSX, JSON, XML, Parquet, Access), "Your data is in a database?" link, Recent uploads, Tips. Review: file list, Dataset name/Description, duplicate-name warning, Preview (first 5 rows) with detected types per column (Text/Number/Date), "1 dataset ready to import". Result: success card with 4 next actions.
- Works: ✅ B-74/83 largely fixed: there is now a pre-import preview with detected types; duplicate name and duplicate content warnings are inline. Empty name → toast "Give the dataset a name" (still toast-only, field not marked). QA B upload imported, "Open dataset" → /datasets/8. Adding a .txt alongside a CSV turns on a "Combine into one dataset" mode and the txt is shown as a CSV with 0 rows and the sentence as the column header; importing the .txt alone fails with an inline error card "Couldn't import QA B not a dataset · Upload failed" + Technical details "Unsupported file type: .txt", Try again / Choose another file — stays on /upload.
- Issues: [Medium] .txt files are accepted by the picker and labelled "CSV · Read" in the queue; the rejection only comes after pressing Import. Should be rejected on add with a clear message. [Low] Error headline says only "Upload failed"; the useful reason is hidden under "Technical details". [Low] Type badges in preview are not editable (no type mapping — clicking a header does nothing). [Low] Empty-name validation is toast-only. [Cosmetic] Duplicate-content warning text has a stray space before the colon ("QA B upload : It has…").
- Console: 400 POST /api/v1/datasets for the .txt (expected)
- Score: 4

### B-80..82 — Upload: 2-sheet XLSX (sheet picker)   (`/upload`)
- Screenshots: [B-80-upload-xlsx-review](screenshots/B_data/B-80-upload-xlsx-review.png), [B-81-upload-xlsx-result](screenshots/B_data/B-81-upload-xlsx-result.png), [B-82-upload-xlsx-try-again](screenshots/B_data/B-82-upload-xlsx-try-again.png)
- What it shows: XLSX in queue with "A preview of XLSX files needs the server…"; Import → error card; Technical details: "The workbook has 2 sheets with data: Sales, Costs. Choose one, or upload it in a batch to get one dataset per sheet." Try again returns to Review with no sheet selector.
- Works: ❌ The server asks to choose a sheet but the UI never offers a sheet picker; Try again just repeats the same failure. There is no way to import either sheet from the UI.
- Issues: [High] (no sheet picker for multi-sheet workbooks; the instruction is buried in Technical details). [Low] No XLSX preview before import.
- Console: 400 POST /api/v1/datasets
- Score: 2

### B-83 — Connections list   (`/connections`)
- Screenshot: [B-83-connections-list](screenshots/B_data/B-83-connections-list.png), [B-109-connections-two](screenshots/B_data/B-109-connections-two.png)
- What it shows: search, Combine databases, New connection; table Connection / Status / Last sync / Datasets / Actions (Test, Browse, Query builder, Guided setup or "Continue setup · step 1 of 4", Open, ⋯).
- Works: ✅
- Issues: [Low] Demo — Live SQLite shows "Not tested · Never" although its DirectQuery dataset works — status is not inferred from use. [Low] Six action buttons per row is busy at 1440 px; the inline action set wraps.
- Console: none
- Score: 4

### B-84..100 — New connection dialog, every type family   (`/connections` drawer)
- Screenshots: [B-84-new-connection-dialog](screenshots/B_data/B-84-new-connection-dialog.png), [B-85-conn-postgres-form](screenshots/B_data/B-85-conn-postgres-form.png), [B-86-conn-postgres-empty-submit](screenshots/B_data/B-86-conn-postgres-empty-submit.png), [B-87-conn-mysql](screenshots/B_data/B-87-conn-mysql.png), [B-88-conn-sql-server](screenshots/B_data/B-88-conn-sql-server.png), [B-89-conn-oracle-database](screenshots/B_data/B-89-conn-oracle-database.png), [B-90-conn-sqlite](screenshots/B_data/B-90-conn-sqlite.png), [B-91-conn-duckdb](screenshots/B_data/B-91-conn-duckdb.png), [B-92-conn-microsoft-access](screenshots/B_data/B-92-conn-microsoft-access.png), [B-93-conn-snowflake](screenshots/B_data/B-93-conn-snowflake.png), [B-94-conn-google-bigquery](screenshots/B_data/B-94-conn-google-bigquery.png), [B-95-conn-databricks-sql](screenshots/B_data/B-95-conn-databricks-sql.png), [B-96-conn-clickhouse](screenshots/B_data/B-96-conn-clickhouse.png), [B-97-conn-trino](screenshots/B_data/B-97-conn-trino.png), [B-98-conn-web-api](screenshots/B_data/B-98-conn-web-api.png), [B-99-conn-odbc-generic](screenshots/B_data/B-99-conn-odbc-generic.png), [B-100-conn-sqlalchemy-url](screenshots/B_data/B-100-conn-sqlalchemy-url.png)
- What it shows: right-side drawer, step 1 "Choose type" grid of 45 types with default ports and search, step 2 "Details" with Connection name, Sensitivity, "Let AI read a few sample rows" (on by default), type-specific fields (Postgres: host/port/db/user/pw/schema/TLS/CA file; MySQL: + TLS; SQL Server: no TLS; Oracle: Service Name; SQLite/Access: File Path; DuckDB: optional path; Snowflake/BigQuery/Databricks/Trino/ODBC/SQLAlchemy: single SQLAlchemy URL; Web API: URL/Method/Auth/JSON path).
- Works: ✅ Empty submit → inline red errors under each required field plus toast "Fill in Connection name, Host, Database first". Driver-missing types now show an amber "The driver for X is not installed on the server" notice (B-106+ changed).
- Issues: [Medium] B-106+ changed but not fixed: uninstalled drivers (Access, Snowflake, BigQuery, Databricks, ClickHouse, Trino, ODBC) are still offered in the type grid with no marker; you only learn after picking one. [Low] Validation errors from one type persist after "Choose type" → another type (Snowflake/Web API show "Connection name is required" before any submit). [Low] The submit toast overlaps the Test connection / Cancel buttons (B-86). [Low] "Let AI read sample rows" defaults ON — a privacy-sensitive default; consider off by default for Confidential/Restricted. [Cosmetic] ClickHouse shows port 9000 (native) while the SQLAlchemy http driver usually uses 8123.
- Console: none
- Score: 4

### B-101..103 — Create "QA B Nile Express" (PostgreSQL)   (`/connections` → `/setup/2`)
- Screenshots: [B-101-conn-pg-filled](screenshots/B_data/B-101-conn-pg-filled.png), [B-102-conn-pg-tested](screenshots/B_data/B-102-conn-pg-tested.png), [B-103-conn-created](screenshots/B_data/B-103-conn-created.png)
- Works: ✅ Test connection → "Connected. These settings work." (inline, check icon on the button). Create connection → redirected straight into Guided setup /setup/2.
- Issues: [Cosmetic] Port field kept a leading zero ("05433") after editing — number input accepts it without normalising.
- Console: none
- Score: 4

### B-104..108, 115..118 — Guided setup (Understand / Choose data / Check & discover / Dashboard) and review page for the new connection   (`/setup/2`, `/connections/2/review`)
- Screenshots: [B-104-setup-understand](screenshots/B_data/B-104-setup-understand.png), [B-105-setup-after-reload](screenshots/B_data/B-105-setup-after-reload.png), [B-106-setup-read-click](screenshots/B_data/B-106-setup-read-click.png), [B-107-review-page](screenshots/B_data/B-107-review-page.png), [B-108-review-sync-stuck](screenshots/B_data/B-108-review-sync-stuck.png), [B-115-review-later](screenshots/B_data/B-115-review-later.png), [B-116-setup-later](screenshots/B_data/B-116-setup-later.png), [B-117-review-source-health](screenshots/B_data/B-117-review-source-health.png), [B-118-review-more-menu](screenshots/B_data/B-118-review-more-menu.png)
- What it shows: 4-step guided setup; step 1 says "Datalytics has not read this database yet, and nothing is reading it now. Read it to see its tables here." with Read the database now / Open the review page / Back to Home. Review page header "Syncing… 0/6", "Last run: running", tabs Relationships / Columns / Entities / Business terms / Schema drift / Source health, all empty.
- Works: ❌ Blocked: "Read the database now" → POST /data-sources/2/sync 409 Conflict, no message shown, page unchanged. The review page at the same time says "Syncing… 0/6" and stayed at 0/6 for 6+ minutes. Steps 2–4 (Choose data, Check & discover, Dashboard) could not be reached. Backend log shows the metadata store (DuckDB file /app/uploads/metadata_cache.duckdb) was locked by another process (a pytest run in this shared environment) — so the root cause is partly environmental, but the UI handling is an app issue.
- Issues: [High] Guided setup contradicts the review page ("nothing is reading it now" vs "Syncing… 0/6") and the 409 from "Read the database now" is swallowed — the user clicks and nothing happens. Show "A read is already running (started hh:mm) — progress x/6" and link to it. [High] A sync that stalls at 0/6 has no timeout, no cancel and no error; "Last run: running" forever. [Low] Review page step tabs wrap onto two rows (Source health alone on row 2) at 1440 px.
- Console: 409 POST /api/v1/data-sources/2/sync (x2)
- Score: 2

### B-110..114 — Browse schema, Import `shipments`, DirectQuery `complaints`   (`/connections` browse modal)
- Screenshots: [B-110-browse-schema](screenshots/B_data/B-110-browse-schema.png), [B-111-browse-shipments](screenshots/B_data/B-111-browse-shipments.png), [B-112-import-shipments](screenshots/B_data/B-112-import-shipments.png), [B-113-browse-complaints-dq](screenshots/B_data/B-113-browse-complaints-dq.png), [B-114-dq-complaints-created](screenshots/B_data/B-114-dq-complaints-created.png)
- What it shows: modal with TABLES & VIEWS (branches, drivers, customers, shipments, complaints, app_sessions_log), Custom query box (Ctrl+Enter), Run Preview, Save query…, 50-row preview, Download CSV, Import/DirectQuery toggle with clear explanations, name field, "Import as Dataset" / "Create DirectQuery Dataset".
- Works: ✅ Browse works even while sync is stuck. Imported shipments → /datasets/9 (64,420 rows × 26 cols, 13.6 MB, "Your data is in" onboarding strip, toast "Imported "shipments" — 64,420 rows"). DirectQuery complaints as "QA B complaints DQ" → /datasets/10 (10 columns, Live).
- Issues: [Medium] The dataset-name field is pre-filled with the table name and clicking into it appends instead of selecting — I ended with "complaintsQA B complaints DQ" before correcting (B-113); the shipments import kept the default name "shipments" (driver note: my fill hit the table button; but a generic "shipments" name with no connection prefix makes collisions likely). [Medium] New DirectQuery dataset onboarding says "We read 0 rows and 10 columns" and Rows "—" — misleading for a live table with rows. [Low] Preview: timestamps wrap onto two lines with microseconds ("2024-07-16T05:25:55.645171") — raw ISO with no formatting. [Low] Shipments preview rows are very tall (row height ~54 px for single-line values).
- Console: 404 GET /datasets/9/analysis (same as others)
- Score: 4

### B-119/120 — Demo — Live SQLite review   (`/connections/1/review`)
- Screenshots: [B-119-sqlite-review](screenshots/B_data/B-119-sqlite-review.png), [B-120-sqlite-sync](screenshots/B_data/B-120-sqlite-sync.png)
- What it shows: "0 tables · 0 columns", "This source has not been synced yet. Run a sync to build its metadata.", "Let the model describe this source" unticked, empty tabs.
- Works: ❌ Run sync → POST /data-sources/1/sync 500 (backend: DuckDB lock held by another process), and the UI shows nothing at all — no toast, no error, button just returns.
- Issues: [High] Server errors on Run sync are silent. [Medium] Seeded demo connection has never been synced, so its review page/glossary-linked metadata is empty for every new user.
- Console: 500 POST /api/v1/data-sources/1/sync
- Score: 2

### B-121..127 — Dataflows: list, create "QA B flow", recipe, save, run   (`/dataflows`, `/dataflows?flow=1`)
- Screenshots: [B-121-dataflows-list](screenshots/B_data/B-121-dataflows-list.png), [B-122-dataflow-editor](screenshots/B_data/B-122-dataflow-editor.png), [B-123-dataflow-created](screenshots/B_data/B-123-dataflow-created.png), [B-124-dataflow-sort-step](screenshots/B_data/B-124-dataflow-sort-step.png), [B-125-dataflow-save-empty-sort](screenshots/B_data/B-125-dataflow-save-empty-sort.png), [B-126-dataflow-saved](screenshots/B_data/B-126-dataflow-saved.png), [B-127-dataflow-run](screenshots/B_data/B-127-dataflow-run.png)
- What it shows: New dataflow (Name, Source dataset with All / Certified / Mine / "Show 3 test-looking" filters, Kind: Transform / Monthly snapshot), list table (Name, Source, Refresh, Last run, Outputs), editor (Pipeline + Add step, Save recipe, live preview "64,420 rows in → 64,420 rows out", Refresh schedule, Refresh outputs now, New dataset name, Run into a new dataset, Delete dataflow).
- Works: ⚠️ Creating a flow from **Demo — Sales** as super admin → POST /dataflows 403 with NO message (B-122: form just stays). From my own `shipments` it worked. Sort step without a column → Save shows toast "step 1: sort needs at least one column" and the step stays . Sort by delivery_fee_egp desc → saved ("1 steps"); Run into "QA B flow output" → "Succeeded, 64,420 rows, just now", output link listed.
- Issues: [High] Silent 403 when creating a dataflow from a seeded dataset (backend requires 'data' capability on the source; super admin is refused and the UI shows nothing). Show the server reason and/or filter the source picker to datasets the user may build on. [Medium] My own uploads (QA B upload, Qa sample, QA B complaints DQ) are hidden from the source list as "test-looking" by name heuristics — surprising; "QA" prefix ≠ test data. [Low] "1 steps" grammar. [Low] Flow name in the list renders as a bordered chip that looks like a button. [Low] Preview rows very tall; raw timestamps with microseconds.
- Console: 403 POST /api/v1/dataflows (x2), 400 PUT /api/v1/dataflows/1 (expected validation)
- Score: 3

### B-128..133 — Lineage: graph, focus, issues filter, list, search   (`/lineage`)
- Screenshots: [B-128-lineage-graph](screenshots/B_data/B-128-lineage-graph.png), [B-129-lineage-node-selected](screenshots/B_data/B-129-lineage-node-selected.png), [B-130-lineage-issues-only](screenshots/B_data/B-130-lineage-issues-only.png), [B-131-lineage-list](screenshots/B_data/B-131-lineage-list.png), [B-132-lineage-search](screenshots/B_data/B-132-lineage-search.png), [B-133-lineage-graph-search](screenshots/B_data/B-133-lineage-graph-search.png)
- What it shows: 3-column graph SOURCES 3 / DATASETS 11 / REPORTS 21 with "+N more" collapsers, filters Node type / Source type / Mode, "Show issues only 4", Graph/List toggle, Export as PNG, zoom +/–/fit, minimap, legend (Declared flow / Join-derived / Broken). Clicking a node: "Focused on" bar with Upstream/Both/Downstream and 1 hop/All, and a side panel (impact warning "If Demo — Sales changes, 16 reports are affected", type/status, Feeds from, Used by, Open, Ask AI about this).
- Works: ✅ B-141 largely fixed (zoom/pan/minimap, filters, search with typeahead, details panel). Dataflow output "QA B flow output" appears as a dataset; dataflow edge drawn as "derived".
- Issues: [Low] At default 53% zoom node labels are ~7 px and unreadable (B-128) — default "fit" makes text too small; start at 100% on the focused area or enlarge cards. [Low] The search box filters only via the typeahead; in List view typing does not filter rows (B-132). [Low] Dataflows themselves are not nodes (only their outputs) so you can't see which flow produced a dataset in the graph. [Low] Issues-only (4) gives no explanation of what the issue is for each highlighted node (they are "No reports use it").
- Console: none
- Score: 4

### B-134..139 — Migration: inventory, SAS map, add item, item detail, link, CSV import   (`/migration`, `/migration?item=1`)
- Screenshots: [B-134-migration](screenshots/B_data/B-134-migration.png), [B-135-migration-sas-map](screenshots/B_data/B-135-migration-sas-map.png), [B-136-migration-item-added](screenshots/B_data/B-136-migration-item-added.png), [B-137-migration-item-detail](screenshots/B_data/B-137-migration-item-detail.png), [B-138-migration-linked](screenshots/B_data/B-138-migration-linked.png), [B-139-migration-csv-import](screenshots/B_data/B-139-migration-csv-import.png)
- What it shows: status chips (All / Not mapped / Mapped / Differences / Reconciled / Signed off / Retired), Add to the inventory (Name, Kind, Owner), CSV/SAS import, empty state, "How SAS maps to Datalytics" table (DATA step → recipe steps "Partly", PROC SQL "Built in", PROC MEANS…). Item detail: Replaced by + Link, Owner + Set owner, Comparisons (instructions to use ⇄ Reconcile on a widget), What the program uses, Attach SAS program, Notes, Retire it, Sign-off, Remove from the inventory.
- Works: ✅ Added "QA B legacy report" → Not mapped; linked to Demo — Sales Overview → Mapped (counts update). CSV with Name/Type/Owner/Folder/Notes imported two rows with owner and folder.
- Issues: [Low] "Remove from the inventory" is a full-width red primary button in the sign-off column — visually heavier than the sign-off it sits under. [Low] Replaced-by dropdown lists every report incl. other testers' "QA F …" and analysis scratch reports, no search. [Low] Native file inputs ("Choose Files / No file chosen") are unstyled vs the rest of the UI. [Low] Comparisons step requires leaving the page to a widget menu — no direct "Reconcile" action here.
- Console: none
- Score: 4

### B-140/141 — Phone width 390 px   (`/datasets/1`, `/datasets`)
- Screenshots: [B-140-sales-phone](screenshots/B_data/B-140-sales-phone.png), [B-141-datasets-phone](screenshots/B_data/B-141-datasets-phone.png)
- Works: ✅ header actions wrap onto their own rows, title on one line, tabs scroll horizontally. List page stacks filters; search box now visible.
- Issues: [Low] Datasets table at 390 px is clipped at the right (Source column cut "Live · PostgreS…") with no visible horizontal scroll cue. [Cosmetic] KPI tiles 2x2 leave Models alone on a third row.
- Console: none
- Score: 4

### B-142 — Build a dashboard from a dataset   (`/datasets/8` → `/reports/22?edit=1`)
- Screenshot: [B-142-build-dashboard](screenshots/B_data/B-142-build-dashboard.png)
- Works: ✅ Opens the editor with the dataset as primary, Fields panel, empty "Design this page" canvas with "Add page from a template".
- Issues: [Low] the new dashboard is named exactly "QA B upload" like its dataset, with no name prompt. (The false "changed in another session" banner was not seen in this pass.)
- Console: none
- Score: 4

### B-143..149 — Suggest dashboards (no LLM)   (`/datasets` row menu)
- Screenshots: [B-143-suggest-dashboards-3s](screenshots/B_data/B-143-suggest-dashboards-3s.png), [B-144-suggest-dashboards-33s](screenshots/B_data/B-144-suggest-dashboards-33s.png), [B-145-suggest-run-20s](screenshots/B_data/B-145-suggest-run-20s.png), [B-146-suggest-running](screenshots/B_data/B-146-suggest-running.png), [B-147-suggest-result-45s](screenshots/B_data/B-147-suggest-result-45s.png), [B-148-suggest-result-95s](screenshots/B_data/B-148-suggest-result-95s.png), [B-149-suggest-cancelled](screenshots/B_data/B-149-suggest-cancelled.png)
- What it shows: modal with optional goal text ("Leave it blank and the charts are picked from your data's own statistics instead, with no AI involved"), About you, Quick vs Analyst panel. Running state shows an elapsed counter, "Still going…" note and a Cancel button.
- Works: ⚠️ there is now a timer and Cancel, but with the goal left BLANK (promised "no AI involved") on a 5-row dataset it was still "Reading the data…" after 102 s; backend log shows LLM endpoint connection attempts during that time. Cancel works.
- Issues: [High] The no-AI path still depends on (or waits for) the unreachable LLM: never completes on a 5-row dataset; no "AI unavailable" message, contradicting the copy. [Low] "Quick: about a minute" estimate is inaccurate here.
- Console: none (backend: LLM endpoint unreachable warnings)
- Score: 2

### B-150..152 — Analysis › Anomalies › Inspect outliers modal   (`/datasets/1` Analysis)
- Screenshots: [B-150-leave-rows-out](screenshots/B_data/B-150-leave-rows-out.png), [B-151-analysis-anomalies](screenshots/B_data/B-151-analysis-anomalies.png), [B-152-outlier-inspect](screenshots/B_data/B-152-outlier-inspect.png)
- Works: ✅ Detector select (1.5×IQR, Isolation Forest, ECOD), box plot, impact (1.5% of total, mean 4,316 vs 4,440), first 50 outlier rows.
- Issues: [Medium] the 560 px modal clips the table — columns after "category" (channel, **revenue** — the inspected column!) are cut off, and dates/product names wrap onto 2–3 lines. [Low] min shown as "-12,012" but the fence text says "(-695.35 – 9,352)" — mixed decimals.
- Console: none
- Score: 3

### Area summary
- Score (avg ≈ 3.4 / 5).The dataset detail page has a sensible tab set (Overview, Columns, Data, Analysis, Rules & alerts, Models, plus Aggregates for live data) and gives plain-language data warnings. The new data checks work from start to finish (add a check, Run now, "All pass"). Upload has a preview step with detected types and an error card that stays on the page. Lineage is a real interactive graph, and the phone layout works. Problems remain on the paths that fail: several server errors are silent (Run sync 500, guided-setup 409, dataflow create 403). Guided setup for a new Postgres connection could not get past step 1 because a sync stalled at 0/6 with no timeout or explanation (the root cause is partly a DuckDB lock in this shared environment). Multi-sheet XLSX still has no sheet picker, and "Suggest dashboards" with no AI still never finishes. Several old grid issues are back (filter removal, Add step menu that can't be dismissed, unsafe edit key, clipped outlier modal).
- Top issues table:

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| B-104/115 | High | Guided setup / review | "Read the database now" → 409 swallowed; setup says nothing is reading while review shows "Syncing… 0/6" forever | Surface the running job (progress, started time, cancel); add timeout/failure state; one source of truth for sync state |
| B-120 | High | Connection review | Run sync → 500 with no UI feedback | Show the server error inline/toast; mark run failed |
| B-122 | High | Dataflows | Creating a flow from a seeded dataset → 403 with no message (super admin) | Show the reason; filter source picker by capability |
| B-81 | High | Upload | Multi-sheet XLSX: no sheet picker (B-85) | Read `detail.sheets` and show a picker / "one dataset per sheet" option |
| B-148 | High | Suggest dashboards | "No AI" path never completes without LLM | Do not call the LLM when goal is blank; time out with "AI unavailable" |
| B-15 | High | Data grid | Removing last filter leaves grid filtered (B-35) | Re-query on every filter-list change |
| B-16 | High | Edit cells | Default key `date` is non-unique; edits hit many rows (B-34) | Default to row id/unique key; show "N rows will change" |
| B-47 | Medium | DirectQuery Data | Filter/calc/search controls enabled but unsupported; rows reshuffle | Disable with tooltip; stable ORDER BY |
| B-50 | Medium | DirectQuery Rules | No data checks for live datasets, no explanation | Support checks via pushed-down SQL or explain why not |
| B-28 | Medium | Steps | Add step menu not dismissible (B-38) | Esc/outside-click close |
| B-152 | Medium | Outlier modal | Inspected column clipped (B-13) | Wider modal, inspected column first/sticky |
| B-06 | Medium | Dataset detail | GET /datasets/{id}/analysis 404 on every load | Return 204/empty or don't request until analysis exists |
| B-61 | Medium | Glossary | Terms only per connection; no link from dataset columns; table/column free text | Allow dataset-scoped terms and column pickers |
| B-114 | Medium | DQ dataset onboarding | "We read 0 rows" for a live table | Say "queried live — N rows at source" |

- Strengths:
  - Plain-language "What you should know about this data" warnings with one-click fixes.
  - New data checks: eight check types, Block vs Warn, clear "Checked 2,000 rows · All pass".
  - Upload review step with type detection, duplicate-name/content warnings, multi-file combine, inline failure card.
  - Connection drawer: 45 types, per-type forms, inline field validation, working Test connection; browse modal with Import vs DirectQuery explained.
  - Lineage graph: focus mode, impact warning, side panel, list view, export.
  - Analysis catalogue (26 analyses) that runs without an LLM; Ask page degrades gracefully when the model is down.
  - Migration workbench: inventory, SAS mapping guide, CSV import, link/owner/sign-off flow.
- Not covered / blocked and why:
  - Guided setup steps 2–4 (Choose data, Check & discover, Dashboard) and review tabs with real content (Relationships/Columns/Entities/Schema drift for nile_express): blocked by the stalled sync (409 / DuckDB metadata lock held by another process in the shared environment).
  - "Leave those rows out" / "Remove the copies" actions on seeded datasets: not applied to avoid editing Demo content.
  - Alerts creation, model training/scoring, Aggregates creation: viewed only (time).
  - Per-column data-check types other than "Only allowed values" were listed but not each executed.
  - Dark theme not checked in this area.


---

## B2 — Connection sync & guided setup (re-test)
Coverage: 14 screens/states / 63 screenshots. Account: admin@datalytics.local. Viewport 1440×900. Port 9408. Started 20:06 EEST.
Context: the backend was restarted with its own DuckDB metadata cache (wave-1 lock conflict with pytest removed). Machine load was ~13 on 2 CPUs (a pytest run was still going), so the first driver commands timed out (environment only).

### B2-01 — Connections list after restart   (`/connections`)
- Screenshot: [B2-01-connections-list](screenshots/B_data/B2-01-connections-list.png)
- What it shows: QA B Nile Express "Connected", "Continue setup · step 1 of 4". Demo — Live SQLite shows a red "Sync failed" pill with "Interrupted by a server restart". Imports card shows shipments Done (64,420 rows).
- Works: ✅ The wave-1 stuck sync is now reported to the user instead of staying in "Syncing…" forever. The restart marked it failed and said why.
- Issues: [Low] "Interrupted by a server restart" is shown, but there is no inline "Run again" action on the row. [Cosmetic] The "×" on the Imports card overlaps the "Open data…" button, so the label is clipped to "Open data.".
- Console: none (401 /auth/me happened before login, which is expected)
- Score: 4

### B2-02..05 — Demo — Live SQLite: Run sync   (`/connections/1/review`)
- Screenshots: [B2-02-sqlite-review-before](screenshots/B_data/B2-02-sqlite-review-before.png), [B2-03-sqlite-sync-clicked](screenshots/B_data/B2-03-sqlite-sync-clicked.png), [B2-04-sqlite-sync-after](screenshots/B_data/B2-04-sqlite-sync-after.png), [B2-05-sqlite-after-reload](screenshots/B_data/B2-05-sqlite-after-reload.png)
- What it shows: Before: "Sync failed", "Last run: failed · 8:05:16 PM — Interrupted by a server restart", 0 tables. After clicking Run sync, the button shows "Syncing… 1/6" and the pill shows "Syncing". The run ends after about 9 s with all 8 steps ok (Discover tables, Sample rows 7.6 s, Profile columns 8 columns, Infer relationships 0, describe, entities, Check for schema drift "Initial schema recorded: 8 column(s)", link_datasets). The pill changes to "Synced".
- Works: ✅ FIXED compared with wave 1 (that run returned 500 and showed nothing). Live progress is shown.
- Issues:
  - [Medium] After the sync finished, the header and the tab counts stayed stale: "0 tables · 0 columns", "Columns (0)", "No tables yet. Run a sync to read this connection's schema." (B2-04). They only showed 1 table / 8 columns after a manual page reload (B2-05). The page does not refetch metadata when the run completes.
  - [Medium] "What this database holds" says "Demo — Live SQLite has 1 tables with 0 rows in total." The live_orders table really has 12,000 rows (checked read-only in /app/uploads/demo_1_directquery.db). The row count is wrong or missing. "1 tables" is also not pluralised correctly.
  - [Low] The source card says "1 not profiled" (amber) even though the run log says "Profile columns · 8 columns · ok". These contradict each other.
  - [Low] The progress counter says "Syncing… 1/6", but the run log lists 8 steps.
  - [Low] Step names mix two styles: "Discover tables" and "Check for schema drift" are user-facing, while "describe", "entities" and "link_datasets" are internal identifiers.
- Console: none (no failed API calls)
- Score: 3

### B2-06..13 — SQLite review tabs   (`/connections/1/review`)
- Screenshots: [B2-06-sqlite-tab-columns](screenshots/B_data/B2-06-sqlite-tab-columns.png), [B2-06b-sqlite-columns-scrolled](screenshots/B_data/B2-06b-sqlite-columns-scrolled.png), [B2-11-sqlite-columns-expanded](screenshots/B_data/B2-11-sqlite-columns-expanded.png), B2-07/[B2-12-sqlite-tab-entities](screenshots/B_data/B2-12-sqlite-tab-entities.png), [B2-08-sqlite-tab-terms](screenshots/B_data/B2-08-sqlite-tab-terms.png), [B2-09-sqlite-tab-drift](screenshots/B_data/B2-09-sqlite-tab-drift.png), [B2-10-sqlite-tab-health](screenshots/B_data/B2-10-sqlite-tab-health.png), [B2-10b-sqlite-tab-relationships](screenshots/B_data/B2-10b-sqlite-tab-relationships.png), [B2-13-sqlite-holds-click](screenshots/B_data/B2-13-sqlite-holds-click.png)
- What it shows:
  - Relationships (0): "Nothing awaiting review. Every proposed relationship has been decided." The Confirm button is disabled.
  - Columns (8): a collapsible live_orders table listing 8 columns, each with a type and an editable description plus a Save button.
  - Entities (0): "No entities yet — run a sync with model descriptions enabled…".
  - Business terms: shows the glossary term "QA B term" (orders.amount) and an "Add a term" button.
  - Schema drift: one BASELINE entry with a hash, "Added: live_orders.amount, …".
  - Source health: says Postgres-only index advice and "No DirectQuery runs with filters yet".
- Works: ✅ Every tab renders and none are blank.
- Issues:
  - [Low] The Relationships empty state says "Every proposed relationship has been decided", but nothing was ever proposed (0 proposed). The wording is misleading. It should say "No relationships found" (a single table).
  - [Low] Column types mix friendly and raw names: "Whole number" and "Text" next to "timestamp" and "currency".
  - [Low] Source health says "5 DirectQuery runs in the last 30 days" and then "No DirectQuery runs with filters yet". This is technically consistent but confusing.
  - [Cosmetic] Clicking the tab strip scrolls the page, and the tabs wrap onto two rows at 1440 px (Source health sits alone on row 2), as in wave 1.
- Console: none
- Score: 4

### B2-14 — QA B Nile Express review page after restart   (`/connections/2/review`)
- Screenshot: [B2-14-nile-review-before](screenshots/B_data/B2-14-nile-review-before.png)
- What it shows: "Sync failed", "Last run: failed · 8:05:16 PM — Interrupted by a server restart", 0 tables.
- Works: ✅ The wave-1 "Syncing… 0/6 forever" state has now ended. A restart marks the orphaned run as failed and says why. Wave 1's "no timeout / no cancel" issue is changed rather than fixed: a run that is stuck while the server stays up still has no visible cancel (see B2-21).
- Issues: None new.
- Console: none
- Score: 4

### B2-15..18 — Guided setup step 1 "Understand"   (`/setup/2`)
- Screenshots: [B2-15-setup-step1](screenshots/B_data/B2-15-setup-step1.png), [B2-16-setup-reading](screenshots/B_data/B2-16-setup-reading.png), [B2-17-setup-read-15s](screenshots/B_data/B2-17-setup-read-15s.png), [B2-18-setup-step1-60s](screenshots/B_data/B2-18-setup-step1-60s.png)
- What it shows: Before reading, the page says "Datalytics has not read this database yet, and nothing is reading it now" and offers Read the database now / Open the review page / Back to Home. After clicking Read, within about 2 s it shows "What this database holds: 6 tables with 71,729 rows in total", "Sept 2018 to Oct 2026", and "Where to start", which ranks the tables shipments (64,420, numbers weight_kg / delivery_fee_egp / cod_amount_egp / delivery_days, Jan 2024–Sept 2026, links to branches/customers/drivers), complaints, customers, branches and drivers. "System tables (1)" holds app_sessions_log.
- Works: ✅ FIXED compared with wave 1 (that click returned 409 and nothing happened). The read starts immediately, and the facts appear before the slow steps finish. Classifying app_sessions_log as a system table is a nice touch.
- Issues:
  - [Medium] "AI is reading your database to describe it in plain words…" and "Measuring what is counted against what, and which numbers add up…" kept spinning for 2+ min. The header already shows "AI model: Default, not reachable", but step 1 never says the AI is unavailable and never stops waiting. The backend log shows the LLM call hanging on ConnectTimeout (llm_timeout_s = 180).
  - [Low] Only shipments got a one-line description ("One row per parcel handed to the company for delivery"). The other tables have none, and nothing explains why.
  - [Low] The date range "Sept 2018 to Oct 2026" mixes abbreviation styles ("Sept" next to "Jan"/"Oct"/"Aug").
- Console: none
- Score: 4

### B2-19..21 — Step 1: sample rows, system tables, "Show details"   (`/setup/2` → `/connections/2/review`)
- Screenshots: [B2-19-setup-sample-rows](screenshots/B_data/B2-19-setup-sample-rows.png), [B2-20-setup-system-tables](screenshots/B_data/B2-20-setup-system-tables.png), [B2-21-setup-details](screenshots/B_data/B2-21-setup-details.png)
- What it shows: "Show sample rows" opens an inline grid (shipment_id, tracking_no NX…EG, service_type, parcel_category, destination_governorate…) that scrolls horizontally inside the card. "System tables (1)" expands to app_sessions_log (3,000 rows, "(approximate)" date range). "Show details: every column, relationship and business term" navigates to the review page.
- Works: ✅ The review page now shows 6 tables · 61 columns, Sample rows ok (64.8 s), Profile columns 61, Infer relationships "3 proposed (3 high confidence)", and the relationship graph (branches ↔ drivers, shipments, complaints).
- Issues:
  - [Medium] "Show details" is styled as an expander (a chevron next to an underlined link) but it actually leaves the wizard for /connections/2/review. The user loses their place in the setup.
  - [Medium] The review sync is stuck at "Syncing… 4/6" with "Last run: running" after the Infer relationships step. The next step ("describe") waits on the unreachable LLM, and nothing tells the user it is waiting for AI. This is the same class of problem as wave 1's stuck sync, but here the cause is the missing LLM (an expected environment limitation) rather than the DuckDB lock. The UI still has no timeout message, no skip and no cancel.
  - [Low] The header says "0 awaiting review · 6 settled" while the run log says "3 proposed (3 high confidence)" and the tab says "Relationships (0)" / "Nothing awaiting review". The counts disagree with each other.
  - [Low] "1 described · 5 not profiled" (amber) even though Profile columns reported 61 columns ok.
- Console: none
- Score: 3

### B2-22..26 — Step 2 "Choose data"   (`/setup/2`)
- Screenshots: [B2-22-setup-step2](screenshots/B_data/B2-22-setup-step2.png), [B2-23-setup-suggest-3s](screenshots/B_data/B2-23-setup-suggest-3s.png), [B2-24-setup-suggest-33s](screenshots/B_data/B2-24-setup-suggest-33s.png), [B2-25-setup-suggest-80s](screenshots/B_data/B2-25-setup-suggest-80s.png), [B2-26-setup-step2-picked](screenshots/B_data/B2-26-setup-step2-picked.png)
- What it shows: An "Analysis 1 step 2 of 4" chip plus "New analysis". The "About you" card has four optional free-text questions and Skip and suggest / Suggest datasets buttons. "Already made from this database" lists QA B complaints DQ (2,343) and shipments (64,420). "Build it myself" offers Browse tables / Query builder. Footer: "Nothing chosen yet" with a disabled "Next: Check & discover".
- Works: ⚠️ The answers collapse into a summary with "Change answers". Suggest datasets shows "AI is choosing the most useful data for you. This can take a minute. Running for 1:42+" and is still running, with no LLM available. I picked the existing "shipments" dataset. The footer changed to "1 dataset chosen" and Next was enabled, so the AI-free path works.
- Issues:
  - [Medium] The suggestion spinner runs for 1:40+ even though the app already knows the model is unreachable (header pill). It should fail fast with "AI is not available — pick an existing dataset or build one yourself", which both point to working paths that are already on the page.
  - [Low] After the answers are saved, the analysis chip is renamed to the "What do you need to know?" text ("late deliveries and delivery fees by branch"). The renaming is good, but it happens silently.
- Console: none
- Score: 3

### B2-27..33 — Step 3 "Check & discover" (waiting) + New analysis + Browse   (`/setup/2`)
- Screenshots: [B2-27-setup-step3](screenshots/B_data/B2-27-setup-step3.png), [B2-28-setup-step3-45s](screenshots/B_data/B2-28-setup-step3-45s.png), [B2-29-setup-step3-demand](screenshots/B_data/B2-29-setup-step3-demand.png), [B2-30-setup-step3-ai-slow](screenshots/B_data/B2-30-setup-step3-ai-slow.png), [B2-31-setup-step3-demand-details](screenshots/B_data/B2-31-setup-step3-demand-details.png), [B2-32-new-analysis](screenshots/B_data/B2-32-new-analysis.png), [B2-33-browse-tables](screenshots/B_data/B2-33-browse-tables.png)
- What it shows: The step first shows "AI is writing down what you want…" and then a "What you want" card ("late deliveries and delivery fees by branch", with Not right? Change it / Show details listing "The questions your dashboard will answer"). The shipments check said "Checking the data, fixing what can be fixed safely… Running for 0:06 → 3:14". After about 3.5 min it changed to "The AI is taking longer than usual (it may be busy or offline). The facts below are complete; you can continue and check back later. [Check again]", with Next: Dashboard enabled.
- Works: ✅ It degrades gracefully. There is a timeout message and the user can continue. The findings arrived at about 7 min (20:31) and were shown after navigating back.
- Issues:
  - [Medium] The timeout message says "The facts below are complete", but nothing at all is shown below it (B2-30). The deterministic findings (duplicates, spaces, -1, and so on) were already computable; they were only delayed by the LLM model_rules / plain_insights calls in _check_one, which run before anything is returned. Show the plain checks first and add AI items later.
  - [Medium] It took about 7 min to check one 64k-row dataset with no LLM available. Each LLM call waits for a connect timeout. The app already knows the model is unreachable (header pill), so it should skip the AI calls.
  - [Low] "New analysis" starts Analysis 2 with the "About you" questions empty again, even though the copy says "reused … so you are asked once".
  - [Low] "Browse tables" in step 2 leaves the wizard for /connections and opens the browse modal over the connections list. Closing it does not return to the setup.
- Console: none
- Score: 3

### B2-34..45 — Step 3 findings vs the planted data problems   (`/setup/2`, `/datasets/9` Steps)
- Screenshots: [B2-34-step3-results](screenshots/B_data/B2-34-step3-results.png), [B2-35-step3-details](screenshots/B_data/B2-35-step3-details.png), [B2-36-step3-details-2](screenshots/B_data/B2-36-step3-details-2.png), [B2-37-step3-details-3](screenshots/B_data/B2-37-step3-details-3.png), [B2-38-step3-details-4](screenshots/B_data/B2-38-step3-details-4.png), [B2-39-step3-insights](screenshots/B_data/B2-39-step3-insights.png), [B2-40-fix-remove-copies](screenshots/B_data/B2-40-fix-remove-copies.png), [B2-41-fix-spaces-warn](screenshots/B_data/B2-41-fix-spaces-warn.png), [B2-42-fixes-applied](screenshots/B_data/B2-42-fixes-applied.png), [B2-43-after-fixes-reload](screenshots/B_data/B2-43-after-fixes-reload.png), [B2-44-dataset9-overview](screenshots/B_data/B2-44-dataset9-overview.png), [B2-45-dataset9-steps](screenshots/B_data/B2-45-dataset9-steps.png)
- What it shows: "Your data is ready — 64,420 rows. This dataset was already in use, so nothing was changed in it automatically." Then "9 things to know", each with a severity bar, a "What to do" line and a one-click fix. "What the data shows" lists 5 insights.
- Findings vs ground truth (I verified each count read-only with psql on nile_express.shipments):
  | Planted problem | Found? | App's wording / fix | Fix sensible? |
  |---|---|---|---|
  | 420 duplicated rows | ✅ exactly 420 | "420 rows are exact copies…" → Remove the copies | Yes. It became a "Remove duplicates (legacy) across all columns" step, rows 64,420 → 64,000. The "(legacy)" label is odd. |
  | Padded governorate names | ✅ exactly 904 | "904 values … have extra spaces. 'North' and 'North ' count as two" → Remove the spaces | Yes. Trim whitespace step. |
  | weight_kg = -1 | ✅ exactly 1,309 | "looks like a code for 'unknown'" → Leave those rows out / Warn me on every refresh | Mostly. It drops whole shipments (−1,300 rows) from every chart, including counts that do not use weight. Setting the value to empty (NULL) would be safer. |
  | declared_value stored as text | ❌ not flagged | Listed among the "7 number columns have extreme values" and charted as a number (sum(declared_value) 51,204,509; "Declared_value in 2024-11 was far above its usual range"). The dataset grid shows it as TXT. | No. A text column is silently treated as numeric in one place and as text in another; there is no "convert to number" suggestion. |
  | Empty internal_note | ✅ 98% empty (63,129/64,420 NULL) | "Leave the column out" | Yes. |
  | Constant currency | ✅ "has the same value in every row" (all EGP) | "Leave the column out" | Yes. |
  | Negative delivery fees | ✅ exactly 38 | "cannot be below zero … entry mistakes" → Leave those rows out / Warn | Yes (62,700 → 62,662). |
  | Delivered before created | ❌ not found | — (55 rows in the DB where delivered_at < created_at) | Missed. There is no cross-column date-order check. |
  | (extra) 89% empty return_reason | ✅ | Treat empty as "Unknown" | Reasonable (fill step). |
  | (extra) 48% empty customer_rating | ✅ | Advice only | OK |
  | (extra) 7 columns with extreme values | ✅ | "Prefer the median…" | OK, but customer_rating and delivery_attempts are small ordinal ranges; calling them "extreme values" is noisy. |
  Score: 7 of 9 planted problems found, with exact counts. Missed: text-typed numbers and delivered-before-created.
- Insights: "Same Day has the highest share of is_late: 31.6% vs 17.7% overall" is useful. "p = 0" should be shown as "p < 0.001". Three of the five insights ("Weight_kg / Declared_value / Delivery_fee_egp in 2024-11 far above usual range", "Weight_kg has run 67% higher since 2024-11") are volume effects: Nov 2024 has 2,849 shipments against about 1,500 normally, while average weight is flat (2.43 against 2.3–2.5). The app sums weights, so the insight reads as "parcels got heavier" when really there were more parcels. The heading also uses raw column names ("Weight_kg").
- Fixes: Remove the copies, Remove the spaces, both Leave those rows out, Treat empty as "Unknown" and both Leave the column out → each turns into "Done" (disabled) and adds a pipeline step on dataset 9 (7 steps, 64,420 rows in → 62,662 rows out, B2-45). The dashboard built afterwards uses 62,662.
- Issues:
  - [High] "Warn me on every refresh" fails 100% of the time with POST /api/v1/setup/2/check/9/fix → 500, and the UI shows nothing. Backend traceback: `ImportError: cannot import name 'DataCheckIn' from 'app.schemas.schemas'`. In main@0cb8f48, backend/app/routers/guided_setup.py:1577 does `from ..schemas.schemas import DataCheckIn`, but the class lives in app/routers/datasets.py:1934. Fix: `from .datasets import DataCheckIn, create_data_check`. This is a CODE bug, not the environment.
  - [Medium] After fixes are applied, the wizard header still says "64,420 rows · 26 columns" and "Your data is ready — 64,420 rows" (also after reload, B2-43), and it still lists all 9 items in the summary bullets. The real output is 62,662 rows × 24 columns. The same stale count appears on the dataset "Data 64,420" tab.
  - [Medium] "This dataset was already in use, so nothing was changed in it automatically", yet the one-click fixes then permanently change that same dataset's pipeline. There is no confirm dialog and no warning that other users and dashboards on "shipments" are affected.
  - [Medium] declared_value is treated as numeric in the checks and insights while the dataset grid types it as TXT. The planted "stored as text" problem is not reported.
  - [Medium] Delivered-before-created (55 rows) is not detected.
  - [Low] Undo exists only as "Show details and undo" in the summary. Once an item is "Done", it has no Undo button of its own.
- Console: 500 POST /api/v1/setup/2/check/9/fix (Warn me on every refresh)
- Score: 3

### B2-46..53 — Step 4 "Dashboard" and the created dashboard   (`/setup/2` → `/reports/24`)
- Screenshots: [B2-46-setup-step4](screenshots/B_data/B2-46-setup-step4.png), [B2-47-setup-step4-wait](screenshots/B_data/B2-47-setup-step4-wait.png), [B2-48-step4-levels](screenshots/B_data/B2-48-step4-levels.png), [B2-49-dashboard-created](screenshots/B_data/B2-49-dashboard-created.png), [B2-50-dashboard-loaded](screenshots/B_data/B2-50-dashboard-loaded.png), [B2-51-dashboard-latepct](screenshots/B_data/B2-51-dashboard-latepct.png), [B2-52-dashboard-composition](screenshots/B_data/B2-52-dashboard-composition.png), [B2-53-dashboard-levels](screenshots/B_data/B2-53-dashboard-levels.png)
- What it shows: "Suggested pages for your dashboard". On arrival it already said "Running for 4:51" (it had started in the background). About 1.5 min later it offered 3 ticked pages: Headline numbers (3 charts, 2 filters), Composition (5 charts), Levels & drivers (9 charts). Also offered: Suggest again, Change it per page, "Create my dashboard (3 pages)", and Start blank. The dashboard was created as /reports/24, "late deliveries and delivery fees by branch", with 3 pages.
- Works: ⚠️ The dashboard is created and opens. The "Your questions" panel honestly says "late deliveries and delivery fees by branch: not answered on the pages chosen — add the page that answers it, or ask it in Ask AI". Composition renders well (bar, diverging bar, combo and donut "62,662 Total shipment id").
- Issues:
  - [High] 6 of 17 generated widgets are broken on first open, each showing "'<name>' is not a column or measure on this dataset": late_pct_vs_promised (headline KPI and the Levels page), delivery_attempts_pct_of_delivery_fee_egp, days_created_to_delivered, days_created_to_updated and days_late_vs_promised. The suggester previews these derived measures ("drawing every chart to make sure it says something"), but the dashboard it saves does not carry their definitions.
  - [Medium] None of the suggestions answer the stated question, which is "by branch". Every breakdown is by service_type, even though shipments links to branches (origin_branch_id). The app does admit this in "Your questions".
  - [Medium] Some suggestions do not make sense: "Delivery attempts pct of delivery fee egp" (attempts as a % of a money amount), "Total weight kg by service type", and "Total of 5 numbers" adding up weight, declared value, fees, COD and attempts. The KPI "Shipment count" shows the caption "countd(shipment_id)".
  - [Low] Two widgets are text-only duplicates ("5538 outlying rows move the average delivery_fee_egp by 63%" appears as both title and body).
  - [Low] The "Declared value against weight kg" scatter has its axes swapped or mis-scaled (y 0–9,000, x 0–0.2) and looks nearly empty.
  - [Low] The dashboard header says "Updated 1 hour ago" for a dashboard created seconds earlier (it carries the dataset refresh time).
- Console: none (the widget errors are rendered in-widget, not as failed API calls)
- Score: 2

### B2-54..59 — Nile review page after the full sync   (`/connections/2/review`)
- Screenshots: [B2-54-nile-review-after](screenshots/B_data/B2-54-nile-review-after.png), [B2-55-nile-relationships](screenshots/B_data/B2-55-nile-relationships.png), [B2-56-nile-columns](screenshots/B_data/B2-56-nile-columns.png), [B2-57-nile-entities](screenshots/B_data/B2-57-nile-entities.png), [B2-58-nile-drift](screenshots/B_data/B2-58-nile-drift.png), [B2-59-nile-health](screenshots/B_data/B2-59-nile-health.png)
- What it shows: "Synced", Last run ok · 8:29:58 PM. The run log shows describe 407,652 ms (6.8 min) and entities 135,121 ms (2.3 min), both "ok", even though no LLM exists. The relationship graph shows branches ↔ complaints/drivers/shipments. Columns (61) lists six tables. Entities (0). Schema drift baseline of 61 columns. Source health shows no filter advice yet.
- Works: ✅ The sync completes end to end. FIXED compared with wave 1 (that run was stuck at 0/6).
- Issues:
  - [Medium] The "describe" and "entities" steps are reported "ok" after 9 minutes of LLM timeouts, while the card says "No description yet" and "Entities (0)". A step that produced nothing because the AI was unreachable should say "skipped — AI unavailable" and fail fast.
  - [Low] "Relationships (0)" and "Nothing awaiting review" are shown even though the graph has 3 relationships and the run proposed 3. The tab count only counts pending items, which reads as "none".
  - [Low] "5 not profiled" shows in amber after a full ok run.
- Console: none
- Score: 3

### B2-60/61 — Sync error surfacing   (`/setup/1`, code review of main@0cb8f48)
- Screenshots: [B2-60-sqlite-setup-during-sync](screenshots/B_data/B2-60-sqlite-setup-during-sync.png), [B2-61-sqlite-setup-read-during-sync](screenshots/B_data/B2-61-sqlite-setup-read-during-sync.png)
- What I checked: I tried to reproduce the wave-1 409 by starting a sync and then opening the setup. The setup no longer shows "Read the database now" once the database has been read, so I could not trigger it in the UI. I checked the code instead:
  - Review page Run sync (frontend/src/pages/SourceReview.tsx:231–244) now shows `toast.error` on failure: "sync is already running" for 409 and "sync could not start" for anything else. So the wave-1 silent 500 on Run sync should now be visible. I could not confirm this live because no failure was reproducible after the restart.
  - Guided setup "Read the database now" (frontend/src/pages/setup/UnderstandStep.tsx:93): `try { await metadataApi.sync(sourceId) } catch { /* 409 … just watch it */ }`. This swallows EVERY error, including 500 and 403, and just reloads. The wave-1 silence on this button is PRESENT in code.
  - The "nothing is reading it now" message is a client-side heuristic (`neverRead = status syncing && sync pending && never synced`). It can still contradict a review page that shows a running sync, as in wave 1.
- Also: SQLite setup step 1 says "Demo — Live SQLite has 1 tables with 0 rows in total" next to a "Rows not counted" pill ("this database keeps no row counts"). Saying "0 rows" contradicts "not counted"; it should say "row count unknown".
- Issues: [High] Guided-setup "Read the database now" silently swallows all sync errors (code-confirmed). [Medium] "0 rows in total" for a 12,000-row SQLite table whose rows are not counted.
- Console: none
- Score: 3

### Summary: works now / still a bug / environment-only

#### Works now (fixed by the backend restart with its own DuckDB cache)
- Demo — Live SQLite Run sync completes in about 9 s (8 steps ok). Wave 1 got a 500.
- QA B Nile Express "Read the database now" starts the read immediately, and step 1 shows 6 tables / 71,729 rows / ranked tables within about 2 s. Wave 1 got a 409 and stayed at "Syncing 0/6" forever.
- The orphaned wave-1 runs are now shown as "Sync failed — Interrupted by a server restart" (list and review page), not "Syncing" forever.
- All four guided-setup steps can be reached end to end. A 3-page dashboard was created (/reports/24).
- Check & discover found 7 of the 9 planted problems with exact counts, and its fixes turn into sensible pipeline steps.

#### Still a bug (product / code)
| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| B2-1 | High | Setup step 3 | "Warn me on every refresh" → 500 every time (ImportError DataCheckIn in guided_setup.py:1577), with no message to the user | Import from `.datasets`, and show a toast on failure |
| B2-2 | High | Setup step 1 | "Read the database now" swallows all errors (UnderstandStep.tsx:93); the wave-1 silence is still in code | Toast on 4xx/5xx; for 409, say "already reading, x/6" |
| B2-3 | High | Setup step 4 → dashboard | 6 of 17 generated widgets fail: "'late_pct_vs_promised' … is not a column or measure" | Save the derived measures with the dashboard, or drop the widgets that fail |
| B2-4 | Medium | Setup steps 1–4, review | With no LLM available, each AI wait lasts minutes: Suggest datasets 1:40+, check about 7 min, describe 6.8 min marked "ok", step 1 spinners never stop. The header already knows the model is unreachable | Fail fast when the model is unreachable; mark steps "skipped — AI unavailable" |
| B2-5 | Medium | Setup step 3 | "The facts below are complete" with nothing below; the deterministic findings are held back by the AI calls | Return the plain checks first and add AI items later |
| B2-6 | Medium | Setup step 3 | declared_value stored as text is not flagged (it is summed as a number), and delivered-before-created (55 rows) is missed | Add a "numbers stored as text" check and a date-order check |
| B2-7 | Medium | Setup step 3 | Row and column counts stay at 64,420 · 26 after fixes (real 62,662 · 24) | Recompute after prep steps |
| B2-8 | Medium | Setup step 3 | One-click fixes change a dataset described as "already in use … nothing changed automatically", with no confirmation | Confirm and list the affected dashboards |
| B2-9 | Medium | Setup step 3 | Volume-driven "weight/fees far above usual" insights (Nov 2024 had twice the shipments; average weight is flat) | Normalise per row or say "because there were 2× shipments" |
| B2-10 | Medium | Setup step 4 | Suggestions ignore "by branch"; nonsense metrics ("attempts pct of delivery fee", "Total of 5 numbers") | Use the linked branches; block summing unrelated units |
| B2-11 | Medium | SQLite review | Header and tabs stay at "0 tables · 0 columns" after the sync completes, until reload; "0 rows in total" for 12,000 rows | Reload metadata on completion; say "rows not counted" |
| B2-12 | Medium | Setup step 1 | "Show details" looks like an expander but leaves the wizard | Expand inline or open a new tab |
| B2-13 | Low | Review | Counter says 1/6 while the log has 8 steps; raw step names (describe, entities, link_datasets); "Relationships (0)" while the graph shows 3; "not profiled" after a profile ran | Align the counters and labels |
| B2-14 | Low | Connections list | The Imports card "×" overlaps the "Open data…" button | Spacing |

#### Environment-only (not product bugs)
- Wave-1 409 on "Read the database now", 500 on Run sync and the 6+ min "Syncing 0/6": caused by the DuckDB metadata cache being locked by a parallel pytest run. These do not reproduce after the restart with its own cache file.
- No LLM service is available: AI suggestions, descriptions and entities never arrive, so all AI text is missing. The slow handling of that (B2-4/B2-5) is still a product issue.
- Heavy machine load (pytest still running, load average about 13 on 2 CPUs): the first driver commands timed out, and step timings (for example "Sample rows 64.8 s") are inflated.

### Area summary
- Score (avg): 3.1 / 5. The data-layer re-test confirms that the wave-1 blockers were caused by the environment. Sync and guided setup now run end to end, and the check step is strong: it found 7 of 9 planted problems with exact counts and plain-language, one-click fixes. The remaining problems are product issues: one hard 500 in "Warn me on every refresh" (an import bug), sync errors that guided setup still swallows, a generated dashboard where a third of the widgets are broken, and no fast-fail when the AI is offline, which turns a 10-second deterministic check into a 7-minute wait.
- Strengths: clear restart-interrupted status; fast facts in step 1 (row counts, date ranges, tables ranked "where to start", system tables separated); exact, well-worded data-quality findings with sensible fixes that become transparent pipeline steps; an honest "not answered on the pages chosen" note on the dashboard; a graceful "AI is taking longer than usual — continue" message.
- Not covered / blocked: I could not reproduce a sync failure live after the restart, so the toast on Run sync failure was verified only in code. "Query builder" in step 2, "Change it" per suggested page, and "Suggest again" were not exercised (time). I did not create "QA B2 Nile Express" because the existing connection was no longer stuck. Hard stop at 21:00.


---

## C — Dashboards & report builder
Coverage: ~45 screens/states / 100+ screenshots (C-00 … C-109). Account: admin@datalytics.local. Viewports: 1440×900, 820×1180, 390×844. Code under test: main 0cb8f48.

### C-00 — Home after login   (`/`)
- Screenshot: [C-00-login](screenshots/C_dashboards/C-00-login.png)
- What it shows: Home with offline-AI banner, stat cards, continue cards.
- Works: ✅ login ok (first attempts hit driver nav timeouts under load — environment, not app)
- Issues: None
- Console: 401 /auth/me before login (expected)
- Score: 4

### C-01 — Dashboards list   (`/reports`)
- Screenshot: [C-01-reports-list](screenshots/C_dashboards/C-01-reports-list.png)
- What it shows: Views (All 22/Recent/Shared), folders (Use cases, Widget gallery), search, status chips All/Drafts/Published/Everyone, dataset filter "Any", sort, grid/list toggle, folder-grouped cards.
- Works: ✅
- Issues: [Cosmetic] folder counts in left tree render as "··2"/"··7" (a stray dot glyph before the count). [Low] Search placeholder truncated "Search dashboar" next to the "/" hint.
- UX notes: The select-checkbox sits on top of thumbnail corner; "Open" button overlays the thumbnail bottom — fine.
- Console: none
- Score: 4

### C-02 / C-03 — Folder ⋯ menu & dashboard card ⋯ menu
- Screenshots: [C-02-card-menu](screenshots/C_dashboards/C-02-card-menu.png) (folder menu: New subfolder / Rename / Delete folder), [C-03-dashboard-card-menu](screenshots/C_dashboards/C-03-dashboard-card-menu.png)
- Card menu: Open, Open in edit mode, Copy link, Move to folder…, Rename, Export as PDF, Delete.
- Works: ✅ "Move to folder…" now exists. no "Duplicate" in the card menu.
- Issues: [Medium] No Duplicate / Save as copy on the card menu.
- Score: 4

### C-04/05/06 — Create a dashboard dialog (Blank / Template / With AI)
- Screenshots: [C-04-new-dashboard-dialog](screenshots/C_dashboards/C-04-new-dashboard-dialog.png), [C-05-new-dialog-template](screenshots/C_dashboards/C-05-new-dialog-template.png), [C-06-new-dialog-ai](screenshots/C_dashboards/C-06-new-dialog-ai.png)
- What it shows: three modes; Blank = name, dataset (Choose later default), folder; Template = 4 layouts (KPI overview, Four-panel comparison, Map and detail, Chart + detail); With AI = prompt + dataset, "Suggest dashboards" disabled until filled.
- Works: ✅ clean, clear dialog.
- Issues: [Low] Dataset list mixes QA uploads and demos without grouping/search; fine with 12 items, won't scale.
- Score: 4.5

### C-07/08 — Create → builder   (`/reports/23?edit=1`)
- Screenshots: [C-07-after-create](screenshots/C_dashboards/C-07-after-create.png), [C-08-builder-after-reload](screenshots/C_dashboards/C-08-builder-after-reload.png)
- Works: ⚠️ Builder now renders straight after Create. BUT the dataset picked in the dialog (Demo — Sales) is not shown: Fields says "Attach a dataset to this report to browse columns", DATASETS shows only "+ Add Dataset", report-filter presets missing. After a reload the dataset is attached (Demo — Sales primary, fields listed).
- Issues: [High] Dataset chosen in Create dialog not reflected in the builder until reload — user thinks the pick was lost and may add it twice.
- UX notes: After reload the header wraps — "— Unclassified —" classification select drops to a second line, title truncated to "QA C dash…" even with free space.
- Console: none
- Score: 3

### C-09 — Builder Insert tab (chart gallery)   (`/reports/23?edit=1`)
- Screenshot: [C-09-insert-tab](screenshots/C_dashboards/C-09-insert-tab.png)
- What it shows: "Search 77 chart types", 12 groups (Basic 8, Comparison 9, Trend 6, Distribution 4, Relationship 9, Part to whole 4, Flow & hierarchy 5, Maps 10, Models 9, Tables & cards 4, Controls 8, Layout 1). Hover shows a preview card with a one-line description.
- Works: ✅
- Issues: [Cosmetic] Search says 77 types while group counts add up to 77 — OK. Hover preview card overlaps the canvas/widget it is next to (C-24x) — acceptable.
- Score: 4.5

### C-10..C-13 — Add Bar chart + Assign data dialog
- Screenshots: [C-10-add-bar](screenshots/C_dashboards/C-10-add-bar.png), [C-11-assign-add-dimension](screenshots/C_dashboards/C-11-assign-add-dimension.png), [C-12-add-dimension-picker](screenshots/C_dashboards/C-12-add-dimension-picker.png), [C-13-bar-rendered](screenshots/C_dashboards/C-13-bar-rendered.png)
- What it shows: Clicking a type adds a 12×6 tile, opens "Assign data" modal (Dimension*, Series, Measure, Target). Field picker groups Dates/Numbers/Categories (with distinct counts)/Calculated/Hierarchies; measure picker is a multi-select checkbox list with search.
- Works: ✅ region × revenue renders with value labels 2.22M/2.2M/2.2M/2.01M and $ axis; tooltip "sum(revenue) : $ 2,010,526".
- Issues: [Low] Y-axis mixes formats: "$ 0", "$ 600,000", then "1.2M", "1.8M", "2.4M" (currency symbol dropped once it abbreviates). [Low] Value labels "2.2M" and "2.2M" for North America/Europe hide the difference — 3 significant digits would help. [Low] Tooltip label is the raw expression "sum(revenue)" not "Revenue".
- UX notes: Assign-data modal closes when you click a role "+ Add" (the field picker replaces it), then the role must be completed in the right panel — the flow jumps from modal to side panel.
- Console: none
- Score: 4

### C-14/15 — Add Pie with a widget selected; Pie rendered
- Screenshots: [C-14-click-pie-with-selection](screenshots/C_dashboards/C-14-click-pie-with-selection.png), [C-15-pie](screenshots/C_dashboards/C-15-pie.png), [C-15c](screenshots/C_dashboards/C-15c.png)
- Works: ⚠️ Clicking a type while a widget is selected ADDS a new widget (it does not convert) — ok. Pie shows outside labels "Software 40% / Hardware 31% / Services 29%".
- Issues: [High] While the Assign-data modal was open, clicking "+ Add" in the modal footer area hit the page-tab "+" and created **Page 2** and moved me there; the Properties pane kept showing the Pie widget from Page 1 (stale selection) and its edits then failed with **404 PATCH /api/v1/reports/23/pages/40/widgets/255** + uncaught AxiosError (pageerror). Same 404 PATCH pattern repeated later for widgets 257/258/259 when switching pages with a widget selected.
- [Medium] A pie with only a measure (no dimension) renders as one solid disc with a stray radius line instead of the "Needs Dimension" placeholder (C-15-pie first version).
- Console: 404 PATCH widgets/255, AxiosError
- Score: 2.5

### C-16 — Widget ⋮ menu in Edit mode
- Screenshot: [C-16-widget-kebab-edit](screenshots/C_dashboards/C-16-widget-kebab-edit.png)
- What it shows: Duplicate widget / Delete widget only. Hover toolbar above tile: drag, duplicate, dataset, filter.
- Works: ✅ menu positioned correctly.
- Score: 4

### C-20..23 — Word cloud
- Screenshots: [C-20-word-cloud](screenshots/C_dashboards/C-20-word-cloud.png), [C-21-wordcloud-assign](screenshots/C_dashboards/C-21-wordcloud-assign.png), [C-22-wordcloud-wordtext-picker](screenshots/C_dashboards/C-22-wordcloud-wordtext-picker.png), [C-23-word-cloud-after-reload](screenshots/C_dashboards/C-23-word-cloud-after-reload.png)
- Works: ❌ Word text = product (10 values), Size weight = revenue. Tile is completely blank — no words, no "no data" message — also after a full reload. 
- Issues: [High] Word cloud renders blank with valid roles. Also my first helper attempt put "revenue" (a number) into "Word text" and was accepted without warning.
- Score: 1

### C-24 — Scatter
- Screenshots: [C-24-scatter-assign](screenshots/C_dashboards/C-24-scatter-assign.png), [C-24-scatter](screenshots/C_dashboards/C-24-scatter.png)
- Works: ❌ Roles are Dimension* + Measure (single — "+ Add" greys out after one measure). With product + units, and with revenue only, the tile shows axes (sum(units) 0–60,000) but NO points. There is no way to give it an X and Y measure. 
- Issues: [High] Scatter renders empty axes; role model allows only one measure.
- Console: 404 PATCH widgets/258/259 while switching pages with selection.
- Score: 1

### C-25 — Flow (Sankey)
- Screenshot: [C-25-sankey](screenshots/C_dashboards/C-25-sankey.png)
- Works: ⚠️ Source=region, Target=category, Weight=revenue → ribbons and node bars render, but there are NO node labels at all, so it's unreadable. Flows use a single pale lavender — no colour by source.
- Issues: [High] Sankey has no node labels.
- Score: 2

### C-26 — Sunburst (Levels role)
- Screenshots: [C-26a-sunburst-levels](screenshots/C_dashboards/C-26a-sunburst-levels.png), [C-26-sunburst](screenshots/C_dashboards/C-26-sunburst.png)
- Works: ⚠️ "Levels" is now a role in Assign data (multi-select) with "Hierarchy source: Level columns / Parent-child". Region→category sunburst renders, but has NO segment labels and a single blue shade for every ring segment; impossible to read without hovering.
- Issues: [Medium] Sunburst: no labels, monochrome segments. [Low] Hierarchy picker (C-12) offers "Region ▸ Country ▸ Product" hierarchies, but the Levels dialog does not list them.
- Score: 2.5

### C-27 — Box plot
- Screenshot: [C-26-sunburst](screenshots/C_dashboards/C-26-sunburst.png) (left-bottom), [C-27-box](screenshots/C_dashboards/C-27-box.png)
- Works: ⚠️ Box per region renders; y axis "-12.01K / $ -4,991 / $ 2,029 / $ 9,049 / 16.07K" — mixed formats and odd ticks; category labels on x axis are ~4px and illegible.
- Issues: [Medium] Box plot x labels unreadable; [Low] mixed currency/abbrev ticks; negative revenue whiskers (data, but no explanation).
- Score: 2.5

### C-28 — Delete a widget (trash icon)
- Screenshot: [C-28-delete-empty-sunburst](screenshots/C_dashboards/C-28-delete-empty-sunburst.png)
- Works: ✅ widget removed immediately, no 500 seen on this delete. 404 PATCH happens when a page switch leaves a selected widget (see C-14/15).
- Score: 3.5

### C-29/30 — Histogram, Treemap
- Screenshots: [C-29-histogram](screenshots/C_dashboards/C-29-histogram.png), [C-30-treemap](screenshots/C_dashboards/C-30-treemap.png)
- Histogram: ⚠️ renders, but bin labels are raw floats "-12011.64–-9203.55", rotated 45°, no currency, and the y axis title is "count" while x-title is "sum(revenue)" (it is NOT a sum, it's per-row revenue). [Low]
- Treemap: ⚠️ product × revenue renders with colours, but labels overflow tiles and overlap ("Drift Onboarding PDrift Support Planet Hardware"), "Comet Sensor Pacl" clipped. [Medium]
- Score: 3

### C-31/32 — Funnel, Bar + line
- Screenshots: [C-31-funnel](screenshots/C_dashboards/C-31-funnel.png), [C-32-bar-line](screenshots/C_dashboards/C-32-bar-line.png)
- Funnel: ✅ now labels all 4 stages (Asia Pacific, Europe, Latin America; North America label first); labels sit outside right, values not shown.
- Bar + line (Dual Axis Bar-Line): ❌ margin_pct SUMMED → right axis "0.0% … 12000.0%" and legend "sum(margin_pct)". Right axis tick labels overlap the rotated axis title "sum(margin_pct)". X labels rotated though there is room.
- Issues: [Medium] percentage measure defaults to Sum; [Low] right axis title overlaps tick labels.
- Score: 2.5

### C-33/34 — KPI card, Gauge
- Screenshots: [C-33-kpi-gauge](screenshots/C_dashboards/C-33-kpi-gauge.png), [C-34-gauge](screenshots/C_dashboards/C-34-gauge.png)
- KPI: ✅ "$ 8,632,597 / revenue" fits. When narrow, the KPI title "KPI Ca…" is truncated by the hover icons (→ ← trash ⋮) [Low].
- Gauge: ⚠️ Value only → arc with "$ 8,632,597" split over two lines ("$" on its own line). No min/max labels; no indication what 100% means without a Target. [Low]
- Score: 3.5

### C-35 — Table
- Screenshot: [C-35-table](screenshots/C_dashboards/C-35-table.png) / [C-36-choropleth](screenshots/C_dashboards/C-36-choropleth.png)
- Works: ⚠️ region × revenue → "2221091.66" raw (no $ / thousands separator) while charts show $ 2,221,092. Header "sum(revenue)" raw expression. Footer "4 groups from 2,000 rows" is nice.
- Issues: [Medium] tables ignore measure format.
- Console: 404 PATCH widgets/271 + AxiosError right after adding (stale selection again).
- Score: 3

### C-36 — Choropleth map
- Screenshot: [C-36-choropleth](screenshots/C_dashboards/C-36-choropleth.png)
- Works: ✅ Country + Measure → shaded world map with zoom +/−/reset. No legend / colour scale shown. [Low]
- UX: after adding the Choropleth, the Properties pane still showed the previous Table widget until I clicked the tile (selection doesn't follow the new widget when Assign-data modal is skipped).
- Score: 4

### C-37..41 — Line, Waterfall, Crosstab, Heat map (Page 7)
- Screenshot: [C-41-page7-state](screenshots/C_dashboards/C-41-page7-state.png) (+ C-37..C-40 per type)
- Works: ⚠️ Line/Waterfall/Crosstab added; Crosstab region × category renders but values raw "670618.28 / 544755.48 / 795152.7" (no currency, inconsistent decimals) — same raw-format issue as Table. Heat map needs Rows + Cell value (Columns alone not enough) — placeholder "Needs Rows · Cell value" is clear.
- Console: 404 PATCH widgets/275 and /300 + AxiosError when a new page was added while a widget was selected.
- Score: 3

### C-42..45 — Display rules (conditional formatting)
- Screenshots: [C-42-format-search-rule](screenshots/C_dashboards/C-42-format-search-rule.png), [C-43-display-rule-added](screenshots/C_dashboards/C-43-display-rule-added.png), [C-44-rule-text-column-gt](screenshots/C_dashboards/C-44-rule-text-column-gt.png), [C-45-rule-region-gt-5](screenshots/C_dashboards/C-45-rule-region-gt-5.png)
- What it shows: Format → Display rules → "+ Add rule": Rule kind (Expression / Colour map / Bands / Data bar), Column, Operator, Value, Applies to (The mark / Widget background / Hide the widget), Fill colour, Remove, + Add rule.
- Works: ✅ Choosing a text column (region) limits operators to equals / does not equal / is one of / is blank / is not blank — the raw Python "'>' not supported between 'str' and 'int'" cannot be triggered. The settings search ("rule") jumping across tabs works well.
- Issues: [Low] Default column for a new rule is "year" (first numeric) rather than the widget's measure; [Low] the rule card is cramped — Fill swatch label "Fill" sits beside Applies-to select and "Remove" is a plain grey text link.
- Score: 4

### C-50..66 — View mode of all seeded dashboards (ids 1–10)
- Screenshots: C-50..C-54 (first 4 s), [C-55-view-3-after-12s](screenshots/C_dashboards/C-55-view-3-after-12s.png), [C-56-view-2-after-12s](screenshots/C_dashboards/C-56-view-2-after-12s.png), [C-57-view-3-after-scroll](screenshots/C_dashboards/C-57-view-3-after-scroll.png), C-58..C-66 *-rendered.png
- Works: ❌/⚠️ **Charts do not render until the user scrolls.** On first open (and even after 12 s idle) Time & Change shows 4 empty white tiles and Distributions / Projects & Feedback show "Loading…" forever; a single wheel scroll makes them all render instantly (C-57). Looks like an IntersectionObserver/lazy-render that never fires for tiles initially in view.
- Demos now open in **View** mode with an Edit button.
- Sales Overview (C-58): KPI "Revenue, cost and units" is clipped (third value "402,108" cut in half); "Revenue against target" gauge value "$ 8,632,597" cut off at the bottom; "Average margin % by product" renders as a dashed line with vertical 4px product labels — essentially empty at this size; "Live embed" tile blank. Hover toolbars (AI / expand / image) float over the title of the tile BELOW, overlapping titles in every row (e.g. covers "Revenue against target").
- Distributions (C-59): histogram, box plot, scatters OK; box-plot category labels illegible tiny glyphs; scatter "Weight against height" has all points squeezed to the right (x-axis starts at 0) — wasted 75% of plot.
- Time & Change (C-57): dual-axis charts OK; right-axis titles "sum(cost)" / "sum(units)" overlap tick labels; product labels rotated and overlapping.
- World Sales Map (C-54/61): tile "Where shipments concentrate" still "SAMPLE Needs Latitude · Longitude — The author has not finished this widget.". Large empty band above the first row. Second tile tab header "Total units (tab)" partially covered by the hover toolbar.
- Use case — Can I trust this data? (C-65): "Rows" and "Missing cost" both show "$ 2,000" formatted as currency and "count(cost)" counts non-missing; "Prepared" tile "Needs Fields — author has not finished"; as-loaded and prepared charts identical.
- Models (C-62): regression, tree, comparison, scoring render well — nice.
- UX Showcase (C-63): page 1 has 4 small tiles and ~60% empty canvas; buttons render.
- Console: 404 GET /api/v1/datasets/{2,3,6}/analysis on Distributions, Projects & Feedback, Live Orders.
- Issues: [High] charts never render until scroll (affects first impression of every demo); [High] World Sales Map unfinished tile; [High] Use-case trust dashboard wrong counts/format; [Medium] KPI/gauge clipping; [Medium] hover toolbars overlap neighbouring tile titles; [Low] 404 /analysis calls.
- Score: 2.5

### C-70/71 — Widget ⋮ menu in View mode; Explain
- Screenshots: [C-70-view-widget-menu](screenshots/C_dashboards/C-70-view-widget-menu.png), [C-71-explain-revenue](screenshots/C_dashboards/C-71-explain-revenue.png)
- Works: ✅ Menu now opens in place: "Why am I seeing this? / Explain revenue / Export data as CSV / Export data as Excel". Hover bar gives AI, Focus (expand), Copy as image.
- Explain revenue opens "What moves revenue — Looking at every column…" modal (no AI needed); stayed on that text for the ~6 s observed.
- Score: 4

### C-72/73 — Export dialog
- Screenshots: [C-72-export-menu](screenshots/C_dashboards/C-72-export-menu.png), [C-73-export-pdf-result](screenshots/C_dashboards/C-73-export-pdf-result.png)
- What it shows: Export "<name>": PDF (server) / Data (Excel) / Offline package (HTML) / Print; Paper A4/Letter/A3; Orientation; Contents page; page chips; preview with page thumbnails 1/2.
- Works: ✅ Export PDF → "Preparing your file… usually under a minute" modal. Much better than before → Changed.
- Score: 4

### C-74 — Present mode
- Screenshot: [C-74-present-mode](screenshots/C_dashboards/C-74-present-mode.png)
- Works: ❌ Full-screen present view shows every data tile stuck on "Loading…" (same lazy-render bug; no scroll possible in present). Bottom 10% of the screen is empty grey.
- Issues: [High] Present mode shows no data.
- Score: 1.5

### C-75 — Print page   (`/reports/1/print`)
- Screenshot: [C-75-print-page](screenshots/C_dashboards/C-75-print-page.png)
- Works: ✅ "Print / Save as PDF", "Download PowerPoint", "Back to report"; all KPIs fit (not clipped here), monthly chart shows partial-month footnote. Breadcrumb says "Dashboards" only.
- Score: 4

### C-80..82 — My dashboards   (`/portal`, NEW)
- Screenshots: [C-80-my-dashboards](screenshots/C_dashboards/C-80-my-dashboards.png), [C-81-my-dash-favourites](screenshots/C_dashboards/C-81-my-dash-favourites.png), [C-82-my-dash-empty-search](screenshots/C_dashboards/C-82-my-dash-empty-search.png)
- What it shows: Tabs All 25 / Made by me 14 / Shared with me 1 / My team 0 / Favourites / Recently opened 24 / Reports sent; search; Category/Tag/Owner filters; cards with Yours/Draft/Published/tag chips and star.
- Works: ✅ Star → Favourites 1 immediately; search "zzz" → "Nothing matches. Try fewer words or clear the filters."
- Issues: [Low] "1 dashboards" (plural). [Low] URL /my-dashboards is a 404 — page lives at /portal; sidebar label and URL disagree. [Low] Cards for dashboards without description are mostly empty white space; no thumbnail (the /reports list has thumbnails). [Cosmetic] World Sales Map shows both "Published" and "Draft" chips.
- Console: none
- Score: 4

### C-83 — Classification
- Screenshot: [C-83-classification-confidential](screenshots/C_dashboards/C-83-classification-confidential.png)
- Works: ❌ Selecting "Confidential" shows a red "DATA: CONFIDENTIAL" badge but the toast says **"Classification cleared"**.
- Score: 2.5

### C-84..87 — Comments
- Screenshots: [C-84-comments-pane](screenshots/C_dashboards/C-84-comments-pane.png), [C-86-comment-typed](screenshots/C_dashboards/C-86-comment-typed.png), [C-87-comment-posted](screenshots/C_dashboards/C-87-comment-posted.png)
- Works: ✅ The Post button is not covered by the copilot button. Comment posted with "Pin to current page" checked; shows author, page, time, ✕.
- Issues: [Medium] Immediately after posting/classifying, a yellow banner "This report was changed in another session. Reload to see those edits" appears although only this session edited. [Low] Posted comment scrolls the author line out of view at the top of the pane.
- Score: 3.5

### C-88/89 — AI copilot
- Screenshots: [C-88-copilot-open](screenshots/C_dashboards/C-88-copilot-open.png), [C-89-copilot-answer](screenshots/C_dashboards/C-89-copilot-answer.png)
- Works: ✅ AI pane (Ask / Insights / Suggest) shows "The model server isn't reachable, so new questions are paused." and a locked, disabled input. The floating FAB only shows a tooltip "Ask AI about this dashboard Ctrl /" on click (the first click did not open the pane) [Low].
- Score: 4

### C-90 — Suggest pane
- Screenshot: [C-90-suggest-pane](screenshots/C_dashboards/C-90-suggest-pane.png)
- Works: ✅ 5 deterministic suggestions with thumbnails, grouped Compare 4 / Trend 1, "+ Add", "More ideas". Wording "Asia Pacific leads distinct year with 2" / "Aurora Suite leads distinct year with 2" is meaningless (counts distinct years) [Medium].
- Score: 3.5

### C-91/92 — Resize + Undo
- Screenshots: [C-91-resize-bar](screenshots/C_dashboards/C-91-resize-bar.png), [C-92-undo](screenshots/C_dashboards/C-92-undo.png)
- Works: ⚠️ Drag on resize handle of Bar Chart did not visibly resize (slight layout shift only); after it the whole AI pane got text-selected (blue highlight over the pane) — the drag selected text instead of resizing. Undo button present and reverts.
- Issues: [Medium] Resize drag selects page text; resize handle hard to hit.
- Score: 2.5

### C-93..96 — Responsive
- Screenshots: [C-93-tablet-view](screenshots/C_dashboards/C-93-tablet-view.png) (820×1180), [C-94-tablet-builder](screenshots/C_dashboards/C-94-tablet-builder.png), [C-95-phone-view](screenshots/C_dashboards/C-95-phone-view.png) (390×844), [C-96-phone-list](screenshots/C_dashboards/C-96-phone-list.png)
- Tablet view: ✅ 4-column grid still fits; title truncated "Demo — S…" on its own line under the toolbar with a stray vertical divider; toolbar wraps.
- Tablet builder: ❌ Left gallery + Properties pane stay open, the canvas is squeezed to a ~180px column with miniature unreadable tiles; tab strip overflows ("Pa…"), View button cut off at right edge.
- Phone view: ⚠️ Tiles stack 1-up, KPIs readable; header action row overflows horizontally ("Subscr…" cut), "No filters app…" cut. Title row good.
- Score: 2.5

### C-97..100 — List actions: Move to folder, Rename, Delete confirm
- Screenshots: [C-97-move-to-folder](screenshots/C_dashboards/C-97-move-to-folder.png), [C-98-rename](screenshots/C_dashboards/C-98-rename.png), [C-99-renamed](screenshots/C_dashboards/C-99-renamed.png), [C-100-delete-confirm](screenshots/C_dashboards/C-100-delete-confirm.png)
- Works: ✅ Move dialog lists folders with clear copy ("Nothing is copied or deleted…"), Move disabled until a folder is picked. Rename inline dialog → saved ("QA C dashboard renamed"). Delete opens an in-app confirm (Cancel/Delete) — cancelled to keep the QA artefact.
- Issues: [Medium] no Duplicate in the card menu.
- Score: 4

### C-101/102 — Cross-filter (slicer) and page filter
- Screenshots: [C-101-cross-filter-region](screenshots/C_dashboards/C-101-cross-filter-region.png), [C-102-filter-pane](screenshots/C_dashboards/C-102-filter-pane.png)
- Works: ✅ Clicking "Asia Pacific" in the Region slicer filters all tiles (Total revenue $ 2,221,092, units 102,974, Revenue by region single bar); chip "region in (Asia Pacific) ×", "Reset filters", undo/redo arrows; tiles show "1 filter" badges; line chart shows "showing 12/24". Filter popover "Filter the whole page by…" lists typed columns with search.
- Issues: [Low] "1 filter" badge on static tiles (Logo, Divider, Explore, Live embed) where it is meaningless; it also collides with the tile's hover icons. [Low] A floating "# 1 filter" pill sits over the bottom-left of the Revenue-by-region chart.
- Score: 4

### C-103..109 — Builder Layout menu, Data tab, Model tab, page size
- Screenshots: [C-103-layout-menu](screenshots/C_dashboards/C-103-layout-menu.png), [C-104-layout-after-escape](screenshots/C_dashboards/C-104-layout-after-escape.png), [C-105-data-tab](screenshots/C_dashboards/C-105-data-tab.png), [C-106-model-tab](screenshots/C_dashboards/C-106-model-tab.png), [C-107-layout-menu-toolbar](screenshots/C_dashboards/C-107-layout-menu-toolbar.png), [C-108-layout-after-escape](screenshots/C_dashboards/C-108-layout-after-escape.png), [C-109-page-size-custom](screenshots/C_dashboards/C-109-page-size-custom.png)
- Layout templates menu: 9 presets (Executive, KPI board, 2×2, Split, Spotlight, Comparison, Detail, Three-up, Free layout) with clear descriptions. ❌ Menu does NOT close with Escape or outside click and stays open over the Properties pane even after clicking "Custom" page size.
- Page size "Custom": ❌ selecting Custom shows no width × height inputs.
- Data tab: ✅ paged data grid (2,000 rows, 20 pages), data views templates, calc columns (profit, days_month_to_date, QA B calc), custom functions, and Display formats panel per column (revenue/cost = $ Currency, decimals, units, symbol, prefix/suffix). Note: revenue/cost have $ Currency set here, yet Table/Crosstab widgets ignore it.
- Model tab: ✅ empty state "Add a second dataset to this report to define relationships between them." — but the page-status footer floats directly below that one line, leaving the rest of the canvas blank grey [Cosmetic].
- Score: 3


### C-110 — Subscribe dialog (View mode)
- Screenshot: [C-110-subscribe-dialog](screenshots/C_dashboards/C-110-subscribe-dialog.png)
- What it shows: "Email me this report — Sent to your own address, containing the rows you can see": How often (daily/weekly/monthly), At (hour list), Format (Excel .xlsx), Cancel / Subscribe.
- Works: ✅ clear and compact. Not submitted (no mail server here).
- Issues: [Low] No weekday / day-of-month selector appears for weekly/monthly in the initial state; no timezone shown next to "08:00".
- Score: 4

### C-111 — Version history (builder)
- Screenshot: [C-111-version-history](screenshots/C_dashboards/C-111-version-history.png)
- What it shows: Today — Revision 986/985/984/983 by admin with "7 pages · 25 widgets", and a grouped "46 changes — Saved within seconds of each other, as one action".
- Works: ✅ readable timeline with grouping. Restore not tried (time).
- Issues: [Low] Revisions have no description of what changed — only counts; 4 revisions in 6 minutes all say "7 pages · 25 widgets". The status bar says "4 widgets" for Page 1 vs "25 widgets" for the whole report — fine but could confuse.
- Score: 3.5

### C-112..115 — Pages: rename, tab menu, page settings
- Screenshots: [C-112-before-rename](screenshots/C_dashboards/C-112-before-rename.png), [C-113-page-renamed](screenshots/C_dashboards/C-113-page-renamed.png), [C-114-page-tab-menu](screenshots/C_dashboards/C-114-page-tab-menu.png), [C-115-delete-page](screenshots/C_dashboards/C-115-delete-page.png)
- Works: ✅ TAB NAME field renames the tab live ("QA C Overview"). Tab ▾ menu: Rename / Move left (disabled on first) / Move right / Page settings / Delete page — tabs can now be reordered. Page 7 shows Waterfall "Needs Delta" (Waterfall role is "Delta", not Measure) and the Crosstab with raw numbers. Delete page not executed (time).
- Issues: [Low] fill "Page 1" via the driver selected all page text (Ctrl+A leaked to document when focus wasn't in an input) — visible in C-112 as whole page highlighted; normal user unlikely to hit. [Medium] Custom page size: no W×H inputs (C-113).
- Score: 4

### Area summary
- Top issues:

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| C-55/57/74 | High | View mode & Present | Charts render only after a scroll; Present mode shows "Loading…" on every tile | Trigger initial render for tiles already in the viewport (IntersectionObserver initial check / rootMargin); render eagerly in Present |
| C-20/24 | High | Gallery | Word cloud blank; Scatter shows empty axes and allows only one measure | Fix word-cloud layout/data mapping; give scatter X/Y measure roles; empty-state text when nothing to plot |
| C-25 | High | Gallery | Sankey has no node labels | Draw node labels (inside/outside by space) |
| C-14/15 | High | Builder | Stale widget selection after page add/switch → 404 PATCH + uncaught AxiosError; "+ Add" near modal hit page "+" | Clear selection on page change; ignore/cancel PATCH for widgets not on current page; catch errors |
| C-07 | High | Create → builder | Dataset picked in Create dialog not shown until reload | Invalidate report/dataset query after create |
| C-54/65 | High | Seeded demos | World Sales Map unfinished tile; "Can I trust this data?" counts/format wrong and "Prepared" tile unfinished | Fix seed configs |
| C-32 | Medium | Bar+line | margin_pct summed → 12000% | Default avg for % measures |
| C-35/41 | Medium | Table/Crosstab | Raw numbers ignore the column display format ($ Currency set on Data tab) | Apply display formats in table cells |
| C-58 | Medium | Sales Overview | Multi-KPI and gauge values clipped; hover toolbars overlap titles of tiles below | Auto-fit; anchor hover bar inside the tile |
| C-83 | Medium | Classification | Setting Confidential toasts "Classification cleared" | Fix toast text |
| C-86 | Medium | Builder | False "changed in another session" banner after own edits | Ignore own-session revisions |
| C-107/109 | Medium | Builder | Layout menu won't close; Custom page size has no inputs | Shared dismiss logic; W×H inputs |
| C-94 | Medium | Responsive | Builder at 820px leaves ~180px canvas | Auto-collapse side panes < 1024px |
| C-30/26/27 | Medium | Treemap/Sunburst/Box | Overflowing / missing / illegible labels | Fit-or-hide labels; colour by level |
| C-03 | Medium | List | No Duplicate dashboard | Add Duplicate / Save as copy |

- Strengths:
  - Clean "Create a dashboard" dialog (Blank / Template / With AI) and 4 layout templates with previews.
  - Chart gallery with 77 types, search, hover descriptions and "SAMPLE Needs X · Assign data" placeholders that say exactly what's missing.
  - Assign-data flow with typed field picker (dates/numbers/categories with distinct counts, calc fields, hierarchies).
  - View-mode widget menu (Why am I seeing this / Explain / CSV / Excel), Focus, Copy as image.
  - Cross-filtering via slicer with chips, reset, undo/redo, per-tile filter badges.
  - Export dialog (PDF/Excel/HTML/Print, paper, orientation, contents page, page chips, preview); print page with PPTX.
  - AI offline handling is now clear and non-blocking; deterministic Suggest pane still works offline.
  - Models demo renders rich, readable statistical output.
  - My dashboards portal: tabs, filters, favourites, good empty-search text.
- Not covered / blocked and why:
  - Hard stop at 21:20 and slow environment (driver navigation timeouts at start) limited the gallery to ~22 of 77 chart types: covered Bar, Pie, Word cloud, Scatter, Sankey, Sunburst, Box, Histogram, Treemap, Funnel, Bar+line, KPI, Gauge, Table, Choropleth, Line, Waterfall, Crosstab, Heat map (partially). Not covered: remaining maps (Point/Line/Cluster/Pie/Layered/Density/Contour/Geo network/Bubble map), models group, Matrix/List/Card, controls (Text/Image/Web/Script/Shape/Button), Container, Gantt, Forecast, Decomposition/Tree/Org/Dendrogram, Icicle/Circle packing, Network/Parallel/Vector, Butterfly/Ribbon/Small multiples, Needle, Step/Compare series.
  - Not covered: Default vs Modern theme switch, parameters, drill-down, page delete, page background, second aggregation, relative-date filters, calc-field creation, version-history restore, alerts dialog, dashboard style/looks, Present navigation, Data checks.
  - Share / Publishing / Archive / guest links intentionally skipped (owned by F2).
  - Delete was opened (in-app confirm) and cancelled to keep the QA artefact "QA C dashboard renamed" (report 23) for evidence.


---

## C3 — Remaining chart types (part 1)
Account: admin@datalytics.local. Viewport 1440x900. Dashboard "QA C3 charts" (/reports/26) on Demo — Sales.

### C3-01..03 — New dashboard dialog / empty builder / Insert gallery
- Screenshots: [C3-01-new-dashboard-dialog](screenshots/C_dashboards/C3-01-new-dashboard-dialog.png), [C3-02-builder-empty](screenshots/C_dashboards/C3-02-builder-empty.png), [C3-03-insert-panel](screenshots/C_dashboards/C3-03-insert-panel.png)
- Works: ✅ dialog with Blank/Template/With AI, name + dataset + folder; Create lands in /reports/26?edit=1 with empty-page guidance. Insert gallery: "Search 77 chart types", grouped (Basic 8, Comparison 9, Trend 6, Distribution 4, Relationship 9, Part-to-whole 4, Flow & hierarchy 5, Maps 10, Models 9, Tables & cards 4, Controls 8, Layout 1).
- Issues: None
- Score: 4

### C3-04..08 — Butterfly (channel × revenue | cost)
- Screenshots: [C3-04-butterfly-added](screenshots/C_dashboards/C3-04-butterfly-added.png), [C3-05-assign-picker](screenshots/C_dashboards/C3-05-assign-picker.png), [C3-07-butterfly-assigned](screenshots/C_dashboards/C3-07-butterfly-assigned.png), [C3-08-butterfly](screenshots/C_dashboards/C3-08-butterfly.png)
- What it shows: clicking a gallery tile adds the widget AND auto-opens an "Assign data" dialog listing required roles (Dimension / Left side / Right side). Each "+ Add" opens a field picker with search.
- Works: ✅ renders with currency axis ($3,000,000 … $0 … $3,000,000, mirrored, abs values), tooltip "Retail / Left: $2,222,562 / Right: $2,015,234".
- Issues:
  - [Low] Left and right bars are vertically offset from each other and from the category tick (left bar above the tick, right bar below) — looks like grouped bars rather than a true butterfly with both halves on one baseline.
  - [Low] No legend and tooltip says "Left"/"Right" instead of the field names (revenue/cost); x-axis title says only "sum(revenue)" though the right half is cost.
  - [Cosmetic] Field picker inconsistent: first picker shows typed chips ("# revenue", "Aa channel · 4 values", hierarchies) but the "Add Right side" picker shows plain names only, no type icons.
- Console: none
- Score: 3

### C3-09 — Dual axis bar (region × revenue | units)
- Screenshot: [C3-09-dual-axis-bar](screenshots/C_dashboards/C3-09-dual-axis-bar.png)
- Works: ⚠️ renders two y-axes ($ revenue left 0–2.4M, units right 0–120,000) with legend; before 2nd measure it renders a plain bar.
- Issues:
  - [Medium] Default tile placed at 4 columns wide (col 9–12): with two axes + two axis titles the plot area collapses to ~30 px; bars become hairlines and the 4 x-axis labels overlap into an illegible blob. Needs a wider default size for dual-axis types or label auto-hide.
  - [Low] Both roles are labelled "Bars" / "Bars" — should say "Left axis" / "Right axis" so users know which measure goes where.
  - [Low] Empty state "SAMPLE / Needs Dimension · Bars · Bars" repeats the ambiguity.
- Console: none
- Score: 2.5

### C3-10 — Dual axis line (month × revenue | margin_pct)
- Screenshot: [C3-10-dual-axis-line](screenshots/C_dashboards/C3-10-dual-axis-line.png)
- Works: ✅ renders 24 months, two lines, two axes ($ left, % right), legend. Briefly shows axes with no lines before data arrives (no loading indicator).
- Issues:
  - [Medium] margin_pct defaults to SUM aggregation → right axis shows up to 2600.0% (meaningless). Percent/ratio columns should default to AVG.
  - [Low] Right-axis title "sum(margin_pct)" is drawn on top of the tick labels (overlap "1950.0%").
  - [Cosmetic] Right-axis ticks oddly stepped (650/1300/1950/2600%) and one decimal "0.0%".
- Console: none
- Score: 3

### C3-11 — Dot plot (product × revenue)
- Screenshot: [C3-11-dot](screenshots/C_dashboards/C3-11-dot.png)
- Works: ✅ 10 products sorted desc, dots aligned, axis $0 / $500,000 / 1M, title "sum(revenue)".
- Issues:
  - [Low] Axis tick format inconsistent: "$ 500,000" then "1M" (no $, abbreviated) on the same axis.
  - [Cosmetic] Gallery search: typing "Dot" in "Search 77 chart types" and clicking it added two Dot Plot widgets in one go (once via search result, once via the tile) — had to delete one. Also adding a new widget re-flows existing tiles (Dual Axis Line shrank to half width and gained a range slider that overlaps x labels).
- Console: none
- Score: 3.5

### C3-12 — Ribbon (month × category, revenue)
- Screenshot: [C3-12-ribbon](screenshots/C_dashboards/C3-12-ribbon.png)
- Works: ✅ ranked stacked columns with ribbons between periods, legend Hardware/Services/Software, quarterly x labels.
- Issues:
  - [Low] No y-axis at all — impossible to read magnitudes without hovering.
  - [Cosmetic] x labels tiny (~8px) and last two ("2025-10", "2025-12") nearly touch; chart doesn't use full tile width (large left/right margins).
  - [Cosmetic] Gallery tile hover-card ("Ribbon — Compare values side by side") stays open over the canvas after clicking, covering the new chart; description text "Compare values side by side" is reused for Dual axis Line and Ribbon (generic copy).
- Console: none
- Score: 3.5

### C3-13/14 — Small multiples (region × revenue, facet by channel)
- Screenshots: [C3-13-small-multiples](screenshots/C_dashboards/C3-13-small-multiples.png), [C3-14-small-multiples-faceted](screenshots/C_dashboards/C3-14-small-multiples-faceted.png)
- Works: ✅ with only Category+Measure it renders a single "All" panel (ranked bar list with values); after setting "Facet by = channel" (Data & aggregation section, not in Assign data) it renders 4 panels Retail/Partner/Wholesale/Online, each sorted desc with $ values.
- Issues:
  - [Medium] The facet ("by what to split into multiples") — the defining role of a small-multiples chart — is not a data role in "Assign data"; out of the box the chart shows a single "All" panel which is not a small multiple at all. Make Facet a required role.
  - [Low] Values rendered in a monospace font with a space after "$" ("$ 593,968"), inconsistent with other charts; panel 4 wraps to a 2nd row leaving a big empty area and the 4th panel's last bar touches the tile's bottom edge (slight clipping).
  - [Low] Facet-by select lists measures (revenue, units, cost…) as facet options — faceting by a continuous measure makes no sense.
  - [Cosmetic] While the native facet <select> was open the driver's screenshot took ~44 s (page busy) — possibly heavy re-render on hover.
- Console: none
- Score: 3

### C3-15 — Step plot (month × units)
- Screenshot: [C3-15-step](screenshots/C_dashboards/C3-15-step.png)
- Works: ✅ step line with markers, y 0–18,000, x months, range slider below.
- Issues:
  - [Low] Line-type charts with a date x-axis auto-add a range brush that defaults to only the last ~12 months (2025-02..2025-12) although data spans 2024-01..2025-12 — users may not realise half the data is hidden. Same on Dual axis line (which before re-flow showed all 24 months).
  - [Cosmetic] Y axis starts at 0 so the steps are squashed into the top 10% of the plot.
- Console: none
- Score: 3.5

### C3-16 — Dual axis time series (date × revenue | units)
- Screenshot: [C3-16-dual-axis-time](screenshots/C_dashboards/C3-16-dual-axis-time.png)
- Works: ⚠️ renders two lines on two axes with brush and legend, but only the first 50 of 633 dates.
- Issues:
  - [Medium] Daily date field is truncated by a default "row limit" of 50 ("Showing 50 of 633 date values", badge "showing 28/50") — a time-series chart showing only Jan 25–Feb 24 2024 by default is misleading. Should auto-bucket (week/month) or lift the limit for time axes.
  - [Medium] Left axis extends to "$ -11,000" although revenue is never negative (smoothing/nice-scale artefact) — wrong-looking negative money.
  - [Low] Right-axis title "sum(units)" overlaps right tick labels (same as Dual axis line); 30 rotated daily labels are dense.
- Console: none
- Score: 2.5

### C3-17 — Comparative time series (month × revenue vs target) ("Compare series" tile)
- Screenshot: [C3-17-compare-series](screenshots/C_dashboards/C3-17-compare-series.png)
- Works: ✅ two lines on twin axes, legend "revenue"/"target".
- Issues:
  - [Low] Right axis repeats the same scale without "$" (600,000 vs $ 600,000) — for a compare-two-series chart in the same unit a single shared axis is expected; mixed formatting is confusing.
  - [Cosmetic] First x labels "2024-01"/"2024-02" overprint each other; vertical labels hard to read.
  - [Cosmetic] Gallery tile "Compare series" ↔ widget title "Comparative Time Series" naming mismatch (also "Dual axis time" ↔ "Dual Axis Time Series", "Needle" ↔ "Needle Plot").
- Console: none
- Score: 3.5

### C3-18 — Numeric series plot (units × revenue)
- Screenshot: [C3-18-numeric-series](screenshots/C_dashboards/C3-18-numeric-series.png)
- Works: ⚠️ renders a connected line+markers over numeric x (units 0–100) but shows only 500 of 2,000 points ("row limit" slider).
- Issues:
  - [Low] Axis titles say "sum(units)"/"sum(revenue)" but the points are row-level values (y goes negative to $-17,000 — row-level returns), so the "sum" label is misleading.
  - [Low] Joining unsorted row-level points with a line produces a zig-zag scribble; numeric series should aggregate per x or default to markers only.
  - [Low] Default 500-row cap again silently truncates.
- Console: none
- Score: 2.5

### C3-19 — Forecast (month × revenue)
- Screenshot: [C3-19-forecast](screenshots/C_dashboards/C3-19-forecast.png)
- Works: ✅ actuals 2024-01..2025-12, "now" marker, dashed forecast line with shaded band for 6 future months (to 2026-06).
- Issues:
  - [Low] Forecast is essentially flat (dashed horizontal line) and the confidence band is a small rectangle — no legend explains "forecast"/band/interval or method.
  - [Cosmetic] 30 vertical x labels squeeze; "2024-01"/"2024-02" overprint.
- Console: none
- Score: 3.5

### C3-20 — Matrix (region × category, revenue)
- Screenshot: [C3-20-matrix](screenshots/C_dashboards/C3-20-matrix.png)
- What it shows: before roles are set, a new Matrix shows the raw dataset rows (all columns, wrapped dates "2025-\n02-23") instead of an empty state. With Rows only → counts per region ("4 groups from 2,000 rows"). With Columns → count crosstab. With Values=revenue → sum crosstab.
- Works: ⚠️ pivot is correct but formatting is poor.
- Issues:
  - [High] Matrix values are raw unformatted floats ("700019.84", "871293.04", "795152.7") — no currency, no thousands separators, inconsistent decimals — while every other chart formats revenue as "$ 700,020".
  - [Medium] Matrix / List / Crosstab role pickers are multi-select (checkbox + "Add" button) unlike single-click pickers elsewhere; selecting a field does nothing until you notice the "Add" button — inconsistent interaction.
  - [Low] No row/column totals by default; values left-aligned instead of right-aligned numbers.
  - [Low] Unconfigured Matrix renders the raw table rather than the "SAMPLE / Needs Rows / Assign data" empty state used by other types.
- Console: none
- Score: 2.5

### C3-21 — List (product, revenue)
- Screenshot: [C3-21-list](screenshots/C_dashboards/C3-21-list.png)
- Works: ✅ with Dimension only it lists products with row counts (217, 212…); with Measure=revenue shows "$ 967,375" sorted desc. Clean, legible.
- Issues:
  - [Low] Values in monospace green font with "$ " spacing — differs from table/matrix style. Before any role assigned, list shows raw dates (first column) rather than an empty state.
- Console: none
- Score: 4

### Area summary
Coverage: 15 chart types attempted / 13 rendered and evaluated (Butterfly, Dual axis bar, Dual axis line, Dot, Ribbon, Small multiples, Step, Dual axis time, Compare series, Numeric series, Forecast, Matrix, List). 21 screenshots C3-01..C3-21 (C3-tmp.png is scratch). A Card widget was added at the hard stop but not configured. Account admin@datalytics.local, 1440x900, dashboard "QA C3 charts" (/reports/26).

- Score (avg): ~3.1. Every chart type tried renders without console errors or failed API calls. The flow (gallery tile → automatic "Assign data" dialog → role pickers) is quick. Most problems are about defaults and formatting: SUM applied to percentages, row limits silently cutting off time series, two-axis charts squeezed into 4-column tiles, inconsistent number formats (Matrix raw floats, "$ 500,000" next to "1M"), and axis titles drawn over tick labels.

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| C3-1 | High | Matrix | Values shown as raw floats (700019.84) with no currency or thousands separators | Apply the field's format (currency) as other charts do |
| C3-2 | Medium | Dual axis time | Daily date axis cut to 50 of 633 values by default; the axis goes to $-11,000 | Auto-bucket dates or lift the limit for time axes; clamp the axis at 0 for non-negative data |
| C3-3 | Medium | Dual axis line | margin_pct summed, so the axis reaches 2600% | Default to AVG for ratio/percent columns |
| C3-4 | Medium | Dual axis bar | Default 4-column tile makes the bars hairlines and the x labels overlap | Wider default tile for dual-axis types; hide labels when they collide |
| C3-5 | Medium | Small multiples | Facet is not a data role, so the default shows a single "All" panel | Make Facet a required role in Assign data; exclude measures from it |
| C3-6 | Medium | Matrix/List pickers | Multi-select picker needs a separate "Add" click, unlike the single-click pickers elsewhere | Use one picker interaction everywhere |
| C3-7 | Low | Dual axis line/time | Right-axis title overlaps the tick labels | Add padding for the right axis title |
| C3-8 | Low | Butterfly | No legend; tooltip says Left/Right; axis title shows only the left measure | Use the field names in the legend, tooltip and axis |
| C3-9 | Low | Step/line charts | Range brush defaults to the last 12 months, hiding half the data | Default the brush to the full range |
| C3-10 | Low | Numeric series | Row-level points joined by a line (scribble), axis titled "sum", 500-row cap | Aggregate per x or use markers only; correct the axis label |
| C3-11 | Low | Dual axis bar | Both roles named "Bars"/"Bars" | Rename to Left axis / Right axis |
| C3-12 | Cosmetic | Gallery | Hover card stays over the canvas after adding; generic descriptions; tile and widget names differ | Close the hover card on click; use specific copy and consistent names |

Strengths
- One-click add with the Assign data dialog opening on its own; required roles are clearly marked; the "SAMPLE / Needs …" empty states help.
- Searchable, typed field picker that includes hierarchies and calculated fields.
- Currency formatting is consistent on most axes and tooltips; Forecast shows a "now" marker and a band.
- No console errors or failed API calls on any chart.

Not covered / blocked and why
- Hard stop at 21:45 reached. Not done: Gantt (Demo — Projects), Needle, Card (added, not configured), Decomposition tree, Tree, Org chart, Dendrogram, Icicle, Circle packing, Network, Parallel coordinates, Vector, Bubble, Area, Donut.


---

## C4 — Maps, models & controls
Coverage (in progress): admin@datalytics.local, 1440x900, dashboard "QA C4 maps" (/reports/27) on Demo — Routes.
Driver note: each screenshot took ~70 s on this shared box (load), which limited coverage before the 21:45 hard stop.

### C4-01 — Create a dashboard dialog   (`/reports`)
- Screenshot: [C4-01-new-dashboard-dialog](screenshots/C_dashboards/C4-01-new-dashboard-dialog.png)
- What it shows: Blank / Template / With AI cards, name, dataset, folder.
- Works: ✅ named "QA C4 maps", picked Demo — Routes, Create → /reports/27?edit=1
- Issues: None
- Score: 5

### C4-02/03/04 — Empty builder + Insert gallery + search "map"
- Screenshots: [C4-02-builder-empty](screenshots/C_dashboards/C4-02-builder-empty.png), [C4-03-insert-tab](screenshots/C_dashboards/C4-03-insert-tab.png), [C4-04-gallery-search-map](screenshots/C_dashboards/C4-04-gallery-search-map.png)
- What it shows: empty canvas with "Design this page" prompt; Insert gallery grouped (Basic 8, Comparison 9, Trend 6, Distribution 4, Relationship 9, Part-to-whole 4, Flow 5, Maps 10, Models 9, Tables & cards 4, Controls 8, Layout 1 = 77). Search "map" → Treemap, Heat Map + all 10 maps.
- Works: ✅ The Routes fields auto-group into Dimensions / Geography (lat/lon) / Measures. Hovering a tile shows a preview card.
- Issues: [Low] Searching "map" also matches Treemap and Heat Map. That's harmless, but the 10 map tiles are pushed below the fold.
- Score: 4

### C4-05..11 — Point Map: add + assign roles
- Screenshots: [C4-05-point-map-added](screenshots/C_dashboards/C4-05-point-map-added.png), [C4-06-point-map-data-roles](screenshots/C_dashboards/C4-06-point-map-data-roles.png), [C4-07-add-field-popup](screenshots/C_dashboards/C4-07-add-field-popup.png), [C4-08-point-map-assigned](screenshots/C_dashboards/C4-08-point-map-assigned.png), [C4-09-point-map-roles-fixed](screenshots/C_dashboards/C4-09-point-map-roles-fixed.png), [C4-10-assign-data-picker](screenshots/C_dashboards/C4-10-assign-data-picker.png), [C4-11-point-map-rendered](screenshots/C_dashboards/C4-11-point-map-rendered.png)
- What it shows: the new Point Map tile shows a blank grey world with "300 rows did not match a country" before any data is assigned. Roles: Country / Latitude / Longitude / Measure.
- Works: ⚠️
  - Clicking a gallery tile a second time silently adds a duplicate widget (2 Point Maps now).
  - Clicking fields in the Fields panel with the widget selected fills the role slots IN ORDER, ignoring type. origin_lat went into **Country**, origin_lon into Latitude and from_city into **Longitude**, with no warning (C4-08).
  - Dragging fields onto the role names in Properties did nothing (C4-09).
  - The "Assign data" dialog → "Add Latitude" picker correctly offers only numeric fields (C4-10) ✅. Assigning lat/lon/shipments there worked.
  - Result (C4-11): the map auto-zooms onto a single blue dot (SE Asia), and the footer says "9 rows did not match a country" even though Country is empty and lat/lon are set. 300 routes from ~9 origin cities should show ~9+ points worldwide; only 1 is visible. Fit-to-data looks wrong, or points are aggregated (Aggregation default = Sum, which would sum the coordinates).
- Issues:
  - [High] Click-to-add from the Fields panel puts fields into type-incompatible roles (text field → Longitude, latitude → Country) with no validation.
  - [High] The Point Map with lat/lon shows only 1 point zoomed in. Default aggregation "Sum" may be summing coordinates; the expected result is one dot per origin.
  - [Medium] The unmatched-rows note ("N rows did not match a country") appears even when the map is lat/lon based and Country is unset. It is misleading.
  - [Medium] Dragging a field onto a role label in the Properties panel isn't supported (the drop is ignored).
  - [Low] A second click on a gallery tile adds a duplicate widget without feedback beyond the toast.
- Console: 401 GET /api/v1/auth/me (several, at login), 404 GET /api/v1/datasets/5/analysis
- Score: 2

### C4-12/13 — Point Map, aggregation + mis-assigned roles
- Screenshots: [C4-12-point-map-row-values](screenshots/C_dashboards/C4-12-point-map-row-values.png), [C4-13-point-map-lat-vs-shipments](screenshots/C_dashboards/C4-13-point-map-lat-vs-shipments.png)
- What it shows: after Aggregation was set to "None (row values)", the role panel showed Country=from_city and Latitude=origin_lon. These were left over from the earlier click-to-add, and removing a role chip by its × did not always stick. With Latitude=origin_lat and Longitude=shipments (wrong, assigned by the picker's keyboard flow), the map draws 300 overlapping blobs stacked over Africa (C4-13), all on one longitude band.
- Works: ⚠️ The map faithfully plots whatever is assigned, but nothing stops a measure like "shipments" (values 2–40) from being used as Longitude.
- Issues:
  - [Medium] The Longitude role accepts any numeric column, including a measure like "shipments", with no range or semantic check. Geography-typed fields (the Fields panel already groups origin_lat/lon under GEOGRAPHY) could be preferred or labelled in the picker.
  - [Medium] Assign-data picker: typing in "Search fields" + Enter does not pick the single match. You must Tab then Enter. Clicking the picker item by text was hijacked by the identically named field in the left Fields panel; this is partly a driver artefact, but the picker items have no distinct accessible name like "Use origin_lat for Latitude".
  - [Low] Roles on a tile can end up with two fields in one single-value slot (Country=origin_lat AND Latitude=origin_lat, C4-15), and Country silently accepts a numeric latitude.
- Score: 2

### C4-14 — Point Map rendered correctly (origin_lat / origin_lon / shipments)
- Screenshot: [C4-14-maps-canvas-full](screenshots/C_dashboards/C4-14-maps-canvas-full.png)
- What it shows: world map with 10 blue origin points (LA, NY, London, Frankfurt, Dubai, Singapore, Tokyo, Sydney, Johannesburg, São Paulo). "Shift-drag to select an area" hint, zoom +/−/reset controls.
- Works: ✅ Points land on the right cities; the unmatched-country footer disappears once lat/lon are assigned.
- Issues: [Cosmetic] The points are all one size and colour although Measure=shipments is set. Size/colour by measure isn't applied by default, so the "Measure" role has no visible effect on a Point Map. [Low] The map is small within a wide tile (lots of empty grey left and right; it doesn't fit-to-width).
- Score: 4

### C4-15 — Bubble Map (unassigned), Point Map (copy)
- Screenshot: [C4-15-bubble-density-tiles](screenshots/C_dashboards/C4-15-bubble-density-tiles.png)
- What it shows: the Bubble Map before roles are assigned shows an empty world plus "300 rows did not match a country". "Point Map (copy)" renders the same 10 points.
- Works: ⚠️
- Issues:
  - [Medium] The floating widget toolbar (move/duplicate/data/filter) sits ON the top edge of the tile and overlaps the canvas gap. A click meant for empty canvas above a tile hit "Duplicate" and created "Point Map (copy)" with no undo prompt.
  - [Low] An unassigned map tile shows "300 rows did not match a country" instead of an "Assign Latitude/Longitude or Country" empty state (Density and Cluster maps do mark "Latitude * Required", which is better).
- Console: no new errors (only the earlier 401 /auth/me and 404 /datasets/5/analysis)
- Score: 3

### Area summary
- Score (avg) ≈ 2.9. Verdict: the map family renders correctly once roles are right (Point Map is accurate and legible), and the gallery and Create flow are polished. Getting roles right is the weak spot. Click-to-add from Fields fills slots in order regardless of type; the Country, Latitude and Longitude roles accept any field; and empty map tiles show a misleading "rows did not match a country" message. On this shared machine each screenshot took ~70 s, so only the Point Map was fully evaluated before the 21:45 hard stop.
- Top issues:

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| C4-A | High | Builder Fields panel → map widget | Click-to-add fills role slots in order ignoring type (latitude → Country, from_city text → Longitude) | Route each clicked field to the first type-compatible role; warn otherwise |
| C4-B | Medium | Map roles | Longitude/Latitude accept any numeric (e.g. shipments) and Country accepts numbers; one slot can hold two fields | Validate by GEOGRAPHY type/range; prefer geo fields in the picker |
| C4-C | Medium | Map tiles | "N rows did not match a country" shown when no roles are set, or when lat/lon mode is intended | Show an "assign Lat/Lon or Country" empty state; hide the country-match note in lat/lon mode |
| C4-D | Medium | Canvas | Floating widget toolbar overlaps the tile edge; a stray click duplicates the widget | Offset the toolbar or require hover-intent; toast with Undo |
| C4-E | Medium | Assign-data picker | Search + Enter doesn't pick the single match | Auto-select the single result on Enter |
| C4-F | Low | Point Map | Measure role has no visual effect (uniform dots) | Size or colour by measure by default, or hide the role |

- Strengths: clear Create dialog; a well-organised 77-type gallery with working search and hover previews; Fields auto-grouped into Geography; the Assign-data picker filters to numeric fields for Lat/Lon; boundary starter packs (Egypt, US, KSA, UAE, EU NUTS-1) and "Upload boundaries" are offered in map settings; Point Map accurate with zoom and area-select.
- Not covered / blocked: there wasn't time (each screenshot took ~70 s) to evaluate Line/route, Cluster, Pie, Layered, Density, Contour, Geo network, Bubble (with data) or Choropleth maps, the second-page Choropleth on Demo — Sales, any Models-group chart, or any Controls/containers (Text, Image, Web content, Script, Shape, Button, Container, Slicer). The [MAP-02](screenshots/QA/MAP-02.png) overlapping-digits bug was not reached. Dashboard /reports/27 "QA C4 maps" was left with 2× Point Map, Point Map (copy), Bubble Map and Density Map (the Line and Cluster tiles may not have been added).


---

## D — Ask AI, insights, automations & monitoring
Coverage: 22 screens / 66 screenshots (D-01…D-65, plus D-11b). Account: admin@datalytics.local. Viewports: 1440×900, 390×844.
Account: admin@datalytics.local. Viewport 1440×900 unless noted. Main @ 0cb8f48. No LLM reachable (endpoint 10.125.18.189:8000 → ConnectTimeout).

### D-01 — Ask AI landing, no scope (`/ask`)
- Screenshot: [D-01-ask-landing](screenshots/D_ai_insights_ops/D-01-ask-landing.png)
- What it shows: Step 1 data picker (All/Datasets/Connections/Mine/Test data, Recent/Datasets/Connections groups), hero robot, disabled composer "Complete step 1 first", History panel.
- Works: ✅ Clean, clear two-step framing. Picker list with type badges and freshness.
- Issues: [Low] Landing does not yet say the model is unreachable (only the red dot in the top-bar picker) — user only learns after picking data. [Low] Page took ~2 min to first render under load ("Loading…" only).
- UX notes: Good empty state. "DirectQuery" badge colour distinct. Recent list puts the DQ dataset first.
- Console: none
- Score: 4

### D-02/03 — Top-bar AI model picker
- Screenshot: [D-02-model-picker](screenshots/D_ai_insights_ops/D-02-model-picker.png), [D-03-model-picker-expanded](screenshots/D_ai_insights_ops/D-03-model-picker-expanded.png)
- What it shows: Auto ("No model is reachable") and Default ("ConnectTimeout") with red dots, "What does this change?" explainer, Check again, Manage models.
- Works: ✅ Explainer clear; Check again shows "Checking…" spinner.
- Issues: [Low] Raw exception name "ConnectTimeout" shown to users — humanise ("Not answering (timed out)").
- UX notes: Good new feature; status dot in top bar is a nice ambient signal.
- Console: none
- Score: 4

### D-04/05 — Manage models → Platform settings, AI model (LLM) (`/platform/settings`)
- Screenshot: [D-04-manage-models](screenshots/D_ai_insights_ops/D-04-manage-models.png), [D-05-endpoint-test](screenshots/D_ai_insights_ops/D-05-endpoint-test.png)
- What it shows: LLM endpoints editor (name, address, model, key, strength, context, on, Test, reorder, delete), default model select, AI features on toggle, single-endpoint fallback settings.
- Works: ✅ Test → "Testing…" then toast "Could not reach the model: ConnectTimeout:" (~10 s).
- Issues: [Low] Toast text ends with a dangling colon "ConnectTimeout:" (empty message). [Low] Several "Allowed: 0 to —." ranges render an em dash as max. [Cosmetic] While testing, the whole endpoint row gets a grey band (looks like a render glitch).
- UX notes: Dense but well explained. "Strength 1–10" and "Context (tokens)" could use examples.
- Console: none
- Score: 3.5

### D-06 — Ask AI with dataset scope, model offline (`/ask?dataset=1`)
- Screenshot: [D-06-ask-sales-selected](screenshots/D_ai_insights_ops/D-06-ask-sales-selected.png)
- What it shows: "Asking about Demo — Sales", 6 suggestion cards, red line "The model server isn't reachable, so new questions are paused.", composer disabled with matching placeholder.
- Works: ⚠️ Offline state is clearly signposted for the composer — big improvement — BUT the suggestion cards remain fully enabled (see D-07).
- Issues: [Medium] Suggestion cards look and act enabled while "new questions are paused" — contradictory.
- UX notes: Suggestions are now sensible on Sales (region/revenue/date/country) — no "sum of latitude".
- Console: none
- Score: 3

### D-07/08 — Suggestion clicked while offline (spinner)
- Screenshot: [D-07-suggestion-click-paused](screenshots/D_ai_insights_ops/D-07-suggestion-click-paused.png), [D-08-ask-after-wait](screenshots/D_ai_insights_ops/D-08-ask-after-wait.png)
- What it shows: Question bubble, "Analyzing your data…" skeleton with elapsed timer and a Stop button; after ~20 s "Still working — the query is being checked against your database."
- Works: ❌ Clicking a suggestion bypasses the pause and spins for 70 s+ (I stopped it at 1m 9s) against a server the page already knows is unreachable. The 07:16 run of the same question (seed/earlier) did fall back after the model timed out.
- Issues: [High] Suggestions still send and spin when the model is known unreachable. [Medium] Slow-note "the query is being checked against your database" is shown though no query was ever written (model not reachable) — misleading stage text.
- UX notes: Disable cards (or route them to the no-AI fallback instantly, as the DQ dataset does in 0.1 s).
- Console: none
- Score: 2

### D-09 — Stop
- Screenshot: [D-09-ask-stopped](screenshots/D_ai_insights_ops/D-09-ask-stopped.png)
- What it shows: Answer card replaced with "Stopped waiting. The server may still finish."
- Works: ✅ Stop exists and works instantly.
- Issues: [Low] "The server may still finish" — but nothing tells the user whether/where a late answer will appear; no Retry/Edit on the stopped turn.
- Console: none
- Score: 3.5

### D-10..12, 15..17 — History: rename / new chat / delete
- Screenshots: [D-10-history-row-actions](screenshots/D_ai_insights_ops/D-10-history-row-actions.png), [D-11-history-rename-field](screenshots/D_ai_insights_ops/D-11-history-rename-field.png), [D-11b-rename-typed](screenshots/D_ai_insights_ops/D-11b-rename-typed.png), [D-12-history-renamed](screenshots/D_ai_insights_ops/D-12-history-renamed.png), [D-15-new-chat](screenshots/D_ai_insights_ops/D-15-new-chat.png), [D-16-delete-conversation](screenshots/D_ai_insights_ops/D-16-delete-conversation.png), [D-17-after-delete](screenshots/D_ai_insights_ops/D-17-after-delete.png)
- What it shows: History grouped by TODAY, pencil/trash on hover, inline title field, confirm modal "Delete this conversation?".
- Works: ✅ Rename to "QA D conversation" persisted after reload; delete modal + delete works; New chat returns to suggestions.
- Issues: [Low] Rename field: the time stamp disappears for the row being edited and the pencil stays as an inert icon next to the input (no explicit Save/Cancel buttons; Enter/Escape only). [Medium] "New chat" keeps the previous "Edit question" draft ("Total revenue by region") in the composer (D-16 background).
- Console: none
- Score: 4

### D-13/14 — Earlier failed answer, Edit question / Retry
- Screenshot: [D-13-old-conversation](screenshots/D_ai_insights_ops/D-13-old-conversation.png), [D-14-edit-question](screenshots/D_ai_insights_ops/D-14-edit-question.png)
- What it shows: Old answer is now a no-AI fallback: "I could not use the AI model for this question (it did not answer)…", lists the columns and 10 analyses available, footer "AI reply: no data was queried for this", Copy/👍/👎/Edit question/Retry.
- Works: ⚠️ Service errors are not phrased as "rephrase". Retry is disabled while offline (sensible). Edit question copies the text into a composer that is disabled — dead end.
- Issues: [Medium] "Edit question" enabled while the composer is disabled — places text in a read-only box. [Low] Fallback is a long wall of plain-text bullets with "- " markdown not rendered as a list; analyses are not clickable links to the Analysis tab. [Low] No "Technical details" disclosure anywhere (searched buttons) — admins can't see the underlying error.
- Console: none
- Score: 3

### D-18..20 — In-conversation scope picker; connection scope (`/ask?source=1`)
- Screenshot: [D-18-scope-picker-open](screenshots/D_ai_insights_ops/D-18-scope-picker-open.png), [D-19-scope-picker-connections](screenshots/D_ai_insights_ops/D-19-scope-picker-connections.png), [D-20-ask-connection-scope](screenshots/D_ai_insights_ops/D-20-ask-connection-scope.png)
- What it shows: Dropdown picker with search, tabs, recent list, keyboard hints, Upload dataset; connection scope gives 4 generic suggestions, "No questions yet for this connection", "Questions are saved per connection".
- Works: ✅
- Issues: [Cosmetic] Picker footer hint truncated: "Esc to clos" (clipped by Upload dataset button).
- Console: none
- Score: 4

### D-21..23 — Dataset (DirectQuery) → Ask about this data (`/datasets/6` → `/ask?dataset=6`)
- Screenshot: [D-21-dq-dataset-page](screenshots/D_ai_insights_ops/D-21-dq-dataset-page.png), [D-22-dq-ask-entry](screenshots/D_ai_insights_ops/D-22-dq-ask-entry.png), [D-23-dq-ask-question](screenshots/D_ai_insights_ops/D-23-dq-ask-question.png)
- What it shows: DQ dataset page with "AI: follow the connection / AI: not allowed" chips; Ask opens the dataset scope correctly with 6 suggestions; a suggestion returns in 0.1 s: "I could not use the AI model for this question (AI is switched off for this data)…".
- Works: ✅ Old 400/"rephrase" (D-08) is gone: scope resolves, explanation is honest.
- Issues: [Medium] Ask AI entry is offered and suggestions are shown for a dataset whose AI policy is "not allowed" — should say so up front instead of after the question. [Low] Fallback leaks internal table name `demo_live_orders_directquery`. [Low] Header row grows after load (label/AI chips appear), shifting buttons — a click on "Ask about this data" during load can land on "Share". [Low] Share dialog does not close on Escape.
- Console: none
- Score: 3.5

### D-24..27 — Ask AI mobile 390×844
- Screenshot: [D-24-ask-mobile](screenshots/D_ai_insights_ops/D-24-ask-mobile.png), [D-25-ask-mobile-scrolled](screenshots/D_ai_insights_ops/D-25-ask-mobile-scrolled.png), [D-26-ask-mobile-history](screenshots/D_ai_insights_ops/D-26-ask-mobile-history.png), [D-27-ask-mobile-answer](screenshots/D_ai_insights_ops/D-27-ask-mobile-answer.png)
- What it shows: scope chip + "History" button, 2-column suggestion grid, offline line, composer; history as a right drawer with close X; answer card with icon-only actions.
- Works: ✅ Usable, no horizontal scroll, drawer works.
- Issues: [Cosmetic] The "Step 2 · Ask a question" pill is half-hidden under the sticky scope bar at the top of the scroll area. [Low] On mobile the answer actions are icon-only (copy/👍/👎/✎/↻) with no labels.
- Console: none
- Score: 4

### D-28..32 — Insights hub dataset picker & stale-results race (`/insights`)
- Screenshot: [D-28-insights-landing](screenshots/D_ai_insights_ops/D-28-insights-landing.png), [D-29-insights-race-early](screenshots/D_ai_insights_ops/D-29-insights-race-early.png), [D-30-insights-race-settled](screenshots/D_ai_insights_ops/D-30-insights-race-settled.png), [D-31-insights-metrics-clean](screenshots/D_ai_insights_ops/D-31-insights-metrics-clean.png), [D-32-insights-race-repro2](screenshots/D_ai_insights_ops/D-32-insights-race-repro2.png)
- What it shows: Dataset select + All/Certified/Mine/Show test-looking chips; "TOP INSIGHTS" card with summary and bullets, View full scan.
- Works: ❌ Race present. Sales → Routes → Metrics quickly: select shows "Demo — Metrics" but the card says "Across 2,000 rows … margin_pct … profit" (Sales findings). Metrics alone gives "height moves with weight". Repro 2 (Sales → Feedback → Routes): "Demo — Routes" with the same Sales findings, still wrong 20 s later.
- Issues: [High] Stale scan response overwrites the current dataset's findings. [Low] Card does not name the dataset it describes, so the mismatch is invisible except by numbers.
- UX notes: It starts empty "Choose a dataset to scan it…".
- Console: none
- Score: 2

### D-33/34 — View full scan → dataset Analysis › Insights (`/datasets/5#insights`)
- Screenshot: [D-33-view-full-scan](screenshots/D_ai_insights_ops/D-33-view-full-scan.png), [D-34-generated-insights](screenshots/D_ai_insights_ops/D-34-generated-insights.png)
- What it shows: Analysis menu with "What stands out? Insights" selected; empty panel with only a "Generate insights" button; after Generate: summary + STANDOUT cards with bar charts.
- Works: ⚠️ It lands on an empty panel and the hub's scan isn't reused. 2× `GET /api/v1/datasets/5/analysis` 404 on arrival.
- Issues: [Medium] View full scan lands on blank "Generate insights" instead of the scan you just saw; 404s on load. [Medium] Finding "Sao Paulo has the highest shipments per row" with p = 0.222 (not significant) shown as STANDOUT, and its chart is sum(shipments) where Dubai is top — headline and chart disagree. [Low] Page loads scrolled so the dataset header/tabs are off-screen.
- Console: 2× http 404 GET /api/v1/datasets/5/analysis
- Score: 2.5

### D-35..38 — Pin a finding; where pins appear
- Screenshot: [D-35-pin-finding](screenshots/D_ai_insights_ops/D-35-pin-finding.png), [D-36-pin-toast](screenshots/D_ai_insights_ops/D-36-pin-toast.png), [D-37-home-no-pins](screenshots/D_ai_insights_ops/D-37-home-no-pins.png), [D-38-portal-no-pins](screenshots/D_ai_insights_ops/D-38-portal-no-pins.png)
- What it shows: tiny pin icon on each finding card; toast "Pinned to your dashboard".
- Works: ❌ Pins appear nowhere: not on Home, not on My dashboards (/portal), not on Datasets. Code confirms: widget pin was removed because "That section is gone, so the button promised a destination nothing displays" (WidgetRenderer.tsx ~1510), but the same button survives on dataset findings (DatasetDetail.tsx:1310) and InsightsPane.
- Issues: [High] Pin finding still promises "Pinned to your dashboard" with no destination and no way to unpin. [Low] Pin icon has no visible label, tiny hit target, sits mid-header.
- Console: none
- Score: 1.5

### D-39/40 — Insights on DirectQuery dataset
- Screenshot: [D-39-insights-dq](screenshots/D_ai_insights_ops/D-39-insights-dq.png), [D-40-insights-dq-scanned](screenshots/D_ai_insights_ops/D-40-insights-dq-scanned.png)
- What it shows: "Live datasets are scanned on request: a scan reads up to 250,000 rows…" + Scan now / Open dataset; after scan one finding (month has 11 gaps).
- Works: ✅ Clear, opt-in scan for live data — good.
- Issues: None
- Console: none
- Score: 4

### D-41 — Insights filter chips
- Screenshot: [D-41-insights-projects-filters](screenshots/D_ai_insights_ops/D-41-insights-projects-filters.png)
- What it shows: "Show 4 test-looking" → "Hide test-looking"; "Mine (5)" active.
- Works: ⚠️ Toggling a chip silently swapped the selected dataset from "Demo — Projects" to "QA B flow output" and started a scan of it.
- Issues: [Medium] Filter chips change the selected dataset (picks the first visible option) and auto-scan it, without the user choosing. [Low] On Automations the "Mine (5)" chip appears active by default on first load while only 1 dataset shows; label count (5) does not match.
- Console: none
- Score: 2.5

### D-42..46, 56..58 — Automations (`/automation`)
- Screenshot: [D-42-automations-list](screenshots/D_ai_insights_ops/D-42-automations-list.png), [D-43-automation-pick](screenshots/D_ai_insights_ops/D-43-automation-pick.png), [D-44-automation-started](screenshots/D_ai_insights_ops/D-44-automation-started.png), [D-45-automation-progress](screenshots/D_ai_insights_ops/D-45-automation-progress.png), [D-46-automation-cancelled](screenshots/D_ai_insights_ops/D-46-automation-cancelled.png), [D-56-automation-feedback-state](screenshots/D_ai_insights_ops/D-56-automation-feedback-state.png), [D-57-automation-details](screenshots/D_ai_insights_ops/D-57-automation-details.png), [D-58-automation-done](screenshots/D_ai_insights_ops/D-58-automation-done.png)
- What it shows: one automation type only — "automated analysis" of a dataset (7 steps: Profile, Describe, Scan, Propose, Review, Build, Tell you), with progress dots, Cancel, Details step table. Hint "Usually about 1 min for 200 rows".
- Works: ⚠️ Start ✅ (Feedback, Projects). Cancel ✅ ("Stopped", "cancelled by admin…"). Steps 1–5 completed without an LLM, but "Build the report" stuck Running from 20:33 to at least 20:41 (>12 min total vs "about 1 min"); bell never notified.
- Issues: [High] Automation run hangs on "Build the report" with no timeout/error and no note; user told it takes ~1 min. [Medium] No name, edit, delete, retry or schedule/trigger options — "create a QA D automation / edit / delete" is not possible (no naming at all; stopped runs can't be removed or retried). [Low] Header says "Waiting to start" while step 1 shows "Running". [Low] After cancel, the step that was "Running" resets to "Waiting" (looks like it never ran). [Low] Progress dots use a half-moon glyph that renders as a tiny clipped "◐".
- UX notes: Clear wording, step table helpful. Brief asked for "every trigger type" — there is only one (manual start).
- Console: none
- Score: 2.5

### D-47 — Notifications bell
- Screenshot: [D-47-notifications-bell](screenshots/D_ai_insights_ops/D-47-notifications-bell.png)
- What it shows: dropdown "Nothing yet — alerts, delivery problems and comments land here."
- Works: ⚠️ Stayed empty throughout: no notification for the cancelled run, the stuck run, or the rule check. Couldn't verify live update because nothing ever produced a notification.
- Issues: [Medium] Automations say "the bell tells you when it is ready" — nothing arrives when a run is stuck or cancelled (no failure/timeout notice). - Console: none
- Score: 3

### D-48..50 — Monitoring › Refresh & jobs (`/monitoring/jobs`)
- Screenshot: [D-48-monitoring-jobs](screenshots/D_ai_insights_ops/D-48-monitoring-jobs.png), [D-49-jobs-failed-only](screenshots/D_ai_insights_ops/D-49-jobs-failed-only.png), [D-50-jobs-row-link](screenshots/D_ai_insights_ops/D-50-jobs-row-link.png)
- What it shows: table Kind/Name/Schedule/Last run/Status (Report schedule "Demo — weekly regional performance", Data alert "Demo — margin below target"), Refresh history with "Failed only".
- Works: ⚠️ Row links work (→ /reports/8, → /datasets/1). Schedule column is "—" for the weekly report schedule and the alert. Automation runs (2 today) and the quality-rule run are not listed though the page says "Everything that runs".
- Issues: [Medium] Weekly schedule still renders "—". [Medium] Automation runs and data-check runs missing. [Low] Report schedule link opens a dashboard titled "Use case — Regional performance review", not the schedule — no schedule highlighted.
- Console: none
- Score: 2.5

### D-51 — Monitoring › Deliveries (`/monitoring/deliveries`)
- Screenshot: [D-51-monitoring-deliveries](screenshots/D_ai_insights_ops/D-51-monitoring-deliveries.png)
- What it shows: empty state "No deliveries yet. Once a report schedule or data alert runs, each attempt is logged here."
- Works: ✅ Clear empty state; no filters to test.
- Issues: None (nothing ran).
- Console: none
- Score: 3.5

### D-52/53 — Monitoring › Activity (`/monitoring/activity`)
- Screenshot: [D-52-monitoring-activity](screenshots/D_ai_insights_ops/D-52-monitoring-activity.png), [D-53-activity-search](screenshots/D_ai_insights_ops/D-53-activity-search.png)
- What it shows: When/Who/Action/Entity/Detail table with a new "Search activity…" box.
- Works: ⚠️ Search works (typing "automation" → 3 rows). Automation start/cancel now logged. Still: no paging (all rows in one list), no filters by user/action/date, no row detail (clicking a row does nothing), Ask AI questions and insight pins/scans not logged. Details still raw ("queries=None asks=None storage_mb=None…", "grant:3: view…").
- Issues: [Medium] Raw key=value details and Python "None" exposed. [Medium] No paging/filters/detail; Ask AI not logged. [Low] Entity column wraps "automation_run #2" over two lines.
- Console: none
- Score: 3

### D-54/55 — Data checks (dataset › Rules & alerts) — new
- Screenshot: [D-54-dataset-checks-alerts](screenshots/D_ai_insights_ops/D-54-dataset-checks-alerts.png), [D-55-quality-rules-run](screenshots/D_ai_insights_ops/D-55-quality-rules-run.png)
- What it shows: "What you should know about this data" (2 findings with "What to do"), Quality rules with Run now / + Rule, Warn/Block, on/Remove; Alerts.
- Works: ✅ Run now → "Checked 2,000 rows · All pass".
- Issues: [Medium] Check runs don't appear in Monitoring (jobs/activity) — there is no central "data checks results" view. [Low] "Not run yet — press Run now" for a rule that runs "before each refresh" — status only per dataset.
- Console: none
- Score: 4

### D-59..62 — Mobile 390×844: Activity, Jobs, Automations, Insights
- Screenshot: [D-59-activity-mobile](screenshots/D_ai_insights_ops/D-59-activity-mobile.png), [D-60-jobs-mobile](screenshots/D_ai_insights_ops/D-60-jobs-mobile.png), [D-61-automations-mobile](screenshots/D_ai_insights_ops/D-61-automations-mobile.png), [D-62-insights-mobile](screenshots/D_ai_insights_ops/D-62-insights-mobile.png)
- What it shows: tables horizontally scrollable inside cards.
- Works: ⚠️
- Issues: [Medium] Activity/Jobs on phone show only When/Who (Kind/Name); Action, Entity, Schedule, Status are off-screen with only a faint scroll shadow. [Medium] Automations mobile: the run's dataset link "Demo — Feedback" wraps one letter per line (column squeezed by status/dots/buttons), "Started 14 …" truncated.
- Console: none
- Score: 2.5

### D-63 — Model picker: choose Auto
- Screenshot: [D-63-model-auto-selected](screenshots/D_ai_insights_ops/D-63-model-auto-selected.png)
- Works: ✅ Selection persists in the top bar ("AI model: Auto, not reachable"); Ask page remains paused. Switched back to Default.
- Issues: None
- Score: 4

### D-64 — Sales full scan (card types)
- Screenshot: [D-64-sales-full-scan](screenshots/D_ai_insights_ops/D-64-sales-full-scan.png)
- What it shows: card kinds OUTLIER IMPACT ×2, ANOMALY ×3, CHANGE POINT ×2, CORRELATION ×2, DATA QUALITY ×1, LAGGARD ×1 (+ STANDOUT on Routes). Each with pin, score, mini histogram/bars.
- Works: ✅ Rich and readable.
- Issues: [Low] Some cards show a chart, neighbours show none, leaving large empty card halves (uneven grid). [Low] Histogram bins with 0 rows take most of the chart (margin_pct 52.81–143.21 all 0).
- Score: 3.5

### D-65 — Ask AI suggestion quality on other datasets
- Screenshot: [D-65-ask-suggestions-projects](screenshots/D_ai_insights_ops/D-65-ask-suggestions-projects.png)
- What it shows: Routes: "Total origin lat by from city", "Top 5 from city by origin lat"; Metrics: "Total height by group"; Projects: "Total progress pct by task", "Top 5 task by progress pct".
- Issues: [Medium] Nonsense SUM suggestions on latitude / percentage / body measures / per-task ID-like columns.
- Score: 2.5

### Area summary
- Score (avg): ≈ 3.0 / 5. Ask AI handles an outage well: when the model server is down the page says so, pauses the composer, falls back to an honest no-AI answer, and has a Stop button. The new model picker and LLM endpoint settings are clear. Rename and delete in history work and are saved. Some things still break trust, though. Suggestion cards bypass the pause and spin for over a minute. The Insights hub shows the wrong dataset's findings after a quick switch. Pinning still promises a dashboard that doesn't exist. Automations hang on "Build the report" with no timeout and no notification. Monitoring is still thin: no schedules, no automation or check runs, raw activity details, and tables that don't work on a phone.
- Top issues:

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| D-30 | High | Insights hub | Stale scan response shows Sales findings under Metrics/Routes | Tag each scan with dataset id / AbortController; ignore late responses; show dataset name in card |
| D-36 | High | Dataset insights → Pin | "Pinned to your dashboard" — pins shown nowhere, can't unpin | Remove the pin button (as done for widgets) or ship a Pinned section on Home/My dashboards |
| D-07 | High | Ask AI suggestions | Suggestion cards stay active while "new questions are paused"; spin 70 s+ | Disable cards when offline, or route to instant no-AI fallback |
| D-58 | High | Automations | Run stuck on "Build the report" >8 min; no timeout, no error, no bell | Step timeout + failed state + notification; Retry/Delete on runs |
| D-48j | Medium | Refresh & jobs | Weekly schedule "—"; automation and check runs missing | Render cron/weekly text; include automation runs & quality-rule runs |
| D-41 | Medium | Insights filter chips | Toggling a chip swaps the selected dataset and auto-scans | Keep selection if still visible; otherwise clear, don't auto-pick |
| D-14 | Medium | Ask AI history | "Edit question" fills a disabled composer; New chat keeps that draft | Disable Edit while offline; clear draft on New chat |
| D-65 | Medium | Ask AI suggestions | SUM of latitude / progress pct / height | Exclude geo/percent/ID-like columns from SUM templates |
| D-61 | Medium | Automations mobile | Dataset name wraps one letter per line | Stack the status/actions under the title below 600 px |
| D-59 | Medium | Monitoring mobile | Action/Status columns hidden off-screen | Stacked card layout on phones |
| D-52 | Medium | Activity | Raw "queries=None…" details; no paging/filters/detail; Ask AI not logged | Humanise details, add paging + filters, log agent questions |
| D-23 | Medium | DQ dataset Ask | Suggestions shown for a dataset whose AI is "not allowed" | Say "AI is off for this dataset" before asking; hide suggestions |

- Strengths:
  - Honest handling when the model is offline: the top-bar status dot, the paused composer, and a no-AI fallback that lists what the platform can still compute.
  - Stop button added; history rename and delete work, with a proper confirm modal.
  - The model picker explains itself ("What does this change?"); the endpoint editor has Test and Check again.
  - Live datasets are only scanned when you ask, with a clear note on how many rows a scan reads.
  - Automation step table is clear, and Cancel works and is audited.
  - Activity now has search and logs automation events. The new data-check panel is good ("What to do", Run now, All pass).
- Not covered / blocked:
  - Real AI answers, Retry, "Technical details" and charts/SQL in answers: blocked, because no LLM is reachable. The no-AI fallback replaces the error card, so the Technical details disclosure never appears.
  - Bell live update: nothing produced a notification, so this could not be checked.
  - Automation edit, delete and other trigger types don't exist in the UI (only a manual "automated analysis" start). I couldn't name a run "QA D automation" because runs have no name field. Two runs were created on Demo — Feedback and Demo — Projects; the Projects run was cancelled. The Feedback run was still stuck at 20:41.
  - Deliveries filters: no rows, nothing to filter.
  - No new monitoring pages exist on main (routes: jobs, deliveries, activity only). Data checks results live per dataset only.


---

## E — Administration, platform & role-based access
Coverage: 30 screens / 111 screenshots (E-01 … E-112). Main branch 0cb8f48.
Accounts: admin@datalytics.local (super admin), demo-global, demo-emea, admin@contoso.invalid, analyst@contoso.invalid, admin@northwind.invalid, analyst@northwind.invalid, admin@example.invalid, plus created qa.e.dup (deactivated).
Viewports: 1440×900 desktop; 390×844 phone (Users).
Note: the driver's screenshot/`login` command hangs on /login under load (networkidle never reached); logins were done by filling the form, and the login page itself was assessed from page text.

### E-01 — Users list (`/admin/users`)
- Screenshot: [E-01-admin-users](screenshots/E_admin_roles/E-01-admin-users.png)
- What it shows: flat list of 5 users (email + role), Bulk import / New user, Edit/Delete per row.
- Works: ✅ list renders. No search, filter, status filter or pagination.
- Issues: [Medium] no search/filter/pagination. [Low] no "last login"/status column; inactive only shown as red word.
- Console: initial 401 /auth/me before login (expected). Otherwise none.
- Score: 3

### E-02/03 — New user dialog (`/admin/users`)
- Screenshots: [E-02-new-user-dialog](screenshots/E_admin_roles/E-02-new-user-dialog.png), [E-03-new-user-invalid-email](screenshots/E_admin_roles/E-03-new-user-invalid-email.png)
- What it shows: Email, Password, Role (pre-selected "Admin (admin)" although a "Select a role…" placeholder exists in the options).
- Works: ❌ Created user "not-an-email" with password "x" and the default Admin role -> "User created".
- Issues: [High] role still defaults to Admin. [High] invalid email accepted. [Medium] 1-char password accepted.
- Console: none
- Score: 2

### E-04/05 — Edit user (`/admin/users`)
- Screenshots: [E-04-edit-user-dialog](screenshots/E_admin_roles/E-04-edit-user-dialog.png), [E-05-edit-user-filled](screenshots/E_admin_roles/E-05-edit-user-filled.png)
- Works: ✅ email + role changed ("Updated" toast). Renamed the bad user to QA.E.User@Example.invalid (mixed case kept — no normalisation), role Demo — Global analyst. Has an "Active" checkbox with clear helper text.
- Issues: [Low] email case preserved/not normalised.
- Score: 4

### E-06/07/08 — Duplicate email
- Screenshots: [E-06-duplicate-case-email](screenshots/E_admin_roles/E-06-duplicate-case-email.png), [E-07-exact-duplicate-email](screenshots/E_admin_roles/E-07-exact-duplicate-email.png), [E-07b-exact-duplicate-result](screenshots/E_admin_roles/E-07b-exact-duplicate-result.png), [E-08-duplicate-error-toast](screenshots/E_admin_roles/E-08-duplicate-error-toast.png)
- Works: ⚠️ "DEMO-GLOBAL@example.invalid" accepted as a NEW user (renamed afterwards to qa.e.dup@example.invalid). Exact-case duplicate rejected with toast "Email already in use" (400).
- Issues: [Medium] case-insensitive duplicate still accepted — two accounts that differ only by case.
- Score: 3

### E-09/10 — Deactivate user
- Screenshots: [E-09-deactivate-unchecked](screenshots/E_admin_roles/E-09-deactivate-unchecked.png), [E-10-users-after-deactivate](screenshots/E_admin_roles/E-10-users-after-deactivate.png)
- Works: ✅ unchecking Active + Save shows red "Inactive" tag next to qa.e.dup@example.invalid.
- Score: 4

### E-11/12/13 — Bulk import (`/admin/users`)
- Screenshots: [E-11-bulk-import-dialog](screenshots/E_admin_roles/E-11-bulk-import-dialog.png), [E-12-bulk-import-filled](screenshots/E_admin_roles/E-12-bulk-import-filled.png), [E-13-bulk-import-result](screenshots/E_admin_roles/E-13-bulk-import-result.png)
- Works: ✅ header skipped; 1 valid row created, "Row 2 (bad-email): invalid email" reported. Clear inline result.
- Issues: [Low] list re-sorts after import (new users jump from top to bottom) — inconsistent ordering. [Low] row numbering "Row 2" counts data rows, not file lines (header=line 1 so bad row is line 3) — ambiguous.
- Score: 4

### E-14..18 — Roles (`/admin/roles`)
- Screenshots: [E-14-roles](screenshots/E_admin_roles/E-14-roles.png), [E-15-new-role-dialog](screenshots/E_admin_roles/E-15-new-role-dialog.png), [E-16-duplicate-role-name](screenshots/E_admin_roles/E-16-duplicate-role-name.png), [E-17-edit-role-dialog](screenshots/E_admin_roles/E-17-edit-role-dialog.png), [E-18-new-role-empty-name](screenshots/E_admin_roles/E-18-new-role-empty-name.png)
- What it shows: list of roles with "Org admin" tag; dialog = Role Name + Org admin checkbox only.
- Works: ⚠️ create/edit work; empty name -> toast "Name is required" (no inline error). Created "QA E Role" twice -> both saved (renamed one to "QA E Role dup").
- Issues: [High] no permission matrix. [Medium] duplicate role names allowed. [Low] validation only by toast, field not highlighted. [Low] no user count per role.
- Score: 2

### E-19..23 — Organization chart (`/admin/org-units`)
- Screenshots: [E-19-org-chart](screenshots/E_admin_roles/E-19-org-chart.png), [E-20-add-unit-dialog](screenshots/E_admin_roles/E-20-add-unit-dialog.png), [E-21-add-unit-step2](screenshots/E_admin_roles/E-21-add-unit-step2.png), [E-22-org-chart-tree-place-user](screenshots/E_admin_roles/E-22-org-chart-tree-place-user.png), [E-23-org-chart-placed](screenshots/E_admin_roles/E-23-org-chart-placed.png)
- What it shows: NEW page. Hierarchy tree (unit + level chip), 2-step "Add unit" (name -> level), "Place a user" picker with per-unit checkboxes + Save placement.
- Works: ✅ created QA E Region (Region) > QA E Branch (Branch); placed QA.E.User at QA E Branch; audited (org_unit.create, user.org_units).
- Issues: [Medium] no "match value" field shown when adding a unit, although the row-security helper says "a unit's match value must equal the values in this column" — unclear what value MYSCOPE emits. [Low] the placement only shows when a user is picked; there's no view of "who is placed where" (members per unit). [Low] no rename/move of units.
- UX notes: explanatory copy is good; "Place at …" checkboxes are only visible in placement mode — nice.
- Console: none
- Score: 3

### E-24..31 — Row security (`/admin/row-security-rules`)
- Screenshots: [E-24-row-security](screenshots/E_admin_roles/E-24-row-security.png), [E-25-new-row-rule-dialog](screenshots/E_admin_roles/E-25-new-row-rule-dialog.png), [E-26-row-rule-invalid-expr](screenshots/E_admin_roles/E-26-row-rule-invalid-expr.png), [E-27-row-rule-myscope](screenshots/E_admin_roles/E-27-row-rule-myscope.png), [E-28-row-rule-created](screenshots/E_admin_roles/E-28-row-rule-created.png), [E-29-auto-generate-rules](screenshots/E_admin_roles/E-29-auto-generate-rules.png), [E-30-auto-generate-shipments](screenshots/E_admin_roles/E-30-auto-generate-shipments.png), [E-31-row-rule-more-menu](screenshots/E_admin_roles/E-31-row-rule-more-menu.png)
- What it shows: rule list (role on dataset + expression), Ask-AI explainer banner with link to Connection rules, New rule dialog with "Quick setup — restrict by current user" (column + match: email / id / org id / org-chart units / literal), Auto-generate rules dialog, ⋯ menu (Edit rule / Delete rule).
- Works: ⚠️ invalid column -> clear toast "Invalid filter expression: name 'regionx' is not defined". BUT the Quick-setup's own "Viewer's org-chart units (and below)" option generates `region in MYSCOPE` and Create fails with "Invalid filter expression: name 'MYSCOPE' is not defined" (400).
- Issues: [High] MYSCOPE rules cannot be saved: `_validate_filter_expr` (backend/app/routers/admin.py:229) runs apply_user_context but never expands MYSCOPE, so the new hierarchical RLS feature (Org chart) is unusable from the UI. [Medium] Role select pre-fills "Admin" (an org-admin role that bypasses all rules) and Dataset pre-fills the first dataset — same default-to-first-option pattern as New user. [Low] Auto-generate: "No user/owner or org-ish columns found" for every dataset incl. shipments (has branch/customer columns) and Demo — Sales (region); Apply stays disabled with no guidance. [Low] errors only in toasts.
- Console: 400 POST /admin/row-security-rules (expected for the invalid cases)
- Score: 2

### E-32..34 — Column security (`/admin/column-security-rules`)
- Screenshots: [E-32-column-security](screenshots/E_admin_roles/E-32-column-security.png), [E-33-new-column-rule-dialog](screenshots/E_admin_roles/E-33-new-column-rule-dialog.png), [E-34-column-rule-created](screenshots/E_admin_roles/E-34-column-rule-created.png)
- Works: ✅ Role + Dataset + column checklist with types; Create disabled until a column is ticked; created "QA E Role on Demo — Sales hides margin_pct"; audited.
- Issues: [Low] no Edit for an existing rule (only Delete).
- Score: 4

### E-35..38 — Connection rules / Ask AI (`/admin/connection-rules`)
- Screenshots: [E-35-connection-rules](screenshots/E_admin_roles/E-35-connection-rules.png), [E-36-connection-rules-sqlite](screenshots/E_admin_roles/E-36-connection-rules-sqlite.png), [E-37-connection-rule-bad-col](screenshots/E_admin_roles/E-37-connection-rule-bad-col.png), [E-38-connection-rules-nile](screenshots/E_admin_roles/E-38-connection-rules-nile.png)
- What it shows: NEW in rail? No — reachable only from the link on Row security (not in rail). Connection picker, rules table, Add a rule (Table, Role, Rule).
- Works: ⚠️ Demo — Live SQLite lists table live_orders. QA B Nile Express (Postgres) TABLE list is still empty, so no rule can be added there. A rule `nonexistent_col = 'x'` was accepted without validation (then removed).
- Issues: [High] TABLE list empty for the Postgres connection (Nile Express) while the page states "every role sees every row". [Medium] rule expression not validated against the table's columns — a typo silently saves a rule that will fail/deny at query time. [Medium] connection rule add/remove is NOT audited (no audit action exists; backend/app/routers/agent.py create_row_policy/delete_row_policy). [Low] page not in the Admin rail. [Cosmetic] "Remove" is an unstyled native-looking button.
- Console: none
- Score: 2

### E-39/40 — Export policy (`/admin/export-policy`)
- Screenshots: [E-39-export-policy](screenshots/E_admin_roles/E-39-export-policy.png), [E-40-export-policy-toggled](screenshots/E_admin_roles/E-40-export-policy-toggled.png)
- Works: ✅ per-dataset matrix (All off / csv / tsv / xlsx / Auto when private / Security rules present). Toggling saves immediately and is audited ("formats off: csv", "cleared"). Reverted.
- Issues: [Low] no save confirmation (no toast/inline "Saved") on an immediately-applied security change. [Low] "Loading…" plain text first render.
- Score: 4

### E-41..46 — API keys (`/admin/api-keys`)
- Screenshots: [E-41-api-keys](screenshots/E_admin_roles/E-41-api-keys.png), [E-42-api-key-empty-name](screenshots/E_admin_roles/E-42-api-key-empty-name.png), [E-43-api-key-secret-shown](screenshots/E_admin_roles/E-43-api-key-secret-shown.png), [E-44-api-key-after-reload](screenshots/E_admin_roles/E-44-api-key-after-reload.png), [E-45-api-key-revoke-confirm](screenshots/E_admin_roles/E-45-api-key-revoke-confirm.png), [E-46-api-key-revoked](screenshots/E_admin_roles/E-46-api-key-revoked.png)
- Works: ✅ empty name -> toast "Name the key first"; "QA E key" created; one-time secret box with Copy + warning; after reload only prefix "dk_kq7wlg6x… · never used"; Revoke -> styled confirm "Any agent using this key stops working immediately" -> list empty. Audited (api_key.create / revoke).
- Issues: [Low] no expiry/scope options; key acts with all of the creator's rights.
- Score: 4

### E-47..51 — Custom connectors (`/admin/custom-connectors`)
- Screenshots: [E-47-custom-connectors](screenshots/E_admin_roles/E-47-custom-connectors.png), [E-48-new-custom-connector](screenshots/E_admin_roles/E-48-new-custom-connector.png), [E-49-custom-connector-empty-submit](screenshots/E_admin_roles/E-49-custom-connector-empty-submit.png), [E-50-custom-connector-created](screenshots/E_admin_roles/E-50-custom-connector-created.png), [E-51-custom-connector-edit](screenshots/E_admin_roles/E-51-custom-connector-edit.png)
- Works: ⚠️ empty submit -> "Key and label are required". Created "QA E Nile preset" with Port = "abc" — accepted and stored.
- Issues: [Medium] no field validation (Port "abc" saved; TLS is free text instead of a mode select). [Medium] custom connector create/edit/delete not audited (no audit call in routers/custom_connectors.py). [Low] list shows "0 locked field(s)" — awkward pluralisation.
- Score: 3

### E-52..55 — Single sign-on (`/admin/sso`)
- Screenshots: [E-52-sso](screenshots/E_admin_roles/E-52-sso.png), [E-53-sso-empty-save](screenshots/E_admin_roles/E-53-sso-empty-save.png), [E-54-sso-oidc-bad-values](screenshots/E_admin_roles/E-54-sso-oidc-bad-values.png), [E-55-sso-saml](screenshots/E_admin_roles/E-55-sso-saml.png)
- Works: ✅ OIDC/SAML segmented control, redirect/ACS/metadata URIs shown, required-field toasts ("Domain and issuer URL are required", "SSO URL and signing certificate are required"). Not saved (per brief).
- Issues: [Low] values carry over between protocols (issuer "ftp://bad" became IdP entity ID); no client-side URL/domain format check ("not a domain", "ftp://bad" accepted in fields). [Low] errors only as toasts.
- Score: 4

### E-56/57 — Maps (`/admin/maps`)
- Screenshots: [E-56-maps](screenshots/E_admin_roles/E-56-maps.png), [E-57-maps-bad-tile-url](screenshots/E_admin_roles/E-57-maps-bad-tile-url.png)
- Works: ✅ Basemap form + 5 starter boundary packs with licences; bad tile URL rejected with clear toast "{z} is missing". Not saved/installed.
- Issues: [Low] after a failed save the "Turn basemap off" button appears even though no basemap is configured.
- Score: 4

### E-58/59 — Calendar (`/admin/calendar`)
- Screenshots: [E-58-calendar](screenshots/E_admin_roles/E-58-calendar.png), [E-59-calendar-july-preview](screenshots/E_admin_roles/E-59-calendar-july-preview.png)
- Works: ✅ fiscal-year start select with live preview ("July 1, 2026 falls in FY2026/27, quarter 1"); Save disabled until changed. Reverted, not saved.
- Score: 5

### E-60..63 — Audit trail (`/admin/audit`)
- Screenshots: [E-60-audit](screenshots/E_admin_roles/E-60-audit.png), [E-61-audit-filtered](screenshots/E_admin_roles/E-61-audit-filtered.png), [E-62-audit-empty-filter](screenshots/E_admin_roles/E-62-audit-empty-filter.png), [E-63-audit-row-click](screenshots/E_admin_roles/E-63-audit-row-click.png)
- Works: ✅ User/role/org-unit/API key/export/column-rule events now audited: user.create, user.update ("deactivated", "email from …; role to …"), user.bulk_create, role.create/update ("renamed from"), org_unit.create, user.org_units. Action filter + target filter + "No audit entries match." empty state.
- Issues: [Medium] not audited: custom connector CRUD, connection (Ask AI) rules. [Low] no row detail drawer; no date-range or actor filter; no export. [Low] intro text uses "--" instead of an em dash.
- Score: 4

### E-64..70 — Settings (`/admin/settings`)
- Screenshots: [E-64-org-settings](screenshots/E_admin_roles/E-64-org-settings.png), [E-65-settings-search-super](screenshots/E_admin_roles/E-65-settings-search-super.png), [E-66-llm-test-5s](screenshots/E_admin_roles/E-66-llm-test-5s.png), [E-67-llm-test-result](screenshots/E_admin_roles/E-67-llm-test-result.png), [E-68-settings-full](screenshots/E_admin_roles/E-68-settings-full.png), [E-69-org-settings-security](screenshots/E_admin_roles/E-69-org-settings-security.png), [E-70-settings-deployment-readonly](screenshots/E_admin_roles/E-70-settings-deployment-readonly.png)
- What it shows: "This organization" (Basemap + links to Maps/SSO/Export/Calendar/API keys/Custom connectors) and "Platform (all organizations)" with search + 12 collapsible groups (AI model 19, Embeddings 3, Email 7, Data import 19, Maps 2, Metadata sync 7, Performance 14, Sessions & security 2, Rate limits 5, Answer-quality gate 3, OpenTelemetry 6, Deployment read-only 9).
- Works: ⚠️ search works ("super" -> Platform admins). LLM "Test connection" now fails after ~34 s (was 60 s) with toast "Could not reach the model: ConnectTimeout:" — still empty detail.
- Issues: [Medium] LLM test still slow and message ends with an empty "ConnectTimeout:". [Medium] Platform admins allowlist shown as "admin@datalytics.local,admin,admin@admin.com". [Low] enum settings (cards/free/both; basic/balanced/rich) are free-text inputs, not selects. [Low] many "Allowed: 1 to —." hints — the dash for "no max" reads as a missing value. [Low] /admin/settings duplicates /platform/settings for super admin.
- Score: 3

### E-71..74 — Platform settings (`/platform/settings`)
- Screenshots: [E-71-platform-settings](screenshots/E_admin_roles/E-71-platform-settings.png), [E-72-platform-security-guest-link](screenshots/E_admin_roles/E-72-platform-security-guest-link.png), [E-73-settings-unsaved-bar](screenshots/E_admin_roles/E-73-settings-unsaved-bar.png), [E-74-settings-invalid-save](screenshots/E_admin_roles/E-74-settings-invalid-save.png)
- Works: ✅ Sessions & security shows "Allow links that open without signing in" (currently OFF — not touched) + "Sign-in lasts (hours) 168". Edited "Analyses per connection" = -5 -> "1 unsaved changes" sticky bar with Discard / Save changes; Save -> server rejects "Input should be greater than or equal to 1"; Discarded.
- Issues: [Low] invalid value not flagged inline before saving (only toast after a 400).
- Score: 4

### E-75..81 — Organizations (`/platform/organizations`)
- Screenshots: [E-75-platform-orgs](screenshots/E_admin_roles/E-75-platform-orgs.png), [E-76-edit-quota-dialog](screenshots/E_admin_roles/E-76-edit-quota-dialog.png), [E-77-quota-negative](screenshots/E_admin_roles/E-77-quota-negative.png), [E-78-quota-negative-save](screenshots/E_admin_roles/E-78-quota-negative-save.png), [E-79-org-ai-usage](screenshots/E_admin_roles/E-79-org-ai-usage.png), [E-80-new-org-invalid](screenshots/E_admin_roles/E-80-new-org-invalid.png), [E-81-new-org-short-password](screenshots/E_admin_roles/E-81-new-org-short-password.png)
- Works: ❌/⚠️ Northwind "Max queries/day" = -3 saved silently (no toast seen) and displayed "Queries today: 0 / -3". Reverted to unlimited. AI usage panel: "Last 30 days: 0 tokens", feature/person tables with "No AI use yet". New org: empty -> "Name, admin email and password are required"; "bad-email" -> "admin_email must be an email address"; password "x" accepted -> Created "QA E Org".
- Issues: [High] negative quota accepted client+server. [Medium] 1-char org admin password accepted. [Low] edit quota fields are free text (no numeric input). [Low] the AI-usage "Person / Tokens" table renders an empty header with no rows/empty message.
- Console: 400 on invalid email (expected)
- Score: 2

### E-82 — Monitoring › Activity (`/monitoring/activity`)
- Screenshot: [E-82-monitoring-activity](screenshots/E_admin_roles/E-82-monitoring-activity.png)
- What it shows: org activity log (When / Who / Action / Entity / Detail) incl. platform.set_org_quota "queries=-3", platform.create_org, report.publish/share etc.
- Works: ✅ read-only, newest first; points to Audit trail for security changes.
- Issues: [Low] two overlapping logs (Activity vs Audit trail) with different action names for the same event (dataset.export_policy vs export_policy.set) — confusing. [Low] raw "queries=None asks=None …" detail text.
- Score: 3

### E-83 — Deactivated user sign-in (`/login`)
- Screenshot: (none — driver screenshot hangs on /login; text captured)
- Works: ✅ qa.e.dup (inactive) cannot sign in.
- Issues: [Low] message is the generic "That email and password don't match" — a deactivated user is not told their account is disabled (acceptable for security, but admins get support calls).
- Score: 4

### E-84..90 — demo-global (Global analyst, Default org)
- Screenshots: [E-84-global-home](screenshots/E_admin_roles/E-84-global-home.png), [E-85-global-admin-users-forbidden](screenshots/E_admin_roles/E-85-global-admin-users-forbidden.png), [E-86-global-datasets](screenshots/E_admin_roles/E-86-global-datasets.png), [E-87-global-dashboards](screenshots/E_admin_roles/E-87-global-dashboards.png), [E-88-global-usecase-regional](screenshots/E_admin_roles/E-88-global-usecase-regional.png), [E-89-global-my-dashboards](screenshots/E_admin_roles/E-89-global-my-dashboards.png), [E-90-global-templates](screenshots/E_admin_roles/E-90-global-templates.png)
- Works: ✅ rail = Home, Ask AI, Data (4), Data sources (2), Analyse (6); no Monitoring/Admin/Platform. 6 datasets, 10 dashboards (view only, "View only · why?"), Use case — Regional shows all 4 regions ($8,632,597). My dashboards (/portal) 10 cards. Templates gallery with dataset matcher.
- Issues: [Low] /admin/users, /platform/organizations, /monitoring/activity silently redirect to Home — no 403 page or toast. [Low] My dashboards cards show BOTH "Published" and "Draft" chips on every card — contradictory. [Low] analyst sees "Upload data" / "New connection" / "New dashboard" actions everywhere — no role capability control (see E-16). [Info] /my-dashboards is a 404 (route is /portal) — fine since the rail links correctly, but the label/URL mismatch is odd.
- Console: 401 /auth/me before login only.
- Score: 4

### E-91..103 — demo-emea (Europe only, `cost` hidden)
- Screenshots: [E-91-emea-home](screenshots/E_admin_roles/E-91-emea-home.png), [E-92-emea-usecase-regional](screenshots/E_admin_roles/E-92-emea-usecase-regional.png), [E-93-emea-sales-dataset](screenshots/E_admin_roles/E-93-emea-sales-dataset.png), [E-94-emea-columns-tab](screenshots/E_admin_roles/E-94-emea-columns-tab.png), [E-95-emea-data-tab](screenshots/E_admin_roles/E-95-emea-data-tab.png), [E-96-emea-measures](screenshots/E_admin_roles/E-96-emea-measures.png), [E-97-emea-rules-alerts](screenshots/E_admin_roles/E-97-emea-rules-alerts.png), [E-98-emea-use-in-python](screenshots/E_admin_roles/E-98-emea-use-in-python.png), [E-99-emea-ask-ai](screenshots/E_admin_roles/E-99-emea-ask-ai.png), [E-100-emea-ask-ai-sales-picked](screenshots/E_admin_roles/E-100-emea-ask-ai-sales-picked.png), [E-101-emea-template-mapping](screenshots/E_admin_roles/E-101-emea-template-mapping.png), [E-102-emea-template-use-dialog](screenshots/E_admin_roles/E-102-emea-template-use-dialog.png), [E-103-emea-export-menu](screenshots/E_admin_roles/E-103-emea-export-menu.png)
- Works: ✅ rows: dashboard and data tab show Europe only ("Rows 1–100 of 514 (filtered from 2,000)"; Revenue $2,199,377; Region chip Europe). ✅ `cost` absent from Columns tab (12), Data tab headers, template column mapping, Use in Python. Export dialog says "Exports use the data as you see it, with your data permissions".
- Issues:
  - [Medium] Data › Measures shows formulas "Margin % = (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100" with edit/delete icons to the restricted user.
  - [Medium] "Margin % by region" widget shows raw "Unknown column or function in measure expression: name 'cost' is not defined".
  - [Medium] Overview tab says "Columns 13" and "Rows 2,000" while Columns tab says 12 and Data tab 514 — leaks hidden column count and unfiltered row count; Ask AI picker likewise shows "2,000 rows · 13 columns".
  - [Low] Data tab footer "(filtered from 2,000)" reveals the total row count behind the row rule.
  - [Low] Quality rule "region is one of: Europe, Asia Pacific, North America, Latin America" visible (with Remove) — exposes the other regions' names; also "region has the same value in every row… Leave this column out" advice is an artefact of RLS.
  - [Low] Dataset analysis endpoint 404 (GET /datasets/1/analysis) logged on every visit.
- Console: 404 /api/v1/datasets/1/analysis
- Score: 3

### E-104..106 — admin@contoso.invalid (Contoso org admin)
- Screenshots: E-104-contoso-admin-home.png, [E-105-contoso-report8-blocked](screenshots/E_admin_roles/E-105-contoso-report8-blocked.png), [E-106-contoso-admin-users](screenshots/E_admin_roles/E-106-contoso-admin-users.png)
- Works: ✅ tenant isolation: Datasets empty ("Add your first dataset"), Dashboards 0, /reports/8 -> "Could not load this dashboard / Report not found", /datasets/1 -> "Dataset not found". Users page lists only the 2 Contoso users. Rail has Monitoring + Admin (13 pages) but no Platform; /platform/organizations redirects to Home.
- Issues: [Low] "Report not found" — product says "dashboard" everywhere else. [Low] silent redirect for /platform/*.
- Score: 4

### E-107 — analyst@contoso.invalid
- Screenshot: [E-107-contoso-analyst-home](screenshots/E_admin_roles/E-107-contoso-analyst-home.png) (captured mid-load: "Loading…" splash — page text confirmed the content)
- Works: ✅ "Welcome to Datalytics, Analyst" onboarding; 0 dashboards/datasets/connections; no Monitoring/Admin; /admin/users, /platform/organizations, /monitoring/activity -> Home; /reports/8 -> "Report not found".
- Issues: [Low] silent redirects (no 403).
- Score: 4

### E-108 — admin@northwind.invalid
- Screenshot: [E-108-northwind-admin-home](screenshots/E_admin_roles/E-108-northwind-admin-home.png)
- Works: ✅ isolated (0 datasets/dashboards; Users = 1; Activity "Nothing recorded yet."; /reports/8 not found); Admin rail; Platform blocked (redirect).
- Score: 4

### E-109 — analyst@northwind.invalid
- Screenshot: [E-109-northwind-analyst-home](screenshots/E_admin_roles/E-109-northwind-analyst-home.png)
- Works: ✅ same as Contoso analyst — no Default org content, admin/monitoring/platform URLs redirect home.
- Score: 4

### E-110..112 — admin@example.invalid (Default org admin, not super admin)
- Screenshots: E-110-example-admin-home.png, [E-111-example-admin-users](screenshots/E_admin_roles/E-111-example-admin-users.png), [E-112-admin-users-phone](screenshots/E_admin_roles/E-112-admin-users-phone.png)
- Works: ✅ full Admin + Monitoring rail, no Platform section; /platform/organizations -> Home; sees 11 datasets, 27 dashboards, Activity log, /reports/8 with Share/Present/Export.
- Issues: [High] the org admin's Users page lists the platform super admin admin@datalytics.local with Edit/Delete — an org admin can edit (email/password/role) or delete the super-admin account (no super-admin protection found in backend/app/routers/admin.py). Not executed to avoid breaking other agents. [Low] phone 390px: "Inactive" tag wraps mid-word ("I / nactive"), long emails break at hyphens; Edit/Delete fine.
- Score: 3

### Role × capability matrix (observed on main)
| Capability | super admin (admin@datalytics.local) | org admin (admin@example / contoso / northwind) | demo-global | demo-emea | analyst (contoso / northwind) |
|---|---|---|---|---|---|
| Rail: Monitoring + Admin (13 pages) | ✅ | ✅ | ❌ hidden | ❌ hidden | ❌ hidden |
| Rail: Platform (Organizations, Platform settings) | ✅ | ❌ (URL → Home) | ❌ | ❌ | ❌ |
| /admin/users, /monitoring/activity | ✅ | ✅ (own org only) | ↪ Home (no 403) | ↪ Home | ↪ Home |
| Default-org datasets / dashboards | ✅ 11 / 27 | example: ✅; contoso/northwind: 0 / 0, "not found" | 6 / 10 (view only) | 6 / 10 (view only) | 0 / 0, "not found" |
| Use case — Regional (/reports/8) | ✅ edit | example ✅; others "Report not found" | ✅ all regions | ✅ Europe only; Margin widget errors | "Report not found" |
| Row security (region) | bypass | bypass (org admin) | all rows | Europe only (514 of 2,000) | n/a |
| Column `cost` | visible | visible | visible | hidden in columns/data/templates/Python; formula visible in Measures; counts leak (13 cols/2,000 rows) | n/a |
| Upload / New connection / New dashboard actions | ✅ | ✅ | ✅ shown | ✅ shown | ✅ shown |
| Export dashboard | ✅ | ✅ | ✅ | ✅ (permission-filtered) | n/a |
| Ask AI | offline (no LLM) | offline | offline | offline (picker shows 2,000 rows · 13 cols) | offline |
| Edit/delete super-admin account | ✅ | ⚠️ Edit/Delete buttons shown for admin@datalytics.local (example org) | ❌ | ❌ | ❌ |

### Area summary
- **Score (avg): 3.4 / 5.** The admin area is broad: there is an Organization chart for hierarchical row security, a Connection rules page for Ask AI, a unified Settings page with search, an unsaved-changes bar and server-side range checks, a Maps page with boundary packs, a Calendar page with a live fiscal-year preview, and audit coverage of users, roles and org units. Tenant isolation between Contoso, Northwind and Default holds, and EMEA row and column security works where it matters (data, columns, templates, exports). The fundamentals reported last time are mostly unchanged, though. New users still default to Admin, the server accepts invalid emails and 1-character passwords, case-only duplicate emails get through, duplicate role names are allowed, roles still have no permission matrix, and negative quotas are saved. The headline new feature is also broken: a row rule written with MYSCOPE can't be saved. The org admin can also edit or delete the platform super-admin account.
- **Top issues**

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| E-28 | High | Row security | Quick-setup "Viewer's org-chart units" generates `region in MYSCOPE` and Create fails "name 'MYSCOPE' is not defined" — hierarchical RLS unusable | Expand MYSCOPE with placeholder values in `_validate_filter_expr` (admin.py:229) before validating |
| E-111 | High | Users (org admin) | Org admin sees Edit/Delete on the platform super admin admin@datalytics.local | Hide super admins from org user lists; refuse PUT/DELETE on super admins unless caller is super admin |
| E-02 | High | New user | Role pre-selects "Admin (admin)" | Default to "Select a role…" and require it, or least-privilege |
| E-03 | High | New user | "not-an-email" + password "x" accepted | Server-side email validation + password policy, as bulk import already does |
| E-77 | High | Organizations | Quota -3 saved, shows "0 / -3" | Validate ≥ 0 (client + API) |
| E-15 | High | Roles | No capability matrix — analysts get Upload/Connections/New dashboard | Add per-role permissions |
| E-36/38 | High | Connection rules | Postgres connection's TABLE list empty; expressions not validated; changes not audited | Load tables from metadata; validate against columns; audit |
| E-96 | Medium | EMEA Measures | Formulas referencing hidden `cost` shown to restricted role | Hide measures/calc columns that depend on hidden columns |
| E-93/100 | Medium | EMEA dataset / Ask AI | "13 columns / 2,000 rows" leak hidden-column count and unfiltered row total | Compute counts after RLS/CLS |
| E-92 | Medium | EMEA dashboard | Raw "Unknown column … 'cost' is not defined" in widget | Friendly "hidden by column security" placeholder |
| E-06 | Medium | New user | Case-only duplicate email accepted | Lower-case + unique index |
| E-16 | Medium | Roles | Duplicate role names | Unique (org, name) |
| E-50 | Medium | Custom connectors | Port "abc" saved; CRUD not audited | Typed fields + audit |
| E-67 | Medium | Settings | LLM test ~34 s → "ConnectTimeout:" with empty detail | Short timeout, readable message |
| E-85 | Low | All non-admin | Forbidden URLs silently redirect to Home | 403 page |

- **Strengths**
  - Tenant isolation is solid. Other orgs' dashboards and datasets return "not found", and each org's user list only shows its own users.
  - EMEA row and column security holds across data, columns, templates, Python and export. Export states that it uses the viewer's permissions.
  - Audit trail now covers users, roles, org units, API keys, export policy and column rules, with action and target filters and an empty state.
  - The API key flow is good: the secret is shown once with a Copy button, only the prefix is kept, and revoking needs a styled confirm.
  - Settings are discoverable: search, grouped sections, read-only deployment values, an unsaved-changes bar and server range validation.
  - Explanatory copy on Row security, Connection rules, Org chart, Export policy and Calendar is good, and the fiscal-year preview is live.
- **Not covered / blocked and why**
  - Did not save SSO, basemap, calendar, platform settings, the guest-link toggle or the approval toggle (per brief, F2 owns the last two).
  - Did not install boundary packs, so the Maps settings stay unchanged for others.
  - Did not test editing or deleting the super admin as an org admin; doing it would break other agents.
  - Ask AI answers can't be produced because no LLM runs here, so I only checked the picker and the offline state.
  - Login page screenshots hang the driver under load, so the deactivated-login result was captured as text only. I restarted my own driver once.
  - Glossary governance isn't under Admin on main.
  - QA E artefacts are left in place: users QA.E.User, qa.e.dup (inactive), qa.e.bulk1; roles QA E Role / QA E Role dup; org units QA E Region / QA E Branch; column rule QA E Role margin_pct; custom connector QA E Nile preset; org "QA E Org" (admin qa.e.orgadmin@example.invalid).


---

## F — New on main: templates, suggestions, publishing & sharing, My dashboards
Coverage: ~40 distinct screens/states / 103 screenshots (F-01 … F-103). Accounts: admin@datalytics.local (owner, super admin), qa.f.reader@example.invalid (role "QA F Reader", team "QA F Team"). Viewport 1440×900 desktop only. Data: Demo — Sales, Demo — Feedback (nile_express not needed).

### Setup
#### F-01/02 — Profile "About you" (`/profile`)
- Screenshots: [F-01-profile](screenshots/F_new_features/F-01-profile.png), [F-02-profile-about-saved](screenshots/F_new_features/F-02-profile-about-saved.png)
- Works: ✅ Typed text, Save → header changes "nothing saved yet" → "saved on your profile"; persists after reload.
- Issues: [Low] Save button is a tiny low-contrast ghost button; no toast confirmation, only header text change.
- Console: none (initial 401 /auth/me before login is expected)
- Score: 4

#### F-03..06 — Admin → Roles / Users: created role "QA F Reader" and user qa.f.reader@example.invalid
- Works: ✅ toasts "Role created", "User created". New-user dialog defaults Role to "Admin (admin)" (first option) — [Medium] risky default: an admin who forgets to change the role creates an admin user. Default should be blank/"Select a role…".
- Score: 4

#### F-07..10 — Admin → Org chart: created top-level unit "QA F Team" (level "Team"), placed reader in it
- Works: ✅ two-step add (name → level name). Place a user → tick unit → Save placement.
- Issues: [Low] Save placement gives no visible confirmation (no toast) — unclear it saved.
- Score: 4

### §5 Suggested dashboards

#### F-11..13 — Dashboards → New dashboard → "With AI" (`/reports`)
- Screenshots: [F-11-dashboards-list](screenshots/F_new_features/F-11-dashboards-list.png), [F-12-new-dashboard-dialog](screenshots/F_new_features/F-12-new-dashboard-dialog.png), [F-13-new-dash-with-ai](screenshots/F_new_features/F-13-new-dash-with-ai.png)
- Works: ✅ Create dialog offers Blank / Template / With AI; With AI asks for goal + dataset, button disabled until dataset picked.
- Score: 4

#### F-14..19 — Suggest dashboards with AI ON (goal typed, About you saved) — AI unreachable
- Screenshots: [F-14-suggest-ai-on-5s](screenshots/F_new_features/F-14-suggest-ai-on-5s.png), [F-15-suggest-ai-on-running](screenshots/F_new_features/F-15-suggest-ai-on-running.png), F-16 (35 s), F-17 (69 s), F-18 (115 s), [F-19-suggest-cancelled](screenshots/F_new_features/F-19-suggest-cancelled.png)
- Works: ❌/⚠️ With no LLM reachable the job never fails: spinner "Reading the data, choosing charts… 115s" + "Still going. Large datasets take longer…" — misleading (2,000-row dataset; the real cause is that the AI model is unreachable, which the top bar already knows: red dot "Default — ConnectTimeout"). Cancel works and returns to the form.
- Issues: [High] AI suggestion silently hangs (>2 min, no timeout, no error) when the model is unreachable; should fail fast or fall back to the no-AI statistics engine with a message ("AI not reachable — showing charts picked from your data"). [Medium] the "Still going… large datasets" hint blames data size wrongly.
- Console: none (no failed API call surfaced)
- Score: 2

#### F-20..23 — Top-bar model picker / "AI off"
- Screenshots: [F-20-model-picker](screenshots/F_new_features/F-20-model-picker.png), [F-21-model-picker-explained](screenshots/F_new_features/F-21-model-picker-explained.png), [F-22-manage-models](screenshots/F_new_features/F-22-manage-models.png), [F-23-platform-ai-switch](screenshots/F_new_features/F-23-platform-ai-switch.png)
- What it shows: picker lists Auto ("No model is reachable") and Default ("ConnectTimeout"), Check again, Manage models (→ Platform settings › AI model).
- Works: ⚠️ The top-bar picker has NO "AI off" option (guide §5.4 says "Turn AI off (the model picker in the top bar)"). The only off switch is the platform-wide "AI features on" in Platform settings (affects everyone — not toggled, other agents share the server). The suggest dialog's own documented no-AI path is "leave the goal blank" + clear "About you"; used that instead.
- Issues: [Medium] No per-user "AI off" in the model picker, contrary to the test guide; users with an unreachable model have no way to choose no-AI except clearing their profile text.
- Score: 3

#### F-24..27 — Suggest without AI (blank goal, About you cleared)
- Screenshots: [F-24-suggest-no-ai-result](screenshots/F_new_features/F-24-suggest-no-ai-result.png), F-25/26/27 (created "Headline numbers" dashboard)
- Works: ✅ ~8 s. "Chosen from what stands out in your data — no AI was used…" 41 ideas, 25 kept, sections Headline numbers / Composition / Levels & drivers / Over time / Patterns & models / Detail, each with "Data shows:" sentences; slicers for region/country/month (from–to date control ✅). "Create this dashboard" on one section opened /reports/11 with 3 slicers + KPIs.
- Issues: [Low] "41 ideas (0 from the AI analysts, 30 from the statistics engine)" — 0+30≠41, numbers don't add up. [Low] "adds 1 fields" (plural grammar). [Low] Created dashboard gets the section title ("Headline numbers") or the dataset name ("Demo — Sales") as its name — the second one duplicates the dataset name and is easily confused with seeded "Demo — …" content. [Low] "Median days month to date 13.0" KPI is a meaningless suggestion. [Cosmetic] the country slicer is a cramped native multi-select list clipped mid-word ("Brazil" cut).
- Score: 4

#### F-28..31 — Suggestions pane inside the builder (rail → AI → Suggest), add one
- Screenshots: [F-28-edit-mode](screenshots/F_new_features/F-28-edit-mode.png), [F-29-rail-ai](screenshots/F_new_features/F-29-rail-ai.png), [F-30-suggestions-pane](screenshots/F_new_features/F-30-suggestions-pane.png), [F-31-suggestion-added-one](screenshots/F_new_features/F-31-suggestion-added-one.png)
- Works: ✅ 20 ideas, chips All/Compare/Trend/Distribution/Relationship; "+ Add" adds a widget (6 → 7 widgets). There is NO "add them all" button in this pane (guide §5.5). The add-all equivalent is the Suggest dialog's "Create one dashboard, a page per section (47 visuals)" — ✅ created /reports/12 with 7 pages.
- Issues: [Low] Suggestion cards show a grey empty thumbnail placeholder (no preview drawn). [Medium] No "Add all" in the builder suggestions pane. [Low] "Asia Pacific leads distinct year with 2", "Argentina leads distinct year with 2" — junk suggestions (counting distinct years per group).
- Score: 3

#### F-32..41 — All-suggestions dashboard + Dashboard style looks
- Screenshots: [F-32-all-suggestions-dashboard](screenshots/F_new_features/F-32-all-suggestions-dashboard.png), F-33/34 pages, [F-35-dashboard-style-panel](screenshots/F_new_features/F-35-dashboard-style-panel.png), [F-36-look-midnight-edit](screenshots/F_new_features/F-36-look-midnight-edit.png), [F-37-look-midnight-view](screenshots/F_new_features/F-37-look-midnight-view.png), [F-38-midnight-over-time](screenshots/F_new_features/F-38-midnight-over-time.png), [F-39-look-deepspace](screenshots/F_new_features/F-39-look-deepspace.png), [F-40-look-ember-composition](screenshots/F_new_features/F-40-look-ember-composition.png), F-41-after-leaving
- Works: ✅ Page properties → DASHBOARD STYLE → Ready-made looks (Midnight, Deep space, Ember, Graphite, Clean, Outline) + many controls. Picking Midnight turns the whole dashboard AND the app chrome dark; text readable; app returns to light after leaving (F-41). Headline numbers are plain big numbers — no "gradient trend line" seen on KPI cards as guide expects.
- Issues: [Medium] "Rows by country" bar chart in the Composition page renders as near-invisible stubs with labels crowded at top and a range slider; "Showing 12 of 14 country values (row limit)" — the suggested chart is cut by a row limit. [Low] Page tabs in view mode are clipped ("Patterns & mo…") with no overflow affordance. [Low] Opening the Page filter pane accidentally (the "Filter" chip) overlaps the properties panel (F-35).
- Score: 4

### §6 Templates

#### F-43..45 — Template gallery (`/templates`)
- Screenshots: [F-43-templates](screenshots/F_new_features/F-43-templates.png), F-44-templates-scroll-1..5, [F-45-templates-matched-sales](screenshots/F_new_features/F-45-templates-matched-sales.png)
- What it shows: 22 built-in templates (Executive summary, Performance overview, What goes together, Scorecard, Trends and seasons, Stages and conversion, Target against actual, Activity monitor, Groups compared, Places, Spread and outliers, Rows explorer, What is in the data, Which numbers move together, Natural groups, Which outcome a row will have, What a number depends on, A number through time, What is out of the ordinary, What a column of text says, What is connected to what, Where a number comes from). Filters All/Built-in/Organisation/Mine/Favourites + 11 kinds; each card has star, Preview (eye), "Make my own copy", Use template.
- Works: ✅ "Match to a dataset: Demo — Sales" adds "Best match" badge, "Fits: all N charts" bar, re-sorts; non-fitting ones say "Does not fit this data — Nothing in this data for: The yes-or-no outcome" and their Use template is disabled.
- Issues: [Low] Some card thumbnails are dark and others light — inconsistent gallery look. [Cosmetic] large empty band above the title (top ~100px).
- Score: 4

#### F-46..52 — Executive summary → preview → Use template on Demo — Sales
- Screenshots: [F-46-template-preview-exec](screenshots/F_new_features/F-46-template-preview-exec.png), [F-47-exec-use-template](screenshots/F_new_features/F-47-exec-use-template.png), [F-48-exec-mapping-filled](screenshots/F_new_features/F-48-exec-mapping-filled.png), [F-49-exec-summary-dashboard](screenshots/F_new_features/F-49-exec-summary-dashboard.png) (edit), [F-50-exec-summary-view](screenshots/F_new_features/F-50-exec-summary-view.png), [F-51-exec-groups](screenshots/F_new_features/F-51-exec-groups.png), [F-52-exec-detail](screenshots/F_new_features/F-52-exec-detail.png)
- Works: ✅ Preview drawn on 1,500 sample rows (KPI cards with gradient trend lines, forecast, "What goes with a higher…"). Mapping dialog pre-fills (revenue, date, units, cost, region, product, region-as-place); changed main split + place to country; "16 of 16 charts will be drawn", "Filter controls on each page: date, country, product". Create → /reports/14?edit=1, 4 pages, mine to edit (Draft). KPI cards show gradient sparkline + vs-previous change ✅.
- Issues: [Medium] Mapping auto-suggests `region` as "The place of each row" AND as "main way to split it" — place should prefer country. [Low] In the preview modal the Escape key / "Use template" button at the bottom is easily confused with the card's Use template behind (the card's button is still clickable while the modal is open? — clicking text "Use template" hit a background card first). [Low] Groups page charts show "Loading…" for ~3 s with an empty checkbox icon as spinner. [Low] Revenue-by-month forecast x-axis labels are clipped at the bottom ("4-01, 4-02…"). [Low] Widget titles use raw column names ("revenue over time", "country in detail", "date" slicer title).
- Score: 4

#### F-53..61 — What goes together
- Screenshots: [F-53-wgt-preview](screenshots/F_new_features/F-53-wgt-preview.png), [F-54-wgt-mapping](screenshots/F_new_features/F-54-wgt-mapping.png) (dialog opens with NO dataset chosen even though gallery is matched to Demo — Sales), F-55/56 mapping, F-57/58/59 on Demo — Feedback (topic × sentiment), F-60/61 on Demo — Sales (country × product × channel)
- Works: ⚠️ On Feedback: every chart says "No values appear together more often than chance on these rows." (honest, but 3 huge empty cards). On Sales: ✅ network graph, role matrix (A/C/B), linked bars, rules table, chord — role views work.
- Issues: [Low] Use-template dialog from the preview ignores the gallery's "Match to a dataset" choice (Executive summary did pre-select it; What goes together did not). [Low] Default mapping put `topic` in both 1st and 3rd label slots (duplicate column suggested). [Low] Empty-result cards keep full height (≈500px of blank).
- Note: no basket/transaction dataset exists here (guide's invoice_no/description); the template is column-pair based ("labels"), not basket/item — wording in guide is outdated.
- Score: 4

#### F-62..69 — Analysis templates on Demo — Sales (What is in the data / A number through time / What is out of the ordinary / What a number depends on)
- Screenshots: F-62/63 (in the data), F-64/65 (through time), F-66/67 (out of the ordinary), F-68/69 (depends on)
- Works: ✅ each created a 1-page dashboard instantly (/reports/18–21). In the data: Rows/avg/min/max + histogram + donut. Through time: KPIs with gradient trend + forecast. Out of the ordinary: monthly line with expected band and numbered change-points + plain-language footnotes ("From 2024-06 the level rose: about 306,832 before, 374,790 since (+22%)"). Depends on: R², RMSE, actual vs predicted, residuals, coefficient table with CI/p and caveats ("not causation"). They explain themselves ✅.
- Issues: [Medium] "Rows" KPI on What is in the data shows "$ 2,000" — a row COUNT formatted as currency (inherits revenue's $ format); donut centre also "$ 2,000 Total revenue" — wrong label & unit (it is a row count). [Low] Default names "What is in the data — Demo — Sales" (double em-dash, not prefixed; easy to confuse with seeded Demo content). [Low] Long dashboard names wrap the title onto a second header row (F-67/69) while short ones sit inline — header layout jumps. [Low] Histogram bin labels "-12011.64–-10607.59" unformatted, rotated, unreadable. [Low] "What a number depends on" picks cost as a predictor of revenue (trivially correlated) — fine statistically but not insightful.
- Score: 4

#### F-70..78 — Key influencers widget display options (Exec summary → "What goes with a higher revenue")
- Screenshots: [F-70-ki-selected](screenshots/F_new_features/F-70-ki-selected.png), [F-71-ki-menu](screenshots/F_new_features/F-71-ki-menu.png), [F-72-ki-options](screenshots/F_new_features/F-72-ki-options.png), [F-74-ki-config](screenshots/F_new_features/F-74-ki-config.png), [F-75-ki-bars](screenshots/F_new_features/F-75-ki-bars.png), [F-76-ki-bars-both](screenshots/F_new_features/F-76-ki-bars-both.png), [F-77-ki-details-toggled](screenshots/F_new_features/F-77-ki-details-toggled.png), [F-78-ki-bubbles-details](screenshots/F_new_features/F-78-ki-bubbles-details.png)
- Works: ✅ Options are under widget Properties → Data → Data roles (Drawn as Bubbles/Bars, Show what goes with Higher/Lower/Both, How many, Number shown, Decimal places, "Show the model's own lines"). Switching updates live; details on shows "Key influencers · revenue ~ year + month + region + country + …, Overall average 4,316.298, Rows used 2,000 of 2,000, tabs What goes with it / Fit".
- Issues: [Medium] Options are hard to find: not under Format/Options but buried in Data → Data roles; the widget ⋮ menu offers only Duplicate/Delete (I duplicated the widget by accident because ⋮ opens on first click with Duplicate under the cursor). [Low] "Bars" mode draws no bars in a narrow card — just a text list "month 2024-02 3,348 · 0.78×"; [Low] influencers are dominated by individual months ("month 2025-06") — not useful; [Low] "margin_pct 30.8 …" truncated; "Overall average 4,316.298" unformatted (not $).
- Score: 3

### §7 Publishing & sharing (dashboard: QA F Exec summary, /reports/14)

#### F-79..82 — Share dialog, People tab; share with a person "Can view"
- Screenshots: [F-79-share-dialog](screenshots/F_new_features/F-79-share-dialog.png), [F-80-share-more-options](screenshots/F_new_features/F-80-share-more-options.png), [F-81-share-typed](screenshots/F_new_features/F-81-share-typed.png), [F-82-share-invited](screenshots/F_new_features/F-82-share-invited.png)
- What it shows: tabs People / Publishing / Embed / Schedule; A person/A role/A team; level select; More options (Access ends on, May download and export, May share it with others (view only), Message); People with access; General access Restricted vs Everyone in your organisation; Link to this page; Guest link section says "Links that open without signing in are switched off for this platform."
- Works: ✅ invite added "qa.f.reader — Can view".
- Issues: [Medium] Default access level for a new person is **Can edit** (not Can view) — least-privilege default would be Can view. [Low] the email field has no visible label for automation/screen readers except placeholder ("name@example.com" not matched; aria-label "Email to share with" OK).
- Score: 4

#### F-83..85 — Reader: My dashboards → Shared with me → opens
- Screenshots: [F-83-reader-my-dashboards](screenshots/F_new_features/F-83-reader-my-dashboards.png), [F-84-reader-shared-with-me](screenshots/F_new_features/F-84-reader-shared-with-me.png), [F-85-reader-opens-dashboard](screenshots/F_new_features/F-85-reader-opens-dashboard.png)
- Works: ✅ "QA F Exec summary — Shared with you — By admin@datalytics.local" in All(11) and Shared with me(1); opens view-only with "View only · why?" button; no Edit/Share.
- Issues: [Low] Reader sees **11** dashboards in All — every seeded Demo dashboard is visible to a brand-new non-admin role (they are org-published, so expected, but cards show both "Published" AND "Draft" chips at once — contradictory).
- Score: 4

#### F-86..87 — Share again with end date today + "May download" off
- Works: ✅ row shows "Ends 14 Oct 2026 · No downloads".
- Score: 5

#### F-88..92 — Share with a team
- Screenshots: [F-88-share-team-tab](screenshots/F_new_features/F-88-share-team-tab.png), F-89 (first click on the Share text matched the dialog title — nothing happened), [F-90-team-share-ask](screenshots/F_new_features/F-90-team-share-ask.png) (in-app confirm "Share with everyone in QA F Team (Team)? Every member, now and later…"), [F-91-team-shared](screenshots/F_new_features/F-91-team-shared.png) ("QA F Team — Team, and the teams under it — Can view"), [F-92-reader-my-team](screenshots/F_new_features/F-92-reader-my-team.png)
- Works: ⚠️ Asked first ✅, share row added ✅. BUT as the reader (who IS placed in QA F Team), **My team = 0, "Nothing has been shared with you yet."** — the team share does not appear under My team (it is only counted under Shared with me because of the personal share).
- Issues: [Medium] Team-shared dashboard not listed under My team for a member of that team. [Low] Empty state text in My team says "Nothing has been shared with you yet." although Shared with me has 1 — wording should be specific to the team.
- Score: 3

#### F-93..96 — Reader with "No downloads": Export
- Screenshots: [F-93-reader-export-greyed](screenshots/F_new_features/F-93-reader-export-greyed.png), [F-94-reader-export-click](screenshots/F_new_features/F-94-reader-export-click.png), [F-95-reader-print-view](screenshots/F_new_features/F-95-reader-print-view.png), [F-96-reader-pptx-attempt](screenshots/F_new_features/F-96-reader-pptx-attempt.png)
- Works: ⚠️ Export button is NOT greyed; it opens the Export dialog where PDF / Data (Excel) / Offline package are disabled with "Your access to this dashboard does not include downloads." ✅ — but **Print is still selected and enabled** → "Open print view" → /reports/14/print shows all 4 pages with **"Print / Save as PDF" and "Download PowerPoint"** buttons. Download PowerPoint runs client-side (pptxgenjs from the rendered DOM) — no server check, so a reader with downloads OFF can still save the whole dashboard as PDF/PPTX.
- Issues: [High] "No downloads" share is bypassable via Export → Print → "Print / Save as PDF" / "Download PowerPoint" (client-side export, no permission check). Disable Print/PPTX for no-download shares or hide those buttons. [Low] Export button itself is not greyed with a reason (guide expects greyed).
- Score: 2

#### F-97..100 — Remove access (person and team)
- Screenshots: [F-97-remove-access-ask](screenshots/F_new_features/F-97-remove-access-ask.png), [F-98-remove-team-ask](screenshots/F_new_features/F-98-remove-team-ask.png), [F-99-reader-after-removal](screenshots/F_new_features/F-99-reader-after-removal.png), [F-100-reader-print-after-removal](screenshots/F_new_features/F-100-reader-print-after-removal.png)
- Works: ✅ in-app confirm "Remove access for qa.f.reader…? They will no longer be able to open this dashboard, unless it reaches them another way (their role, their team, a shared folder, or because it is published)". After removing both person + team, the reader's /reports/14 shows "Could not load this dashboard — Report not found" and /reports/14/print "Could not load this report — Report not found" ✅ (no leak).
- Issues: [Low] After removal, the person-level select resets to "Can edit" (default) again.
- Score: 5

#### F-101 — Publishing tab (looked only; not exercised — time)
- Shows State Draft + Archive; Approval checkbox "Ask for approval before anything is published" (org-wide); Details Category/Tags/Save; "Readers may download and export"; Published versions ("Nothing has been published yet."); Owner + Hand over.
- Issues: [Low] The org-wide approval switch sits inside one dashboard's share dialog — easy to flip for the whole organisation by accident; belongs in admin settings (or needs a confirm).
- Score: — (not tested)

#### F-102/103 — My dashboards (admin) + Arabic
- Screenshots: [F-102-admin-my-dashboards](screenshots/F_new_features/F-102-admin-my-dashboards.png), [F-103-my-dashboards-arabic](screenshots/F_new_features/F-103-my-dashboards-arabic.png)
- Works: ✅ Sections All 22 / Made by me 12 / Shared with me 0 / My team 0 / Favourites 0 / Recently opened 14 / Reports sent; search; Owner filter. Arabic: fully RTL, tabs/search/owner filter/chips translated (منشورة / مسودة / لك), counts on the left of labels.
- Issues: [Low] Dashboard names/descriptions (seeded and template-generated "What is in the data — Demo — Sales") stay English in Arabic — content, expected. [Low] No category/tag filter visible on My dashboards (guide expects category / tag / owner filters) — only Owner is shown, perhaps because no category was set.
- Score: 4

### Area summary
- **Score (avg ≈ 3.7).** Templates and the no-AI suggestion engine are the strongest new work: fast, self-explaining, honest about what they did ("no AI was used"), with good mapping dialogs and plain-language notes. Sharing works for the basic person/team/remove flow, with good in-app confirmations and a clean "not found" after removal. The weak points are (1) security of the "No downloads" share — Export → Print still yields Print/Save as PDF and a client-side "Download PowerPoint" for a reader whose downloads are off; (2) team sharing doesn't surface under "My team" for a member; (3) the AI-on path hangs indefinitely when the model is unreachable and there is no per-user "AI off" in the top-bar picker; plus a set of formatting slips (row counts shown as "$ 2,000").
- Top issues:

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| F-95/96 | High | Reader → Export → Print view | Share with "May download" OFF still lets the reader open the print view and use **Print / Save as PDF** and **Download PowerPoint** (client-side pptxgenjs; no server check) — whole dashboard leaves the app | Disable Print option + hide PPTX/Print buttons on /print when the share has no-download; enforce on the server for /print data |
| F-14..18 | High | Suggest dashboards (AI on) | With the model unreachable the job spins >2 min with "Still going… large datasets take longer" — no timeout, no error, no fallback | Fail fast when the LLM health check is red; fall back to the statistics engine with a clear message |
| F-92 | Medium | My dashboards → My team (reader) | Dashboard shared with "QA F Team" is not listed under My team for a member placed in that team (count 0, "Nothing has been shared with you yet") | Resolve team shares (incl. sub-units) for the My team section |
| F-20 | Medium | Top-bar model picker | No "AI off" choice per user (guide §5.4); only a platform-wide switch | Add "Off — no AI" entry to the picker |
| F-63 | Medium | Template "What is in the data" | "Rows" KPI and donut centre show **$ 2,000** / "Total revenue" for a row count | Don't inherit the measure's currency format for count; label donut centre "Rows" |
| F-79 | Medium | Share dialog | New person share defaults to **Can edit** | Default to Can view |
| F-05 | Medium | Admin → New user | Role defaults to "Admin (admin)" | Default to empty "Select a role…" |
| F-70..74 | Medium | Key influencers widget | Display options are buried in Properties → Data → Data roles; ⋮ menu has only Duplicate/Delete (accidental duplicate) | Put "Drawn as / details" in Format, or in the ⋮ menu |
| F-47/48 | Medium | Exec summary mapping | `region` auto-picked as both "main split" and "place of each row" | Prefer country/city for place; avoid reusing a column |
| F-30 | Medium | Builder Suggest pane | No "Add all" button (guide §5.5) | Add "Add all shown" |
| F-24 | Low | Suggest result | "41 ideas (0 from AI, 30 from statistics)" doesn't add up; "adds 1 fields" | Fix counts / plural |
| F-33 | Low | Suggested "Rows by country" | Chart cut by row limit, stubs unreadable | Raise limit for small-cardinality columns |

- Strengths:
  - Statistics-only suggestion engine: ~8 s, 47 visuals over 6 themed pages, slicers incl. from–to date, "Data shows:" sentence under each idea.
  - 22 templates with sample-data previews, dataset fit scoring ("Best match", "Fits: all N charts", "Does not fit — Nothing for: yes/no outcome").
  - Analysis templates explain themselves (change-points with numbers, R²/RMSE/CI with "not causation" caveats).
  - Dashboard looks (Midnight/Deep space/Ember…) restyle the whole dashboard area and app chrome, readable, revert on leaving.
  - Share dialog: clear end-date / no-download chips, in-app confirmations for team share and removal, clean "Report not found" after removal, full RTL Arabic My dashboards.
- Not covered / blocked and why (hard stop 20:05; browser driver lost its page several times after `login`, costing ~10 min):
  - §7.5 Publish to org / publish update / Published versions → Go back to version 1 — not done.
  - §7.6 Archive + Restore, §7.7 Hand over, §7.8 approval-before-publish — not done (approval switch seen only).
  - §7.9 Guest links: only confirmed they are OFF by default ("Links that open without signing in are switched off for this platform"); enabling in Platform settings → Security, logged-out open, and the **map widget → guest link** test were NOT done here (covered in F2). Note: Exec summary has a choropleth map (revenue by country) — ready for that test.
  - §7.10 Row rule for QA F Reader (region = Europe) + verify dashboard/export — not done.
  - §7.11 favourites star, category/tag filters, Reports sent after a schedule — not done; §7.12 Arabic Share dialog — not done (Arabic My dashboards done).
  - Direct download URL "forbidden" check for the no-download reader — not done (print/PPTX bypass found instead).
  - Phone/tablet viewports and dark app theme on these screens — not done.


---

## F2 — Publishing, archive, hand-over, guest links, row rules
Coverage: ~14 screens/states / 55 screenshots (F2-01 … F2-56). Accounts: admin@datalytics.local (owner / super admin), qa.f.reader@example.invalid (role QA F Reader). Viewport 1440×900. Dashboard: QA F Exec summary (/reports/14).
Driver note: `login` often leaves a detached page; worked around with `newpage` + `goto` after each login. Several React buttons ("Release changes", in-app confirm "Go back to this") did not react to the driver's text click (it clicked the wrapper) — used `mouseclick x y`; not an app bug.

### F2-01..06 — Publishing tab: category + tags, publish to organisation (`/reports/14` → Share → Publishing / People)
- Screenshots: [F2-02-publishing-tab](screenshots/F_new_features/F2-02-publishing-tab.png), [F2-03-category-tags-saved](screenshots/F_new_features/F2-03-category-tags-saved.png), [F2-04-publish-org-click](screenshots/F_new_features/F2-04-publish-org-click.png), [F2-05-people-guest-section](screenshots/F_new_features/F2-05-people-guest-section.png), [F2-06-publishing-after-publish](screenshots/F_new_features/F2-06-publishing-after-publish.png)
- What it shows: State Draft/Archive, Approval switch, Details (Category, Tags, Save), "Readers may download and export", Published versions, Owner + Hand over.
- Works: ✅ Category "QA F Sales", tags "qa-f, exec, revenue" saved (persist on reopen). Clicking "Everyone in your organisation" publishes immediately → State "Published — Everyone in your organisation can open it, view only. Published by admin@… on 14 Oct 2026. Readers see version 161".
- Issues: [Low] Details Save gives no toast/confirmation. [Medium] Publishing to the whole organisation is a single click on a radio card with no confirmation (while sharing with a team asks first) — inconsistent and easy to misclick. [Low] Version numbers start at "Version 161" (internal revision counter) — the guide/users expect "version 1"; confusing. [Low] Share-dialog new-person level still defaults to "Can edit".
- Console: none
- Score: 4

### F2-07..19 — Edit, publish update (`/reports/14` edit mode)
- Screenshots: [F2-07-edit-mode](screenshots/F_new_features/F2-07-edit-mode.png), [F2-08-edited-heading](screenshots/F_new_features/F2-08-edited-heading.png), [F2-09-publishing-draft-changes](screenshots/F_new_features/F2-09-publishing-draft-changes.png), [F2-10-published-versions-list](screenshots/F_new_features/F2-10-published-versions-list.png), F2-11/12 unreleased banner, F2-17, [F2-18-released-toast](screenshots/F_new_features/F2-18-released-toast.png), [F2-19-versions-two](screenshots/F_new_features/F2-19-versions-two.png)
- Works: ✅ Set page display title "QA F EDIT v2 heading". Header shows "Unreleased changes [Release changes]"; Publishing tab says "You have changes readers do not see yet." Release → toast "Released: viewers now see this version"; versions list: Version 162 Updated (What readers see), 161 Updated, 161 Published.
- Issues: [Medium] The Publishing tab has no "Publish update" button — the only way to publish an edit is the small "Release changes" button in the builder header; the tab only states that there are unseen changes. Add the action where the state is shown. [Low] Versions list shows two rows both called "Version 161" (Updated + Published) — duplicate labels, impossible to tell apart. [Low] A yellow "This report was changed in another session. Reload…" banner appeared right after my own edit+publish in the same tab (false conflict warning).
- Console: none
- Score: 3

### F2-20..24 — Go back to version 1; reader vs draft
- Screenshots: [F2-20-reader-sees-v162](screenshots/F_new_features/F2-20-reader-sees-v162.png), [F2-21-go-back-confirm](screenshots/F_new_features/F2-21-go-back-confirm.png), [F2-22-went-back](screenshots/F_new_features/F2-22-went-back.png), [F2-23-owner-draft-keeps-edit](screenshots/F_new_features/F2-23-owner-draft-keeps-edit.png), [F2-24-reader-sees-v1](screenshots/F_new_features/F2-24-reader-sees-v1.png)
- Works: ✅ Reader saw the edit (v162). "Go back to this" on the first-published 161 asks in-app "Show readers version 161 again? … Your own draft is not changed" → list gets "Version 161 · Went back — What readers see". Reader reloads: heading gone (v1) ✅; owner's draft still has "QA F EDIT v2 heading" ✅ and status returns to "You have changes readers do not see yet".
- Issues: [Cosmetic] Reader's view shows floating widget hover toolbars (eye/expand) overlapping card tops and a "Saved" status in the footer for a view-only user.
- Console: none
- Score: 4

### F2-25..33 — Archive and Restore
- Screenshots: [F2-25-archive-confirm](screenshots/F_new_features/F2-25-archive-confirm.png) (0 shares), [F2-26-reader-shared](screenshots/F_new_features/F2-26-reader-shared.png), [F2-27-archive-confirm-counts](screenshots/F_new_features/F2-27-archive-confirm-counts.png), [F2-28-archived](screenshots/F_new_features/F2-28-archived.png), [F2-29-reader-archived](screenshots/F_new_features/F2-29-reader-archived.png), [F2-30-reader-archived-print](screenshots/F_new_features/F2-30-reader-archived-print.png), [F2-31-reader-mydash-archived](screenshots/F_new_features/F2-31-reader-mydash-archived.png), [F2-32-owner-archived-view](screenshots/F_new_features/F2-32-owner-archived-view.png), [F2-33-restored](screenshots/F_new_features/F2-33-restored.png)
- Works: ✅ Archive asks in-app: "People will stop being able to open it. 1 shares, 0 links and 0 schedules are kept but do not work until you restore it. Nothing is deleted." State → "Archived — Nobody but you and administrators can open it". Reader (shared Can view + org-published): /reports/14 → "Could not load this dashboard — Report not found"; /reports/14/print → "Report not found"; gone from My dashboards ✅ (no leak). Restore works.
- Issues: [Medium] **Restore brings it back as Published** (org-wide, readers immediately see it again), not as a draft as the guide says — an archived dashboard silently re-publishes. [Low] Owner's archived dashboard view shows no "Archived" banner (F2-32 looks like a normal live dashboard with "Unreleased changes"). [Low] "1 shares" — plural grammar. [Low] Counts did not mention that it was also published to the whole organisation. [Low] Archived 404 in console as `pageerror AxiosError` (unhandled).
- Console: reader: 404 on /reports/14, /translations, /parameters, /bookmarks + [pageerror] AxiosError 404 (uncaught)
- Score: 4

### F2-34..39 — Owner → Hand over
- Screenshots: [F2-34-handover-confirm](screenshots/F_new_features/F2-34-handover-confirm.png), [F2-35-handed-over](screenshots/F_new_features/F2-35-handed-over.png), [F2-36-people-after-handover](screenshots/F_new_features/F2-36-people-after-handover.png), [F2-37-people-after-reload](screenshots/F_new_features/F2-37-people-after-reload.png), [F2-38-new-owner-view](screenshots/F_new_features/F2-38-new-owner-view.png), [F2-39-new-owner-share](screenshots/F_new_features/F2-39-new-owner-share.png)
- Works: ✅ In-app confirm "Hand 'QA F Exec summary' over to qa.f.reader…? They will decide who can open it and whether it is published. You keep editing access." → "Owned by qa.f.reader@example.invalid". After reload old owner appears as "admin — Can edit" share; reader now has Share + Edit and sees "You — Owner". New owner could switch General access to Restricted (unpublish) ✅.
- Issues: [Low] Immediately after hand-over (before reload) the People tab shows "You — Owner" and the reader as "Can view" — stale until reload. [Low] Hand-over input has no autocomplete/validation of org members before the confirm. [Low] New owner unpublishing (Everyone → Restricted) is one click with no confirmation, removing access from the whole org.
- Console: none
- Score: 4

### F2-40..47 — Approval before publishing
- Screenshots: [F2-40-reader-unpublish](screenshots/F_new_features/F2-40-reader-unpublish.png), [F2-41-approval-ticked](screenshots/F_new_features/F2-41-approval-ticked.png), [F2-42-owner-publish-refused](screenshots/F_new_features/F2-42-owner-publish-refused.png), [F2-43-asked-approval](screenshots/F_new_features/F2-43-asked-approval.png), [F2-44-admin-approve-panel](screenshots/F_new_features/F2-44-admin-approve-panel.png), [F2-45-approved](screenshots/F_new_features/F2-45-approved.png), [F2-46-owner-published-after-approval](screenshots/F_new_features/F2-46-owner-published-after-approval.png), [F2-47-approval-unticked](screenshots/F_new_features/F2-47-approval-unticked.png)
- Works: ✅ Admin ticks the org-wide switch → "Not asked for yet … Note (optional) / Ask for approval". Owner (reader, non-admin) clicks Everyone in your organisation → server 409, toast "Your organisation asks for an administrator's approval before a dashboard goes out to its readers, and nobody has asked for approval yet. Ask for a review, then publish once it is approved." Owner Ask for approval with note → "Waiting for approval, asked by …". Admin sees note + Approve / Send back → "Approved by admin@…". Owner publishes → Published, Readers see version 162. Switch UNTICKED at the end ✅ (F2-47).
- Issues: [Medium] The org-wide approval switch is a plain checkbox inside one dashboard's share dialog; it flips for the whole organisation on one click with no confirmation (also seen by F). [Low] After the refused publish, the General access radio stays on "Restricted" correctly, but the refusal comes only as a 5-second toast — the Publishing tab should be pointed to. [Low] Admin has no notification/queue link to the pending request in this flow (had to open the dashboard).
- Console: 409 POST /reports/14/publish (expected refusal)
- Score: 4

### F2-48..55 — Guest links (Platform settings → Sessions and security; Share → Anyone with a guest link)
- Screenshots: [F2-05-people-guest-section](screenshots/F_new_features/F2-05-people-guest-section.png) (off: "Links that open without signing in are switched off for this platform…"), [F2-48-platform-security](screenshots/F_new_features/F2-48-platform-security.png), [F2-49-guest-toggle-on](screenshots/F_new_features/F2-49-guest-toggle-on.png), [F2-50-guest-saved](screenshots/F_new_features/F2-50-guest-saved.png), [F2-51-guest-section-on](screenshots/F_new_features/F2-51-guest-section-on.png), [F2-52-guest-link-created](screenshots/F_new_features/F2-52-guest-link-created.png), [F2-53-guest-copied](screenshots/F_new_features/F2-53-guest-copied.png), F2-54a/b (URL field), F2-55-guest-open-map-dashboard
- Works: ✅ Off by default in the Share dialog. Platform settings: the switch lives under **"Sessions and security"** (guide says "Security"); "1 unsaved changes → Save changes → Settings saved". Share dialog then offers Link expires 1/7/30/90 days, "Pin current layout", Create guest link → "Copy it now: this address is shown only once." + row "admin@… expires 21 Oct 2026 · 0 views · Revoke". Warning box: "Guest viewers see this dashboard … with YOUR data permissions" ✅.
- ❌ **Broken.** Opening the guest link for "QA F Exec summary" (has a country map) in a fresh logged-out page (`clearcookies`, `newpage`, goto /shared/<token>) → **bounced to /login** (sign-in page shown, F2-55). Console: `[http 401] GET /api/v1/map-settings` (plus quiet 401s on /auth/me). The backend itself serves the link: `GET /api/v1/shared/<token>` → **200** without a cookie, so the frontend's map widget calls the authenticated `/map-settings` endpoint and the global 401 handler redirects the guest to /login.
- Issues: [High] Guest links to any dashboard containing a map are unusable: guest bounced to /login by the 401 on /api/v1/map-settings. Fix: make map settings public on the /shared path (or include them in the /shared payload) and do not redirect to /login on 401s from a guest page. [Low] "Copy it now: shown only once" URL field is narrower than the URL, so the token is truncated on screen. With clipboard write blocked the Copy button fails silently (pageerror `NotAllowedError … writeText`) and shows "Copied". [Low] The Platform setting is called "Sessions and security", not "Security". [Low] "1 unsaved changes" (plural grammar).
- Console: 401 GET /api/v1/map-settings → redirect; [pageerror] NotAllowedError Clipboard writeText (headless permission; but the UI showed "Copied")
- Not done (browser driver stuck at the end): contrast guest link on a dashboard **without** a map; "remove maker's access / archive → link says not found" in the browser. Cleanup: the browser could not reach Platform settings after 21:10, so I switched **guest_links_enabled OFF via the same settings API the page uses (PUT /api/v1/platform/settings)**. Verified: the guest link now answers 404 ("none that exists opens") ✅.
- Score: 2

### Area summary
- **Score (avg ≈ 3.5).** Publishing, versions, archive, hand-over and the approval workflow all work end to end. Each one asks first with a clear, plain-language confirmation, and the server enforces the rules: the 409 refusal is backed by a precise toast, and archived dashboards give a clean "Report not found" on both the dashboard and print routes. Weak spots: guest links are broken for any dashboard with a map. Restore re-publishes an archived dashboard to the whole organisation instead of bringing it back as a draft. Publishing an update has no button in the Publishing tab (only "Release changes" in the builder). Version labels repeat an internal counter ("Version 161" twice).
- Top issues:

| ID | Severity | Screen | Issue | Suggested fix |
|---|---|---|---|---|
| F2-55 | High | /shared/<token> (guest, dashboard with map) | Guest is bounced to /login: map widget calls authenticated /api/v1/map-settings → 401 → global redirect | Serve map settings in the /shared payload / public endpoint; never redirect to /login from a guest page |
| F2-33 | Medium | Publishing → Restore | Restore brings the dashboard back **Published** to the whole org, not as a draft | Restore to Draft (or ask "Restore and publish again?") |
| F2-41 | Medium | Share → Publishing → Approval | Org-wide "Ask for approval" switch flips with one click inside a single dashboard's dialog, no confirm | Move to admin settings or add a confirm naming the org-wide effect |
| F2-04 | Medium | Share → People → General access | Publishing to the whole organisation (and unpublishing) is a single click with no confirmation | Confirm like team share does |
| F2-09 | Medium | Publishing tab | No "Publish update" action: the tab only says "You have changes readers do not see yet"; the update is published via the small "Release changes" button in the builder header | Add "Publish these changes" in the tab |
| F2-10/19 | Low | Published versions | Labels use the internal revision ("Version 161" appears twice, Updated + Published) | Number published versions 1, 2, 3… and show time |
| F2-11 | Low | Builder | False "This report was changed in another session" banner right after own edit/publish | Ignore own-session revisions |
| F2-32 | Low | Archived dashboard (owner) | No "Archived" banner while viewing an archived dashboard | Show a state banner with Restore |
| F2-28 | Low | Archive confirm | "1 shares", counts omit org-wide publication | Pluralise; mention "published to everyone" |
| F2-53 | Low | Guest link created | Show-once URL is truncated in the field; Copy shows "Copied" even when clipboard write fails | Wrap/select-all field; show error on copy failure |

- Strengths: plain-language confirmations everywhere (archive counts, hand-over effects, go-back "your draft is not changed"); server-side enforcement of approval (409 + helpful message); readers correctly get v1 after Go back while the owner's draft keeps the edit; archived dashboards are fully hidden from readers (dashboard, print, My dashboards); hand-over keeps the old owner as editor; guest-link panel warns that guests see data with the maker's permissions, has expiry, pinning, view counter and Revoke.
- Not covered / blocked and why: the browser driver kept detaching pages after `login` (each account switch cost 2–5 min under load avg ≈ 13), and stopped signing in at all after 21:10. Not done: §7.9 contrast link on a no-map dashboard and "remove maker's access/archive → not found" in the browser (the API check after the toggle-off returned 404); **§7.10 row rule (region = Europe for QA F Reader) — not done**; **§7.11 My dashboards filters / Favourites / Reports sent after schedule — not done**; **§7.12 Arabic Share dialog + My dashboards — not done** (F did Arabic My dashboards).
- State left behind: QA F Exec summary (/reports/14) is now **owned by qa.f.reader@example.invalid**, admin has Can edit, published to the organisation (v162), category "QA F Sales", tags qa-f/exec/revenue, page 1 display title "QA F EDIT v2 heading" in the draft. Two guest links exist on it (inactive because the platform switch is OFF). Approval switch OFF. Guest-links platform switch OFF.


---

## 8. Screenshot index

Every screenshot in this package, in journey order per area.

### QA plan — 57 high cases — 40 screenshots

- [ADM-02](screenshots/QA/ADM-02.png)
- [ASK-02](screenshots/QA/ASK-02.png)
- [ASK-04](screenshots/QA/ASK-04.png)
- [AUTH-01](screenshots/QA/AUTH-01.png)
- [BUILD-01](screenshots/QA/BUILD-01.png)
- [BUILD-02](screenshots/QA/BUILD-02.png)
- [BUILD-02b](screenshots/QA/BUILD-02b.png)
- [BUILD-03](screenshots/QA/BUILD-03.png)
- [BUILD-04](screenshots/QA/BUILD-04.png)
- [BUILD-06](screenshots/QA/BUILD-06.png)
- [BUILD-07](screenshots/QA/BUILD-07.png)
- [BUILD-08](screenshots/QA/BUILD-08.png)
- [BUILD-10](screenshots/QA/BUILD-10.png)
- [CONN-02](screenshots/QA/CONN-02.png)
- [DASH-03](screenshots/QA/DASH-03.png)
- [DASH-03b](screenshots/QA/DASH-03b.png)
- [DASH-04](screenshots/QA/DASH-04.png)
- [DASH-04a](screenshots/QA/DASH-04a.png)
- [DS-03](screenshots/QA/DS-03.png)
- [HOME-01](screenshots/QA/HOME-01.png)
- [INS-01](screenshots/QA/INS-01.png)
- [INS-02](screenshots/QA/INS-02.png)
- [LIN-01](screenshots/QA/LIN-01.png)
- [MAP-00](screenshots/QA/MAP-00.png)
- [MAP-01](screenshots/QA/MAP-01.png)
- [MAP-02-zoom](screenshots/QA/MAP-02-zoom.png)
- [MAP-02](screenshots/QA/MAP-02.png)
- [MAP-03](screenshots/QA/MAP-03.png)
- [MAP-04](screenshots/QA/MAP-04.png)
- [MAP-04a](screenshots/QA/MAP-04a.png)
- [MAP-04b](screenshots/QA/MAP-04b.png)
- [MAP-04c](screenshots/QA/MAP-04c.png)
- [MAP-04d](screenshots/QA/MAP-04d.png)
- [MOB-03](screenshots/QA/MOB-03.png)
- [SEC-01](screenshots/QA/SEC-01.png)
- [SEC-02](screenshots/QA/SEC-02.png)
- [SHARE-01](screenshots/QA/SHARE-01.png)
- [UP-01](screenshots/QA/UP-01.png)
- [UP-02](screenshots/QA/UP-02.png)
- [UP-02b](screenshots/QA/UP-02b.png)

### A — Shell, login, home, global UI — 88 screenshots

- [A-01-login](screenshots/A_shell/A-01-login.png)
- [A-02-login-empty](screenshots/A_shell/A-02-login-empty.png)
- [A-03-login-invalid-email](screenshots/A_shell/A-03-login-invalid-email.png)
- [A-04-login-wrong-password](screenshots/A_shell/A-04-login-wrong-password.png)
- [A-05-login-unknown-user](screenshots/A_shell/A-05-login-unknown-user.png)
- [A-07-sso-callback-noparams](screenshots/A_shell/A-07-sso-callback-noparams.png)
- [A-08-deeplink-after-login](screenshots/A_shell/A-08-deeplink-after-login.png)
- [A-08-deeplink-lands-home](screenshots/A_shell/A-08-deeplink-lands-home.png)
- [A-08b-protected-loading](screenshots/A_shell/A-08b-protected-loading.png)
- [A-09-home](screenshots/A_shell/A-09-home.png)
- [A-09b-home-full](screenshots/A_shell/A-09b-home-full.png)
- [A-10-home-dashboards-section](screenshots/A_shell/A-10-home-dashboards-section.png)
- [A-11-home-datasets-section](screenshots/A_shell/A-11-home-datasets-section.png)
- [A-12-home-bottom](screenshots/A_shell/A-12-home-bottom.png)
- [A-13-home-dash-mine](screenshots/A_shell/A-13-home-dash-mine.png)
- [A-14-home-dash-sort](screenshots/A_shell/A-14-home-dash-sort.png)
- [A-15-home-card-menu](screenshots/A_shell/A-15-home-card-menu.png)
- [A-16-account-menu](screenshots/A_shell/A-16-account-menu.png)
- [A-17-profile](screenshots/A_shell/A-17-profile.png)
- [A-18-profile-saved](screenshots/A_shell/A-18-profile-saved.png)
- [A-18a-profile-typed](screenshots/A_shell/A-18a-profile-typed.png)
- [A-19-model-picker](screenshots/A_shell/A-19-model-picker.png)
- [A-20-notifications](screenshots/A_shell/A-20-notifications.png)
- [A-21-command-palette](screenshots/A_shell/A-21-command-palette.png)
- [A-22-palette-search](screenshots/A_shell/A-22-palette-search.png)
- [A-23-palette-open-dashboard](screenshots/A_shell/A-23-palette-open-dashboard.png)
- [A-24-rail-admin-expanded](screenshots/A_shell/A-24-rail-admin-expanded.png)
- [A-25-rail-admin-scrolled](screenshots/A_shell/A-25-rail-admin-scrolled.png)
- [A-26-rail-groups-collapsed](screenshots/A_shell/A-26-rail-groups-collapsed.png)
- [A-27-rail-collapsed](screenshots/A_shell/A-27-rail-collapsed.png)
- [A-27b-rail-collapsed-hover](screenshots/A_shell/A-27b-rail-collapsed-hover.png)
- [A-28-dest-ask](screenshots/A_shell/A-28-dest-ask.png)
- [A-29-dest-datasets](screenshots/A_shell/A-29-dest-datasets.png)
- [A-30-dest-lineage](screenshots/A_shell/A-30-dest-lineage.png)
- [A-31-dest-glossary](screenshots/A_shell/A-31-dest-glossary.png)
- [A-32-dest-dataflows](screenshots/A_shell/A-32-dest-dataflows.png)
- [A-33-dest-upload](screenshots/A_shell/A-33-dest-upload.png)
- [A-34-dest-connections](screenshots/A_shell/A-34-dest-connections.png)
- [A-35-dest-reports](screenshots/A_shell/A-35-dest-reports.png)
- [A-36-dest-portal](screenshots/A_shell/A-36-dest-portal.png)
- [A-37-dest-templates](screenshots/A_shell/A-37-dest-templates.png)
- [A-38-dest-insights](screenshots/A_shell/A-38-dest-insights.png)
- [A-39-dest-automation](screenshots/A_shell/A-39-dest-automation.png)
- [A-40-dest-migration](screenshots/A_shell/A-40-dest-migration.png)
- [A-41-dest-monitoring-jobs](screenshots/A_shell/A-41-dest-monitoring-jobs.png)
- [A-42-dest-monitoring-deliveries](screenshots/A_shell/A-42-dest-monitoring-deliveries.png)
- [A-43-dest-monitoring-activity](screenshots/A_shell/A-43-dest-monitoring-activity.png)
- [A-44-dest-admin-settings](screenshots/A_shell/A-44-dest-admin-settings.png)
- [A-45-dest-admin-users](screenshots/A_shell/A-45-dest-admin-users.png)
- [A-46-dest-admin-roles](screenshots/A_shell/A-46-dest-admin-roles.png)
- [A-47-dest-admin-org-units](screenshots/A_shell/A-47-dest-admin-org-units.png)
- [A-48-dest-admin-row-security-rules](screenshots/A_shell/A-48-dest-admin-row-security-rules.png)
- [A-49-dest-admin-column-security-rules](screenshots/A_shell/A-49-dest-admin-column-security-rules.png)
- [A-50-dest-admin-export-policy](screenshots/A_shell/A-50-dest-admin-export-policy.png)
- [A-51-dest-admin-api-keys](screenshots/A_shell/A-51-dest-admin-api-keys.png)
- [A-52-dest-admin-custom-connectors](screenshots/A_shell/A-52-dest-admin-custom-connectors.png)
- [A-53-dest-admin-sso](screenshots/A_shell/A-53-dest-admin-sso.png)
- [A-54-dest-admin-maps](screenshots/A_shell/A-54-dest-admin-maps.png)
- [A-55-dest-admin-calendar](screenshots/A_shell/A-55-dest-admin-calendar.png)
- [A-56-dest-admin-audit](screenshots/A_shell/A-56-dest-admin-audit.png)
- [A-57-dest-platform-organizations](screenshots/A_shell/A-57-dest-platform-organizations.png)
- [A-58-dest-platform-settings](screenshots/A_shell/A-58-dest-platform-settings.png)
- [A-59-home-arabic](screenshots/A_shell/A-59-home-arabic.png)
- [A-60-datasets-arabic](screenshots/A_shell/A-60-datasets-arabic.png)
- [A-61-rtl-english](screenshots/A_shell/A-61-rtl-english.png)
- [A-61b-ltr-restored](screenshots/A_shell/A-61b-ltr-restored.png)
- [A-62-home-dark](screenshots/A_shell/A-62-home-dark.png)
- [A-63-dataset-dark](screenshots/A_shell/A-63-dataset-dark.png)
- [A-64-dashboard-dark](screenshots/A_shell/A-64-dashboard-dark.png)
- [A-65-404](screenshots/A_shell/A-65-404.png)
- [A-66-embed-noparams](screenshots/A_shell/A-66-embed-noparams.png)
- [A-67-home-continue-setup](screenshots/A_shell/A-67-home-continue-setup.png)
- [A-68-phone-home](screenshots/A_shell/A-68-phone-home.png)
- [A-69-phone-drawer](screenshots/A_shell/A-69-phone-drawer.png)
- [A-70-phone-datasets](screenshots/A_shell/A-70-phone-datasets.png)
- [A-71-phone-dashboard](screenshots/A_shell/A-71-phone-dashboard.png)
- [A-72-phone-account-menu](screenshots/A_shell/A-72-phone-account-menu.png)
- [A-73-tablet-home](screenshots/A_shell/A-73-tablet-home.png)
- [A-74-tablet-drawer](screenshots/A_shell/A-74-tablet-drawer.png)
- [A-75-tablet-datasets](screenshots/A_shell/A-75-tablet-datasets.png)
- [A-76-tablet-dashboard](screenshots/A_shell/A-76-tablet-dashboard.png)
- [A-77-tablet-account-menu](screenshots/A_shell/A-77-tablet-account-menu.png)
- [A-78-tablet-login-after-logout](screenshots/A_shell/A-78-tablet-login-after-logout.png)
- [A-79-phone-login](screenshots/A_shell/A-79-phone-login.png)
- [A-80-login-tab-focus](screenshots/A_shell/A-80-login-tab-focus.png)
- [A-82-after-skip-focus](screenshots/A_shell/A-82-after-skip-focus.png)
- [A-83-home-contoso-analyst-empty](screenshots/A_shell/A-83-home-contoso-analyst-empty.png)
- [A-84-home-demo-emea](screenshots/A_shell/A-84-home-demo-emea.png)

### B — Data (incl. B2) — 215 screenshots

- [B-01-datasets-list](screenshots/B_data/B-01-datasets-list.png)
- [B-02-row-menu-last](screenshots/B_data/B-02-row-menu-last.png)
- [B-03-sort-menu](screenshots/B_data/B-03-sort-menu.png)
- [B-04-filter-live](screenshots/B_data/B-04-filter-live.png)
- [B-05-bulk-select](screenshots/B_data/B-05-bulk-select.png)
- [B-06-sales-overview](screenshots/B_data/B-06-sales-overview.png)
- [B-07-sales-overview-lower](screenshots/B_data/B-07-sales-overview-lower.png)
- [B-08-sales-profiled](screenshots/B_data/B-08-sales-profiled.png)
- [B-09-sales-insights](screenshots/B_data/B-09-sales-insights.png)
- [B-10-sales-columns](screenshots/B_data/B-10-sales-columns.png)
- [B-100-conn-sqlalchemy-url](screenshots/B_data/B-100-conn-sqlalchemy-url.png)
- [B-101-conn-pg-filled](screenshots/B_data/B-101-conn-pg-filled.png)
- [B-102-conn-pg-tested](screenshots/B_data/B-102-conn-pg-tested.png)
- [B-103-conn-created](screenshots/B_data/B-103-conn-created.png)
- [B-104-setup-understand](screenshots/B_data/B-104-setup-understand.png)
- [B-105-setup-after-reload](screenshots/B_data/B-105-setup-after-reload.png)
- [B-106-setup-read-click](screenshots/B_data/B-106-setup-read-click.png)
- [B-107-review-page](screenshots/B_data/B-107-review-page.png)
- [B-108-review-sync-stuck](screenshots/B_data/B-108-review-sync-stuck.png)
- [B-109-connections-two](screenshots/B_data/B-109-connections-two.png)
- [B-11-sales-columns-lower](screenshots/B_data/B-11-sales-columns-lower.png)
- [B-110-browse-schema](screenshots/B_data/B-110-browse-schema.png)
- [B-111-browse-shipments](screenshots/B_data/B-111-browse-shipments.png)
- [B-112-import-shipments](screenshots/B_data/B-112-import-shipments.png)
- [B-113-browse-complaints-dq](screenshots/B_data/B-113-browse-complaints-dq.png)
- [B-114-dq-complaints-created](screenshots/B_data/B-114-dq-complaints-created.png)
- [B-115-review-later](screenshots/B_data/B-115-review-later.png)
- [B-116-setup-later](screenshots/B_data/B-116-setup-later.png)
- [B-117-review-source-health](screenshots/B_data/B-117-review-source-health.png)
- [B-118-review-more-menu](screenshots/B_data/B-118-review-more-menu.png)
- [B-119-sqlite-review](screenshots/B_data/B-119-sqlite-review.png)
- [B-12-sales-data-grid](screenshots/B_data/B-12-sales-data-grid.png)
- [B-120-sqlite-sync](screenshots/B_data/B-120-sqlite-sync.png)
- [B-121-dataflows-list](screenshots/B_data/B-121-dataflows-list.png)
- [B-122-dataflow-editor](screenshots/B_data/B-122-dataflow-editor.png)
- [B-123-dataflow-created](screenshots/B_data/B-123-dataflow-created.png)
- [B-124-dataflow-sort-step](screenshots/B_data/B-124-dataflow-sort-step.png)
- [B-125-dataflow-save-empty-sort](screenshots/B_data/B-125-dataflow-save-empty-sort.png)
- [B-126-dataflow-saved](screenshots/B_data/B-126-dataflow-saved.png)
- [B-127-dataflow-run](screenshots/B_data/B-127-dataflow-run.png)
- [B-128-lineage-graph](screenshots/B_data/B-128-lineage-graph.png)
- [B-129-lineage-node-selected](screenshots/B_data/B-129-lineage-node-selected.png)
- [B-13-filter-panel](screenshots/B_data/B-13-filter-panel.png)
- [B-130-lineage-issues-only](screenshots/B_data/B-130-lineage-issues-only.png)
- [B-131-lineage-list](screenshots/B_data/B-131-lineage-list.png)
- [B-132-lineage-search](screenshots/B_data/B-132-lineage-search.png)
- [B-133-lineage-graph-search](screenshots/B_data/B-133-lineage-graph-search.png)
- [B-134-migration](screenshots/B_data/B-134-migration.png)
- [B-135-migration-sas-map](screenshots/B_data/B-135-migration-sas-map.png)
- [B-136-migration-item-added](screenshots/B_data/B-136-migration-item-added.png)
- [B-137-migration-item-detail](screenshots/B_data/B-137-migration-item-detail.png)
- [B-138-migration-linked](screenshots/B_data/B-138-migration-linked.png)
- [B-139-migration-csv-import](screenshots/B_data/B-139-migration-csv-import.png)
- [B-14-filter-applied](screenshots/B_data/B-14-filter-applied.png)
- [B-140-sales-phone](screenshots/B_data/B-140-sales-phone.png)
- [B-141-datasets-phone](screenshots/B_data/B-141-datasets-phone.png)
- [B-142-build-dashboard](screenshots/B_data/B-142-build-dashboard.png)
- [B-143-suggest-dashboards-3s](screenshots/B_data/B-143-suggest-dashboards-3s.png)
- [B-144-suggest-dashboards-33s](screenshots/B_data/B-144-suggest-dashboards-33s.png)
- [B-145-suggest-run-20s](screenshots/B_data/B-145-suggest-run-20s.png)
- [B-146-suggest-running](screenshots/B_data/B-146-suggest-running.png)
- [B-147-suggest-result-45s](screenshots/B_data/B-147-suggest-result-45s.png)
- [B-148-suggest-result-95s](screenshots/B_data/B-148-suggest-result-95s.png)
- [B-149-suggest-cancelled](screenshots/B_data/B-149-suggest-cancelled.png)
- [B-15-filter-removed](screenshots/B_data/B-15-filter-removed.png)
- [B-150-leave-rows-out](screenshots/B_data/B-150-leave-rows-out.png)
- [B-151-analysis-anomalies](screenshots/B_data/B-151-analysis-anomalies.png)
- [B-152-outlier-inspect](screenshots/B_data/B-152-outlier-inspect.png)
- [B-16-edit-cells](screenshots/B_data/B-16-edit-cells.png)
- [B-17-edit-cell-active](screenshots/B_data/B-17-edit-cell-active.png)
- [B-18-calc-column-dialog](screenshots/B_data/B-18-calc-column-dialog.png)
- [B-19-calc-add-form](screenshots/B_data/B-19-calc-add-form.png)
- [B-20-calc-formula-mode](screenshots/B_data/B-20-calc-formula-mode.png)
- [B-21-calc-test](screenshots/B_data/B-21-calc-test.png)
- [B-22-calc-saved](screenshots/B_data/B-22-calc-saved.png)
- [B-23-group-bin](screenshots/B_data/B-23-group-bin.png)
- [B-24-measures](screenshots/B_data/B-24-measures.png)
- [B-25-steps-panel](screenshots/B_data/B-25-steps-panel.png)
- [B-26-add-step-menu](screenshots/B_data/B-26-add-step-menu.png)
- [B-27-add-step-after-esc](screenshots/B_data/B-27-add-step-after-esc.png)
- [B-28-add-step-after-outside](screenshots/B_data/B-28-add-step-after-outside.png)
- [B-29-step-filter-rows-form](screenshots/B_data/B-29-step-filter-rows-form.png)
- [B-30-sales-analysis](screenshots/B_data/B-30-sales-analysis.png)
- [B-31-analysis-insights](screenshots/B_data/B-31-analysis-insights.png)
- [B-32-sales-rules](screenshots/B_data/B-32-sales-rules.png)
- [B-33-add-rule-form](screenshots/B_data/B-33-add-rule-form.png)
- [B-34-check-allowed-values](screenshots/B_data/B-34-check-allowed-values.png)
- [B-35-check-added](screenshots/B_data/B-35-check-added.png)
- [B-36-check-run](screenshots/B_data/B-36-check-run.png)
- [B-37-quality-report](screenshots/B_data/B-37-quality-report.png)
- [B-38-quality-report-result](screenshots/B_data/B-38-quality-report-result.png)
- [B-39-sales-models](screenshots/B_data/B-39-sales-models.png)
- [B-40-more-actions-menu](screenshots/B_data/B-40-more-actions-menu.png)
- [B-41-share-dialog](screenshots/B_data/B-41-share-dialog.png)
- [B-42-use-in-python](screenshots/B_data/B-42-use-in-python.png)
- [B-43-ask-about-data](screenshots/B_data/B-43-ask-about-data.png)
- [B-44-ask-answer-no-llm](screenshots/B_data/B-44-ask-answer-no-llm.png)
- [B-45-dq-overview](screenshots/B_data/B-45-dq-overview.png)
- [B-46-dq-data](screenshots/B_data/B-46-dq-data.png)
- [B-47-dq-filter-panel](screenshots/B_data/B-47-dq-filter-panel.png)
- [B-48-dq-calc-panel](screenshots/B_data/B-48-dq-calc-panel.png)
- [B-49-dq-aggregates](screenshots/B_data/B-49-dq-aggregates.png)
- [B-50-dq-rules](screenshots/B_data/B-50-dq-rules.png)
- [B-51-dq-columns](screenshots/B_data/B-51-dq-columns.png)
- [B-52-dq-analysis](screenshots/B_data/B-52-dq-analysis.png)
- [B-53-dq-models](screenshots/B_data/B-53-dq-models.png)
- [B-54-dq-more-menu](screenshots/B_data/B-54-dq-more-menu.png)
- [B-55-dataset-2-overview](screenshots/B_data/B-55-dataset-2-overview.png)
- [B-56-dataset-3-overview](screenshots/B_data/B-56-dataset-3-overview.png)
- [B-57-dataset-4-overview](screenshots/B_data/B-57-dataset-4-overview.png)
- [B-58-dataset-5-overview](screenshots/B_data/B-58-dataset-5-overview.png)
- [B-59-routes-data](screenshots/B_data/B-59-routes-data.png)
- [B-60-feedback-columns](screenshots/B_data/B-60-feedback-columns.png)
- [B-61-glossary-list](screenshots/B_data/B-61-glossary-list.png)
- [B-62-glossary-add-term](screenshots/B_data/B-62-glossary-add-term.png)
- [B-63-glossary-empty-save](screenshots/B_data/B-63-glossary-empty-save.png)
- [B-64-glossary-filled](screenshots/B_data/B-64-glossary-filled.png)
- [B-65-glossary-term-saved](screenshots/B_data/B-65-glossary-term-saved.png)
- [B-66-glossary-always-toggled](screenshots/B_data/B-66-glossary-always-toggled.png)
- [B-67-upload-page](screenshots/B_data/B-67-upload-page.png)
- [B-68-upload-review](screenshots/B_data/B-68-upload-review.png)
- [B-69-upload-empty-name](screenshots/B_data/B-69-upload-empty-name.png)
- [B-70-upload-empty-name-submit](screenshots/B_data/B-70-upload-empty-name-submit.png)
- [B-71-upload-type-click](screenshots/B_data/B-71-upload-type-click.png)
- [B-72-upload-progress](screenshots/B_data/B-72-upload-progress.png)
- [B-73-upload-result](screenshots/B_data/B-73-upload-result.png)
- [B-74-upload-opened](screenshots/B_data/B-74-upload-opened.png)
- [B-75-upload-sample2-review](screenshots/B_data/B-75-upload-sample2-review.png)
- [B-76-upload-add-txt](screenshots/B_data/B-76-upload-add-txt.png)
- [B-77-upload-txt-preview](screenshots/B_data/B-77-upload-txt-preview.png)
- [B-78-upload-txt-only](screenshots/B_data/B-78-upload-txt-only.png)
- [B-79-upload-txt-result](screenshots/B_data/B-79-upload-txt-result.png)
- [B-80-upload-xlsx-review](screenshots/B_data/B-80-upload-xlsx-review.png)
- [B-81-upload-xlsx-result](screenshots/B_data/B-81-upload-xlsx-result.png)
- [B-82-upload-xlsx-try-again](screenshots/B_data/B-82-upload-xlsx-try-again.png)
- [B-83-connections-list](screenshots/B_data/B-83-connections-list.png)
- [B-84-new-connection-dialog](screenshots/B_data/B-84-new-connection-dialog.png)
- [B-85-conn-postgres-form](screenshots/B_data/B-85-conn-postgres-form.png)
- [B-86-conn-postgres-empty-submit](screenshots/B_data/B-86-conn-postgres-empty-submit.png)
- [B-87-conn-mysql](screenshots/B_data/B-87-conn-mysql.png)
- [B-88-conn-sql-server](screenshots/B_data/B-88-conn-sql-server.png)
- [B-89-conn-oracle-database](screenshots/B_data/B-89-conn-oracle-database.png)
- [B-90-conn-sqlite](screenshots/B_data/B-90-conn-sqlite.png)
- [B-91-conn-duckdb](screenshots/B_data/B-91-conn-duckdb.png)
- [B-92-conn-microsoft-access](screenshots/B_data/B-92-conn-microsoft-access.png)
- [B-93-conn-snowflake](screenshots/B_data/B-93-conn-snowflake.png)
- [B-94-conn-google-bigquery](screenshots/B_data/B-94-conn-google-bigquery.png)
- [B-95-conn-databricks-sql](screenshots/B_data/B-95-conn-databricks-sql.png)
- [B-96-conn-clickhouse](screenshots/B_data/B-96-conn-clickhouse.png)
- [B-97-conn-trino](screenshots/B_data/B-97-conn-trino.png)
- [B-98-conn-web-api](screenshots/B_data/B-98-conn-web-api.png)
- [B-99-conn-odbc-generic](screenshots/B_data/B-99-conn-odbc-generic.png)
- [B2-01-connections-list](screenshots/B_data/B2-01-connections-list.png)
- [B2-02-sqlite-review-before](screenshots/B_data/B2-02-sqlite-review-before.png)
- [B2-03-sqlite-sync-clicked](screenshots/B_data/B2-03-sqlite-sync-clicked.png)
- [B2-04-sqlite-sync-after](screenshots/B_data/B2-04-sqlite-sync-after.png)
- [B2-05-sqlite-after-reload](screenshots/B_data/B2-05-sqlite-after-reload.png)
- [B2-06-sqlite-tab-columns](screenshots/B_data/B2-06-sqlite-tab-columns.png)
- [B2-06b-sqlite-columns-scrolled](screenshots/B_data/B2-06b-sqlite-columns-scrolled.png)
- [B2-07-sqlite-tab-entities](screenshots/B_data/B2-07-sqlite-tab-entities.png)
- [B2-08-sqlite-tab-terms](screenshots/B_data/B2-08-sqlite-tab-terms.png)
- [B2-09-sqlite-tab-drift](screenshots/B_data/B2-09-sqlite-tab-drift.png)
- [B2-10-sqlite-tab-health](screenshots/B_data/B2-10-sqlite-tab-health.png)
- [B2-10b-sqlite-tab-relationships](screenshots/B_data/B2-10b-sqlite-tab-relationships.png)
- [B2-11-sqlite-columns-expanded](screenshots/B_data/B2-11-sqlite-columns-expanded.png)
- [B2-12-sqlite-tab-entities](screenshots/B_data/B2-12-sqlite-tab-entities.png)
- [B2-13-sqlite-holds-click](screenshots/B_data/B2-13-sqlite-holds-click.png)
- [B2-14-nile-review-before](screenshots/B_data/B2-14-nile-review-before.png)
- [B2-15-setup-step1](screenshots/B_data/B2-15-setup-step1.png)
- [B2-16-setup-reading](screenshots/B_data/B2-16-setup-reading.png)
- [B2-17-setup-read-15s](screenshots/B_data/B2-17-setup-read-15s.png)
- [B2-18-setup-step1-60s](screenshots/B_data/B2-18-setup-step1-60s.png)
- [B2-19-setup-sample-rows](screenshots/B_data/B2-19-setup-sample-rows.png)
- [B2-20-setup-system-tables](screenshots/B_data/B2-20-setup-system-tables.png)
- [B2-21-setup-details](screenshots/B_data/B2-21-setup-details.png)
- [B2-22-setup-step2](screenshots/B_data/B2-22-setup-step2.png)
- [B2-23-setup-suggest-3s](screenshots/B_data/B2-23-setup-suggest-3s.png)
- [B2-24-setup-suggest-33s](screenshots/B_data/B2-24-setup-suggest-33s.png)
- [B2-25-setup-suggest-80s](screenshots/B_data/B2-25-setup-suggest-80s.png)
- [B2-26-setup-step2-picked](screenshots/B_data/B2-26-setup-step2-picked.png)
- [B2-27-setup-step3](screenshots/B_data/B2-27-setup-step3.png)
- [B2-28-setup-step3-45s](screenshots/B_data/B2-28-setup-step3-45s.png)
- [B2-29-setup-step3-demand](screenshots/B_data/B2-29-setup-step3-demand.png)
- [B2-30-setup-step3-ai-slow](screenshots/B_data/B2-30-setup-step3-ai-slow.png)
- [B2-31-setup-step3-demand-details](screenshots/B_data/B2-31-setup-step3-demand-details.png)
- [B2-32-new-analysis](screenshots/B_data/B2-32-new-analysis.png)
- [B2-33-browse-tables](screenshots/B_data/B2-33-browse-tables.png)
- [B2-34-step3-results](screenshots/B_data/B2-34-step3-results.png)
- [B2-35-step3-details](screenshots/B_data/B2-35-step3-details.png)
- [B2-36-step3-details-2](screenshots/B_data/B2-36-step3-details-2.png)
- [B2-37-step3-details-3](screenshots/B_data/B2-37-step3-details-3.png)
- [B2-38-step3-details-4](screenshots/B_data/B2-38-step3-details-4.png)
- [B2-39-step3-insights](screenshots/B_data/B2-39-step3-insights.png)
- [B2-40-fix-remove-copies](screenshots/B_data/B2-40-fix-remove-copies.png)
- [B2-41-fix-spaces-warn](screenshots/B_data/B2-41-fix-spaces-warn.png)
- [B2-42-fixes-applied](screenshots/B_data/B2-42-fixes-applied.png)
- [B2-43-after-fixes-reload](screenshots/B_data/B2-43-after-fixes-reload.png)
- [B2-44-dataset9-overview](screenshots/B_data/B2-44-dataset9-overview.png)
- [B2-45-dataset9-steps](screenshots/B_data/B2-45-dataset9-steps.png)
- [B2-46-setup-step4](screenshots/B_data/B2-46-setup-step4.png)
- [B2-47-setup-step4-wait](screenshots/B_data/B2-47-setup-step4-wait.png)
- [B2-48-step4-levels](screenshots/B_data/B2-48-step4-levels.png)
- [B2-49-dashboard-created](screenshots/B_data/B2-49-dashboard-created.png)
- [B2-50-dashboard-loaded](screenshots/B_data/B2-50-dashboard-loaded.png)
- [B2-51-dashboard-latepct](screenshots/B_data/B2-51-dashboard-latepct.png)
- [B2-52-dashboard-composition](screenshots/B_data/B2-52-dashboard-composition.png)
- [B2-53-dashboard-levels](screenshots/B_data/B2-53-dashboard-levels.png)
- [B2-54-nile-review-after](screenshots/B_data/B2-54-nile-review-after.png)
- [B2-55-nile-relationships](screenshots/B_data/B2-55-nile-relationships.png)
- [B2-56-nile-columns](screenshots/B_data/B2-56-nile-columns.png)
- [B2-57-nile-entities](screenshots/B_data/B2-57-nile-entities.png)
- [B2-58-nile-drift](screenshots/B_data/B2-58-nile-drift.png)
- [B2-59-nile-health](screenshots/B_data/B2-59-nile-health.png)
- [B2-60-sqlite-setup-during-sync](screenshots/B_data/B2-60-sqlite-setup-during-sync.png)
- [B2-61-sqlite-setup-read-during-sync](screenshots/B_data/B2-61-sqlite-setup-read-during-sync.png)

### C — Dashboards & builder (incl. C3/C4 chart types) — 149 screenshots

- [C-00-login](screenshots/C_dashboards/C-00-login.png)
- [C-01-reports-list](screenshots/C_dashboards/C-01-reports-list.png)
- [C-02-card-menu](screenshots/C_dashboards/C-02-card-menu.png)
- [C-03-dashboard-card-menu](screenshots/C_dashboards/C-03-dashboard-card-menu.png)
- [C-04-new-dashboard-dialog](screenshots/C_dashboards/C-04-new-dashboard-dialog.png)
- [C-05-new-dialog-template](screenshots/C_dashboards/C-05-new-dialog-template.png)
- [C-06-new-dialog-ai](screenshots/C_dashboards/C-06-new-dialog-ai.png)
- [C-07-after-create](screenshots/C_dashboards/C-07-after-create.png)
- [C-08-builder-after-reload](screenshots/C_dashboards/C-08-builder-after-reload.png)
- [C-09-insert-tab](screenshots/C_dashboards/C-09-insert-tab.png)
- [C-10-add-bar](screenshots/C_dashboards/C-10-add-bar.png)
- [C-100-delete-confirm](screenshots/C_dashboards/C-100-delete-confirm.png)
- [C-101-cross-filter-region](screenshots/C_dashboards/C-101-cross-filter-region.png)
- [C-102-filter-pane](screenshots/C_dashboards/C-102-filter-pane.png)
- [C-103-layout-menu](screenshots/C_dashboards/C-103-layout-menu.png)
- [C-104-layout-after-escape](screenshots/C_dashboards/C-104-layout-after-escape.png)
- [C-105-data-tab](screenshots/C_dashboards/C-105-data-tab.png)
- [C-106-model-tab](screenshots/C_dashboards/C-106-model-tab.png)
- [C-107-layout-menu-toolbar](screenshots/C_dashboards/C-107-layout-menu-toolbar.png)
- [C-108-layout-after-escape](screenshots/C_dashboards/C-108-layout-after-escape.png)
- [C-109-page-size-custom](screenshots/C_dashboards/C-109-page-size-custom.png)
- [C-11-assign-add-dimension](screenshots/C_dashboards/C-11-assign-add-dimension.png)
- [C-110-subscribe-dialog](screenshots/C_dashboards/C-110-subscribe-dialog.png)
- [C-111-version-history](screenshots/C_dashboards/C-111-version-history.png)
- [C-112-before-rename](screenshots/C_dashboards/C-112-before-rename.png)
- [C-113-page-renamed](screenshots/C_dashboards/C-113-page-renamed.png)
- [C-114-page-tab-menu](screenshots/C_dashboards/C-114-page-tab-menu.png)
- [C-115-delete-page](screenshots/C_dashboards/C-115-delete-page.png)
- [C-12-add-dimension-picker](screenshots/C_dashboards/C-12-add-dimension-picker.png)
- [C-13-bar-rendered](screenshots/C_dashboards/C-13-bar-rendered.png)
- [C-14-click-pie-with-selection](screenshots/C_dashboards/C-14-click-pie-with-selection.png)
- [C-15-pie](screenshots/C_dashboards/C-15-pie.png)
- [C-15b](screenshots/C_dashboards/C-15b.png)
- [C-15c](screenshots/C_dashboards/C-15c.png)
- [C-16-widget-kebab-edit](screenshots/C_dashboards/C-16-widget-kebab-edit.png)
- [C-20-word-cloud](screenshots/C_dashboards/C-20-word-cloud.png)
- [C-21-wordcloud-assign](screenshots/C_dashboards/C-21-wordcloud-assign.png)
- [C-22-wordcloud-wordtext-picker](screenshots/C_dashboards/C-22-wordcloud-wordtext-picker.png)
- [C-23-word-cloud-after-reload](screenshots/C_dashboards/C-23-word-cloud-after-reload.png)
- [C-24-scatter-assign](screenshots/C_dashboards/C-24-scatter-assign.png)
- [C-24-scatter-measures](screenshots/C_dashboards/C-24-scatter-measures.png)
- [C-24-scatter](screenshots/C_dashboards/C-24-scatter.png)
- [C-24x](screenshots/C_dashboards/C-24x.png)
- [C-24y](screenshots/C_dashboards/C-24y.png)
- [C-25-sankey](screenshots/C_dashboards/C-25-sankey.png)
- [C-25x](screenshots/C_dashboards/C-25x.png)
- [C-26-sunburst](screenshots/C_dashboards/C-26-sunburst.png)
- [C-26a-sunburst-levels](screenshots/C_dashboards/C-26a-sunburst-levels.png)
- [C-27-box](screenshots/C_dashboards/C-27-box.png)
- [C-27x](screenshots/C_dashboards/C-27x.png)
- [C-28-delete-empty-sunburst](screenshots/C_dashboards/C-28-delete-empty-sunburst.png)
- [C-29-histogram](screenshots/C_dashboards/C-29-histogram.png)
- [C-30-treemap](screenshots/C_dashboards/C-30-treemap.png)
- [C-31-funnel](screenshots/C_dashboards/C-31-funnel.png)
- [C-32-bar-line](screenshots/C_dashboards/C-32-bar-line.png)
- [C-33-kpi-gauge](screenshots/C_dashboards/C-33-kpi-gauge.png)
- [C-33-kpi](screenshots/C_dashboards/C-33-kpi.png)
- [C-34-gauge](screenshots/C_dashboards/C-34-gauge.png)
- [C-35-table](screenshots/C_dashboards/C-35-table.png)
- [C-36-choropleth](screenshots/C_dashboards/C-36-choropleth.png)
- [C-37-line](screenshots/C_dashboards/C-37-line.png)
- [C-38-waterfall](screenshots/C_dashboards/C-38-waterfall.png)
- [C-39-crosstab](screenshots/C_dashboards/C-39-crosstab.png)
- [C-40-heatmap](screenshots/C_dashboards/C-40-heatmap.png)
- [C-41-page7-state](screenshots/C_dashboards/C-41-page7-state.png)
- [C-42-format-search-rule](screenshots/C_dashboards/C-42-format-search-rule.png)
- [C-43-display-rule-added](screenshots/C_dashboards/C-43-display-rule-added.png)
- [C-44-rule-text-column-gt](screenshots/C_dashboards/C-44-rule-text-column-gt.png)
- [C-45-rule-region-gt-5](screenshots/C_dashboards/C-45-rule-region-gt-5.png)
- [C-50-view-1](screenshots/C_dashboards/C-50-view-1.png)
- [C-51-view-2](screenshots/C_dashboards/C-51-view-2.png)
- [C-52-view-3](screenshots/C_dashboards/C-52-view-3.png)
- [C-53-view-4](screenshots/C_dashboards/C-53-view-4.png)
- [C-54-view-5](screenshots/C_dashboards/C-54-view-5.png)
- [C-55-view-3-after-12s](screenshots/C_dashboards/C-55-view-3-after-12s.png)
- [C-56-view-2-after-12s](screenshots/C_dashboards/C-56-view-2-after-12s.png)
- [C-57-view-3-after-scroll](screenshots/C_dashboards/C-57-view-3-after-scroll.png)
- [C-58-view-1-rendered](screenshots/C_dashboards/C-58-view-1-rendered.png)
- [C-59-view-2-rendered](screenshots/C_dashboards/C-59-view-2-rendered.png)
- [C-60-view-4-rendered](screenshots/C_dashboards/C-60-view-4-rendered.png)
- [C-61-view-5-rendered](screenshots/C_dashboards/C-61-view-5-rendered.png)
- [C-62-view-6-rendered](screenshots/C_dashboards/C-62-view-6-rendered.png)
- [C-63-view-7-rendered](screenshots/C_dashboards/C-63-view-7-rendered.png)
- [C-64-view-8-rendered](screenshots/C_dashboards/C-64-view-8-rendered.png)
- [C-65-view-9-rendered](screenshots/C_dashboards/C-65-view-9-rendered.png)
- [C-66-view-10-rendered](screenshots/C_dashboards/C-66-view-10-rendered.png)
- [C-70-view-widget-menu](screenshots/C_dashboards/C-70-view-widget-menu.png)
- [C-71-explain-revenue](screenshots/C_dashboards/C-71-explain-revenue.png)
- [C-72-export-menu](screenshots/C_dashboards/C-72-export-menu.png)
- [C-73-export-pdf-result](screenshots/C_dashboards/C-73-export-pdf-result.png)
- [C-74-present-mode](screenshots/C_dashboards/C-74-present-mode.png)
- [C-75-print-page](screenshots/C_dashboards/C-75-print-page.png)
- [C-80-my-dashboards](screenshots/C_dashboards/C-80-my-dashboards.png)
- [C-81-my-dash-favourites](screenshots/C_dashboards/C-81-my-dash-favourites.png)
- [C-82-my-dash-empty-search](screenshots/C_dashboards/C-82-my-dash-empty-search.png)
- [C-83-classification-confidential](screenshots/C_dashboards/C-83-classification-confidential.png)
- [C-84-comments-pane](screenshots/C_dashboards/C-84-comments-pane.png)
- [C-85-version-history](screenshots/C_dashboards/C-85-version-history.png)
- [C-86-comment-typed](screenshots/C_dashboards/C-86-comment-typed.png)
- [C-87-comment-posted](screenshots/C_dashboards/C-87-comment-posted.png)
- [C-88-copilot-open](screenshots/C_dashboards/C-88-copilot-open.png)
- [C-89-copilot-answer](screenshots/C_dashboards/C-89-copilot-answer.png)
- [C-90-suggest-pane](screenshots/C_dashboards/C-90-suggest-pane.png)
- [C-91-resize-bar](screenshots/C_dashboards/C-91-resize-bar.png)
- [C-92-undo](screenshots/C_dashboards/C-92-undo.png)
- [C-93-tablet-view](screenshots/C_dashboards/C-93-tablet-view.png)
- [C-94-tablet-builder](screenshots/C_dashboards/C-94-tablet-builder.png)
- [C-95-phone-view](screenshots/C_dashboards/C-95-phone-view.png)
- [C-96-phone-list](screenshots/C_dashboards/C-96-phone-list.png)
- [C-97-move-to-folder](screenshots/C_dashboards/C-97-move-to-folder.png)
- [C-98-rename](screenshots/C_dashboards/C-98-rename.png)
- [C-99-renamed](screenshots/C_dashboards/C-99-renamed.png)
- [C3-01-new-dashboard-dialog](screenshots/C_dashboards/C3-01-new-dashboard-dialog.png)
- [C3-02-builder-empty](screenshots/C_dashboards/C3-02-builder-empty.png)
- [C3-03-insert-panel](screenshots/C_dashboards/C3-03-insert-panel.png)
- [C3-04-butterfly-added](screenshots/C_dashboards/C3-04-butterfly-added.png)
- [C3-05-assign-picker](screenshots/C_dashboards/C3-05-assign-picker.png)
- [C3-06-after-pick](screenshots/C_dashboards/C3-06-after-pick.png)
- [C3-07-butterfly-assigned](screenshots/C_dashboards/C3-07-butterfly-assigned.png)
- [C3-08-butterfly](screenshots/C_dashboards/C3-08-butterfly.png)
- [C3-09-dual-axis-bar](screenshots/C_dashboards/C3-09-dual-axis-bar.png)
- [C3-10-dual-axis-line](screenshots/C_dashboards/C3-10-dual-axis-line.png)
- [C3-11-dot](screenshots/C_dashboards/C3-11-dot.png)
- [C3-12-ribbon](screenshots/C_dashboards/C3-12-ribbon.png)
- [C3-13-small-multiples](screenshots/C_dashboards/C3-13-small-multiples.png)
- [C3-14-small-multiples-faceted](screenshots/C_dashboards/C3-14-small-multiples-faceted.png)
- [C3-15-step](screenshots/C_dashboards/C3-15-step.png)
- [C3-16-dual-axis-time](screenshots/C_dashboards/C3-16-dual-axis-time.png)
- [C3-17-compare-series](screenshots/C_dashboards/C3-17-compare-series.png)
- [C3-18-numeric-series](screenshots/C_dashboards/C3-18-numeric-series.png)
- [C3-19-forecast](screenshots/C_dashboards/C3-19-forecast.png)
- [C3-20-matrix](screenshots/C_dashboards/C3-20-matrix.png)
- [C3-21-list](screenshots/C_dashboards/C3-21-list.png)
- [C4-01-new-dashboard-dialog](screenshots/C_dashboards/C4-01-new-dashboard-dialog.png)
- [C4-02-builder-empty](screenshots/C_dashboards/C4-02-builder-empty.png)
- [C4-03-insert-tab](screenshots/C_dashboards/C4-03-insert-tab.png)
- [C4-04-gallery-search-map](screenshots/C_dashboards/C4-04-gallery-search-map.png)
- [C4-05-point-map-added](screenshots/C_dashboards/C4-05-point-map-added.png)
- [C4-06-point-map-data-roles](screenshots/C_dashboards/C4-06-point-map-data-roles.png)
- [C4-06-point-map-data-tab](screenshots/C_dashboards/C4-06-point-map-data-tab.png)
- [C4-07-add-field-popup](screenshots/C_dashboards/C4-07-add-field-popup.png)
- [C4-08-point-map-assigned](screenshots/C_dashboards/C4-08-point-map-assigned.png)
- [C4-09-point-map-roles-fixed](screenshots/C_dashboards/C4-09-point-map-roles-fixed.png)
- [C4-10-assign-data-picker](screenshots/C_dashboards/C4-10-assign-data-picker.png)
- [C4-11-point-map-rendered](screenshots/C_dashboards/C4-11-point-map-rendered.png)
- [C4-12-point-map-row-values](screenshots/C_dashboards/C4-12-point-map-row-values.png)
- [C4-13-point-map-lat-vs-shipments](screenshots/C_dashboards/C4-13-point-map-lat-vs-shipments.png)
- [C4-14-maps-canvas-full](screenshots/C_dashboards/C4-14-maps-canvas-full.png)
- [C4-15-bubble-density-tiles](screenshots/C_dashboards/C4-15-bubble-density-tiles.png)

### D — Ask AI, Insights, automations, monitoring — 66 screenshots

- [D-01-ask-landing](screenshots/D_ai_insights_ops/D-01-ask-landing.png)
- [D-02-model-picker](screenshots/D_ai_insights_ops/D-02-model-picker.png)
- [D-03-model-picker-expanded](screenshots/D_ai_insights_ops/D-03-model-picker-expanded.png)
- [D-04-manage-models](screenshots/D_ai_insights_ops/D-04-manage-models.png)
- [D-05-endpoint-test](screenshots/D_ai_insights_ops/D-05-endpoint-test.png)
- [D-06-ask-sales-selected](screenshots/D_ai_insights_ops/D-06-ask-sales-selected.png)
- [D-07-suggestion-click-paused](screenshots/D_ai_insights_ops/D-07-suggestion-click-paused.png)
- [D-08-ask-after-wait](screenshots/D_ai_insights_ops/D-08-ask-after-wait.png)
- [D-09-ask-stopped](screenshots/D_ai_insights_ops/D-09-ask-stopped.png)
- [D-10-history-row-actions](screenshots/D_ai_insights_ops/D-10-history-row-actions.png)
- [D-11-history-rename-field](screenshots/D_ai_insights_ops/D-11-history-rename-field.png)
- [D-11b-rename-typed](screenshots/D_ai_insights_ops/D-11b-rename-typed.png)
- [D-12-history-renamed](screenshots/D_ai_insights_ops/D-12-history-renamed.png)
- [D-13-old-conversation](screenshots/D_ai_insights_ops/D-13-old-conversation.png)
- [D-14-edit-question](screenshots/D_ai_insights_ops/D-14-edit-question.png)
- [D-15-new-chat](screenshots/D_ai_insights_ops/D-15-new-chat.png)
- [D-16-delete-conversation](screenshots/D_ai_insights_ops/D-16-delete-conversation.png)
- [D-17-after-delete](screenshots/D_ai_insights_ops/D-17-after-delete.png)
- [D-18-scope-picker-open](screenshots/D_ai_insights_ops/D-18-scope-picker-open.png)
- [D-19-scope-picker-connections](screenshots/D_ai_insights_ops/D-19-scope-picker-connections.png)
- [D-20-ask-connection-scope](screenshots/D_ai_insights_ops/D-20-ask-connection-scope.png)
- [D-21-dq-dataset-page](screenshots/D_ai_insights_ops/D-21-dq-dataset-page.png)
- [D-22-dq-ask-entry](screenshots/D_ai_insights_ops/D-22-dq-ask-entry.png)
- [D-23-dq-ask-question](screenshots/D_ai_insights_ops/D-23-dq-ask-question.png)
- [D-24-ask-mobile](screenshots/D_ai_insights_ops/D-24-ask-mobile.png)
- [D-25-ask-mobile-scrolled](screenshots/D_ai_insights_ops/D-25-ask-mobile-scrolled.png)
- [D-26-ask-mobile-history](screenshots/D_ai_insights_ops/D-26-ask-mobile-history.png)
- [D-27-ask-mobile-answer](screenshots/D_ai_insights_ops/D-27-ask-mobile-answer.png)
- [D-28-insights-landing](screenshots/D_ai_insights_ops/D-28-insights-landing.png)
- [D-29-insights-race-early](screenshots/D_ai_insights_ops/D-29-insights-race-early.png)
- [D-30-insights-race-settled](screenshots/D_ai_insights_ops/D-30-insights-race-settled.png)
- [D-31-insights-metrics-clean](screenshots/D_ai_insights_ops/D-31-insights-metrics-clean.png)
- [D-32-insights-race-repro2](screenshots/D_ai_insights_ops/D-32-insights-race-repro2.png)
- [D-33-view-full-scan](screenshots/D_ai_insights_ops/D-33-view-full-scan.png)
- [D-34-generated-insights](screenshots/D_ai_insights_ops/D-34-generated-insights.png)
- [D-35-pin-finding](screenshots/D_ai_insights_ops/D-35-pin-finding.png)
- [D-36-pin-toast](screenshots/D_ai_insights_ops/D-36-pin-toast.png)
- [D-37-home-no-pins](screenshots/D_ai_insights_ops/D-37-home-no-pins.png)
- [D-38-portal-no-pins](screenshots/D_ai_insights_ops/D-38-portal-no-pins.png)
- [D-39-insights-dq](screenshots/D_ai_insights_ops/D-39-insights-dq.png)
- [D-40-insights-dq-scanned](screenshots/D_ai_insights_ops/D-40-insights-dq-scanned.png)
- [D-41-insights-projects-filters](screenshots/D_ai_insights_ops/D-41-insights-projects-filters.png)
- [D-42-automations-list](screenshots/D_ai_insights_ops/D-42-automations-list.png)
- [D-43-automation-pick](screenshots/D_ai_insights_ops/D-43-automation-pick.png)
- [D-44-automation-started](screenshots/D_ai_insights_ops/D-44-automation-started.png)
- [D-45-automation-progress](screenshots/D_ai_insights_ops/D-45-automation-progress.png)
- [D-46-automation-cancelled](screenshots/D_ai_insights_ops/D-46-automation-cancelled.png)
- [D-47-notifications-bell](screenshots/D_ai_insights_ops/D-47-notifications-bell.png)
- [D-48-monitoring-jobs](screenshots/D_ai_insights_ops/D-48-monitoring-jobs.png)
- [D-49-jobs-failed-only](screenshots/D_ai_insights_ops/D-49-jobs-failed-only.png)
- [D-50-jobs-row-link](screenshots/D_ai_insights_ops/D-50-jobs-row-link.png)
- [D-51-monitoring-deliveries](screenshots/D_ai_insights_ops/D-51-monitoring-deliveries.png)
- [D-52-monitoring-activity](screenshots/D_ai_insights_ops/D-52-monitoring-activity.png)
- [D-53-activity-search](screenshots/D_ai_insights_ops/D-53-activity-search.png)
- [D-54-dataset-checks-alerts](screenshots/D_ai_insights_ops/D-54-dataset-checks-alerts.png)
- [D-55-quality-rules-run](screenshots/D_ai_insights_ops/D-55-quality-rules-run.png)
- [D-56-automation-feedback-state](screenshots/D_ai_insights_ops/D-56-automation-feedback-state.png)
- [D-57-automation-details](screenshots/D_ai_insights_ops/D-57-automation-details.png)
- [D-58-automation-done](screenshots/D_ai_insights_ops/D-58-automation-done.png)
- [D-59-activity-mobile](screenshots/D_ai_insights_ops/D-59-activity-mobile.png)
- [D-60-jobs-mobile](screenshots/D_ai_insights_ops/D-60-jobs-mobile.png)
- [D-61-automations-mobile](screenshots/D_ai_insights_ops/D-61-automations-mobile.png)
- [D-62-insights-mobile](screenshots/D_ai_insights_ops/D-62-insights-mobile.png)
- [D-63-model-auto-selected](screenshots/D_ai_insights_ops/D-63-model-auto-selected.png)
- [D-64-sales-full-scan](screenshots/D_ai_insights_ops/D-64-sales-full-scan.png)
- [D-65-ask-suggestions-projects](screenshots/D_ai_insights_ops/D-65-ask-suggestions-projects.png)

### E — Admin, platform, roles — 111 screenshots

- [E-01-admin-users](screenshots/E_admin_roles/E-01-admin-users.png)
- [E-02-new-user-dialog](screenshots/E_admin_roles/E-02-new-user-dialog.png)
- [E-03-new-user-invalid-email](screenshots/E_admin_roles/E-03-new-user-invalid-email.png)
- [E-04-edit-user-dialog](screenshots/E_admin_roles/E-04-edit-user-dialog.png)
- [E-05-edit-user-filled](screenshots/E_admin_roles/E-05-edit-user-filled.png)
- [E-06-duplicate-case-email](screenshots/E_admin_roles/E-06-duplicate-case-email.png)
- [E-07-exact-duplicate-email](screenshots/E_admin_roles/E-07-exact-duplicate-email.png)
- [E-07b-exact-duplicate-result](screenshots/E_admin_roles/E-07b-exact-duplicate-result.png)
- [E-08-duplicate-error-toast](screenshots/E_admin_roles/E-08-duplicate-error-toast.png)
- [E-09-deactivate-unchecked](screenshots/E_admin_roles/E-09-deactivate-unchecked.png)
- [E-10-users-after-deactivate](screenshots/E_admin_roles/E-10-users-after-deactivate.png)
- [E-100-emea-ask-ai-sales-picked](screenshots/E_admin_roles/E-100-emea-ask-ai-sales-picked.png)
- [E-101-emea-template-mapping](screenshots/E_admin_roles/E-101-emea-template-mapping.png)
- [E-102-emea-template-use-dialog](screenshots/E_admin_roles/E-102-emea-template-use-dialog.png)
- [E-103-emea-export-menu](screenshots/E_admin_roles/E-103-emea-export-menu.png)
- [E-105-contoso-report8-blocked](screenshots/E_admin_roles/E-105-contoso-report8-blocked.png)
- [E-106-contoso-admin-users](screenshots/E_admin_roles/E-106-contoso-admin-users.png)
- [E-107-contoso-analyst-home](screenshots/E_admin_roles/E-107-contoso-analyst-home.png)
- [E-108-northwind-admin-home](screenshots/E_admin_roles/E-108-northwind-admin-home.png)
- [E-109-northwind-analyst-home](screenshots/E_admin_roles/E-109-northwind-analyst-home.png)
- [E-11-bulk-import-dialog](screenshots/E_admin_roles/E-11-bulk-import-dialog.png)
- [E-111-example-admin-users](screenshots/E_admin_roles/E-111-example-admin-users.png)
- [E-112-admin-users-phone](screenshots/E_admin_roles/E-112-admin-users-phone.png)
- [E-12-bulk-import-filled](screenshots/E_admin_roles/E-12-bulk-import-filled.png)
- [E-13-bulk-import-result](screenshots/E_admin_roles/E-13-bulk-import-result.png)
- [E-14-roles](screenshots/E_admin_roles/E-14-roles.png)
- [E-15-new-role-dialog](screenshots/E_admin_roles/E-15-new-role-dialog.png)
- [E-16-duplicate-role-name](screenshots/E_admin_roles/E-16-duplicate-role-name.png)
- [E-17-edit-role-dialog](screenshots/E_admin_roles/E-17-edit-role-dialog.png)
- [E-18-new-role-empty-name](screenshots/E_admin_roles/E-18-new-role-empty-name.png)
- [E-19-org-chart](screenshots/E_admin_roles/E-19-org-chart.png)
- [E-20-add-unit-dialog](screenshots/E_admin_roles/E-20-add-unit-dialog.png)
- [E-21-add-unit-step2](screenshots/E_admin_roles/E-21-add-unit-step2.png)
- [E-22-org-chart-tree-place-user](screenshots/E_admin_roles/E-22-org-chart-tree-place-user.png)
- [E-23-org-chart-placed](screenshots/E_admin_roles/E-23-org-chart-placed.png)
- [E-24-row-security](screenshots/E_admin_roles/E-24-row-security.png)
- [E-25-new-row-rule-dialog](screenshots/E_admin_roles/E-25-new-row-rule-dialog.png)
- [E-26-row-rule-invalid-expr](screenshots/E_admin_roles/E-26-row-rule-invalid-expr.png)
- [E-27-row-rule-myscope](screenshots/E_admin_roles/E-27-row-rule-myscope.png)
- [E-28-row-rule-created](screenshots/E_admin_roles/E-28-row-rule-created.png)
- [E-29-auto-generate-rules](screenshots/E_admin_roles/E-29-auto-generate-rules.png)
- [E-30-auto-generate-shipments](screenshots/E_admin_roles/E-30-auto-generate-shipments.png)
- [E-31-row-rule-more-menu](screenshots/E_admin_roles/E-31-row-rule-more-menu.png)
- [E-32-column-security](screenshots/E_admin_roles/E-32-column-security.png)
- [E-33-new-column-rule-dialog](screenshots/E_admin_roles/E-33-new-column-rule-dialog.png)
- [E-34-column-rule-created](screenshots/E_admin_roles/E-34-column-rule-created.png)
- [E-35-connection-rules](screenshots/E_admin_roles/E-35-connection-rules.png)
- [E-36-connection-rules-sqlite](screenshots/E_admin_roles/E-36-connection-rules-sqlite.png)
- [E-37-connection-rule-bad-col](screenshots/E_admin_roles/E-37-connection-rule-bad-col.png)
- [E-38-connection-rules-nile](screenshots/E_admin_roles/E-38-connection-rules-nile.png)
- [E-39-export-policy](screenshots/E_admin_roles/E-39-export-policy.png)
- [E-40-export-policy-toggled](screenshots/E_admin_roles/E-40-export-policy-toggled.png)
- [E-41-api-keys](screenshots/E_admin_roles/E-41-api-keys.png)
- [E-42-api-key-empty-name](screenshots/E_admin_roles/E-42-api-key-empty-name.png)
- [E-43-api-key-secret-shown](screenshots/E_admin_roles/E-43-api-key-secret-shown.png)
- [E-44-api-key-after-reload](screenshots/E_admin_roles/E-44-api-key-after-reload.png)
- [E-45-api-key-revoke-confirm](screenshots/E_admin_roles/E-45-api-key-revoke-confirm.png)
- [E-46-api-key-revoked](screenshots/E_admin_roles/E-46-api-key-revoked.png)
- [E-47-custom-connectors](screenshots/E_admin_roles/E-47-custom-connectors.png)
- [E-48-new-custom-connector](screenshots/E_admin_roles/E-48-new-custom-connector.png)
- [E-49-custom-connector-empty-submit](screenshots/E_admin_roles/E-49-custom-connector-empty-submit.png)
- [E-50-custom-connector-created](screenshots/E_admin_roles/E-50-custom-connector-created.png)
- [E-51-custom-connector-edit](screenshots/E_admin_roles/E-51-custom-connector-edit.png)
- [E-52-sso](screenshots/E_admin_roles/E-52-sso.png)
- [E-53-sso-empty-save](screenshots/E_admin_roles/E-53-sso-empty-save.png)
- [E-54-sso-oidc-bad-values](screenshots/E_admin_roles/E-54-sso-oidc-bad-values.png)
- [E-55-sso-saml](screenshots/E_admin_roles/E-55-sso-saml.png)
- [E-56-maps](screenshots/E_admin_roles/E-56-maps.png)
- [E-57-maps-bad-tile-url](screenshots/E_admin_roles/E-57-maps-bad-tile-url.png)
- [E-58-calendar](screenshots/E_admin_roles/E-58-calendar.png)
- [E-59-calendar-july-preview](screenshots/E_admin_roles/E-59-calendar-july-preview.png)
- [E-60-audit](screenshots/E_admin_roles/E-60-audit.png)
- [E-61-audit-filtered](screenshots/E_admin_roles/E-61-audit-filtered.png)
- [E-62-audit-empty-filter](screenshots/E_admin_roles/E-62-audit-empty-filter.png)
- [E-63-audit-row-click](screenshots/E_admin_roles/E-63-audit-row-click.png)
- [E-64-org-settings](screenshots/E_admin_roles/E-64-org-settings.png)
- [E-65-settings-search-super](screenshots/E_admin_roles/E-65-settings-search-super.png)
- [E-66-llm-test-5s](screenshots/E_admin_roles/E-66-llm-test-5s.png)
- [E-67-llm-test-result](screenshots/E_admin_roles/E-67-llm-test-result.png)
- [E-68-settings-full](screenshots/E_admin_roles/E-68-settings-full.png)
- [E-69-org-settings-security](screenshots/E_admin_roles/E-69-org-settings-security.png)
- [E-70-settings-deployment-readonly](screenshots/E_admin_roles/E-70-settings-deployment-readonly.png)
- [E-71-platform-settings](screenshots/E_admin_roles/E-71-platform-settings.png)
- [E-72-platform-security-guest-link](screenshots/E_admin_roles/E-72-platform-security-guest-link.png)
- [E-73-settings-unsaved-bar](screenshots/E_admin_roles/E-73-settings-unsaved-bar.png)
- [E-74-settings-invalid-save](screenshots/E_admin_roles/E-74-settings-invalid-save.png)
- [E-75-platform-orgs](screenshots/E_admin_roles/E-75-platform-orgs.png)
- [E-76-edit-quota-dialog](screenshots/E_admin_roles/E-76-edit-quota-dialog.png)
- [E-77-quota-negative](screenshots/E_admin_roles/E-77-quota-negative.png)
- [E-78-quota-negative-save](screenshots/E_admin_roles/E-78-quota-negative-save.png)
- [E-79-org-ai-usage](screenshots/E_admin_roles/E-79-org-ai-usage.png)
- [E-80-new-org-invalid](screenshots/E_admin_roles/E-80-new-org-invalid.png)
- [E-81-new-org-short-password](screenshots/E_admin_roles/E-81-new-org-short-password.png)
- [E-82-monitoring-activity](screenshots/E_admin_roles/E-82-monitoring-activity.png)
- [E-83-deactivated-login](screenshots/E_admin_roles/E-83-deactivated-login.png)
- [E-84-global-home](screenshots/E_admin_roles/E-84-global-home.png)
- [E-85-global-admin-users-forbidden](screenshots/E_admin_roles/E-85-global-admin-users-forbidden.png)
- [E-86-global-datasets](screenshots/E_admin_roles/E-86-global-datasets.png)
- [E-87-global-dashboards](screenshots/E_admin_roles/E-87-global-dashboards.png)
- [E-88-global-usecase-regional](screenshots/E_admin_roles/E-88-global-usecase-regional.png)
- [E-89-global-my-dashboards](screenshots/E_admin_roles/E-89-global-my-dashboards.png)
- [E-90-global-templates](screenshots/E_admin_roles/E-90-global-templates.png)
- [E-91-emea-home](screenshots/E_admin_roles/E-91-emea-home.png)
- [E-92-emea-usecase-regional](screenshots/E_admin_roles/E-92-emea-usecase-regional.png)
- [E-93-emea-sales-dataset](screenshots/E_admin_roles/E-93-emea-sales-dataset.png)
- [E-94-emea-columns-tab](screenshots/E_admin_roles/E-94-emea-columns-tab.png)
- [E-95-emea-data-tab](screenshots/E_admin_roles/E-95-emea-data-tab.png)
- [E-96-emea-measures](screenshots/E_admin_roles/E-96-emea-measures.png)
- [E-97-emea-rules-alerts](screenshots/E_admin_roles/E-97-emea-rules-alerts.png)
- [E-98-emea-use-in-python](screenshots/E_admin_roles/E-98-emea-use-in-python.png)
- [E-99-emea-ask-ai](screenshots/E_admin_roles/E-99-emea-ask-ai.png)

### F — Templates, suggestions, publishing & sharing (incl. F2) — 163 screenshots

- [F-01-profile](screenshots/F_new_features/F-01-profile.png)
- [F-02-profile-about-saved](screenshots/F_new_features/F-02-profile-about-saved.png)
- [F-03-admin-roles](screenshots/F_new_features/F-03-admin-roles.png)
- [F-04-new-role-dialog](screenshots/F_new_features/F-04-new-role-dialog.png)
- [F-05-new-user-dialog](screenshots/F_new_features/F-05-new-user-dialog.png)
- [F-06-new-user-filled](screenshots/F_new_features/F-06-new-user-filled.png)
- [F-07-org-chart](screenshots/F_new_features/F-07-org-chart.png)
- [F-08-add-unit](screenshots/F_new_features/F-08-add-unit.png)
- [F-09-add-unit-step2](screenshots/F_new_features/F-09-add-unit-step2.png)
- [F-10-org-chart-placed](screenshots/F_new_features/F-10-org-chart-placed.png)
- [F-100-reader-print-after-removal](screenshots/F_new_features/F-100-reader-print-after-removal.png)
- [F-101-publishing-tab](screenshots/F_new_features/F-101-publishing-tab.png)
- [F-102-admin-my-dashboards](screenshots/F_new_features/F-102-admin-my-dashboards.png)
- [F-103-my-dashboards-arabic](screenshots/F_new_features/F-103-my-dashboards-arabic.png)
- [F-11-dashboards-list](screenshots/F_new_features/F-11-dashboards-list.png)
- [F-12-new-dashboard-dialog](screenshots/F_new_features/F-12-new-dashboard-dialog.png)
- [F-13-new-dash-with-ai](screenshots/F_new_features/F-13-new-dash-with-ai.png)
- [F-14-suggest-ai-on-5s](screenshots/F_new_features/F-14-suggest-ai-on-5s.png)
- [F-15-suggest-ai-on-running](screenshots/F_new_features/F-15-suggest-ai-on-running.png)
- [F-16-suggest-ai-on-30s](screenshots/F_new_features/F-16-suggest-ai-on-30s.png)
- [F-17-suggest-ai-on-60s](screenshots/F_new_features/F-17-suggest-ai-on-60s.png)
- [F-18-suggest-ai-on-110s](screenshots/F_new_features/F-18-suggest-ai-on-110s.png)
- [F-19-suggest-cancelled](screenshots/F_new_features/F-19-suggest-cancelled.png)
- [F-20-model-picker](screenshots/F_new_features/F-20-model-picker.png)
- [F-21-model-picker-explained](screenshots/F_new_features/F-21-model-picker-explained.png)
- [F-22-manage-models](screenshots/F_new_features/F-22-manage-models.png)
- [F-23-platform-ai-switch](screenshots/F_new_features/F-23-platform-ai-switch.png)
- [F-24-suggest-no-ai-result](screenshots/F_new_features/F-24-suggest-no-ai-result.png)
- [F-25-suggested-dashboard-created](screenshots/F_new_features/F-25-suggested-dashboard-created.png)
- [F-26-after-create-wait](screenshots/F_new_features/F-26-after-create-wait.png)
- [F-27-suggested-dashboard-open](screenshots/F_new_features/F-27-suggested-dashboard-open.png)
- [F-28-edit-mode](screenshots/F_new_features/F-28-edit-mode.png)
- [F-29-rail-ai](screenshots/F_new_features/F-29-rail-ai.png)
- [F-30-suggestions-pane](screenshots/F_new_features/F-30-suggestions-pane.png)
- [F-31-suggestion-added-one](screenshots/F_new_features/F-31-suggestion-added-one.png)
- [F-32-all-suggestions-dashboard](screenshots/F_new_features/F-32-all-suggestions-dashboard.png)
- [F-33-all-sugg-composition](screenshots/F_new_features/F-33-all-sugg-composition.png)
- [F-34-all-sugg-over-time](screenshots/F_new_features/F-34-all-sugg-over-time.png)
- [F-35-dashboard-style-panel](screenshots/F_new_features/F-35-dashboard-style-panel.png)
- [F-35b](screenshots/F_new_features/F-35b.png)
- [F-36-look-midnight-edit](screenshots/F_new_features/F-36-look-midnight-edit.png)
- [F-37-look-midnight-view](screenshots/F_new_features/F-37-look-midnight-view.png)
- [F-38-midnight-over-time](screenshots/F_new_features/F-38-midnight-over-time.png)
- [F-39-look-deepspace](screenshots/F_new_features/F-39-look-deepspace.png)
- [F-40-look-ember-composition](screenshots/F_new_features/F-40-look-ember-composition.png)
- [F-41-after-leaving-dark-dashboard](screenshots/F_new_features/F-41-after-leaving-dark-dashboard.png)
- [F-42-rename](screenshots/F_new_features/F-42-rename.png)
- [F-43-templates](screenshots/F_new_features/F-43-templates.png)
- [F-44-templates-scroll-1](screenshots/F_new_features/F-44-templates-scroll-1.png)
- [F-44-templates-scroll-2](screenshots/F_new_features/F-44-templates-scroll-2.png)
- [F-44-templates-scroll-3](screenshots/F_new_features/F-44-templates-scroll-3.png)
- [F-44-templates-scroll-4](screenshots/F_new_features/F-44-templates-scroll-4.png)
- [F-44-templates-scroll-5](screenshots/F_new_features/F-44-templates-scroll-5.png)
- [F-45-templates-matched-sales](screenshots/F_new_features/F-45-templates-matched-sales.png)
- [F-46-template-preview-exec](screenshots/F_new_features/F-46-template-preview-exec.png)
- [F-47-exec-use-template](screenshots/F_new_features/F-47-exec-use-template.png)
- [F-48-exec-mapping-filled](screenshots/F_new_features/F-48-exec-mapping-filled.png)
- [F-49-exec-summary-dashboard](screenshots/F_new_features/F-49-exec-summary-dashboard.png)
- [F-50-exec-summary-view](screenshots/F_new_features/F-50-exec-summary-view.png)
- [F-51-exec-groups](screenshots/F_new_features/F-51-exec-groups.png)
- [F-52-exec-detail](screenshots/F_new_features/F-52-exec-detail.png)
- [F-53-wgt-preview](screenshots/F_new_features/F-53-wgt-preview.png)
- [F-54-wgt-mapping](screenshots/F_new_features/F-54-wgt-mapping.png)
- [F-55-wgt-mapping-filled](screenshots/F_new_features/F-55-wgt-mapping-filled.png)
- [F-56-wgt-mapping-final](screenshots/F_new_features/F-56-wgt-mapping-final.png)
- [F-57-wgt-dashboard](screenshots/F_new_features/F-57-wgt-dashboard.png)
- [F-58-wgt-view](screenshots/F_new_features/F-58-wgt-view.png)
- [F-59-wgt-view-2](screenshots/F_new_features/F-59-wgt-view-2.png)
- [F-60-wgt-sales-view](screenshots/F_new_features/F-60-wgt-sales-view.png)
- [F-61-wgt-sales-rules](screenshots/F_new_features/F-61-wgt-sales-rules.png)
- [F-62-tpl-what-is-in-the-data-mapping](screenshots/F_new_features/F-62-tpl-what-is-in-the-data-mapping.png)
- [F-63-tpl-what-is-in-the-data-dashboard](screenshots/F_new_features/F-63-tpl-what-is-in-the-data-dashboard.png)
- [F-64-tpl-a-number-through-time-mapping](screenshots/F_new_features/F-64-tpl-a-number-through-time-mapping.png)
- [F-65-tpl-a-number-through-time-dashboard](screenshots/F_new_features/F-65-tpl-a-number-through-time-dashboard.png)
- [F-66-tpl-what-is-out-of-the-ordinary-mapping](screenshots/F_new_features/F-66-tpl-what-is-out-of-the-ordinary-mapping.png)
- [F-67-tpl-what-is-out-of-the-ordinary-dashboard](screenshots/F_new_features/F-67-tpl-what-is-out-of-the-ordinary-dashboard.png)
- [F-68-tpl-what-a-number-depends-on-mapping](screenshots/F_new_features/F-68-tpl-what-a-number-depends-on-mapping.png)
- [F-69-tpl-what-a-number-depends-on-dashboard](screenshots/F_new_features/F-69-tpl-what-a-number-depends-on-dashboard.png)
- [F-70-ki-selected](screenshots/F_new_features/F-70-ki-selected.png)
- [F-71-ki-menu](screenshots/F_new_features/F-71-ki-menu.png)
- [F-72-ki-options](screenshots/F_new_features/F-72-ki-options.png)
- [F-73-ki-data-tab](screenshots/F_new_features/F-73-ki-data-tab.png)
- [F-74-ki-config](screenshots/F_new_features/F-74-ki-config.png)
- [F-75-ki-bars](screenshots/F_new_features/F-75-ki-bars.png)
- [F-76-ki-bars-both](screenshots/F_new_features/F-76-ki-bars-both.png)
- [F-77-ki-details-toggled](screenshots/F_new_features/F-77-ki-details-toggled.png)
- [F-78-ki-bubbles-details](screenshots/F_new_features/F-78-ki-bubbles-details.png)
- [F-79-share-dialog](screenshots/F_new_features/F-79-share-dialog.png)
- [F-80-share-more-options](screenshots/F_new_features/F-80-share-more-options.png)
- [F-81-share-typed](screenshots/F_new_features/F-81-share-typed.png)
- [F-82-share-invited](screenshots/F_new_features/F-82-share-invited.png)
- [F-83-reader-my-dashboards](screenshots/F_new_features/F-83-reader-my-dashboards.png)
- [F-84-reader-shared-with-me](screenshots/F_new_features/F-84-reader-shared-with-me.png)
- [F-85-reader-opens-dashboard](screenshots/F_new_features/F-85-reader-opens-dashboard.png)
- [F-86-share-more-options-open](screenshots/F_new_features/F-86-share-more-options-open.png)
- [F-87-share-ends-nodownload](screenshots/F_new_features/F-87-share-ends-nodownload.png)
- [F-88-share-team-tab](screenshots/F_new_features/F-88-share-team-tab.png)
- [F-89-share-team-done](screenshots/F_new_features/F-89-share-team-done.png)
- [F-90-team-share-ask](screenshots/F_new_features/F-90-team-share-ask.png)
- [F-91-team-shared](screenshots/F_new_features/F-91-team-shared.png)
- [F-92-reader-my-team](screenshots/F_new_features/F-92-reader-my-team.png)
- [F-93-reader-export-greyed](screenshots/F_new_features/F-93-reader-export-greyed.png)
- [F-94-reader-export-click](screenshots/F_new_features/F-94-reader-export-click.png)
- [F-95-reader-print-view](screenshots/F_new_features/F-95-reader-print-view.png)
- [F-96-reader-pptx-attempt](screenshots/F_new_features/F-96-reader-pptx-attempt.png)
- [F-97-remove-access-ask](screenshots/F_new_features/F-97-remove-access-ask.png)
- [F-98-remove-team-ask](screenshots/F_new_features/F-98-remove-team-ask.png)
- [F-99-reader-after-removal](screenshots/F_new_features/F-99-reader-after-removal.png)
- [F2-01-exec-summary-owner](screenshots/F_new_features/F2-01-exec-summary-owner.png)
- [F2-02-publishing-tab](screenshots/F_new_features/F2-02-publishing-tab.png)
- [F2-03-category-tags-saved](screenshots/F_new_features/F2-03-category-tags-saved.png)
- [F2-04-publish-org-click](screenshots/F_new_features/F2-04-publish-org-click.png)
- [F2-05-people-guest-section](screenshots/F_new_features/F2-05-people-guest-section.png)
- [F2-06-publishing-after-publish](screenshots/F_new_features/F2-06-publishing-after-publish.png)
- [F2-07-edit-mode](screenshots/F_new_features/F2-07-edit-mode.png)
- [F2-08-edited-heading](screenshots/F_new_features/F2-08-edited-heading.png)
- [F2-09-publishing-draft-changes](screenshots/F_new_features/F2-09-publishing-draft-changes.png)
- [F2-10-published-versions-list](screenshots/F_new_features/F2-10-published-versions-list.png)
- [F2-11-builder-unreleased-banner](screenshots/F_new_features/F2-11-builder-unreleased-banner.png)
- [F2-12-unreleased-hover](screenshots/F_new_features/F2-12-unreleased-hover.png)
- [F2-13-released](screenshots/F_new_features/F2-13-released.png)
- [F2-14-versions-after-release](screenshots/F_new_features/F2-14-versions-after-release.png)
- [F2-15-after-reload](screenshots/F_new_features/F2-15-after-reload.png)
- [F2-16-release-again](screenshots/F_new_features/F2-16-release-again.png)
- [F2-17-release-toast](screenshots/F_new_features/F2-17-release-toast.png)
- [F2-18-released-toast](screenshots/F_new_features/F2-18-released-toast.png)
- [F2-19-versions-two](screenshots/F_new_features/F2-19-versions-two.png)
- [F2-20-reader-sees-v162](screenshots/F_new_features/F2-20-reader-sees-v162.png)
- [F2-21-go-back-confirm](screenshots/F_new_features/F2-21-go-back-confirm.png)
- [F2-22-went-back](screenshots/F_new_features/F2-22-went-back.png)
- [F2-23-owner-draft-keeps-edit](screenshots/F_new_features/F2-23-owner-draft-keeps-edit.png)
- [F2-24-reader-sees-v1](screenshots/F_new_features/F2-24-reader-sees-v1.png)
- [F2-25-archive-confirm](screenshots/F_new_features/F2-25-archive-confirm.png)
- [F2-26-reader-shared](screenshots/F_new_features/F2-26-reader-shared.png)
- [F2-27-archive-confirm-counts](screenshots/F_new_features/F2-27-archive-confirm-counts.png)
- [F2-28-archived](screenshots/F_new_features/F2-28-archived.png)
- [F2-29-reader-archived](screenshots/F_new_features/F2-29-reader-archived.png)
- [F2-30-reader-archived-print](screenshots/F_new_features/F2-30-reader-archived-print.png)
- [F2-31-reader-mydash-archived](screenshots/F_new_features/F2-31-reader-mydash-archived.png)
- [F2-32-owner-archived-view](screenshots/F_new_features/F2-32-owner-archived-view.png)
- [F2-33-restored](screenshots/F_new_features/F2-33-restored.png)
- [F2-34-handover-confirm](screenshots/F_new_features/F2-34-handover-confirm.png)
- [F2-35-handed-over](screenshots/F_new_features/F2-35-handed-over.png)
- [F2-36-people-after-handover](screenshots/F_new_features/F2-36-people-after-handover.png)
- [F2-37-people-after-reload](screenshots/F_new_features/F2-37-people-after-reload.png)
- [F2-38-new-owner-view](screenshots/F_new_features/F2-38-new-owner-view.png)
- [F2-39-new-owner-share](screenshots/F_new_features/F2-39-new-owner-share.png)
- [F2-40-reader-unpublish](screenshots/F_new_features/F2-40-reader-unpublish.png)
- [F2-41-approval-ticked](screenshots/F_new_features/F2-41-approval-ticked.png)
- [F2-42-owner-publish-refused](screenshots/F_new_features/F2-42-owner-publish-refused.png)
- [F2-43-asked-approval](screenshots/F_new_features/F2-43-asked-approval.png)
- [F2-44-admin-approve-panel](screenshots/F_new_features/F2-44-admin-approve-panel.png)
- [F2-45-approved](screenshots/F_new_features/F2-45-approved.png)
- [F2-46-owner-published-after-approval](screenshots/F_new_features/F2-46-owner-published-after-approval.png)
- [F2-47-approval-unticked](screenshots/F_new_features/F2-47-approval-unticked.png)
- [F2-48-platform-security](screenshots/F_new_features/F2-48-platform-security.png)
- [F2-49-guest-toggle-on](screenshots/F_new_features/F2-49-guest-toggle-on.png)
- [F2-50-guest-saved](screenshots/F_new_features/F2-50-guest-saved.png)
- [F2-51-guest-section-on](screenshots/F_new_features/F2-51-guest-section-on.png)
- [F2-52-guest-link-created](screenshots/F_new_features/F2-52-guest-link-created.png)
- [F2-53-guest-copied](screenshots/F_new_features/F2-53-guest-copied.png)
- [F2-54a-url-start](screenshots/F_new_features/F2-54a-url-start.png)
- [F2-54b-url-end](screenshots/F_new_features/F2-54b-url-end.png)
