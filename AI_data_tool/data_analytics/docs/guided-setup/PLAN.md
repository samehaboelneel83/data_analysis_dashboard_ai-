# Guided setup — implementation plan

Agreed with the owner on 2026-10-07. Branch: `emad`. Nothing is pushed.

## The problem

Datalytics already has most of the intelligence (a source review, quality reports,
insights, an AI dashboard designer that checks every chart), but the user cannot find
a path through it:

- The AI description of a database is off by default, tables are listed by name (not
  by importance), there are no sample rows, and the review page has no menu entry.
- Nothing suggests a dataset, or explains why tables or columns were chosen.
- There are 3 different AI dashboard designers in 3 places; the best one is hidden in
  Ask AI.
- Results are detailed but hard to read (for example `nan 73%`, "1,567 outliers",
  "−1 looks like a code for unknown"), and they never say what to do.

## The agreed user journey

After connecting a database, the user enters one guided flow with a progress bar:

**Understand → Choose data → Check & discover → Dashboard**

1. **Connect** a database (as today).
2. **Understand**: the AI reads the database and describes it in plain language:
   what it holds, each table ranked from most to least useful, sample rows, how the
   tables relate. The user can correct or add to anything.
3. **About you** (optional, asked once): what the user does, what to focus on, what
   they need to know, what to leave out. These are hints, not rules. The answers are
   reused by every later step and never asked again.
4. **Choose data**: the AI proposes 2–3 datasets. Each card says
   **Includes / Leaves out / Why** (for example "you are a lawyer, so it keeps the
   rulings and leaves out colleagues' names"). The user can tick several, refine one
   in a side chat, or press **Build it myself** (today's manual tools). Then confirm.
5. **Check & discover**: a short plain-language data health summary plus the top
   insights. Every line says **what is wrong → why it matters → what to do**, with a
   **Fix it** button where possible and **Show details** for the full report.
6. **Dashboard**: one AI designer proposes 3 dashboards built on the findings, with a
   side chat to refine and **Blank** as the alternative. The builder keeps its
   suggestion pane and copilot either way. Only useful charts: every chart passes the
   designer's result checks and shows why it is there.

The user can leave at any step and come back; Home shows
"Continue: cars database, step 2 of 4".

## Decisions

| # | Decision |
|---|---|
| D1 | **The AI sees exactly what the logged-in user sees.** It reads data with the user's own privileges: row and column security apply. An admin switch "AI may read sample rows" stays, on by default (it matters when the model runs outside the server). |
| D2 | **Fits every user**: developers, business people (lawyer, manager), people who never used a database. Simple is the default; every section has its own **Show details**; a per-user setting "Always show details" expands everything. |
| D3 | The user can create **several datasets** in one go. |
| D4 | All AI text follows the **app language** (Arabic UI → Arabic summaries). |
| D5 | **Alongside, not instead**: every old page stays. The flow saves into the same objects (connection description, datasets, insights, dashboards), so the user finds them later in the usual pages. |
| D6 | **Plain first, details behind a button, never removed.** Every AI or quality message follows *what → why it matters → what to do*. |

## Where results live after the flow (nothing is a separate store)

| Step | Creates or uses | Found later in |
|---|---|---|
| Understand | Source description, table meanings, relationships | Connections → Review data source (gets a menu entry) |
| About you | The brief | Setup page, and reused by Ask AI and the dashboard designer |
| Choose data | Normal datasets | Datasets |
| Check & discover | Health notes, saved checks, insights | Dataset → Rules & alerts, Insights |
| Dashboard | A normal dashboard | Dashboards |

## Changes to old pages (only these)

1. A simple summary on top, today's page below under **Show details**: dataset Columns
   tab, quality report, Review data source, Insights.
2. Links back into the flow: "Continue setup" on a connection without datasets,
   "Run Check & discover" on a dataset that was never checked.
3. The 3 AI dashboard entry points (Dashboards "With AI", Review page "Suggest a
   dashboard", Ask AI) all open the same designer.
4. Small readability fixes: an empty value shows as "Empty", never `nan`.

## Rules for every sub-step

- Backend tests for new services and routes; frontend tests for new components.
- Every new string goes into both `en.ts` and `ar.ts`.
- Before ticking a sub-step: its tests, the full frontend test run, `npm run build`,
  rebuild the containers, and check the screen in the browser (light, dark, Arabic).
- The `cars` database (`cars_hatla2ee` and 3 real-estate tables) is the walkthrough
  case for every phase.
- Commit only when the owner asks.

## Plan

### Phase 0 — Foundations
- [x] 0a Plain-first building block: a shared `PlainSummary` component (lines of
      *what / why / do*, severity, optional action button, **Show details** slot) and
      the per-user "Always show details" preference.
- [x] 0b AI access follows the user's privileges (D1): sample rows for the AI are read
      through the same security as the user; admin switch "AI may read sample rows",
      on by default; new connections no longer start with model descriptions off.
- [x] 0c Setup progress: a `setup_journeys` record per user and connection (current
      step, brief, chosen datasets, dashboard) with get/update API.

### Phase 1 — Understand
- [x] 1a Backend: database summary endpoint — plain-language overview, tables ranked
      by usefulness (rows, relationships, fact vs lookup, freshness, model's rank) with
      a one-line reason, a few sample rows each, in the user's language.
- [x] 1b Frontend: `/setup/:connectionId` page with the 4-step progress bar and the
      Understand step (summary, ranked tables, sample rows, edit description,
      Show details → Review data source).
- [x] 1c Entry points: after creating a connection go to setup; "Continue setup" on
      Connections and on Home; menu entry for Review data source.
  - >> GATE 1: walk through the cars database with the owner.

### Phase 2 — About you + Choose data
- [x] 2a About-you questions (all optional), saved on the journey.
- [x] 2b Backend: suggest datasets — 2–3 proposals (tables, columns, joins, filters)
      with Includes / Leaves out / Why; each proposal's SQL is run and checked
      (row count, empty columns) with the user's privileges before it is shown.
- [x] 2c Frontend: proposal cards with preview rows, multi-select, Build it myself.
- [x] 2d Refine a proposal in a side chat; the card updates in place.
- [x] 2e Create the chosen datasets (import jobs) and move on when they are ready.
  - >> GATE 2

### Phase 3 — Check & discover
- [x] 3a Backend: plain health summary from the quality report (what / why / do),
      including checks across columns (for example future model years, mileage too
      low for the car's age) proposed by the model and verified on the data.
- [x] 3b Fix it actions: treat empty as "Unknown", exclude bad rows from a measure,
      save a check (warn) — all through the existing prep pipeline and checks.
- [x] 3c Top insights in plain language, saved so they appear on the Insights page.
- [x] 3d Frontend step.
  - >> GATE 3

### Phase 4 — Dashboard
- [x] 4a One designer: the brief-first designer accepts datasets, the journey's brief
      and the Check & discover findings.
- [x] 4b Frontend step: 3 proposals, each chart with its reason, side chat to refine,
      Blank; create the dashboard and open it in the builder.
- [x] 4c Old entry points (Dashboards "With AI", Review page, Ask AI) open the same
      designer.
  - >> GATE 4

### Phase 5 — Old pages, plain first
- [x] 5a Dataset Columns tab: "What you should know" box; `nan` shown as "Empty".
- [x] 5b Quality report: plain summary on top.
- [x] 5c Review data source: plain summary on top.
- [x] 5d Insights page: plain summary on top.
- [x] 5e Links back into the flow ("Continue setup", "Run Check & discover").

### Phase 6 — End-to-end QA
- [x] 6a Full walkthrough as three users: developer, lawyer-style business user,
      first-time user; English and Arabic; restricted user (row/column security).
- [x] 6b Fix what the walkthrough finds; update `qa/TEST_PLAN.md`.

## Log

- 2026-10-07: plan agreed with the owner.
- 2026-10-07: 0a done — `components/ui/PlainSummary.tsx`, `lib/detailsPreference.ts`
  (per-user, localStorage like language), "Always show details" in the account menu.
  Type check clean; 298 test files / 3,872 tests pass.
- 2026-10-07: 0b done — new connections let the AI describe them (form checkbox, on by
  default); the review catalog now follows the Connections list's visibility (a member
  could read any connection's catalog before: security fix); sample rows are read with
  the user's own connection row rules parsed into the SQL, personal values masked
  (`services/guided_setup/access.py`). The visibility rule moved from the router into
  that service (layer rule: services may not import routers or raise HTTP errors).
- 2026-10-07: 0c done — `setup_journeys` (model, migration 0059, startup ALTER for the
  `summary` column), `/api/v1/setup` routes: journeys, get-or-start, update.
- 2026-10-07: 1a done — `services/guided_setup/understand.py`: facts + usefulness score
  (group first: main, supporting, technical), the model's words in the reader's
  language, checked against the catalog, a human's description always wins. Written
  in the BACKGROUND and kept on the journey: the first live run waited 5+ minutes
  because every configured model endpoint was unreachable; now the facts answer in
  ~0.04 s and the page polls. A model that is down is reported once, not re-asked.
  Years are not measures; date ranges from the sync's sample say "approximate".
- 2026-10-07: 1b done — `/setup/:id` (`pages/Setup.tsx`, `pages/setup/*`), progress bar,
  Understand step (overview, ranked tables, sample rows, edits, Show details → review
  page), steps 2–4 honest placeholders. Polling stops after 3 minutes and says the AI
  is slow. Checked live on Cars DB in English and Arabic (month names localised).
- 2026-10-07: 1c done — new connection → `/setup/:id`; every connection row offers
  "Guided setup" / "Continue setup · step n of 4" (the review page link for
  non-admins); Home shows "Continue setting up".
- 2026-10-07: checks — frontend 300 files / 3,887 tests, type check clean, build OK.
  Backend full suite: 7,085 passed; the 23 failures and 25 errors are identical on the
  untouched last commit (container-only: files outside `backend/` not mounted, env).
  ARCHITECTURE.md/.html counts were already stale (12 failures at HEAD); updated to the
  real numbers, the doc test passes 35/35.
- Open: the configured AI endpoints (Qwen) were unreachable during the whole session,
  so the AI-written words were verified with tests only, not live.

- 2026-10-07 (owner feedback after GATE 1): the AI is asked ONCE per language and the
  answer kept until "Ask AI again" (now always shown). Leaving the page, switching
  language, re-syncing or correcting a description no longer asks again: a
  correction wins over the AI's text when drawn. A failed re-ask keeps the earlier
  words and says so. Verified live on Cars DB (connection 38): 3 visits, 0 new AI calls.
- 2026-10-07: Phase 2 done — `services/guided_setup/datasets.py`: proposals checked (one
  read, catalog tables, qualified columns), run AS the person (row rules parsed in), one
  repair round with the database's error, plain fallback from the facts. Live on Cars DB:
  3 different datasets (broad / depreciation / mileage), a chat change ("2015+, no city")
  and a real import job (dataset 226, 9,319 rows). Bugs found live and fixed: a model
  answer without `sql` crashed the repair; a crashed job stayed "pending" and every
  visit restarted it (now recorded as failed, with plain proposals); three near-identical
  proposals (prompt now asks for a broad one plus different angles). Creating datasets
  is admin-only, as the app's import is. About you is asked before the first suggestion.
- 2026-10-07: Phase 3 done — `services/guided_setup/health.py`: quality report → what/why/
  what to do with Fix it (prep steps through the dataset's own route; "Warn me" saves a
  check), generic rules (negative amounts, future dates), model rules over 2+ columns
  verified on the rows (kept only when 3+ rows and at most 25% break them). Live: 254
  cars aged 5+ with < 10,000 km; 225 "New" cars older than a year. Fixed live: a flag
  column ("Yes" or blank) was called constant; -1 codes were reported twice; numeric
  blanks were "misread as No"; 66.5% rounded to 66; insights called market data "your
  inventory".
- 2026-10-07: Phase 4 done — the dataset designer (`suggest_dashboards`, quick) told the
  brief + findings; 3 proposals per single dataset, every chart drawn; change by asking;
  blank. Dashboard building moved to `lib/buildDashboard.ts` (shared with the dialog).
  Review page's "Suggest a dashboard" now opens the guided setup (old dialog kept as
  "Quick suggestion"); Ask AI's proposals link to it; Dashboards "With AI" already uses
  the same designer.
- 2026-10-07: Phase 5 done — `components/setup/DatasetHealth.tsx` on the dataset Columns and
  Rules & alerts tabs (setup findings when there are any, else a quick model-free health
  that works for UPLOADED files too: `/setup/datasets/{id}/health` + `/fix` through the
  dataset's own prep route); `nan`/`None` shown as "Empty"; review page and Insights page
  get plain summaries on top (`SourceSummary`, `SetupInsights`), optional and silent on
  failure. Frontend 303 files / 3,908 tests pass.
- 2026-10-07: Phase 6 done — walked as a user in Chrome on a NEW connection (EGX Stocks,
  642,725 rows, investor) and on Cars DB (dealer, English + Arabic), plus a non-admin.
  19 problems found and fixed; full list, scores and next steps in
  [EVALUATION_REPORT.md](EVALUATION_REPORT.md). Main ones: the model guessed periods
  (now measured MIN/MAX as the user); a date in preview rows broke saving and left the
  step pending (rows JSON-safe; every background job records its own failure); a job
  held a DB transaction during the AI wait and froze the app behind a migration (jobs
  release transactions before long waits); nonsense insights from summed prices
  (`health.sensible`); a rule comparing a percentage with prices (percentages labelled,
  max share 10%). Frontend 3,922/3,923 (one existing flaky test passes alone), build OK.

