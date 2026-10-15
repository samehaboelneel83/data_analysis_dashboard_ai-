# QA report — final release-readiness check

**Build / branch:** `fix/integ2` @ `a9acecbb` (every round-1 and round-2 fix plus the known-gap review), AI_data_tool/data_analytics
**App URL:** http://127.0.0.1:3001 (Vite dev server; /api → backend :8000; Postgres db `datalytics_r2`, freshly seeded). 7 datasets (6 demo + the lead's "C11 DQ check" DirectQuery check dataset), 10 dashboards.
**Browser:** headless Chromium via the `b_fixqa.mjs` driver. Clicks by visible text; where the driver's text matcher picked the wrong element, the visible control was clicked by screen position (each noted).
**Viewport:** 1440×900, plus 390×844 for MOB-01/02/03
**Seeded:** yes (fresh demo seed)
**Logins used** (password `demo-password`): admin@datalytics.local (most cases), demo-global@example.invalid (SEC-01, B-21), demo-emea@example.invalid (NAV-04, SEC-02, SEC-03), admin@example.invalid (B-21)
**Date:** 2026-10-15, 18:42–20:33 EEST
**Tester:** Claude (agent) — all 57 `high` cases + 7 fix checks

## Summary

| | Count |
|---|---|
| Total run | 57 of 57 |
| Passed | 50 |
| Failed | 0 |
| Blocked / skipped | 7 blocked (no AI model server: ASK-02, ASK-03, ASK-04, ASK-06, SEC-03, BUILD-10, BUILD-11) |

Fix checks: 7 of 7 pass.

Baseline (`qa_rerun_2026-10-15`, the branch before the remaining fixes): 46 pass / 4 fail / 7 blocked. All 4 baseline failures now pass; nothing regressed.

**Top issues** (none fails a case):

1. At 390 px, /reports keeps its Views/Folders side panel, so the list is squeezed ("Use cases" folder title wraps one letter per line, search cut off) — unchanged from the baseline (shot MOB-02b).
2. MAP-04: a screenshot 8 s after the half-width resize showed tiles overlapping while the layout re-flowed (MAP-04b); 8 s later clean (MAP-04c). Undo passed through an in-between state before landing on the seeded size.
3. Cosmetic: the dual-axis line chart's two roles are both labelled "Line" (no left/right hint), and its right-axis tick labels are partly covered by the rotated "avg(margin_pct)" title; the Sales Overview gauge prints "$ 8.632.597" (dots) while other tiles use commas; deleting a glossary term asks for no confirmation; a Platform settings hint reads "Allowed: 1 to —."

**Notes for the next run:**

- No AI model server in this environment: Ask AI and the page copilot say "The model server isn't reachable, so new questions are paused." and Send is disabled → the same 7 cases as the baseline are blocked.
- Machine heavily loaded (load avg 7–8, the full test suites ran in parallel): pages took 20–60 s; the AUTH-04 screenshot timed out after 3 min, so that result is from the page text.
- Driver quirks (not app bugs): `click "Ask about this data"` resolved to a wide header container and opened "Use in Python"; `click "Import"` on /upload matched a "Demo — Routes · Imported…" link; `fill "Email"` in the New User dialog filled the search box behind it. Each step was redone by clicking the visible control by position.
- Headless Chromium has no clipboard: "Copy link" shows "Couldn't copy the link" (as baseline).
- Guest links: turned ON for SHARE-02, link revoked afterwards, setting back to off with Reset (unchecked after a reload).
- Clean-up: deleted dataset "QA final Sample", dashboard "QA final Dashboard", glossary term "QA final term"; the New User validation created no user; World Sales Map "Shipping routes" back at col 1–12 · row 24–28 (checked after reload); viewport reset to 1440×900.
- Console: no page errors or uncaught exceptions. Besides the expected `401 GET /api/v1/auth/me` while logged out: `[warn] [WidgetRenderer] widget N still loading after 20s (visible: false, request not sent)` for off-screen tiles; `404 GET /api/v1/datasets/1/analysis` (no saved analysis yet, page fine); `403 POST /api/v1/datasets/1/widget-data` on SEC-02 (the server refusing the column-restricted tile, shown as the friendly message).

## Compared with the baseline

| Case | Baseline | Now | What I saw |
|---|---|---|---|
| DASH-04 (C-30) | FAIL | **PASS** | Empty name: Create disabled with the hint "Give the dashboard a name"; spaces-only also disabled; nothing created. Shots DASH-04a/b. |
| MAP-02 (C-29) | FAIL | **PASS** | All 7 bubbles inside the tile with one number each (75/98/34/26/25/24/18 = 300); no faint second value; guest view the same. Shots MAP-02, SHARE-02b. |
| INS-02 (AD-06) | FAIL | **PASS** | "View full scan →" opens /datasets/1#insights with Re-scan, the summary sentence and ~12 cards (OUTLIER IMPACT ×2, ANOMALY ×3, CHANGE POINT ×2, CORRELATION ×2, LAGGARD, DATA QUALITY). Shot INS-02. |
| SEC-02 (E-12) | FAIL | **PASS** | EMEA: Europe only ($2,199,377 vs GLOBAL $8,632,597; target 2,281,278.85); the cost tile shows a lock and "This tile uses data your role can't see." instead of the raw error. Shot SEC-02. |

Also changed: SEC-03 is still blocked, but the EMEA scope header now shows the filtered "514 rows · 12 columns" (was the unfiltered 2,000 · 13). MAP-04: Undo now reverts the resize (it did not in the baseline).

## Results

| Test ID | Result | What actually happened | Console errors | Notes |
|---|---|---|---|---|
| AUTH-01 | pass | Empty submit stays on /login: "Enter your email address." / "Enter your password." | 401 /auth/me (expected) | AUTH-01 |
| AUTH-02 | pass | "Enter a full email address, like name@company.com."; stays on /login | none | AUTH-02 |
| AUTH-03 | pass | "That email and password don't match. Check them and try again." | 401 POST /auth/login (expected) | AUTH-03 |
| AUTH-04 | pass | Same message; still on /login | 401 POST /auth/login (expected) | screenshot timed out under load |
| AUTH-05 | pass | Home "Good evening, Admin"; rail + account menu | none | |
| AUTH-06 | pass | Logged out, /reports → /login; after sign-in back on /reports with the list | 401 /auth/me (expected) | AUTH-06 |
| AUTH-07 | pass | Account menu > Log out → /login; / afterwards stays on /login | 401 (expected) | AUTH-07a |
| NAV-01 | pass | All 8 rail items load their page; active item highlighted; no Try again | none | |
| NAV-04 | pass | EMEA rail has no Monitoring / Admin / Platform; /admin/users bounces to / | none | NAV-04a/b |
| NAV-05 | pass | MONITORING, ADMIN (14 pages), PLATFORM present | none | |
| HOME-01 | pass | KPI cards (10 / 7 / 1), quick actions, honest empty "Continue where you left off", dashboards + datasets lists | none | HOME-01 |
| HOME-02 | pass | World Sales Map card → /reports/5 | lazy-tile warnings | |
| HOME-03 | pass | Demo — Routes → /datasets/5 | none | HOME-03 |
| DS-01 | pass | 7 datasets listed by name | none | DS-01 |
| DS-02 | pass | Tabs Overview / Columns 13 / Data 2,000 / Analysis / Rules & alerts 1 / Models; "Ask about this data" shown | none | plan's tab names are outdated |
| DS-03 | pass | 16 columns, rows 1–100 of 2,000, pager, horizontal scroll | none | DS-03 |
| DS-04 | pass | ƒx "profit" column in the header with values | none | |
| DS-09 | pass | → /ask?dataset=1, "Demo — Sales · 2,000 rows · 13 columns" | none | clicked by position (driver quirk) |
| UP-01 | pass | No file → no submit control; "Import" step label inert; stays on /upload | none | UP-01 |
| UP-02 | pass | Import → "Dataset imported"; Data tab region, country, revenue, units, date (5 rows) | none | UP-02a, UP-02; deleted afterwards |
| ASK-01 | pass | "Step 1 Choose your data" picker (8 items); Send disabled | none | ASK-01 |
| ASK-02 | blocked | No model server; Send disabled | none | |
| ASK-03 | blocked | same | none | |
| ASK-04 | blocked | same | none | |
| ASK-06 | blocked | same | none | |
| DASH-01 | pass | 10 dashboards + 2 folders listed | none | DASH-01 |
| DASH-03 | pass | Sales Overview widgets load ($8,632,597 / 402,108 / 19.0%) | lazy-tile warnings | small tiles clip content (as baseline) |
| DASH-04 | pass | Create disabled until named | none | was FAIL |
| DASH-05 | pass | "QA final Dashboard" → editable empty canvas | none | deleted afterwards |
| BUILD-01 | pass | Gallery of 77 chart types, Properties panel, Edit mode | none | BUILD-01 |
| BUILD-02 | pass | Bar region × revenue, 4 bars | none | BUILD-02/02b |
| BUILD-03 | pass | KPI "$ 8,632,597 revenue" | none | BUILD-03 |
| BUILD-04 | pass | Asia Pacific bar filters the tiles ($2,221,092); Reset filters → $8,632,597 | none | BUILD-04 |
| BUILD-06 | pass | Executive layout: KPI on top, bar below, no overlap | none | BUILD-06 |
| BUILD-07 | pass | Drag KPI onto the bar swaps them | none | BUILD-07 |
| BUILD-08 | pass | Smallest size col 1–4 · row 1–4; data still readable | none | BUILD-08 |
| BUILD-10 | blocked | No model server; copilot input disabled | none | BUILD-10 |
| BUILD-11 | blocked | same | none | |
| MAP-01 | pass | Whole world, routes visible | none | MAP-01/01b |
| MAP-02 | pass | One readable count per bubble | none | was FAIL |
| MAP-03 | pass | All network labels inside the tile | none | MAP-03 |
| MAP-04 | pass | Half width: map refits; Undo → seeded size (checked after reload) | warnings only | transient overlap right after the resize |
| INS-01 | pass | Picker + Demo — Sales top insights | none | INS-01 |
| INS-02 | pass | Full insights list | none | was FAIL |
| CONN-01 | pass | Demo — Live SQLite with its actions | none | CONN-01 |
| CONN-02 | pass | Name / Host / Database "is required"; drawer stays open | none | CONN-02 |
| LIN-01 | pass | Sources 2 → Datasets 8 → Reports 11, with edges | none | LIN-01 |
| SEC-01 | pass | GLOBAL: 4 regions, $8,632,597, margins 10.94 / 10.55 / 10.08 / 8.21 | none | SEC-01 |
| SEC-02 | pass | EMEA: Europe only, $2,199,377; cost tile shows the restricted message | 403 widget-data (expected) | was FAIL |
| SEC-03 | blocked | No model server; header 514 rows · 12 columns | 404 analysis | |
| ADM-01 | pass | The 4 users listed | none | ADM-01 |
| ADM-02 | pass | "Email is required", then "Password is required for a new user"; nothing created | none | ADM-02a/b |
| SHARE-01 | pass | Page link shown; Copy link → "Couldn't copy the link" (headless) | none | SHARE-01a/b |
| SHARE-02 | pass | Logged out, guest link stays on /shared/… read-only, no rail; all maps draw | 401 /auth/me only | link revoked, setting reset |
| MOB-01 | pass | Form fits; Sign In 308×44 px | none | MOB-01a |
| MOB-02 | pass | Overlay drawer; closes after navigating and on Escape | none | squeezed /reports (as baseline) |
| MOB-03 | pass | Tiles stack and scroll; maps not clipped | warnings only | toolbar overflow + floating AI button (as baseline) |

## Fix checks

| Fix | Result | What I saw | Shots |
|---|---|---|---|
| AD-12 | **PASS** | Logged out, `/ask?dataset=1` → /login; after sign-in landed on /ask?dataset=1, not Home | FIX-AD12 |
| B-18 | **PASS** | Clicked the box, typed, Enter: URL kept dataset=1; Tab+Enter the same, Demo — Sales still selected; the box is read-only while the model is offline | FIX-B18 |
| B-21 | **PASS** | admin@example.invalid on "All data (org-wide)": added "QA final term", persisted after reload, then deleted. demo-global sees "QA org term" (organisation-wide) with no Add/Edit/Delete; Always box disabled | FIX-B21-* |
| E-08 | **PASS** | "What each role may do" matrix: 4 roles × Add data / Add connections / Create dashboards / Use AI / Download and export; org-admin rows fixed as always allowed | FIX-E08 |
| C-21 | **PASS** | PAGE SIZE Fit / 16:9 / 4:3 / Custom; Custom shows 1280 × 720 px inputs | C21-* |
| C-11 | **PASS** | month × revenue (left) and margin_pct (right): right axis avg(margin_pct) 0.0%–28.0%, not thousands | C11, C11f |
| C-07 | **PASS** | Scatter roles X axis\*, Y axis\*, Label; cost × revenue renders | C07a, C07 |

## Failures in detail

None.

## Sign-off

- Short run complete: yes
- Full plan complete: no — high cases only (57/57), plus the 7 fix checks
- Safe to demo: yes, with caveats — the AI features need a reachable model server; the dashboards list is cramped on phones.
