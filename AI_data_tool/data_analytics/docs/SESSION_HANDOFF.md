# Session handoff — Datalytics (written 2026-10-12)

Load this file at the start of a new chat. It says what the project is, what was built in the last
long session, what state the code is in, and what is open. Everything here was true on 2026-10-12;
check `git status` and `git log` before relying on it.

## 1. The project

- **Datalytics**: a local BI web app (upload or connect data, datasets, dashboards, Ask AI, insights).
- **Repo root**: `/mnt/hdd16/Omda 2025/projects/Datalytics/data_analysis_dashboard_ai-`
- **App folder**: `AI_data_tool/data_analytics` (all paths below are relative to it).
- **Stack**: FastAPI + async SQLAlchemy (`backend/app`), React + TypeScript + Vite + Recharts
  (`frontend/src`), PostgreSQL, Valkey, Docker Compose.
- **Containers**: `datalytics_backend`, `datalytics_frontend`, `datalytics_db`, `datalytics_valkey`.
- **URLs**: app http://localhost:3001, API http://localhost:8000/api/v1, Swagger http://localhost:8000/docs.
- **Sign-in**: seeded accounts only; see `CLAUDE.md` and `qa/TEST_DATA.md`.
- **Agent notes**: `CLAUDE.md`. **Architecture**: `ARCHITECTURE.md` / `.html`.

## 2. State of the code

| | |
|---|---|
| Branch | `emad` |
| Last commit | `35c16ef` "feat: analysis templates, executive summary, association roles, model views" |
| Against `main` | 8 commits ahead (about 465 files, 45,000 lines added) |
| Pushed | **No.** `git push origin emad` fails inside the agent session (no GitHub credentials); the owner runs it. |
| Uncommitted | The whole **publishing and sharing** work, the test guide, this file (about 40 files). |

To commit the open work: ask the agent to commit; then run `git push origin emad` yourself.

## 3. What was built in the last session

### Committed

**Large data** (`docs/discovery/PLAN.md` §BH–§BI)
- Import and DirectQuery both work on very large tables (tested to 200 million rows), with several people at once.
- CSV and Excel uploads are read in pieces (`services/upload_stream.py`).
- Adding only new rows no longer reloads the whole table (`services/refresh_on_disk.py`).
- Data checks run on the whole table and say when a sample was used.
- "Answer once" and the memory count work across server processes (Valkey).
- Decision form: a "moves only with volume" check.

**Suggested dashboards** (`docs/discovery/PLAN.md` §BJ–§BK, `docs/templates/PLAN.md`)
- More widget types among suggestions; a button to add them all.
- Modern looks (`frontend/src/lib/dashboardLooks.ts`), gradient headline numbers and area charts.
- A from–to date control.
- With AI on, suggestions use the person's "About you" (Profile), the connection description, and the
  dataset, column and dashboard descriptions (`services/ai_context.py`). With AI off a dashboard with
  controls is still built.

**Templates** (`docs/templates/PLAN.md`)
- "Executive summary", "What goes together" (association rules with five role views).
- Ten analysis templates in a new "Analysis" group.
- Key influencers: six display options.

**Nile Express retry-4**: all guided-setup scenarios rerun and compared with retry-1
(`docs/guided-setup/RETRY_4_COMPARISON.md` and `.pdf`).

### Not committed: publishing and sharing

Full write-up: **`docs/publishing/PLAN.md`** (what existed, gaps, risks, decisions, phases, measurements, not-done list).

- **Sharing**: with a person, a role or a team (and the teams under it); end date; separate
  "may download" and "may share on" rights; optional message. Sharing on is view-only, to people only,
  never more than was held.
- **Lifecycle**: archive / restore, going back to an earlier published version, handing over to another
  owner, optional approval before publishing (an organisation switch).
- **Details**: category, tags, "readers may download" per dashboard.
- **Reader's page** `/portal` ("My dashboards"): made by me, shared with me, my team, favourites, recently
  opened, reports sent; search, filters, paging. English and Arabic.
- **Risks closed**: guest links stop when their maker loses access or the dashboard is archived; a
  schedule decides again at every run; viewing no longer implies downloading.
- **Behaviour change**: links that open without signing in are **off by default**. Turn on
  "Allow links that open without signing in" in Platform settings → Security to use them.

Key files:
- Rules: `backend/app/core/capability.py` (`report_grants`, `export_refusal`, `require_export`)
- Endpoints: `backend/app/routers/publishing.py` (`/reports/{id}/access|publication|archive|restore|owner|review/*|grants/{gid}|releases/{rid}/rollback`, `/portal/catalog|facets|favorites/{id}|deliveries`)
- Also touched: `routers/authz.py`, `reports.py`, `review.py`, `shared.py`, `workspace.py`, `services/delivery.py`, `models/models.py`, `main.py`
- Migration: `backend/alembic/versions/0068_publishing_sharing.py` (checked on PostgreSQL and SQLite)
- Screens: `frontend/src/components/report/share/ShareDashboardDialog.tsx`, `PublishingPanel.tsx`, `frontend/src/pages/Portal.tsx`, wording in `frontend/src/i18n/pages/publishing.ts`
- Tests: `backend/tests/test_publishing.py` (20), `ShareDashboardDialog.test.tsx`, `PublishingPanel.test.tsx`, `Portal.test.tsx`

Measured on the running instance (111 dashboards): `/portal/catalog` 9 ms and 12 KB against 48 ms and
941 KB for the existing `/reports` list (which is unchanged).

## 4. Last test results (2026-10-12)

| Suite | Result |
|---|---|
| Whole backend | 8,210 passed, 26 skipped (about 25 minutes) |
| Whole frontend | 4,468 passed, 369 files |
| Type check | clean |

How to run:
- Backend, some files: `docker exec -e VALKEY_URL= datalytics_backend python -m pytest tests/<file> -q -p no:cacheprovider`
- Backend, everything: run detached, ignore `tests/test_widget_roles.py` and `tests/test_ask_benchmark.py`.
  Before it, copy `docs`, `frontend/src` and `ARCHITECTURE.*` into the container at `/docs`, `/frontend/src`, `/ARCHITECTURE.*`
  (some tests read them).
- Frontend: `docker exec datalytics_frontend npx tsc --noEmit -p .` and `docker exec datalytics_frontend npx vitest run`.
- `ARCHITECTURE.md/.html` state counts that a test derives from the code (tables 100, router modules 38,
  pages 25, revisions 68, backend test modules 533, frontend test files 369). Update them when adding any of these.

## 5. Test databases added

Two real public datasets in the local Postgres (container `datalytics_db`):

| Database | Content | Main table |
|---|---|---|
| `online_retail` | UCI "Online Retail II", UK retailer, Dec 2009 – Dec 2011 | `invoice_lines` 1,067,371 rows; also `invoices`, `customers`, `products`, `countries` |
| `nyc_taxi` | NYC yellow taxi trips, January 2024 | `trips` 2,964,624 rows; also `zones`, `vendors`, `payment_types`, `rate_codes` |

Connection from the app: host `postgres`, port `5432`, user `analytics_reader` (read-only), password in
`qa/new_databases.env` (ignored by git). From the host machine: `localhost:5433`.
The connections are **not yet created in the app**.

User test steps for everything above: **`qa/NEW_FEATURES_TEST_GUIDE.md`** (not yet walked through; some
menu names in it may differ slightly from the screen).

Other databases already there: `nile_express`, `olist`, `employees`, `cars`, `egx`, `egypt_stats`, `ai_data`.

## 6. The owner's standing rules

- **Plain language first**: what it is, why, what to do; details behind "Show details".
- **Ask AI once**; ask again only when the person presses a button.
- **General-purpose platform**: no business-, region- or sample-specific logic, prompt examples or wording
  (enforced by `backend/tests/test_domain_neutral.py` and `frontend/src/test/neutralCatalogue.test.ts`).
- Works for **any database**, in **English and Arabic**.
- **AI sees only what the signed-in user may see.**
- Thresholds should be **admin settings** (pattern: a field in `core/config.Settings`, a spec in
  `services/app_settings.py`, a label and help pair in `frontend/src/i18n/pages/adminPlatform.ts`).
- **Security is server-side**: one access resolver (`core/capability.py`), no second permission system,
  404 for what a person may not know exists, 403 for what they can see but may not do.
- **Evidence only**: report tests that were run and numbers that were measured; say what was not.
- Do recommendations without asking where possible.

Working rules for the agent:
- Commit only when asked. Push only when asked (and the owner has to run it).
- Do not delete the owner's data; do not `git stash`; do not set column targets or meta on real datasets.
- Do not edit backend `.py` files while a live job or benchmark runs through the server (the reload kills it).
- Do not repeat passwords in chat; they live in `CLAUDE.md`, `qa/TEST_DATA.md` and `qa/new_databases.env`.

## 7. What is open

**Waiting for the owner**
1. Commit the publishing work, then `git push origin emad`.
2. Walk through `qa/NEW_FEATURES_TEST_GUIDE.md` on the two new databases.
3. Decide whether to delete the old scratch dashboard "Discovery check (scratch)" (report 294, dataset 255).
4. Decide whether guest links should be switched on for this instance.

**Recommended next work on publishing** (`docs/publishing/PLAN.md` §8)
1. Move the Dashboards page onto the light catalogue and filter in the database.
2. "Ask for access", and email notices for shares.
3. An approval queue page with a reviewer role.
4. A load test with many readers at once.

Also not done there: reader comments and subscriptions, a download right per format, bulk sharing, a
database rule for one share per role or team, browser tests as a non-administrator.

**Other open lists**
- Large data and discovery: the "Not done" lists in `docs/discovery/PLAN.md` §BC–§BK.
- Guided setup: open faults in `docs/guided-setup/RETRY_4_COMPARISON.md`.
- Templates: `docs/templates/PLAN.md`.
- Suggestions: `docs/suggestions/PLAN.md` §6.

## 8. A good first message for the new chat

> Read `AI_data_tool/data_analytics/docs/SESSION_HANDOFF.md` and `docs/publishing/PLAN.md`, run
> `git status`, then tell me what is uncommitted and continue with: <what you want next>.
