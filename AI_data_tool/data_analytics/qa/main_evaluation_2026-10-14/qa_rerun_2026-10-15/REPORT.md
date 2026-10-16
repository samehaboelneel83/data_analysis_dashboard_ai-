# QA report

**Build / branch:** s_mostafa (main 0cb8f48 + 3 fix commits: F-01 guest/embed maps, E-01/E-02 platform-admin protection, B-01 startup schema repair) — AI_data_tool/data_analytics
**App URL:** http://127.0.0.1:3001 (Vite; /api → backend :8000; Postgres :5433 db datalytics_fix)
**Browser:** headless Chromium (puppeteer driver, port 9431). The driver was restarted once at ~09:00 with one extra read-only command (`val`, reads an input's displayed value) to read the one-time guest-link URL, which is shown only inside an input box; no clicks/typing via selectors or API.
**Viewport:** 1440×900, plus 390×844 for MOB-01/02/03
**Seeded:** yes (fresh seed: 6 demo datasets, 10 demo dashboards)
**Login used for most cases:** ADMIN admin@datalytics.local (GLOBAL for SEC-01, EMEA for NAV-04/SEC-02/SEC-03; admin@example.invalid and admin@contoso.invalid for the fix checks)
**Date:** 2026-10-15, 08:25–09:40 EEST
**Tester:** Claude (agent) — all 57 `high` cases + fix verification

## Summary

| | Count |
|---|---|
| Total run | 57 of 57 |
| Passed | 46 |
| Failed | 4 |
| Blocked / skipped | 7 blocked (no LLM) |

Baseline (unfixed main 0cb8f48): 45 pass / 4 fail / 8 blocked. Only change: SHARE-02 BLOCKED → PASS.

**Top issues** (worst first, all unchanged from baseline):

1. SEC-02 — EMEA user sees the raw error "Unknown column or function in measure expression: name 'cost' is not defined" on the Margin % by region tile (column security shows up as a broken tile).
2. DASH-04 — "Create a dashboard" lets you click Create with an empty name; an "Untitled dashboard" is created without a name-required message.
3. INS-02 — "View full scan →" lands on Analysis > Insights with an empty panel and only a "Generate insights" button.
4. MAP-02 — Origin density bubbles print two overlapping numbers per bubble (e.g. "34" over a faint "7").
5. (observations, not case fails) At 390 px /reports keeps its Views/Folders side panel so the list is squeezed (folder title one letter per line, search cut off) — shot MOB-02c. EMEA's Ask AI scope header shows the unfiltered "2,000 rows · 13 columns". Toolbar Undo after a tile resize on World Sales Map did not revert it. Demo — Sales Overview small tiles still clip content.

**Notes for the next run** (flakes, missing seed, AI model down):

- No LLM: Ask AI and the page copilot disable the input up front ("The model server isn't reachable, so new questions are paused.") → ASK-02/03/04/06, SEC-03, BUILD-10/11 blocked.
- Machine heavily loaded (load avg ~5): first page loads after login took up to ~60 s ("Loading…"), some clicks needed a retry. The lead reported a short frontend outage around 09:20–09:25; the only case affected (AUTH-06, blank page) was waited out/re-checked and redirected correctly, so it is a pass.
- Guest links: turned ON in Platform settings → Sessions and security for SHARE-02 / F-01, then turned OFF again with **Reset** (back to the environment value `false`; "Changed here" badge gone; after a reload the box is unchecked). Re-opening a guest link afterwards as a logged-out guest shows "This link does not exist or has expired." (404 /api/v1/shared/…), as designed. Three guest links remain listed (2 on World Sales Map — one created before the driver restart — and 1 on Demo — Distributions); they cannot open while the setting is off.
- Headless Chromium has no clipboard, so "Copy link" shows "Couldn't copy the link".
- MAP-04 resized the seeded Shipping routes tile; the toolbar Undo did not revert it, so I dragged it back to its seeded size (col 1–12, row 24–28; status "Saved").
- Items created (all "QA …", not deleted): dataset "QA Sample 0845" (UP-02), dashboards "QA Dashboard 0852" (DASH-05/BUILD) and "QA Untitled leftover" (the stray "Untitled dashboard" from DASH-04, renamed). Users qa.e02.user@example.invalid and qa.e02.mixed@example.invalid (Contoso) were created and deleted.
- Screenshots: shots/

---

## Results

| Test ID | Result | What actually happened | Console errors | Notes |
|---|---|---|---|---|
| AUTH-01 | pass | Empty submit stays on /login; inline "Enter your email address." / "Enter your password." | none (401 GET /auth/me expected while logged out) |  |
| AUTH-02 | pass | "Enter a full email address, like name@company.com."; stays on /login | none |  |
| AUTH-03 | pass | "That email and password don't match. Check them and try again."; stays on /login | 401 POST /auth/login (expected) |  |
| AUTH-04 | pass | Same message as AUTH-03; still on /login | 401 POST /auth/login (expected) |  |
| AUTH-05 | pass | Lands on / "Good morning, Admin"; rail Home/Ask AI/Datasets/...; account menu "admin" top right | none | Home took ~60 s to render under load ("Loading…") |
| AUTH-06 | pass | Logged out, /reports -> /login (after the 401 /auth/me check; page was blank ~60 s under load first); signed in, /reports shows the dashboard list (DASH-01) | 401 GET /auth/me (expected) |  |
| AUTH-07 | pass | Account menu (admin) > Log out -> /login; opening / again ends on /login, Home not shown | 401 GET /auth/me (expected) |  |
| NAV-01 | pass | Rail Home, Ask AI, Datasets, Lineage, Upload, Connections, Dashboards, Insights each load their own page (/, /ask, /datasets, /lineage, /upload, /connections, /reports, /insights); no Try again / crash; active item highlighted (shots) | none |  |
| NAV-04 | pass | EMEA rail: Home, Ask AI, DATA, DATA SOURCES, ANALYSE only — no Monitoring / Admin / Platform. Direct /admin/users redirects to / ("Good morning, Demo-emea") | none (401 /auth/me lines from the logged-out login step) |  |
| NAV-05 | pass | Rail shows MONITORING (Refresh & jobs, Deliveries, Activity), ADMIN (13 pages), PLATFORM (Organizations, Platform settings) | none |  |
| HOME-01 | pass | KPI tiles (10 dashboards, 6 datasets, 1 connection), quick actions, "Continue where you left off" (honest empty), Dashboards list, Datasets table; AI box says model server unreachable | none |  |
| HOME-02 | pass | Clicked "Demo — World Sales Map" card on Home -> /reports/5 viewer with maps | 404 GET /datasets/1/analysis (no analysis yet; page fine) | Viewer took ~60 s to load under load |
| HOME-03 | pass | Clicked "Demo — Routes" in the Home Datasets section -> /datasets/5 detail | 404 GET /datasets/5/analysis (x2; no analysis yet, page renders fine) |  |
| DS-01 | pass | /datasets lists all 6 demo datasets by name incl. Demo — Sales; no Try again | none |  |
| DS-02 | pass | Title "Demo — Sales", tabs Overview / Columns 13 / Data 2,000 / Analysis / Rules & alerts 1 / Models; "Ask about this data" visible | 404 GET /datasets/1/analysis | Tab names differ from plan (plan text outdated, as in baseline) |
| DS-03 | pass | Data tab: table of 16 columns (date … margin_pct, target, ƒx profit), rows 1–100 of 2,000, pager, horizontal scroll | none | shot DS-03 |
| DS-04 | pass | ƒx column "profit" (revenue - cost) appears in the Data tab header with values (e.g. -336.69, 443.09) | none |  |
| DS-09 | pass | "Ask about this data" -> /ask?dataset=1, "Asking about Demo — Sales · 2,000 rows · 13 columns", suggestions; banner "The model server isn't reachable, so new questions are paused." | none | First click did nothing under load; second click navigated |
| UP-01 | pass | With no file there is no Import/submit control (only "Browse files" + drop zone); step label "Import" is not clickable; stays on /upload | none | shot UP-01. Same design as baseline (submit impossible rather than a message) |
| UP-02 | pass | `upload qa_sample.csv` -> Review with preview (region, country, revenue, units, date; 5 rows); named "QA Sample 0845"; Import dataset -> "Dataset imported / QA Sample 0845 is ready to use"; Open dataset -> /datasets/7, Data tab shows region, country, revenue, units, date (5 rows) | 404 GET /datasets/7/analysis (no analysis yet) | shot UP-02. Success is an in-page panel, not a toast; detail opens via "Open dataset" |
| ASK-01 | pass | /ask with no dataset: "Step 1 Choose your data" picker (All 7: 6 datasets + 1 connection); question box and Send disabled, so nothing can be sent without scope | none |  |
| ASK-02 | blocked | No LLM: "Your question" textarea and "Send question" are disabled ("The model server isn't reachable, so new questions are paused."); could not send "hi" | none |  |
| ASK-03 | blocked | No LLM: input disabled (same as ASK-02) | none |  |
| ASK-04 | blocked | No LLM: input disabled (same as ASK-02) | none |  |
| ASK-06 | blocked | No LLM: input disabled (same as ASK-02) | none |  |
| DASH-01 | pass | /reports lists the 10 seeded dashboards by name (Demo — Sales Overview, World Sales Map, Use case — …, UX Showcase…), folders Use cases / Widget gallery, filters | none |  |
| DASH-03 | pass | Demo — Sales Overview opens /reports/1; widgets load (KPIs $8,632,597 / 402,108 / 19.0%, Revenue by region bars, Monthly revenue line) | 404 GET /datasets/1/analysis | shot DASH-03. Visual, same as baseline: small tiles clip content (gauge value, 2nd value of "Revenue, cost and units", "Average margin % by product" squashed) |
| DASH-04 | fail | "New dashboard" opens "Create a dashboard" (Blank/Template/With AI, Dashboard name, Dataset, Folder); Create is enabled with an empty name and clicking it creates "Untitled dashboard" (/reports/11?pick=data) with no name-required message | none | shots DASH-04a, DASH-04 (same as baseline). Stray dashboard renamed "QA Untitled leftover" |
| DASH-05 | pass | Dialog: name "QA Dashboard 0852", Dataset Demo — Sales, Create -> /reports/12?edit=1, empty editable canvas "Design this page" with Demo — Sales attached (primary) | 404 GET /datasets/1/analysis |  |
| BUILD-01 | pass | Empty canvas "Design this page", left panel Insert/Fields/Templates (Insert = gallery of 77 chart types), right Properties panel, Edit mode active | none | shot BUILD-01 |
| BUILD-02 | pass | Insert > Bar adds "Bar Chart" (SAMPLE, "Needs Dimension"); clicking field region then revenue binds Dimension=region, Measure=revenue; 4 bars render (2.22M, 2.2M, 2.2M, 2.01M) | none | shots BUILD-02, BUILD-02c. Clicking a field by text sometimes missed under load (clicked by position) |
| BUILD-03 | pass | Insert > KPI ("Needs Measure") + revenue -> "$ 8,632,597 revenue", Aggregation Sum | none | shot BUILD-03 |
| BUILD-04 | pass | Clicked Asia Pacific bar: chip "region = Asia Pacific", tiles show "1 filter", Total revenue $2,221,092, Units 102,974, Region slicer only Asia Pacific, Monthly revenue rescaled; Reset filters restores $8,632,597 | none | shot BUILD-04. Cosmetic: selected bar value label white on light green |
| BUILD-06 | pass | Layout menu lists Executive (default), KPI board, Split, Spotlight, Free layout, …; Executive put KPI full width on top, bar below; no overlap, no big empty band | none | shot BUILD-06 |
| BUILD-07 | pass | `drag` of the KPI's move handle onto the Bar chart: they swapped (Bar on top, KPI below at row 7–8), both kept a usable size | none | shot BUILD-07 |
| BUILD-08 | pass | `drag` of the Bar chart resize handle to the top-left: stops at col 1–4 × row 1–4 (~230×245 px); all 4 bars, axis and labels still visible | none | shot BUILD-08 |
| BUILD-10 | blocked | No LLM: page copilot ("Ask AI · QA Dashboard 0852 · Page 1") opens with a "New insight" card and suggestions, but input + send are disabled: "The model server isn't reachable, so new questions are paused." No crash | none | shot BUILD-10 |
| BUILD-11 | blocked | No LLM: same disabled copilot input | none |  |
| MAP-01 | pass | Shipping routes: whole world in the tile, route arcs visible, Asia/Australia not cut off | none | shot MAP-01 |
| MAP-02 | fail | Origin density: bubbles inside the tile, but each bubble still prints two overlapping numbers (e.g. "34" over a faint "7", "5" over "0"), counts hard to read | none | shot MAP-02 (same defect as baseline) |
| MAP-03 | pass | Routes as a network: London, Tokyo, Sydney, Los Angeles (+ Frankfurt, New York, Dubai, Singapore, Sao Paulo, Johannesburg) labels inside the tile | none | shot MAP-03 |
| MAP-04 | pass | Edit mode: dragged the Shipping routes resize handle to half width -> tile became col 1–6, map refit with the whole world visible, no clipping; dragged it back to col 1–12 (seeded size restored, "Saved") | none | shots MAP-04a/b/c/e. Minor: the toolbar Undo after the resize did not revert it (it greyed out, tile stayed narrow), so the size was restored by dragging |
| INS-01 | pass | /insights: Dataset picker lists 6 datasets; Demo — Sales -> TOP INSIGHTS (margin_pct / profit outliers, units 2025-01 spike, cost 2024-09 dip) with histograms | none | shot INS-01 |
| INS-02 | fail | "View full scan →" -> /datasets/1#insights, Analysis tab with "What stands out? Insights" selected, but the Insights panel is empty except for a "Generate insights" button — the longer list is not shown | 404 GET /datasets/1/analysis (x2) | shot INS-02 (same as baseline) |
| CONN-01 | pass | /connections lists "Demo — Live SQLite" (SQLite, Not tested, 1 dataset) with Test / Browse / Query builder / Guided setup / Open actions | none |  |
| CONN-02 | pass | New connection > PostgreSQL > Next > Create connection with empty fields: "Connection name is required", "Host is required", "Database is required"; drawer stays open; toast "Fill in Connection name, Host, Database first" | none | shot CONN-02 |
| LIN-01 | pass | Graph: Sources (2) -> Datasets (7) -> Reports (12) columns with extract/reads edges; Graph/List toggle, filters, "Show issues only", Export as PNG | none | shot LIN-01 |
| SEC-01 | pass | GLOBAL on "Use case — Regional performance review" (/reports/8): 4 regions, Revenue $8,632,597, Against target 9,109,506.47, Margin % by region (cost-based) 10.94 / 10.55 / 10.08 / 8.21 | 404 GET /datasets/1/analysis | shot SEC-01 |
| SEC-02 | fail | EMEA on the same report: Europe only, Revenue $2,199,377 (< GLOBAL $8,632,597), Against target 2,281,278.85 — RLS works. But the "Margin % by region" tile shows the raw error "Unknown column or function in measure expression: name 'cost' is not defined" instead of hiding the tile / a friendly restricted-column message | 404 GET /datasets/1/analysis | shot SEC-02 (same defect as baseline) |
| SEC-03 | blocked | No LLM: as EMEA, /ask?dataset=1 (Demo — Sales) has the question box + Send disabled ("The model server isn't reachable…") | none | Note: the scope header shows "2,000 rows · 13 columns" for EMEA, i.e. the unfiltered row/column count, although EMEA only sees Europe rows and no cost |
| ADM-01 | pass | /admin/users lists admin@example.invalid, demo-emea, demo-global, admin@datalytics.local (Platform Admin) with Edit/Delete | none |  |
| ADM-02 | pass | New User > Create empty: "Email is required"; with email only: "Password is required for a new user"; nothing created | none (401 /auth/me lines were from the logged-out login step) | shot ADM-02. Errors are toasts only |
| SHARE-01 | pass | Share "QA Dashboard 0852" dialog (People / Publishing / Embed / Schedule): "Link to this page" http://127.0.0.1:3001/reports/12?page=19 with Copy link. Copy link -> toast "Couldn't copy the link" (headless Chromium has no clipboard permission, not verifiable here). Guest-link section: "switched off for this platform" (default) | none | shot SHARE-01a |
| SHARE-02 | pass | Platform settings > Sessions and security > "Allow links that open without signing in" turned ON (Save changes) as admin@datalytics.local. Share "Demo — World Sales Map" > Create guest link (7 days) -> /shared/QFpJ…SXRk. Logged out (cleared cookies, new page) and opened it 3×: stays on /shared/… after 8 s, header "Demo — World Sales Map · Shared view · read only", no rail/app chrome, all map tiles render (choropleth, points, bubbles, routes, clusters, network, pies, layered). Setting turned back OFF at the end | 401 GET /auth/me only (expected for a guest); no map-settings 401, no redirect | shots F01-map-run1/2/3, F01-map-run3-scrolled. Baseline: BLOCKED (setting off) |
| MOB-01 | pass | 390×844: login form fits, Sign In button full width (308×44 px, tappable), signed in to / | none | shot MOB-01 |
| MOB-02 | pass | 390×844: "Open navigation" opens an overlay drawer (full rail, page dimmed behind); tapping Dashboards goes to /reports and the drawer closes; reopened drawer closes on Escape | none | shots MOB-02a, MOB-02b. Observation (not this case's expectation): at 390 px /reports keeps its Views/Folders side panel (~248 px wide), so the dashboard list is squeezed — "Use cases" folder title wraps one letter per line, search box and "New dashboard" are cut off (shot MOB-02c) |
| MOB-03 | pass | 390×844, Demo — World Sales Map: widgets stack one per row and the canvas scrolls; KPIs, Units by country bubbles and Shipping routes draw with the whole world, nothing clipped | 404 GET /datasets/1/analysis | shots MOB-03a/b/c. Minor (as baseline): toolbar overflows to the right ("Subscr…" cut off), floating AI button covers the map corner; the tab container's children also appear as stand-alone tiles at the top |

---

## Failures in detail

### DASH-04
- **Page:** /reports → New dashboard
- **Account:** ADMIN
- **Steps:** Click "New dashboard"; leave "Dashboard name" empty (placeholder "Untitled dashboard"); click Create.
- **Expected:** Create disabled, or a "name is required" message.
- **Actual:** Create is enabled; "Untitled dashboard" is created (/reports/11?pick=data) and the "Choose the data for this dashboard" picker opens.
- **Screenshot:** shots/DASH-04a.png, shots/DASH-04.png
- **Console:** none
- **Network:** no failed requests

### MAP-02
- **Page:** Demo — World Sales Map, tile "Origin density" (also in the guest view)
- **Account:** ADMIN
- **Steps:** Scroll to Origin density and wait.
- **Expected:** Bubbles inside the tile, counts readable.
- **Actual:** Bubbles are inside the tile, but each shows two overlapping numbers (bold count over a faint second value: "34"/"7", "5"/"0", "1"/"3"…).
- **Screenshot:** shots/MAP-02.png, shots/F01-map-run3-scrolled.png
- **Console:** none
- **Network:** no failed requests

### INS-02
- **Page:** /insights → View full scan
- **Account:** ADMIN
- **Steps:** Pick Demo — Sales, wait for Top insights, click "View full scan →".
- **Expected:** The dataset page's Insights section with the longer list.
- **Actual:** /datasets/1#insights opens on the Analysis tab with "What stands out? Insights" selected, but the panel is empty except for "Generate insights".
- **Screenshot:** shots/INS-02.png
- **Console:** 404 GET /api/v1/datasets/1/analysis (x2)
- **Network:** as above

### SEC-02
- **Page:** Use case — Regional performance review
- **Account:** EMEA demo-emea@example.invalid
- **Steps:** Log in as EMEA and open the report by name.
- **Expected:** Europe only, `cost` removed cleanly, totals smaller than for GLOBAL.
- **Actual:** Europe only, Revenue $2,199,377 vs GLOBAL $8,632,597 (correct), but the "Margin % by region" tile shows "Unknown column or function in measure expression: name 'cost' is not defined".
- **Screenshot:** shots/SEC-02.png (GLOBAL for contrast: shots/SEC-01.png)
- **Console:** 404 GET /api/v1/datasets/1/analysis
- **Network:** as above

---

## Compared with baseline (unfixed main)

Baseline (the QA run in ../EVALUATION.md, section 7, first part): 45 pass / 4 fail / 8 blocked. This run: 46 pass / 4 fail / 7 blocked.

| Case | Baseline (main 0cb8f48) | Now (s_mostafa) | Why |
|---|---|---|---|
| SHARE-02 | BLOCKED (guest links off at platform level; baseline did not change the setting) | PASS | This run turned "Allow links that open without signing in" ON via Platform settings as the platform admin, created a guest link on Demo — World Sales Map and opened it logged out 3×: it stays on /shared/… with all maps drawn, no redirect to /login and no map-settings 401 (the F-01 fix). The change comes from enabling the setting for this run; whether the guest stays on the map view is what F-01 fixes (see Fix verification). Unfixed main was not re-tested with the setting on in this run, so this run alone does not show main's behaviour. *Lead's note:* before fixing, the same check was run on the unfixed code with guest links on: the logged-out guest of Demo — World Sales Map was sent to /login in 3 of 3 runs (401 on GET /api/v1/map-settings), while a no-map dashboard stayed on the shared view. |

All other 56 cases have the same result as the baseline: the same 4 FAILs (DASH-04, MAP-02, INS-02, SEC-02 — same symptoms), the same 7 no-LLM BLOCKED cases (ASK-02/03/04/06, SEC-03, BUILD-10/11), and everything else PASS.

---

## Fix verification

| Fix | Result | What I saw | Screenshots (shots) |
|---|---|---|---|
| F-01 guest/embed maps | **PASS** | Guest links ON (Platform settings), logged out (`clearcookies` + `newpage`). Guest link to "Demo — World Sales Map" opened 3×: final URL after 8 s each time = `/shared/QFpJ…SXRk` (no redirect to /login); header "Shared view · read only", no app rail; every map tile draws (Revenue by country choropleth, Where we sell points, Units by country bubbles, Shipping routes, Origin density clusters, City shipping network, Category mix pies, Destinations and origins, Routes as a network). Guest link to "Demo — Distributions" (no maps) once: stays on `/shared/vaNW…z3s`, histogram/box/scatter/correlation render. Console in all 4 runs: only `401 GET /api/v1/auth/me` (the expected "am I signed in?" probe); **no `GET /api/v1/map-settings` 401**, no other 4xx. | F01-map-run1.png, F01-map-run2.png, F01-map-run3.png, F01-map-run3-scrolled.png, F01-nomap.png |
| E-01 platform-admin row protected | **PASS** | As admin@example.invalid (Default org admin, no PLATFORM section in its rail): Admin → Users shows admin@example.invalid, demo-emea, demo-global with Edit + Delete, and admin@datalytics.local ("Platform Admin (admin)") with a grey **"Platform admin"** label and **no Edit/Delete buttons** (3 Edit + 3 Delete buttons on the page for 4 rows). As admin@datalytics.local: same page, all 4 rows incl. admin@datalytics.local have Edit + Delete. | E01-bootstrap-admin-users.png, E01-platform-admin-users.png |
| E-02 reserved platform-admin email | **PASS** | As admin@contoso.invalid: New user, email `ADMIN@datalytics.local`, password QaPass-0915-demo, role Analyst → Create → `403 POST /api/v1/admin/users` and red toast **"This address is reserved for platform administrators"**; dialog stays open, the Contoso user list is unchanged (no account created). Then `qa.e02.user@example.invalid` → toast "User created", row appears as `qa.e02.user@example.invalid` (Analyst). Extra: `QA.E02.Mixed@Example.Invalid` → stored and listed as `qa.e02.mixed@example.invalid` (lower-cased). Both QA users deleted via Delete → confirm dialog; list back to admin@contoso / analyst@contoso. | E02-refused2.png (toast), E02-refused.png, E02-created.png |

B-01 (startup schema repair) has no browser-visible check of its own; the app started on the fresh database and every page used in this run loaded without schema errors.

---

## Sign-off

- Short run (auth → maps → RLS → mobile) complete? yes
- Full plan complete? no — high cases only, all 57 run, plus the three fix checks
- Safe to demo to a user? With caveats: avoid the EMEA view of the Regional performance review, the "View full scan" link and the Origin density labels; keep guest links off unless needed.
