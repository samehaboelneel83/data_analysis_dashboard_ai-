# Datalytics — all documentation in one file

Everything the repository documents, in reading order. Each part is one
of the original files; the originals still exist and are the ones to edit.

| Part | What it covers |
|---|---|
| [Part 1: Datalytics, explained simply](#part-1-datalytics-explained-simply) | `README_SIMPLE.md` |
| [Part 2: Setup, stack and API reference](#part-2-setup-stack-and-api-reference) | `README.md` |
| [Part 3: Demo walkthrough](#part-3-demo-walkthrough) | `docs/DEMO_WALKTHROUGH.md` |
| [Part 4: The Dashboards page](#part-4-the-dashboards-page) | `docs/DASHBOARDS_PAGE.md` |
| [Part 5: The Insights page](#part-5-the-insights-page) | `docs/INSIGHTS_PAGE.md` |
| [Part 6: Offline deployment](#part-6-offline-deployment) | `docs/OFFLINE_DEPLOYMENT.md` |
| [Part 7: Backup and recovery](#part-7-backup-and-recovery) | `docs/BACKUP_AND_RECOVERY.md` |
| [Part 8: Architecture, layer by layer](#part-8-architecture-layer-by-layer) | `ARCHITECTURE.md` |


---

# Part 1: Datalytics, explained simply

*Source: `README_SIMPLE.md`*

## Datalytics, explained simply

Datalytics is a web app for looking at data without writing code. You bring
data in — a file you upload, or a database you connect — and then you can
build dashboards from it, ask it questions in plain language, and let it
find things worth noticing on its own. Everyone sees only the rows and
columns they are allowed to see; that rule is applied once, underneath
everything, so no page can leak what another page hides.

It runs as three containers: a **PostgreSQL** database, a **Python/FastAPI**
backend and a **React** frontend. `docker compose up` starts all three.
(Setup, ports and the API are in [README.md](#part-2-setup-stack-and-api-reference); the full technical
design is in [ARCHITECTURE.md](#part-8-architecture-layer-by-layer).)

---

### The idea in one picture

```
   bring data in                 work with it                    share it
 ┌────────────────┐     ┌──────────────────────────────┐    ┌────────────────┐
 │ Upload a file  │     │ Dashboards  — build charts   │    │ Share a link   │
 │  CSV/XLSX/...  │────▶│ Ask AI      — ask questions  │───▶│ Embed a page   │
 │ Connect a DB   │     │ Insights    — let it look    │    │ Export/print   │
 │  45 kinds      │     └──────────────────────────────┘    └────────────────┘
 └────────────────┘              ▲
                                 │  every page reads through the SAME security
                                 │  (row rules, column rules, roles)
```

---

### The pages, and what each one is for

| Page | What you do there |
|---|---|
| **Home** | Where you land. Recent datasets and dashboards, and a search box. |
| **Upload** | Drop in a CSV, Excel, JSON or Parquet file. It becomes a *dataset*: the columns are detected (number, category, date, text) and it is ready to use. |
| **Connections** | Connect a live database instead of uploading — PostgreSQL, MySQL, SQL Server, Oracle, Snowflake, BigQuery and about forty others. The app reads the tables and writes a short description of each one, so later features (Ask AI especially) know what the data is about. |
| **Datasets** | Every dataset you have, and inside each one: its columns, statistics, outliers, correlations, and analysis tools (key influencers, segments, statistical tests). |
| **Dashboards** | The report builder. Drag charts onto a grid, pick which columns they show, and click one chart to filter the others. 67 widget types: 32 charts, 9 maps, 11 analytics visuals, 14 controls and cards. |
| **Ask AI** | Type a question in plain language — *"how many orders per city last month?"* — and get the answer as rows, a sentence, and a chart if you ask for one. See the next section. |
| **Insights** | Pick a dataset and the app scans it for things worth a look: the biggest values, sudden changes, unusual rows, relationships between columns. Each finding is a sentence with a small chart. |
| **Lineage** | Where a dataset came from and what was built on it. |
| **Refresh & jobs · Deliveries · Activity** | Scheduled refreshes of connected data, scheduled dashboard deliveries by email, and who did what. |
| **Admin** | Users, roles, organisation units, single sign-on, API keys — and the two kinds of data security rule described below. |

---

### How "Ask AI" turns a question into an answer

This is the part people ask about most, so here is what happens when you
press *Send*.

1. **Is it a question about the data at all?** "hi", "thanks", "what can you
   do" get a short reply and nothing is queried. "Create a dataset" is told
   where that is done — the chat answers questions, it does not take actions.
2. **Is it about something already on screen?** "As a bar chart", "explain
   this", "show the rows as a table" re-use the last result — no new query.
3. **What kind of question is it?** A lookup, a total, a trend, a comparison,
   a "why". Or "what *is* this data?", which is answered from the catalog:
   every table in scope and what each one holds.
4. **Which columns should a chart use?** If you asked for a chart and it is
   not obvious, it asks you — with buttons naming the real columns — rather
   than guessing.
5. **Write the SQL, check it, run it.** The generated SQL is checked before
   it runs: only `SELECT`, only tables and columns that exist, only joins the
   catalog knows are real, and never a column you are not allowed to see. If
   it fails a check, the model gets the reason back and tries again, up to
   three times, then the app says honestly that it could not answer.
6. **Say what came back.** A sentence written from the actual rows — numbers
   stated exactly, never invented — with the rows underneath, "Show SQL", and
   export to CSV, Excel or PDF.

Two things it will never do: state a number it did not compute, and answer a
question by pretending a made-up table is your data.

---

### Security, in two sentences

**Row rules** say which rows a person may see (a regional manager sees their
region). **Column rules** say which columns (nobody in Support sees salary).
Both are set once in Admin and enforced in one place, so dashboards, Ask AI,
Insights, exports and shared links all obey them without being told.

---

### Sharing

A dashboard can be shared by link, embedded in another site, printed to PDF,
or delivered by email on a schedule. Every one of those goes through the same
security as the page itself.

---

### Where to go next

- **Try it:** [docs/DEMO_WALKTHROUGH.md](#part-3-demo-walkthrough)
- **The dashboard builder in detail:** [docs/DASHBOARDS_PAGE.md](#part-4-the-dashboards-page)
- **The Insights page in detail:** [docs/INSIGHTS_PAGE.md](#part-5-the-insights-page)
- **Running it without internet:** [docs/OFFLINE_DEPLOYMENT.md](#part-6-offline-deployment)
- **Backups:** [docs/BACKUP_AND_RECOVERY.md](#part-7-backup-and-recovery)
- **How it is built, layer by layer:** [ARCHITECTURE.md](#part-8-architecture-layer-by-layer)


---

# Part 2: Setup, stack and API reference

*Source: `README.md`*

## Datalytics v2 — Containerised Data Analytics Platform

> New here? Read [README_SIMPLE.md](#part-1-datalytics-explained-simply) first — what the app is,
> what each page does, and how a question becomes an answer, in plain words.
> This file is the setup and API reference.

Full-stack web application: upload any dataset, explore it, build multi-page
interactive reports with cross-filtering between visuals.

```
┌──────────────────────────────────────────────────┐
│                Docker Network                     │
│  ┌──────────┐   ┌────────────┐   ┌─────────────┐ │
│  │ Postgres │◄──│  FastAPI   │◄──│  React Vite │ │
│  │  :5432   │   │   :8000    │   │    :3000    │ │
│  └──────────┘   └────────────┘   └─────────────┘ │
└──────────────────────────────────────────────────┘
```

### Quick start

```bash
# 1. Copy env file
cp .env.example .env

# 2. Start all containers (first run: ~2 min)
docker compose up --build

# 3. Open the app
open http://localhost:3000
```

| Service      | URL                          |
|--------------|------------------------------|
| Frontend     | http://localhost:3000        |
| Backend API  | http://localhost:8000        |
| Swagger docs | http://localhost:8000/docs   |

---

### Features

#### Datasets
- Upload CSV · XLSX · JSON · Parquet (up to 100 MB)
- Auto-detect column types: numeric, categorical, datetime, text
- Full statistical analysis: descriptive stats, outliers, correlations, chi-square

#### Report Builder
- Multi-page reports with named, reorderable pages
- 12 widget types on a 12-column grid canvas:
  - **Charts:** Bar, Line, Pie, Donut, Scatter, Treemap
  - **Controls:** KPI Card, Table, Crosstab, List, Text, Button
- **Properties panel** per widget: dimension, measure, aggregation, sort, limit

#### Aggregations (16 options)
| Group   | Options |
|---------|---------|
| Numeric | Sum, Average, Median, Min, Max, Std Deviation, Variance, Range, P25, P75, P90, P95 |
| Count   | Count, Count Distinct, Frequency, Percentage % |

Plus **Running Sum** and **Running Average** post-aggregation metrics for bar/line/list.

#### Cross-filtering
Click any chart bar / pie slice / table row to filter all other widgets on the page.
Each widget has an **Interaction mode** (set in Properties):
- **Two-way ⇄** — emits and receives filters
- **Broadcast only →** — filters others, ignores incoming
- **Receive only ←** — reacts to others, never emits
- **Isolated —** — completely independent

Active filters shown in the **Filter Bar** with individual clear buttons.

#### Data View Hierarchy
Saved per-dataset folder tree (Dimensions / Measures / Dates / Text).
- Auto-generate from detected column types
- Add folders, rename nodes, change node type and aggregation
- Persistent in PostgreSQL

---

### Stack

| Layer    | Technology |
|----------|-----------|
| Database | PostgreSQL 16 Alpine |
| Backend  | Python 3.12 · FastAPI · SQLAlchemy async · asyncpg |
| Analysis | pandas · numpy · scipy |
| Frontend | React 18 · TypeScript · Vite · Recharts |
| Infra    | Docker · Docker Compose |

---

### Project structure

```
datalytics/
├── docker-compose.yml
├── .env.example
├── postgres/
│   └── init.sql              schema + indexes
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py           FastAPI app + CORS + lifespan
│       ├── core/
│       │   ├── config.py     env-var settings
│       │   └── database.py   async SQLAlchemy engine
│       ├── models/models.py  ORM models
│       ├── schemas/schemas.py Pydantic I/O models
│       ├── services/
│       │   ├── analytics.py  type detection + stats engine
│       │   └── widget_data.py aggregation query engine
│       └── routers/
│           ├── datasets.py   upload / CRUD
│           ├── analysis.py   run analysis
│           ├── reports.py    reports / pages / widgets
│           ├── hierarchy.py  data view tree
│           └── widget_data.py live widget queries
└── frontend/
    ├── Dockerfile
    ├── src/
    │   ├── types/report.ts   shared TypeScript types
    │   ├── services/api.ts   Axios API client
    │   ├── components/
    │   │   ├── Layout.tsx
    │   │   └── report/
    │   │       ├── CrossFilterContext.tsx  page-level filter state
    │   │       ├── FilterBar.tsx           active filter pills
    │   │       ├── WidgetRenderer.tsx      all chart/control renders
    │   │       ├── WidgetConfigPanel.tsx   properties panel
    │   │       ├── InteractionSettings.tsx  broadcast/receive config
    │   │       └── HierarchyTree.tsx       data view tree UI
    │   └── pages/
    │       ├── Dashboard.tsx   dataset list
    │       ├── Upload.tsx      drag-and-drop upload
    │       ├── DatasetDetail.tsx analysis viewer
    │       ├── Reports.tsx     report list
    │       └── ReportBuilder.tsx designer
```

---

### API reference

#### Datasets
```
GET    /api/v1/datasets
POST   /api/v1/datasets            multipart: file, name, description
GET    /api/v1/datasets/{id}
DELETE /api/v1/datasets/{id}
```

#### Analysis
```
POST   /api/v1/datasets/{id}/analysis   body: { analysis_type: "full|numeric|categorical|datetime" }
GET    /api/v1/datasets/{id}/analysis
```

#### Widget data (live query)
```
POST   /api/v1/datasets/{id}/widget-data
body: { config: { dimension, measure, aggregation, filters, limit, sort, sort_by, running } }
```

#### Reports
```
GET/POST        /api/v1/reports
GET/PATCH/DELETE /api/v1/reports/{id}
POST/PATCH/DELETE /api/v1/reports/{id}/pages/{pid}
POST/PATCH/DELETE /api/v1/reports/{id}/pages/{pid}/widgets/{wid}
```

#### Hierarchy
```
GET/POST        /api/v1/datasets/{id}/hierarchy
PATCH/DELETE    /api/v1/datasets/{id}/hierarchy/{node_id}
POST            /api/v1/datasets/{id}/hierarchy/auto-generate
```

---

### Development (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://... uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### Reset everything
```bash
docker compose down -v   # drops the postgres volume
docker compose up --build
```


---

# Part 3: Demo walkthrough

*Source: `docs/DEMO_WALKTHROUGH.md`*

## Demo walkthrough

Four use cases, each a question somebody actually asks. Every step is a click
path with the insight it produces — so a demo can be *driven* rather than
narrated.

> **Where to find it.** The app runs on **http://localhost:3001** (docker compose;
> a local `npm run dev` serves it on 3000). There is no second “service” to
> publish to —
> reports already live server-side, so building, sharing and viewing all happen at
> the same address. The API and its Swagger docs are on **:8000**.
>
> **Load the demo first.** In the app: **Settings → Load demo content**, or
> `POST /api/v1/demo/seed`. It is idempotent — running it twice leaves one copy —
> and `DELETE /api/v1/demo/seed` removes every trace, including the two demo
> logins created below.
>
> **From nothing, in one command.** `.\scripts\demo_up.ps1` brings the stack up,
> waits on `/health/ready` (not on a clock — the probe reports 503 until Alembic
> has finished), creates the first admin, seeds, and prints every login. That
> bootstrap step is not a convenience: startup creates an Organization and an
> Admin role but **no User**, and there is no signup endpoint, so a freshly
> composed stack has nobody who can sign in. `.\scripts\demo_down.ps1` unseeds;
> add `-Stack` to stop the containers too.

Seeding creates eight reports: six (**Demo — …**, including the UX showcase)
exercise all 57 widget types, and two (**Use case — …**) carry the narratives
here.

Use cases 3 and 4 do not add reports of their own — "who can see this?" and
"what needs attention?" are questions *about* a report, and answering them on one
somebody has already read is clearer than inventing two more dashboards.

---

### 0 · The workspace menu

Seeding files every demo report into two folders, so the left-hand tree has a
shape rather than a flat "Unfiled" list.

| Step | Do this | What it shows |
|------|---------|---------------|
| 1 | Expand the nav rail (⟨ / ⟩) | The **Workspace** tree appears under Reports. It renders only when the rail is open — a tree in a 56px icon column is not legible |
| 2 | Open **Use cases** and **Widget gallery** | Folders and reports share one ordering, so an author can put an important report above a folder |
| 3 | Click the ▸ beside a report | Its **pages** appear. They are joined in at read time, never stored — so a page added in the builder shows up here with no second write |
| 4 | Click a page name | Opens the report at that page. The caret expands, the label opens: one control each, because a row that did both could never do the other |
| 5 | **+** beside Workspace | A new folder |
| 6 | Drag a report onto a folder | It moves. Drop it on the **Workspace** header to send it back to the top level — otherwise anything filed could never come out |
| 7 | Try dragging a folder into its own child | Refused. A cycle in the navigation menu would hang the tree for everyone in the org |
| 8 | Delete a folder | The prompt says *“anything inside it moves up a level — no reports are deleted”*, and that is exactly what the server does. You can change or remove **what you created**; an org admin can manage anything, so departed colleagues’ folders are never stranded |

#### Your workspaces, and the ones you were given

Roots are grouped under **MY WORKSPACES** and **SHARED WITH ME** once a user has
some of each — the headings are suppressed entirely when everything falls into
one group, so an admin who owns nothing is not told the whole org's tree was
"shared" with them. The grouping keys on *ownership*, not on whether you may
edit it: an admin can manage every folder in the org, so "can I change this?"
cannot answer "is this mine?".

#### Seeing two different menus

The seeder restricts **Use cases** to the EMEA analyst's role and leaves
**Widget gallery** open to everyone, so the two demo logins get *different
menus*. That is the whole feature in one gesture, and the reason both halves are
seeded: a demo where every folder were locked would show the mechanism and hide
the default.

| Step | Do this | What it shows |
|------|---------|---------------|
| 9  | Sign in as `demo-global@example.invalid` | **Widget gallery** only. **Use cases** is not there — not greyed out, not empty: absent |
| 10 | Sign in as `demo-emea@example.invalid` | Both folders. The grant is what puts **Use cases** back |
| 11 | As an admin, click 🔓 on a folder | Pick roles. 🔒 means restricted; 🔓 means everyone in the org can see it — **no grants means visible**, because the opposite default would empty every non-admin menu the day it shipped |
| 12 | Restrict a folder you made, then view it as the other login | Gone from theirs, still in yours. A creator never loses sight of their own folder, and neither does an admin — an admin locked out could not administer the lock |

> **This hides menu entries; it does not prevent access.** `GET /reports/{id}`
> still returns a report to any member of the org who knows its id. Report
> *access* is `ReportCapability`; row and column access are the RLS rules
> demonstrated in use case 3. `TestVisibilityIsNotAccessControl` asserts this on
> purpose, so that quietly turning the menu into an ACL breaks a test instead of
> making this paragraph wrong.

**The point:** the tree is navigation, not tagging. A report with no folder still
appears under **Unfiled**, so nothing can exist without a way to open it.

---

### Demo logins

Two accounts exist so row-level security can be *shown* rather than described.

| Login | Password | Sees |
|-------|----------|------|
| `demo-emea@example.invalid` | `demo-password` | Europe rows only, no `cost` column |
| `demo-global@example.invalid` | `demo-password` | Everything |

Not secrets: they exist only inside the demo org, see only demo data, and are
deleted on unseed. A login nobody can use demonstrates nothing.

---

### 1 · "Which regions are underperforming, and why?"

**Report:** Use case — Regional performance review

| Step | Do this | What it shows |
|------|---------|---------------|
| 1 | Read the KPI row | Revenue against target, and margin on the gauge |
| 2 | Click **Europe** in the Region slicer | Every tile re-filters. This is cross-filtering — no query written, no page reload |
| 3 | Look at *Margin % by region* | The margin is a **post-aggregation measure**, `(SUM(revenue) - SUM(cost)) / SUM(revenue)`. It is *not* an average of a margin column, because a region's margin is not the mean of its products' margins. This is the calculation most tools get wrong |
| 4 | Open **Report settings → Parameters**, change *Target margin %* from 30 to 40 | The variance colouring moves with it. What-if analysis without editing the report |
| 5 | Right-click a bar → **Drill down** | Region → country. The hierarchy is authored per dataset, not per chart |
| 6 | **Share → Create link** | A share link. The recipient needs no account and sees only this report |

**The point:** one question, answered without leaving the page — and the margin
figure is right for a reason someone can explain.

---

### 2 · "Can I trust this data?"

**Report:** Use case — Can I trust this data?

| Step | Do this | What it shows |
|------|---------|---------------|
| 1 | Compare *Revenue by category — as loaded* with *— prepared* | Same measure, different totals |
| 2 | Open the prepared tile's **Prep pipeline** | One step: drop rows with no cost. Rows without cost have no margin, and averaging over them understates every category |
| 3 | Open the *Rows the prep steps changed* table | A **calculated column**, `unit_margin`, computed at query time — the source file is never modified |
| 4 | Open **Model view** | A **relationship** joins sales to routes on country. Multi-dataset modelling, not a single flat table |
| 5 | Check the histogram and box plot | Distribution and spread, so "trust" is a judgement someone can make rather than a claim |

**The point:** the cleaned number is shown *next to* the raw one. A data-quality
story that only shows the cleaned figure is asking to be taken on faith.

---

### 3 · "Who is allowed to see what?"

**Report:** Use case — Regional performance review (same report, different eyes)

| Step | Do this | What it shows |
|------|---------|---------------|
| 1 | Sign in as `demo-global@example.invalid` | All regions, `cost` column present |
| 2 | Sign out, sign in as `demo-emea@example.invalid` | **Same report.** Europe rows only, and `cost` is *gone* — not blanked |
| 3 | Ask the agent "what were total sales?" *(needs `llm_enabled`)* | The answer respects the same rules. Generated SQL inherits RLS — the agent cannot be used to route around it |
| 4 | As an admin, open **Admin → Row security** | The rule is one expression, `region == 'Europe'`, on the role rather than the user |
| 5 | Open **Share → Embed** | An embed config, origins restricted to `localhost`. No per-viewer licence |

**The point:** column denial removes columns from the projection rather than
masking them, and RLS is applied during query construction — so there is no
path, including the AI, that returns a row the viewer may not see.

---

### 4 · "What needs attention right now?"

**Report:** Use case — Regional performance review → monitoring

| Step | Do this | What it shows |
|------|---------|---------------|
| 1 | Open **Schedules** | A weekly delivery, with recipients and a subject line |
| 2 | Open **Alerts** | `AVG(margin_pct) < 25` — a condition watched without anyone opening the report |
| 3 | Note both are **paused** | Deliberate. See below |

> **Both are seeded with `interval_minutes = 0`, which is never due.**
> `refresh_scheduler` runs anything that comes due, and neither model has an
> enabled flag, so 0 is the only inert spelling. A demo that mailed the address
> it invented would be an incident, not a rough edge. Set a real interval to see
> them fire.

---

### Actions worth showing that no seeder can create

These are runtime behaviour — the demo data sets them up, but somebody has to click.

| Action | Where | Note |
|--------|-------|------|
| Cross-filtering | Any chart on any report | Each widget has an interaction mode: two-way, broadcast, receive, isolated |
| Drill-down | Sales reports | Region → country, from the authored hierarchy |
| Bookmarks | Demo — Sales Overview | Saves filter state, not a screenshot |
| Sync slicers | Use case 1 | The Region slicer is set to apply across pages |
| Agent questions | Any dataset | Requires `llm_enabled` and a reachable model endpoint. Air-gapped installs without a model skip this |
| Export | Any report | PDF server-side, PowerPoint client-side |
| Multi-file upload | Data → Upload | Pick several files at once. With more than one, choose **separate datasets** or **append into one** |
| Access import | Data → Upload, or a connection | An `.mdb`/`.accdb` becomes one dataset per table |

---

### Uploading several files, and Microsoft Access

| Step | Do this | What it shows |
|------|---------|---------------|
| 1 | **Data → Upload**, select three CSVs | One dataset per file, each named after its own file so they are told apart in the list |
| 2 | Select them again and choose **A single dataset** | One dataset, rows appended. Columns are the *union*: a file missing a column contributes nulls for its rows, rather than the upload being refused |
| 3 | Include one unreadable file in a batch | The good files still land. The page lists which file failed and why, and deliberately does **not** navigate away — leaving would take the only record of the failure with it |
| 4 | Upload an `.mdb` or `.accdb` | One dataset per user table. Access's own `MSys*` catalogue tables are skipped, and the uploaded database is not kept: every table is already its own CSV |
| 5 | Add a **Microsoft Access** connection with a server-side path | Browse its tables and import one, the same as any other source |

> **What "any Access version" actually covers.** `.mdb` (Access 97–2003) and
> `.accdb` (2007–365), read through mdbtools, which the backend image bundles.
> **Encrypted or password-protected files cannot be read** — no open-source tool
> decrypts them, so the app says so and asks for an unencrypted copy rather than
> failing vaguely. Access is read-only and import-only: there is no DirectQuery
> and no custom SQL, because mdbtools has no query engine to push one into.

---

### Cleaning up

`DELETE /api/v1/demo/seed` removes everything — datasets, reports, both logins,
the share link, the embed config, the schedule and the alert.

Teardown deletes the grants **before** the identities that own them. Those tables
cascade from `users.id`, so deleting users first works on PostgreSQL and silently
orphans on SQLite. For a live share token that is not a detail worth leaving to
the database's configuration.


---

# Part 4: The Dashboards page

*Source: `docs/DASHBOARDS_PAGE.md`*

## The Dashboards page

**Route** `/reports` (and the alias `/dashboards`) · **Source** `frontend/src/pages/Reports.tsx` · **Tests** `frontend/src/pages/Reports.test.tsx`

Every statement here is read from the code. Where a rule is enforced server-side, the endpoint is named — the page only ever *mirrors* a permission, it never decides one.

---

### 1. What this page is for

The inventory of dashboards you can open. It answers three questions and nothing else: **what exists**, **what am I allowed to do with it**, and **how do I make another one**. Designing a dashboard happens on `/reports/:id`; this page only lists, creates, shares, publishes and deletes.

---

### 2. Page header

| Element | Behaviour |
|---|---|
| **Dashboards** | `t('nav.dashboards')` |
| Subtitle | "Design multi-page interactive dashboards — drafts stay private until you publish or share them" (`t('dashboards.subtitle')`). It states the privacy default, which is the single most misunderstood thing on the page. |
| **Search dashboards** | `useListFilter` over each report's **name and description**. Client-side — the list endpoint takes no `limit`/`offset`. **It only appears once there are 8 or more dashboards**; below that the box is chrome competing with the list it filters. |
| **+ New dashboard** | Opens the inline create form below the header. Always available to any member. |

---

### 3. Creating a dashboard

`+ New dashboard` reveals a card with three fields:

- **Dashboard name*** — the only required field; **Create & Open** stays disabled until it is non-empty.
- **Description (optional)** — shown on the card afterwards.
- **Dataset** — a `<select>` of every dataset you can read, defaulting to **"— No dataset (add later) —"**. A dashboard with no dataset is legal; its widgets pick one later.

On success: `POST /reports`, a toast, the form closes, and the new dashboard is **prepended** to the grid so it appears where you are already looking. It does **not** navigate you into the designer — you stay on the list.

---

### 4. The three states, which are three different claims

These are deliberately distinct and must never be collapsed into one another.

| State | What renders | What it means |
|---|---|---|
| **Loading** | "Loading…" | The request is in flight. |
| **Error** | `LoadError` block with **Try again** | The request failed. |
| **Empty** | Card with a chart icon, "No dashboards yet", and **Create your first dashboard** | The request succeeded and you genuinely have none. |

The error state exists because of a specific bug: without the `.catch`, a server error cleared `loading` and fell through to "No dashboards yet" — telling someone with fifty dashboards that they had none, and inviting them to rebuild work that already existed.

**No matches** is a fourth, separate message ("Nothing matches …"). A search that finds nothing is not the same claim as owning nothing, so it never borrows the empty state's copy.

---

### 5. Grouping — My workspaces / Granted to me

The grid splits on **authorship**, not permission:

- **My workspaces** — `is_mine === true`
- **Granted to me** — everything else, under the line *"Published or shared with you by others. View-only dashboards open without design controls."*

**Both headings appear only when both groups are non-empty.** If you authored everything, you get a plain unlabelled grid — a lone "My workspaces" heading over your entire list says nothing. Same contract as the workspace tree in the rail.

Why authorship and not permission: an org admin can administer *every* dashboard in the organisation, so grouping on capability would file the whole company under "mine".

---

### 6. The card, element by element

```
┌─────────────────────────────────────────────┐
│ Dashboard name          [view only] [PUBLISHED] │  ← title + status
│                         ⧉  📣  🗑  ⋯            │  ← controls
│ Description                                  │
│                                              │
│ [dataset chip]                      date     │  ← footer
│ ┌──────────────────────────────────────────┐ │
│ │           Open designer →                │ │
│ └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

| Element | Source | Notes |
|---|---|---|
| **Name** | `r.name` | A link to `/reports/:id`. |
| **Description** | `r.description` | Omitted entirely when absent. Dashboards built by *Suggest dashboards* carry "Suggested from the data" here — that is a description, not a special badge. |
| **view only** chip | `my_capability === 'view'` | You can open it but not design it. |
| **PUBLISHED** chip | `created_by != null && published` | Everyone in the organisation can open it, view-only. |
| **Dataset chip** | `datasets.find(d => d.id === r.dataset_id)` | Falls back to the words **"No dataset"** when the dashboard has none, or when its dataset is not one you can read. |
| **Date** | `r.created_at`, locale-formatted | This is the **created** date, not last-modified. |
| **Open designer →** | link to `/reports/:id` | Reads **"Open →"** instead when you cannot edit — a "designer" link onto a dashboard whose every edit the server refuses is a dead control with extra steps. |

---

### 7. The four controls, and who sees each

Three different flags gate them. They are not interchangeable.

```
canEdit        = (my_capability ?? 'view') !== 'view'
owned          = created_by != null
canAdminister  = owned && (is_mine || viewer is an org admin)
```

| Control | Shown when | Does |
|---|---|---|
| **Share** ⧉ | `canAdminister` | Opens the share dialog (§8). |
| **Publish / Unpublish** 📣 | `canAdminister` | `POST /reports/{id}/publish`. Toggles org-wide view-only access. |
| **Delete** 🗑 | `canEdit` | Confirms, then `DELETE /reports/{id}`. |
| **⋯ menu** | `canEdit` | Holds one item: **Delete dashboard**. |

Two things worth understanding:

**`owned` excludes legacy rows.** A dashboard created before authorship existed has `created_by === null`. The publish-and-grant regime does not apply to it at all, so Publish and Share are absent — offering them would be a button the server answers 400 to.

**`canEdit` and `canAdminister` are different questions.** Someone granted `edit` on *your* dashboard can delete it but cannot publish or share it: administering the audience stays with the author (and admins). Conversely an admin can administer a dashboard they cannot… well, they can edit everything, but the distinction is real for granted non-admin editors.

Every one of these mirrors a server rule. The page hides what the server refuses; it never grants anything by showing a button.

---

### 8. Publish vs Share — the distinction the page exists to make clear

These are two different mechanisms and the subtitle, the dialog copy and the toasts all repeat the difference on purpose.

| | **Publish** | **Share** |
|---|---|---|
| Audience | Everyone in the organisation | One named person, by email |
| Strength | View-only, always | `view`, `edit`, or `edit + data` |
| Reaches a draft? | No — publishing *is* what stops it being a draft | **Yes** — a grant opens a private draft to that person |
| Reversible | Yes, Unpublish returns it to a private draft | Yes, Remove drops the grant |
| Endpoint | `POST /reports/{id}/publish` | `POST` / `DELETE /reports/{id}/grants` |

**Grants are the only way another user gets design rights on a dashboard.** Publishing can never give edit access, no matter the audience.

---

### 9. The Share dialog

Opened by ⧉. Titled *Share "<name>"*, with the standing explanation: *"Sharing gives one person access — including to a draft. Publishing (separate) makes it view-only for the whole organisation."*

- **Email field** — by email, deliberately, never a picker of everyone in the organisation. A share dialog that lists every colleague is also a directory listing, and this product does not publish one.
- **Level** — `Can view` / `Can edit` / `Can edit + data`. The `<option value>`s are `view` / `edit` / `data` and are an API contract; the labels are free text.
- **Enter** in the email field submits.
- Below, the current grants, each with **Remove**. Three states of its own: `Loading…`, "Not shared with anyone yet.", or the list.
- Re-sharing with someone who already has a grant **replaces** their level rather than adding a second row.

It is a real modal: focus trap, Escape to close, focus restored on exit, via the shared `useModalDialog` hook that every overlay in the app uses.

---

### 10. What this page deliberately does not do

- **No pagination.** The grid renders every dashboard you can see. (The Datasets page pages at 8; this one does not.)
- **No sort control.** Order comes from the server.
- **No export or download.** Nothing here produces a file.
- **No navigation after create.** You stay on the list and choose when to open.
- **No last-modified date.** The footer date is creation.

---

### 11. Where the behaviour actually lives

| Concern | File |
|---|---|
| The page | `frontend/src/pages/Reports.tsx` |
| Search box | `frontend/src/components/ui/ListFilter.tsx` |
| Confirm dialog | `frontend/src/components/ui/ConfirmDialog.tsx` |
| Overflow menu | `frontend/src/components/ActionMenu.tsx` |
| Error block | `frontend/src/components/ui/LoadError.tsx` |
| Modal focus trap | `frontend/src/components/ui/useModalDialog.ts` |
| List, create, delete, publish, grants | `backend/app/routers/reports.py` |
| Who may do what | `backend/app/core/capability.py` |

---

### 12. Known quirks, recorded rather than hidden

**Delete appears twice on every editable card** — once as the red trash button and once as the only item in the ⋯ menu. This is intentional and pinned by a test (*"the ⋯ menu delete item fires the same handler as the icon button"*), but it does mean the overflow menu currently holds nothing the row does not already show. If the menu gains a second action the redundancy resolves itself; if it does not, one of the two is removable.

**The search box hides below 8 dashboards.** Someone with 7 dashboards and a colleague with 9 see different chrome. That is `useListFilter`'s deliberate threshold, not a bug, but it surprises people comparing screens.

**The dataset chip silently reads "No dataset" in two different situations** — the dashboard genuinely has none, *or* it points at a dataset this viewer cannot read. The card cannot tell the two apart because the lookup is a local `find` over the datasets you can see.

**The date is creation, not modification.** A dashboard edited this morning can show a date from March.


---

# Part 5: The Insights page

*Source: `docs/INSIGHTS_PAGE.md`*

## The Insights page

**Route** `/insights` · **Source** `frontend/src/pages/InsightsHub.tsx` (246 lines) · **Tests** `frontend/src/pages/InsightsHub.test.tsx` (14)

Every statement here is read from the code. Where a rule is enforced server-side the endpoint is named — this page mirrors refusals, it never decides them.

---

### 1. What this page is for, and what it deliberately is not

Every analysis capability in the platform is **dataset-scoped**, so each one correctly lives as a section or tab of `/datasets/:id`. The cost of that was invisibility: you had to already know which dataset page to open and how far to scroll before you could find, say, key influencers.

This page is the front door to that family. Its job is **navigation**:

> pick a dataset → pick a question → land on the section that already implements it.

It re-implements **nothing** — with exactly one exception, the Top insights preview (§4), which it renders itself so that "is there anything here worth looking at?" can be answered without a click.

---

### 2. Header and dataset picker

| Element | Behaviour |
|---|---|
| **Insights** | `t('nav.insights')` |
| Subtitle | "Pick a dataset, then ask it a question. Every capability here runs on the same secured data your widgets read." (`t('insights.subtitle')`) — it states the governance guarantee, because a page offering six kinds of analysis is exactly where someone wonders whether the numbers obey their row rules. They do. |
| **Dataset** `<select>` | `id="insights-hub-dataset"`, properly labelled. Each option is the dataset name, plus **` · live`** for a DirectQuery one — so you can see *before* choosing why half the cards are about to grey out. |
| **Search datasets…** | `useListFilter` over the dataset **name** only. Client-side, and it appears only once you have **8 or more** datasets. |

**The default selection is the most recently *created* dataset, not the first one the API returned.** There is no "last opened" signal anywhere in the product (Home's Recents falls back the same way for the same reason), and someone landing here almost always wants the dataset they were just working with rather than dataset #1. The code says so explicitly rather than leaving it to look like an accident.

**A search that matches nothing does not empty the dropdown.** The options fall back to the full list (`noMatches ? datasets : filtered`), so a typo can never strand you with a picker you cannot pick from.

---

### 3. The three states

| State | What renders |
|---|---|
| **Loading** | `LoadingState` |
| **Error** | `LoadError` with a working **Try again** that re-runs the load and clears the error |
| **Empty** | `EmptyState` — "No datasets yet — upload one or connect a database first." |

These are three different claims and never borrow each other's copy. The page's whole content is the dataset list, so a failed load gets a persistent, retryable banner rather than a message that would sit there with no way out.

---

### 4. Top insights — the one thing this page computes

The panel between the picker and the cards. It fires **automatically** the moment a dataset is selected, whether by the default or by you.

```
TOP INSIGHTS                                   View full scan →
<one-paragraph narrative>
  • <finding title> — <detail>
      <inline chart>
  • …up to three
```

- **Source** — `insightsApi.runShared(datasetId)` → `POST /datasets/{id}/insights`.
- **Top three only.** The backend already returns findings sorted by score, so the page slices rather than ranks.
- **View full scan →** goes to `/datasets/:id#insights`, the section that owns the complete result.
- **It has its own three states**, independent of the page's: a "Scanning for insights…" loader, a retryable `LoadError`, and *nothing at all* when the scan finds nothing worth surfacing — no empty panel announcing that it has no news.

#### Why `runShared` and not `run`

`runShared` de-duplicates concurrent scans of the same dataset: N callers in flight share **one** request. That matters here because clicking through to `/datasets/:id#insights` fires the identical scan moments later, and because every Dynamic Pin card on a dashboard evaluates through the same helper — five cards over one dataset cost one scan, not five.

#### The inline charts

`FindingChart` draws each finding the same way the Insights pane's "+ Chart it" button would:

| Finding's columns | Chart |
|---|---|
| one categorical + one numeric | bar, summed by category |
| exactly one numeric | histogram, 20 bins |
| anything else (e.g. a correlation between two measures) | **no chart** — text only |

A correlation has no bar or histogram shape worth a thumbnail, so it stays a sentence rather than being forced into a picture.

---

### 5. The six capability cards

Each card is a link to the section that implements it. The **suffix is a cross-file contract** with `DatasetDetail.tsx` — change an anchor there and the card lands on nothing.

| Card | Goes to | Needs imported data |
|---|---|---|
| **Insight scan** | `/datasets/:id#insights` | **yes** |
| **Anomalies** | `/datasets/:id#anomalies` | **yes** |
| **Key influencers** | `/datasets/:id#influencers` | no |
| **Patterns** | `/datasets/:id#associations` | no |
| **Segments** | `/datasets/:id#segment` | **yes** |
| **Statistical tests** | `/datasets/:id?tab=statistics` | no |

Two things worth knowing about that last row: it is a **query parameter, not an anchor**, and the value is `statistics` while the tab is labelled "Analysis" — a bookmark-compatibility contract, not a typo.

---

### 6. DirectQuery: disabled, not hidden

For a DirectQuery dataset the three `importOnly` cards render as `<div aria-disabled="true">`, dimmed, with the line:

> *Needs imported data — this dataset is DirectQuery.*

This is the deliberate part. The alternatives were both worse:

- **Hide them** — the capability appears to not exist, and the reader never learns why.
- **Link them anyway** — the card navigates to a section that will not be on the page when it loads. Offering a control that silently does nothing is a real defect, and this codebase has shipped that bug before.

The gate mirrors the server exactly. `POST /datasets/{id}/insights` refuses at `backend/app/routers/datasets.py:1327`:

```python
if not ds.filename or ds.mode == "directquery":
    raise HTTPException(400, "Insights run over import-mode datasets")
```

The Top insights preview is skipped for the same reason — no request is made, so there is no error banner for a refusal the page already knew about.

---

### 7. The Ask AI line

> Prefer plain language? **Ask AI** answers questions about this data directly.

Links to `/ask?dataset=:id` with the current dataset pre-selected (or bare `/ask` if none is). It is the escape hatch from "pick a capability" to "just ask" — the same secured frame, a different interface to it.

---

### 8. Where the behaviour actually lives

| Concern | File |
|---|---|
| The page | `frontend/src/pages/InsightsHub.tsx` |
| Inline finding charts | `frontend/src/components/insights/FindingChart.tsx`, `MiniBarChart.tsx` |
| Scan de-duplication | `insightsApi.runShared` in `frontend/src/services/api.ts` |
| Search box | `frontend/src/components/ui/ListFilter.tsx` |
| The three state components | `frontend/src/components/ui/{LoadingState,LoadError,EmptyState}.tsx` |
| The scan endpoint and its DirectQuery refusal | `backend/app/routers/datasets.py` |
| The engine behind it | `backend/app/services/insights.py` |
| The sections every card links into | `frontend/src/pages/DatasetDetail.tsx` |

---

### 9. Known quirks, recorded rather than hidden

**The anchors are a contract nothing enforces.** `#insights`, `#anomalies`, `#influencers`, `#associations`, `#segment` and `?tab=statistics` must match `DatasetDetail.tsx`. Renaming a section there leaves the card pointing at a fragment that does not exist, and the failure is silent — the page loads, scrolled to the top, with no error.

**"Anomalies" is import-only by inference, not by its own endpoint.** The comment in `CAPABILITIES` reasons that `/outlier-details` refuses DirectQuery identically to `/insights` and `/segment`. That is correct today; it is a conclusion about a sibling endpoint rather than a gate read from that endpoint.

**The search filters the picker, not the page.** Unlike every other `useListFilter` surface, the result here narrows a `<select>` rather than a list of cards — and, as above, a no-match silently restores the full list rather than showing a "nothing matches" message.

**The page has no `noMatches` message at all,** for the same reason: there is no list to empty.

**The default dataset can surprise.** "Most recently created" is not "most recently used". Upload a throwaway CSV and it becomes the hub's default until something newer arrives.


---

# Part 6: Offline deployment

*Source: `docs/OFFLINE_DEPLOYMENT.md`*

## Offline Deployment (Isolated Network, No Internet)

Production for this platform runs in an isolated network with **no internet
access at runtime**. Every dependency that needs the internet must be
resolved on a build machine that DOES have internet, packaged, and carried
across the air gap. Nothing in the running stack may fetch from a public
host — no CDN assets, no font CDNs, no `pip`/`npm` installs, no telemetry to
a public endpoint.

This document is the full story: build outside, transfer, load, bring the
stack up, what to expect on first boot, and what stays disabled unless you
point it at an internal endpoint.

### 1. What used to reach the internet (and no longer does)

An audit of the codebase found exactly one runtime internet dependency: the
frontend imported its three type faces (Syne, Manrope, JetBrains Mono) from
`fonts.googleapis.com` (`frontend/src/styles/mcait/fonts.css`). That import
has been replaced with local `@font-face` rules pointing at woff2 files
vendored into `frontend/src/assets/fonts/`; Vite fingerprints and bundles
them into `dist/assets/` at build time like any other static asset. There is
now no `fonts.googleapis` (or `fonts.gstatic`, `cdn.`, `unpkg`, `jsdelivr`,
`cdnjs`) string anywhere in `frontend/src/**`, `frontend/index.html`, or a
production `dist/` build — a regression test
(`frontend/src/offlineAssets.test.ts`) pins this so it can't regress
silently.

None of these three faces have Arabic glyphs. Arabic text already falls
through to the system fallback stack (`ui-sans-serif, system-ui,
-apple-system, "Segoe UI", sans-serif` — see `--font-sans` /
`--sans` in `frontend/src/styles/mcait/typography.css` and
`frontend/src/index.css`), which is unchanged by this work and resolves to
whatever Arabic-capable font the host OS provides. No regression there.

Everything else that talks to a service (the LLM endpoint, the optional
embeddings backend, the optional OpenTelemetry collector) already points at
an internal host by configuration — see §5.

### 2. Build outside the isolated network

On a machine WITH internet (this is where `pip install`, `npm install`, and
base-image pulls happen):

```powershell
# from the repo root
docker compose build backend frontend
docker pull postgres:16-alpine
# (once Task O2 lands: docker pull valkey/valkey:8-alpine — no changes
#  needed here, the bundle script reads it from docker-compose.yml)

# package everything into offline_bundle/
powershell -File .\scripts\build_offline_bundle.ps1
```

`scripts/build_offline_bundle.ps1` (PowerShell 5.1 compatible):

1. Regex-reads every `image:` line out of `docker-compose.yml` (today:
   `postgres:16-alpine`; will automatically pick up `valkey/valkey:8-alpine`
   once O2 adds it — no script edit needed).
2. Runs `docker compose build backend frontend` (skippable with
   `-SkipBuild` if the images already exist locally).
3. `docker pull`s the image-only services, then `docker save`s every image
   (pulled + built) to `offline_bundle/<name>.tar`.
4. Writes `offline_bundle/MANIFEST.json`: image names, image IDs, digests
   (via `docker inspect`), the git commit the bundle was built from, and the
   build timestamp.
5. Prints the transfer/load instructions reproduced in §3 below.

Flags: `-DryRun` prints what would be built/saved without touching Docker
(fast structure check); `-SkipBuild` saves already-built local images
without rebuilding.

Sizes, two honest kinds -- the O1 bundle run MEASURED these docker-save tars
(pre-tier-5 backend): postgres 111.3 MB, backend 303.4 MB, frontend 152.1 MB.
Tier 5's ML deps (scikit-learn, statsforecast, and its numba/llvmlite chain,
baked in at build time per the air-gap constraint) grow the BACKEND tar to an
ESTIMATED ~600-900 MB -- re-run `scripts/build_offline_bundle.ps1` to measure
your actual bundle; the other images are untouched by tier 5:

| image                     | save tar size                          |
|---------------------------|----------------------------------------|
| `postgres:16-alpine`      | 111.3 MB (measured, O1 run)            |
| `valkey/valkey:8-alpine`  | ~60 MB (estimated)                     |
| `data_analytics-backend`  | ~600-900 MB (estimated post-tier-5)    |
| `data_analytics-frontend` | 152.1 MB (measured, O1 run)            |

The backend image is ~1.4-1.8 GB uncompressed (numba/llvmlite's LLVM payload
is most of the growth over pre-tier-5); `docker save`'s tar comes out at
roughly half that. These are approximate and will drift with base-image and
dependency updates -- `offline_bundle/MANIFEST.json` records the exact image
digests for whatever bundle you actually built, and that file (not this
table) is the source of truth to verify a transferred bundle against. (The
frontend image here runs the Vite dev server per `frontend/Dockerfile` — see
§4 for the alternative of shipping the built `dist/` instead.)

### 3. Transfer and load, inside the isolated network

1. Copy the entire `offline_bundle/` directory (all `*.tar` files +
   `MANIFEST.json`) plus a checkout of this repository across the air gap
   (USB drive, secure file transfer — whatever your environment's approved
   mechanism is).
2. On the target host, for each `*.tar`:
   ```powershell
   docker load -i offline_bundle\postgres_16-alpine.tar
   docker load -i offline_bundle\data_analytics-backend.tar
   docker load -i offline_bundle\data_analytics-frontend.tar
   ```
3. Confirm the loaded images match `MANIFEST.json` (`docker images`,
   compare digests).
4. Create a `.env` (see `docker-compose.yml` for the variables it reads —
   `POSTGRES_*`, `SECRET_KEY`, `ALLOWED_ORIGINS`, `VITE_API_URL`, etc.) with
   values appropriate to the isolated network (internal hostnames, not
   `localhost`, if the frontend/backend are reached from other machines).
5. Bring the stack up:
   ```powershell
   docker compose up -d
   ```
   Compose uses the already-loaded local images/tags; nothing is pulled.

### 4. Frontend serving: dev server vs production build

`frontend/Dockerfile` is multi-stage, and compose defines **two** frontend
services. Which one you run is the difference between a development box and
a deployment:

| Service | Stage | Command | Port | Use |
|---|---|---|---|---|
| `frontend` | `dev` | `npm run dev` (HMR, source bind-mounted) | 3001 | day-to-day development; started by a plain `docker compose up` |
| `web` | `prod` | nginx serving the built `dist/` | 8090 | real deployments; behind the `prod` profile |

```powershell
# production: build the bundle into an nginx image and run it
docker compose --profile prod up -d --build web
```

The `web` image serves the static bundle **and proxies `/api` to the
backend**, so the app and the API share one origin. That is why the built
bundle contains no API hostname: `services/api.ts` falls back to a relative
`/api/v1` in production, and the same image runs on localhost, on a
customer's hostname, or behind their TLS terminator with no rebuild. Only a
split deployment (API on a different host) needs
`--build-arg VITE_API_URL=https://api.example.com`, exposed in compose as
`VITE_API_URL_BUILD`.

Override the published port with `WEB_PORT` (8080 is left alone on purpose —
it collides with other stacks often enough to be a bad default).

For the air-gapped bundle: `web` is a **built** service like the others, so
add it to `$BuiltServices` in `scripts/build_offline_bundle.ps1` when you
want the deployment image carried across the gap. Its nginx base layer is
pulled from the internet-connected machine at build time, exactly like
`postgres` and `valkey`.

### 5. First-boot expectations

#### Alembic adoption / stamp

`backend/app/main.py`'s `lifespan` runs `_run_alembic()` at startup, under a
Postgres advisory lock (safe with multiple Uvicorn workers). Three cases,
all handled automatically — no manual DBA step required on first boot:

- **Fresh database** (no tables at all): `alembic upgrade head` runs every
  migration from scratch.
- **Database already stamped by Alembic** (has `alembic_version`):
  `alembic upgrade head` — a no-op if already current.
- **Database that only ever ran `create_all`/`_migrate`** (app tables exist,
  no `alembic_version` table — i.e., any environment that predates Alembic
  being adopted, T1): the app detects this and runs `alembic stamp head`,
  which writes only the version marker and runs no DDL. The existing schema
  is adopted without being touched. See `backend/alembic/README.md` for
  detail.

If the alembic step itself fails for any reason, startup logs the exception
and continues — `create_all`/`_migrate` (the pre-Alembic path) still runs,
so a first boot never hard-fails on a migration problem; it degrades to the
old schema-sync behavior instead.

#### Uploads / data volumes

`uploaded_files` and `postgres_data` are named Docker volumes — they start
empty on a fresh host and persist across `docker compose down`/`up`
(not across `docker compose down -v`).

### 6. What stays disabled offline (unless pointed at an internal endpoint)

Everything below defaults to **off** or **internal-only** by configuration
(`backend/app/core/config.py`) — nothing tries to reach the public internet,
and a deployment that changes nothing here runs fully offline with these
features simply inactive:

- **LLM endpoint** (`llm_base_url`, default
  `http://10.125.18.189:8000/v1`, `llm_enabled=True`): used only for
  Layer-1 column/table descriptions during a catalog sync — an improvement,
  never a requirement. `services/llm.py` returns `None` rather than raising
  when the box is unreachable, so a sync still completes with the model
  endpoint down. **This must point at an internal, self-hosted
  OpenAI-compatible endpoint (e.g. vLLM) inside the isolated network** — it
  is internal by design, never a public API.
- **Backend-B embeddings** (`embedding_base_url` / `embedding_model` /
  `embedding_dim`, all `None` by default): Tier-2 retrieval's lexical
  Backend A (pure numpy TF-IDF) is always available and is the default.
  Backend B (an OpenAI-compatible embeddings endpoint) only activates if all
  three settings are provided, pointing at an internal endpoint; any
  query-time failure (unreachable, wrong response shape, timeout) falls
  back to Backend A automatically — retrieval degrading, never breaking the
  agent.
- **OpenTelemetry** (`otel_enabled=False` by default, `otel_endpoint`
  unset): off by default, and the otel packages are never even imported
  unless explicitly enabled (`core/telemetry.py`), so a broken or absent
  otel install can never brick startup. If enabled, `otel_endpoint` must
  point at an **internal** collector — never a public SaaS telemetry
  endpoint.
- **SMTP** (`smtp_host=""` by default): outbound email for scheduled
  deliveries/alerts. An unset host means delivery is recorded as
  undeliverable rather than raising; a deployment without an internal SMTP
  relay still schedules deliveries, the status column just explains why
  nothing arrived. Point `smtp_host` at an internal mail relay to enable it.
- **Valkey shared cache** (Task O2, `valkey_url`, default `None`): the
  platform runs with today's in-process cache behavior byte-for-byte when
  unset. Only activates against an internal Valkey service added to
  `docker-compose.yml`.

None of the above require internet — only, optionally, an internal service
inside the isolated network. With all of them left at their defaults, the
platform is fully functional offline (query, report, dashboard, connector,
row-security, and scheduling features do not depend on any of the above).


---

# Part 7: Backup and recovery

*Source: `docs/BACKUP_AND_RECOVERY.md`*

## Backup and Recovery

What is durable in a Datalytics deployment, how to back it up, and how to prove the
backup works. Written for an air-gapped install, where there is no managed database
service to fall back on and no vendor to call.

> **If you read nothing else:** `postgres_data` is the only volume whose loss is
> unrecoverable. Back it up on a schedule, and restore it somewhere at least once
> before you need to.

> **There are scripts for this now.** `.\scripts\backup.ps1` and
> `.\scripts\restore.ps1` implement exactly the procedure below,
> including the ordering rule that is easy to get backwards. The manual commands
> stay because an operator on a non-Windows host still needs them, and because a
> script you cannot read is one you cannot trust in an emergency.
>
> ```powershell
> .\scripts\backup.ps1 -BackupDir D:\backups -RetentionDays 30
> .\scripts\restore.ps1 -Dump <dump> -Uploads <tar.gz> -WhatIf   # then -Confirm
> ```
>
> `backup.ps1` verifies the dump's `PGDMP` header **before** rotating anything, so a
> run of failures cannot delete the last good backup. `restore.ps1` refuses to run
> without `-Confirm`, and waits on `/health/ready` afterwards rather than declaring
> success when the files finish copying.

---

### What state exists

| Store | Volume / location | Durable? | Loss means |
|-------|------------------|----------|-----------|
| **PostgreSQL** | `postgres_data` | **Yes — critical** | Total loss. Every report, dataset definition, user, org, RLS rule, agent run, share link, schedule |
| **Uploaded files** | `uploaded_files` | **Yes — important** | Import-mode datasets lose their source data; report definitions survive but cannot render |
| **Valkey cache** | container-local | No | Nothing. Rebuilt on demand; a cold cache is slower, not broken |
| **Embeddings model** | baked into the image | No | Nothing. Restore by redeploying the image |

Two volumes matter. The rest is reconstructible.

#### Why `uploaded_files` is not optional

A restored database without `uploaded_files` yields a system that looks intact —
datasets listed, reports openable — and fails at the first widget render, because the
Parquet/CSV behind each import-mode dataset is gone. **Back up both volumes, from the
same moment**, or restores will be subtly wrong rather than obviously broken.

---

### Backing up

#### Database

`pg_dump` from the running container. Custom format (`-Fc`) is compressed and lets
`pg_restore` run in parallel:

```bash
docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-datalytics}" -d "${POSTGRES_DB:-datalytics}" -Fc \
  > "backup/datalytics-$(date +%Y%m%d-%H%M%S).dump"
```

Restore requires the **same major PostgreSQL version** (16, per `docker-compose.yml`).
Record the version alongside the dump.

#### Uploaded files

```bash
docker run --rm \
  -v datalytics_uploaded_files:/data:ro \
  -v "$(pwd)/backup:/backup" \
  alpine tar czf "/backup/uploads-$(date +%Y%m%d-%H%M%S).tar.gz" -C /data .
```

Confirm the volume name first — Compose prefixes it with the project directory:

```bash
docker volume ls | grep uploaded_files
```

#### Consistency between the two

The dump and the tarball should describe the same instant. Uploads are
write-once-then-referenced, so the safe ordering is:

1. Snapshot `uploaded_files` **first**
2. `pg_dump` **second**

A file present on disk but absent from the database is inert. A row referencing a file
that was never captured is a broken dataset. Taking files first makes the harmless
direction the only possible one.

For a strictly consistent pair, stop the backend for the duration:

```bash
docker compose stop backend    # frontend keeps serving; API returns errors
# ... take both backups ...
docker compose start backend
```

---

### Scheduling

Any scheduler works; the platform does not provide one for this. A daily dump with
14 days of retention:

```bash
#!/usr/bin/env bash
# backup-datalytics.sh — run daily via cron/Task Scheduler
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/datalytics-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. files first (see "Consistency" above)
docker run --rm \
  -v datalytics_uploaded_files:/data:ro \
  -v "$BACKUP_DIR:/backup" \
  alpine tar czf "/backup/uploads-$STAMP.tar.gz" -C /data .

# 2. then the database
docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-datalytics}" -d "${POSTGRES_DB:-datalytics}" -Fc \
  > "$BACKUP_DIR/datalytics-$STAMP.dump"

# 3. fail loudly on an empty or truncated dump rather than rotating a good one away
if [ ! -s "$BACKUP_DIR/datalytics-$STAMP.dump" ]; then
  echo "FATAL: dump is empty — not rotating" >&2
  exit 1
fi

# 4. retention
find "$BACKUP_DIR" -name 'datalytics-*.dump'   -mtime +14 -delete
find "$BACKUP_DIR" -name 'uploads-*.tar.gz'    -mtime +14 -delete
```

Step 3 matters more than it looks: without it, a run of failed backups quietly deletes
the last good one.

---

### Restoring

#### Full recovery onto a clean host

```bash
# 1. bring up ONLY postgres, so the backend cannot write during the restore
docker compose up -d postgres
docker compose exec postgres pg_isready -U datalytics    # wait for ready

# 2. restore the database
docker compose exec -T postgres \
  pg_restore -U datalytics -d datalytics --clean --if-exists \
  < backup/datalytics-20260828-020000.dump

# 3. restore uploaded files
docker run --rm \
  -v datalytics_uploaded_files:/data \
  -v "$(pwd)/backup:/backup" \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/uploads-20260828-020000.tar.gz -C /data"

# 4. start the rest
docker compose up -d

# 5. confirm the app considers itself servable
curl -fsS localhost:8000/health/ready | python -m json.tool
```

Step 5 is the actual success check. `/health/ready` returns 503 until migrations have
completed, so a 200 with `"postgres": {"status": "ok"}` means the restored database is
reachable *and* at the schema version this build expects.

#### On schema version

The dump carries the schema it was taken from. Starting a **newer** build against an
older dump is fine — Alembic runs at startup under an advisory lock and migrates
forward. Restoring a **newer** dump into an **older** build is not supported; keep the
image tag with the backup.

---

### Verifying the backup

An untested backup is a guess. Run this quarterly, and after any change to the stack.

**Drill:**

1. Copy the most recent dump and tarball to a scratch host (or a second compose
   project with a distinct `COMPOSE_PROJECT_NAME`)
2. Restore per the steps above
3. Confirm, in order:
   - `curl -f localhost:8000/health/ready` returns 200
   - Logging in works — proves `users`, `organizations`, `roles` restored
   - A report list loads — proves report tables restored
   - **Open a report with an import-mode widget and confirm it renders** — the only
     step that proves `uploaded_files` and the database agree
   - A DirectQuery widget renders, if the environment can reach its source
4. Write down the date, the dump used, and the wall-clock time from start to serving

Step 3's fourth item is the one that catches the failure mode this document exists to
prevent. Steps 1–3 can all pass with a completely empty uploads volume.

**Record the drill.** "We have backups" is not a recovery plan; "we restored on
2026-08-28 in 22 minutes" is.

---

### What this does not cover

- **Point-in-time recovery.** Daily `pg_dump` means up to 24 hours of loss. If the
  business needs tighter, configure WAL archiving (`archive_mode=on`) and a base
  backup — out of scope here, and it changes the Postgres service definition.
- **Off-host replication.** Copying backups off the machine is deployment-specific and,
  in an air-gapped environment, usually a physical-media procedure.
- **Encryption at rest.** Dumps contain every row in the system, including anything
  classified as PII. Treat the backup directory with the same controls as the database.


---

# Part 8: Architecture, layer by layer

*Source: `ARCHITECTURE.md`*

## Architecture

Datalytics is a containerised, self-hostable analytics platform: connect a data
source, model it, and build multi-page interactive reports with cross-filtering,
row-level security, and natural-language querying against a self-hosted model.

This document describes the system as **seven layers in data-flow order** — the
path a byte takes from a source system to a pixel on screen. Each layer states
what it owns, where its code lives, and the contract it exposes to the layer above.

> **Scope.** `README.md` is the quick start and feature tour. This document is the
> architecture reference. Where the two disagree, this file is authoritative.

---

### Contents

- [The seven layers at a glance](#the-seven-layers-at-a-glance)
- [Runtime topology](#runtime-topology)
- [Layer 1 — Data Sources & Connectivity](#layer-1--data-sources--connectivity)
- [Layer 2 — Ingestion & Metadata](#layer-2--ingestion--metadata)
- [Layer 3 — Storage & Persistence](#layer-3--storage--persistence)
- [Layer 4 — Query & Semantic](#layer-4--query--semantic)
- [Layer 5 — Analytics & AI](#layer-5--analytics--ai)
- [Layer 6 — API & Services](#layer-6--api--services)
- [Layer 7 — Presentation](#layer-7--presentation)
- [Cross-cutting concerns](#cross-cutting-concerns)
- [Request lifecycles](#request-lifecycles)
- [Testing](#testing)

---

### The seven layers at a glance

| # | Layer | Owns | Principal code |
|---|-------|------|----------------|
| 1 | **Data Sources & Connectivity** | Reaching external systems; dialect capability; pooled engines | `services/connectors.py`, `connections.py`, `engines.py`, `secrets.py`, `net_guard.py` |
| 2 | **Ingestion & Metadata** | Turning raw sources into described, profiled datasets | `services/ingest.py`, `services/metadata/`, `routers/datasets.py`, `services/pii.py` |
| 3 | **Storage & Persistence** | Durable state and cached state | `models/models.py`, `alembic/`, `services/cache_backend.py` |
| 4 | **Query & Semantic** | Translating widget intent into safe, governed SQL | `services/query_builder.py`, `widget_data.py`, `widget_shaping.py`, `direct_query.py`, `duck_agg.py`, `prep.py`, `sql_expr.py`, `core/rls.py` |
| 5 | **Analytics & AI** | Statistics, forecasting, anomaly detection, NL→SQL | `services/analysis/`, `services/agent/`, `analytics.py` |
| 6 | **API & Services** | HTTP surface, authn/authz, delivery, sharing | `routers/` (19 modules), `core/security.py`, `services/delivery.py`, `refresh_scheduler.py`, `services/automation_runner.py` |
| 7 | **Presentation** | Report authoring and rendering | `frontend/src/pages/`, `components/report/` |

Layers depend **downward only**. Layer 7 never reaches past Layer 6; Layer 6
composes Layers 1–5. The one deliberate exception is the AI agent (Layer 5),
which calls into Layer 4's RLS resolution directly so generated SQL inherits the
same governance as hand-built widgets — see [Agent](#nlsql-agent).

**This is enforced, not just described.** `backend/tests/test_layer_conformance.py`
parses every import in `app/services/` and `app/core/` and fails on any upward
dependency. Three remaining violations are held in a `KNOWN_VIOLATIONS` allowlist that
can only shrink: a new upward import fails the build, and so does an allowlist entry
whose violation has been fixed. The layer map in that test and the tables in this
document must be changed together.

All three are the same accepted-by-design pattern — `dataset_refresh`, `ingest` and
`metadata/sync` reading layer 3's frame cache. Cache reads and invalidation both flow
from whoever touches the data, so these are correct as they stand. **No remaining entry
represents a module in the wrong place.**

---

### Runtime topology

Five containers on one Docker network (`docker-compose.yml`):

```
┌──────────────────────────────────────────────────────────────────┐
│                      datalytics_net                              │
│                                                                  │
│   ┌──────────┐   ┌─────────────┐   ┌──────────────┐              │
│   │ frontend │──▶│   backend   │──▶│   postgres   │              │
│   │  :3000   │   │    :8000    │   │  16-alpine   │              │
│   │  (Vite)  │   │  (FastAPI)  │   │    :5432     │              │
│   └──────────┘   └──────┬──────┘   └──────────────┘              │
│                         │                                        │
│                  ┌──────┴───────┐                                │
│                  ▼              ▼                                │
│           ┌────────────┐  ┌──────────────┐                       │
│           │   valkey   │  │  embeddings  │                       │
│           │  8-alpine  │  │  (local ST)  │                       │
│           └────────────┘  └──────────────┘                       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼  (optional, external)
                    ┌──────────────────────┐
                    │  vLLM model endpoint │   llm_base_url
                    │   (self-hosted)      │   default: qwen3.5
                    └──────────────────────┘
```

Volumes: `postgres_data`, `uploaded_files`.

Nothing in the running stack fetches from the public internet. The model endpoint
is self-hosted and configurable; setting `llm_enabled=False` disables the AI layer
entirely and the platform runs fully air-gapped. See `docs/OFFLINE_DEPLOYMENT.md`.

---

### Layer 1 — Data Sources & Connectivity

**Owns:** reaching external systems, and knowing what each one can do.

#### Connector registry

`services/connectors.py` declares a `ConnectorSpec` per source type and exposes
them through `_REGISTRY`. **45 connectors** are registered — the count and the
breakdown below are `_ALL_SPECS` grouped by `category`, which is the only source
of truth:

| Category | Count | Driver | DirectQuery |
|----------|-------|--------|-------------|
| PostgreSQL-compatible | 16 | `psycopg2` (bundled) | Yes |
| MySQL-compatible | 11 | `pymysql` (bundled) | Yes |
| Cloud warehouse | 5 | operator-installed | ClickHouse only |
| SQL Server-compatible | 4 | `pymssql` (bundled) | Yes |
| Oracle-compatible | 3 | `oracledb` (bundled) | Yes |
| File | 3 | `sqlite`, `duckdb-engine`, `mdbtools` | Partial |
| API | 1 | Web API | — |
| Advanced | 2 | SQLAlchemy URL | — |

**37 of the 45 are DirectQuery-capable.**

Wire-compatible variants (Aurora, Redshift, TimescaleDB, Supabase, Neon and the
rest) are counted inside their family rather than listed separately — each is a
registered connector in its own right, sharing its family's driver.

A spec declares how to **connect** (SQLAlchemy dialect + driver) and what the
engine can **compute**. Two capability sets gate push-down:

```python
PERCENTILE_FAMILIES = {"postgresql", "oracle"}
STAT_FAMILIES       = {"postgresql"}
```

Engines outside these sets raise `DirectQueryUnsupported` rather than silently
returning wrong numbers. This fail-closed stance is deliberate: a Redshift or
CockroachDB connection is PostgreSQL-wire but does not implement `WIDTH_BUCKET`
or `CORR`, so it is registered with `full_stats=False`.

Cloud warehouses (Snowflake, BigQuery, Databricks, Trino) are **discoverable but
import-only** — enterprises pin their own driver versions, so the driver module
is named in the spec and imported lazily.

**ClickHouse is the exception, and the sixth SQL family.** Everything above this
line describes a catalog that maps onto five wire-compatible families;
ClickHouse is wire-compatible with none of them, so it carries its own
`sql_family` rather than borrowing one. It keeps the warehouse driver gate
(`clickhouse_sqlalchemy` is operator-installed like every other warehouse
driver) but resolves DirectQuery.

The SQL comes from the same builder every other family uses, transpiled once at
the end by `direct_query._finalize_for_dialect` — `sqlglot.transpile(read=
"postgres", write="clickhouse")`, which is an **identity function for the other
five**. That identity is the safety argument for adding a family to a builder
five families already depend on, and it is pinned per-family in
`tests/test_clickhouse_connector.py`.

Two details of that transpile are load-bearing:

- **Bound parameters are hidden across it.** sqlglot has no idea `:f0` is a
  SQLAlchemy placeholder and its ClickHouse writer renders it `{f0: }` — a named
  placeholder with an *empty type*, which the server rejects. Each bind is
  swapped for a sentinel string literal before the transpile and restored after.
- **Percentiles are refused, not transpiled.** ClickHouse spells them
  `quantile(0.5)(col)`, and sqlglot parses `PERCENTILE_CONT(…) WITHIN GROUP (…)`
  as valid ClickHouse and emits it unchanged — so it cannot act as a safety net
  here. The refusal comes from the registry instead (`percentile_override=False`,
  `stat_override=False`), the same fail-closed route Redshift takes for
  `WIDTH_BUCKET`.


**Microsoft Access is the one connector with no SQLAlchemy dialect.** Jet/ACE is
wire-compatible with none of the five families, and Microsoft's ACE provider is
Windows-only, so on a Linux image it cannot be reached through an engine at all.
`services/mdb.py` reads `.mdb`/`.accdb` by running the bundled **mdbtools** CLIs
and parsing their CSV output, and `connections.py` special-cases `access` in the
same four places it already special-cases `api`. `build_url` raises for it,
deliberately: there is no URL to build.

That makes it import-only (`sql_family=None`), read-only, and unable to run
custom SQL — mdbtools has no usable query engine. Encrypted Access files cannot
be read by any open-source tool, so they are refused with an instruction to save
an unencrypted copy rather than a generic parse error.

`ConnectorSpec.probe` exists for it: `driver_installed` normally asks
`importlib` for a Python module, and mdbtools is a *binary*, so without the probe
the catalog would advertise Access as available on hosts that cannot read it.

An import-only source is refused DirectQuery **at the request**, in
`data_sources.py`'s import endpoint, not at the first widget. The check is not
redundant with `sql_family=None`: `preview_table` succeeds for these types (the
Access connector reads its file; the API connector fetches its rows), so the
schema probe in the DirectQuery branch would happily create a dataset in
`mode="directquery"` that cannot render. Found by driving a live stack, not by
the suite — every unit test had passed.

#### Joining datasets, and keeping the result

A prep `join` step is a VIEW: it re-joins on every read and lives inside one
dataset's pipeline. `POST /datasets/{id}/materialize` runs that pipeline once and
writes the result as a new import dataset, which is how several joined datasets
become one listable dataset reports can be built on.
`POST /datasets/{id}/rebuild` re-runs it.

The result is a **snapshot**: it does not follow its sources, so editing a
source's pipeline cannot silently change a dataset somebody has already built a
report on. The recipe is stored verbatim under a third reserved `column_meta`
key, `__derived_from__`, beside `__prep_steps__` and `__exports_disabled__` and
for the same reason -- `create_all` never ALTERs a deployed table, so a real
column would be missing everywhere the schema already exists. Rebuild replays
that snapshot, never the source's current steps, and fails **hard** (409) where a
read fails soft: a missing join frame degrades to a no-op on a read, which here
would silently drop every joined column from persisted data.

Two refusals govern it, both fail-closed:

- **A source carrying row- or column-security rules cannot be materialized.**
  Every read applies the *caller's* RLS, so a snapshot taken by a restricted user
  would freeze their slice as everyone's data -- the copy carries no rules of its
  own, so colleagues would read silently wrong totals. Copying the source's rules
  onto the result was rejected: a join renames colliding columns (`region` ->
  `region_2`) and an `aggregate` step can remove the rule's column entirely, so
  the copied rule would guard a column that no longer exists.
- **Materializing is an export.** It writes source rows to a new file, so it goes
  through the same `_exports_disabled` check as `GET /{id}/export`; otherwise
  disabling export and then materializing would launder the data into a copy with
  no policy. The strictest source policy is propagated onto the result.

The lineage graph carries `derived_from` edges for these, distinct from `joins`:
one is a snapshot taken at `built_at`, the other is live.

Join keys are **suggested, not just detected**. `metadata/infer_keys.py` has always
worked out how tables connect -- name candidates, type compatibility, value overlap
measured with a DuckDB join, then cardinality -- and stored the result as a
`Relationship` with a confidence and an `evidence` blob. Nothing read it at join
time until the prep editor did: choosing a dataset to join now pre-fills both keys
from the best known link, ranked `confirmed > declared > inferred` and then by
confidence, which is why `RelationshipOut` carries `source`, `confidence` and
`cardinality` (but not `evidence` -- that is review material for `SourceReview`).

The suggestion is a starting point, never a guarantee: a relationship records how
two tables link, **not** that the match is one-to-one. On the demo data a
`declared` relationship takes 2,000 rows to 35,137, because the key repeats on the
other side. The editor names that where it happens -- a join whose row count grows
is called out per step -- since a fan-out otherwise makes every total silently
wrong, which is the failure `infer_keys`' own docstring warns about.

**A join can match on several columns.** One column often does not identify a row
-- region + quarter, order + line -- and joining on only one of them multiplies
rows instead of adding columns. A step carries either shape:

    {"left_on": "cust", "right_on": "id"}                     # one pair
    {"left_ons": ["region", "quarter"],
     "right_ons": ["region", "period"]}                       # composite

`join_key_pairs()` in `prep.py` is the single reader, and the editor writes back
in the narrowest shape that fits, so a one-key step's JSON is unchanged and every
pipeline saved before composite keys existed keeps working with no migration.
Validation refuses ragged key lists (they would pair the wrong columns), and at
apply time a join whose keys are not ALL present is skipped entirely rather than
matched on the remainder -- a partial key silently widens the match, which is
worse than not joining.

#### Aggregate datasets

A scheduled `GROUP BY` over a DirectQuery dataset, saved as an import dataset
(`services/aggregates.py`, `POST /datasets/{id}/aggregates`). The compiled SQL
runs where the data lives, through the same refresh path as every import
dataset; a dashboard on the aggregate reads thousands of rows instead of
scanning millions.

Governed, not copied. The aggregate carries no rules of its own:
`core/rls.py` follows `aggregate_of_dataset_id` and applies the **source's**
row-level and column rules at read time. That is sound only if the grain
carries every column those rules read — creation refuses otherwise, naming
the role and column, and every scheduled refresh re-checks and records a
`ScheduleFailure` if a later rule outgrew the grain (reads for that role fail
closed meanwhile). A source column denied to a role denies every measure
built on it. Only `sum`/`count`/`min`/`max`; `row_count` is always present.
Deleting the source cascades to its aggregates.

#### Key influencers

`services/analysis/influencers.py` answers "what drives this?" -- which factors move
a chosen outcome, ranked by how far each group's rate (or mean) sits from the dataset
baseline.

Deliberately **not** a fitted model. Every number is one a reader can check by hand:
the group is a column-value rule, the lift is a ratio of two rates, the support is a
row count. A gradient-boosted ensemble would rank more accurately and explain nothing,
and for a self-serve feature a confidently wrong "your top driver is X" that nobody can
audit is worse than no answer. It adds no dependency at all -- pandas computes the lift
exactly.

Three guards keep it from inventing an answer: groups thinner than 2% of the data (or
10 rows) are dropped before ranking, so an anecdote cannot top the list; columns with
more than 50 distinct values are skipped as identifiers, with a warning naming them;
and ranking is on |lift - 1|, so a factor that HALVES the outcome ranks alongside one
that doubles it. The payload carries a not-causation caveat because a UI rendering
"top driver" without one invites exactly the wrong reading.

Column security applies to the *factors*, not only the frame: a denied column is
dropped before the analysis, since naming it with a rate attached would leak precisely
what the rule hides.

#### Saved models, and scoring with one

Every analysis above refits and discards, which answers "what could predict
this, and how well" and never "score these rows". `prediction_models` is the
store that closes that — the champion from `automated_prediction`, refit on the
whole frame rather than the three quarters the comparison used, kept so it can
answer rows whose outcome is not known yet.

**Feature alignment is the part a naive store gets wrong.** `_encode` one-hot
encodes with `pd.get_dummies`, so the columns it produces depend on the values
present in the frame. A model trained on three regions has three dummy columns;
score a frame containing one and get one, in a different position — sklearn
either raises or reads the wrong number as the wrong feature. So the training
column order travels with the model (`feature_columns`) and every scored frame
is reindexed onto it. A missing FEATURE is refused instead, because that means
the caller is scoring the wrong data.

**An unseen category is reported, not hidden.** A value the model never met
encodes as zero across that column's dummies, which is honest — the model has
no opinion — but silently returning the prediction lets somebody score a year
of new data the model recognises none of and read it as a forecast.

**A saved model carries the columns it was trained on.** This is the security
property nothing else here has: the estimator's answers are derived from every
feature, so a caller denied one of them is refused the MODEL, not just the
column. Dropping the column from their request would change nothing, since the
influence is already inside the fitted object. Such a model is also omitted
from their listing entirely — naming it would tell them the column exists and
is worth predicting from.

**And the rows it was trained on.** A model is a derivative of its training
rows the way a snapshot is: a tree's leaves and a forest's splits are built
from them. `materialize` refuses a governed dataset outright for the
neighbouring reason — a snapshot written under one person's RLS carries no
rules of its own. This can afford to be narrower, because the filter is
RECORDED (`trained_rls`) rather than guessed: a model may be used by anyone
who sees exactly those rows, and nobody else. An admin's model is for admins;
an EMEA analyst's is for EMEA analysts. Filters are compared verbatim, so two
equivalent rules written differently are refused — the safe direction.

The artifact is a joblib pickle, so loading one executes code. Nothing accepts
an uploaded model: the only writer is `services/analysis/model_store.py`, and
the artifact never leaves the server — no endpoint serialises it.

#### Decomposition tree

`shape_decomposition` in `widget_data.py` breaks one number down a level at a
time: total revenue, then by region, then within EMEA by product. The reader
drills by clicking a child and climbs by clicking a breadcrumb, and the server
recomputes each level from the path -- so the client holds no analytical logic
and a drilled tree survives a refresh, a filter change, and a cross-filter.

**Children always reconcile to their parent.** A level capped at
`DECOMP_MAX_CHILDREN` folds its tail into an "Other" bucket rather than dropping
it, because a drill-down whose parts do not sum to the whole is worse than none
-- the reader trusts the parts anyway and cannot see what is missing. For a
non-additive aggregation (avg/min/max) the bucket is named but its value
withheld, since there is no honest number to put there.

The next level is normally the reader's choice. With `auto_split` the server
picks the field whose groups vary most relative to their mean, and the response
carries `auto: true` so the UI can mark it as suggested -- a server choice
presented as the reader's own is how an analysis quietly becomes wrong.
`DECOMP_MAX_LEVELS` keeps id-like columns out of that ranking: found live, where
splitting demo revenue suggested `date` (633 distinct values) over `category`,
because maximal variation and zero explanation look identical to a variance
score.

#### Paginated output and subscriptions

The report PDF is a **banded document**, not a screenshot of a dashboard: a
cover, a table of contents, one section per page, and tables that flow across as
many pages as their data needs, repeating the header. `PDF_MAX_TABLE_ROWS`
bounds that at 5,000 rows and the document SAYS when it binds -- a table
truncated in silence is a wrong answer that looks like a right one, which is
what the previous 40-row cap produced. Page number, report name and the
sensitivity label are drawn on every page after the cover, because pages get
separated from the documents they came from.

**Subscriptions are self-serve, and each one is its own schedule.** A
`ReportSchedule` resolves row-level security as its CREATOR, so appending a
subscriber to somebody else's schedule would email them the creator's slice --
silently, and possibly rows they may not see. `POST /reports/{id}/subscribe`
therefore creates a schedule owned by the subscriber; the cost is one render per
subscriber, which is the right trade against sending the wrong data cheaply.

Subscribing yourself needs only `view` (receiving data you can already read
grants nothing new); adding somebody else to a distribution list still needs
`edit`. Unsubscribing removes only a schedule you created BY subscribing, so a
subscriber cannot delete an author's distribution list.

#### Small multiples, and transformations that keep themselves current

`shape_small_multiples` draws the same chart once per value of a facet field.
Deliberately a WRAPPER over the existing shapers rather than a new shaping path:
each panel is produced by the ordinary entry for the inner widget type over a
filtered frame, so aggregation, measures, quick calcs and formatting are
identical to the un-faceted chart and any later fix reaches the panels for free.

**Every panel shares one scale.** `max_value` spans all of them and is returned
once, because comparing panels to each other is the entire point -- per-panel
axes would draw a small category identically to a large one, which is the single
way this visual lies. Panels are capped at `FACET_MAX_PANELS` and the tail is
counted in `omitted` rather than dropped in silence: a reader comparing panels
cannot see which categories never reached the page.

**A materialized dataset can refresh itself.** `due_datasets` now admits derived
datasets -- they have no `data_source_id` at all, which is precisely what used to
exclude them -- and `_rebuild_derived` replays the recipe in `__derived_from__`
on the schedule, writing in place so every report pointing at the dataset picks
up the new rows with no rewiring. That is the useful half of a "dataflow": a
transformation that stays current instead of waiting for somebody to press
Rebuild.

The rebuild runs AS THE RECORDED BUILDER (`built_by_user_id`), the same stance
`ReportSchedule` takes with its creator: a scheduled run has nobody at the
keyboard, and reading the base frame with no identity would be an unfiltered
read. A missing source or a departed builder logs and advances the timestamp
rather than raising, so one broken recipe never stops the loop.

#### Dataflows: a transformation as a first-class object

A prep pipeline belongs to one dataset, and a materialized result records its
recipe in that dataset's `column_meta`. Both are owned by a dataset. A `Dataflow`
lifts that: it owns the recipe, can produce SEVERAL outputs, carries its own
refresh interval, and -- the reason it exists -- has its own authoring
permissions rather than inheriting whatever the reports using its output allow.

**The hole this closes is concrete.** `max_dataset_capability` ends with "a
dataset no report uses is unrestricted". A materialized result is, by definition,
used by no report the moment it is created -- so under the old inheritance every
member of the org could author a freshly built transformation. Two endpoints were
worse: `DELETE /datasets/{id}` and `PATCH /{id}/refresh-schedule` consulted no
capability at all, so anyone could delete or reschedule anybody's pipeline. Both
now call `require_dataset_write`, which resolves a dataflow's grants FIRST -- so
operating on what a pipeline produced cannot route around the pipeline's own
permissions.

**Authoring is gated; reading is not.** Edit, schedule, run, delete and grant all
require capability. An output is an ordinary dataset, readable org-wide with RLS
narrowing rows per identity -- which is what `DatasetShare` already records as the
platform's model. Gating reads here would contradict every other read path rather
than extend one, and a test proves a `view` user still reads every output row.

**Default-open, with one deliberate difference from `ReportCapability`.** No rows
at all means every role has full access, so nothing existing breaks on the day it
ships. But once ANY grant exists the dataflow is governed, and an unlisted role
falls to `view` -- because granting one team `edit` is meant to say "this team
owns this pipeline", and if unlisted roles kept full access that grant would
restrict nobody.

Outputs need no join table: a produced dataset records `dataflow_id` inside the
`__derived_from__` JSON it already carries, so linking one needed no schema change
and every derived dataset predating dataflows keeps working untouched.

The schedule lives on the dataflow, not its outputs -- which is why the scheduler
needs a second pass (`due_dataflows`): the dataset query filters on
`Dataset.refresh_interval_minutes`, and an output's own interval is normally None.
One interval drives every output, so the set refreshes together rather than each
output drifting. `refresh_dataflow` runs as the dataflow's CREATOR for the same
reason `_rebuild_derived` runs as the recorded builder: a scheduled run has nobody
at the keyboard, and reading with no identity would be an unfiltered read.

Both materialization refusals carry over unchanged -- governed sources refused,
export-blocked sources refused, re-checked on EVERY run rather than only at create
-- because otherwise "make a dataflow instead" would be the documented bypass for
two security controls.

**Which datasets can be scheduled, and where the control lives.** Three kinds
are eligible and the UI must agree with the endpoint on all three, because a
control the server refuses is worse than no control: a SOURCE-backed dataset
re-reads its connection; a DERIVED dataset replays the recipe in
`__derived_from__`; and a plain upload can do neither, so it is offered nothing.
DirectQuery is excluded because nothing is cached to refresh. A dataflow's
OUTPUT is excluded too -- its schedule lives on the dataflow, which drives every
output together, and a second control on one output would let it drift from its
siblings.

The interval control sits in the same menu as the manual refresh, because both
answer "when does this data update" and splitting them leaves a user hunting for
one having found the other. The 5-minute floor is enforced server-side only; the
dropdown simply starts there rather than repeating the number as a second place
to update.

#### Right-to-left, app-wide

Direction was a per-widget flag: `cfg.rtl` mirrored one chart's axes, and the
shell around it stayed left-to-right whatever the reader needed. It is now an
app-level setting that writes `dir` on the DOCUMENT ROOT -- the single switch the
browser acts on, mirroring flexbox, grid, scrollbars, text alignment and every
logical property at once, including portals and dialogs rendered outside the
React tree.

**Stored per user, not per org, deliberately.** `OrgTheme` has no general
settings blob, and adding a column would land in the trap recorded throughout
this document: `create_all` never ALTERs a live table, so the column would exist
on fresh installs and be silently missing on every deployed one. Direction is
also genuinely a reader's preference -- two people in one org may want opposite
directions, which a single org value could not express.

**The decision that makes it actually work** is how a widget's own flag is read.
`WidgetConfigPanel` writes `rtl` into every saved config, so essentially every
widget that exists carries `rtl: false` -- meaning "the author never turned this
on", not "the author demanded left-to-right". Read as a plain boolean, that
stored `false` would pin every existing widget to LTR and make the app-wide
switch do nothing at all. So `widgetIsRtl` treats only an explicit `true` as an
override and lets everything else follow the app. A test pins this, and it fails
under the natural wrong implementation.

**What `dir` cannot fix** are physical CSS properties and direction-coded
characters. 78 occurrences of `marginLeft`/`paddingRight`/`borderLeft`/
`textAlign: 'left'` across 38 files became their logical equivalents
(`marginInlineStart`, `paddingInlineEnd`, `borderInlineStart`, `textAlign:
'start'`) -- each exactly equivalent under LTR, so nothing changed for existing
readers. Positioned offsets were reviewed individually rather than swept: an
element pinned to ONE edge (a dropdown, a badge) mirrors, while one pinned to
both (`left: 0; right: 0`) is spanning its container and must not. Navigational
arrows flip via `navArrows`; trend arrows and disclosure triangles do not, because
up is up in every language.

**Deliberately still absent, and stated rather than glossed:** there is no i18n
or translation framework -- interface text is English regardless of direction --
and server-side PDF export remains left-to-right, since reportlab would need
`arabic_reshaper` and a bidi pass. Mirroring only the on-screen preview would
make the screen disagree with the downloaded file.

#### The shared cache is now wired up

`VALKEY_URL` defaults to `redis://valkey:6379/0` -- the service this compose file
already runs. It was previously unset, which shipped a genuinely odd state: a
256MB Valkey container, with a healthcheck, connected to nothing, while every
worker process repeated identical widget renders in its own in-process cache.
That was the capability audit's sharpest finding in miniature -- built, tested,
and switched off.

**Safe to default ON because failure degrades rather than breaks.** `ValkeyCache`
uses 2-second socket timeouts, logs any error, opens a circuit for 300s and
serves from the in-process fallback. Verified live rather than assumed: with the
service stopped, the first render paid one ~3.5s connection timeout and every
render after it returned in ~0.04s from the fallback, with no 500s at any point.
So the worst case while Valkey is down is one slow request per five minutes, not
a slow request each time.

**No `depends_on: valkey`**, matching the rule already applied to `embeddings`:
the backend must start and keep running whether or not an optional service
exists. A dependency would turn a cache outage into a boot failure, which is
precisely what the circuit breaker exists to prevent.

The measured effect on a real render: 0.25s cold, 0.06s warm -- and warm now
means warm for *every* worker, which is the entire point of moving the cache out
of the process. A deployment with no Valkey sets `VALKEY_URL=` to restore the
previous behaviour exactly.

`tests/test_compose_defaults.py` pins this, because the claim lives in a YAML
file no other test reads.

#### Subscriptions became reachable

`POST /reports/{id}/subscribe` and its two siblings shipped working and
**unreachable**: three endpoints, zero frontend callers. The feature existed only
over HTTP, which is the same defect class as the refresh-schedule endpoint the
live check caught earlier -- a capability that is correct in the service layer
and invisible to the person it was built for.

**Where the control sits is the load-bearing decision.** Subscribing needs only
`view`, and the report toolbar is gated on `editMode`, which a view-only user can
never enter (`useEffect(() => { if (!canEdit && editMode) setEditMode(false) })`).
Putting it there would have hidden the feature from exactly its audience. It
lives beside the PDF button instead, in the always-visible header, because a
subscription is the recurring form of that same export.

The dialog states whose data the copy contains, because that is not guessable and
changes how every figure is read: the schedule is owned by the SUBSCRIBER, so
row-level security resolves as them rather than as the report's author.

Cadence-dependent fields are sent only when they mean something -- `weekday` for
weekly, `monthday` for monthly, neither for daily -- matching what the endpoint
validates, and the day-of-month list stops at 28, the only day every month has.
Both are pinned by tests that fail under the obvious wrong implementation.

#### Right-to-left reaches the PDF

The screen and the downloaded file disagreed: the app mirrored right-to-left end
to end, while `pdf_export` handed strings straight to reportlab, which draws
glyphs in the order it is given and performs no shaping. Arabic came out as
isolated letter forms in reversed order -- and the default Helvetica has no
Arabic glyphs at all, so it drew NOTHING and raised nothing. A silent wrong
answer.

Three separate problems, all of which had to be solved:

  * **Shaping.** Arabic letters change form by position. `arabic_reshaper` maps
    them to the presentation forms a non-shaping renderer can draw individually.
  * **Ordering.** `python-bidi` applies the Unicode bidirectional algorithm, so
    mixed text like "مبيعات 2026" puts the number where a reader expects it.
  * **Glyph coverage.** DejaVu Sans covers Arabic and is ALREADY IN THE IMAGE via
    matplotlib -- so nothing is downloaded, no font asset is added, and the
    air-gapped guarantee is untouched.

**Latin never enters that path.** `has_rtl` gates every call, so a report with no
RTL script is byte-identical to before -- which is what makes this safe to apply
unconditionally instead of behind a flag, and a flag nobody turns on is exactly
how the original gap happened. The test pinning this checks that the shaping
libraries are never *imported* for Latin text, because the reshape+bidi
round-trip on plain Latin is itself a no-op and a value comparison would pass
under either implementation.

**A pre-existing bug the live check caught.** Exporting a report whose *name* was
Arabic returned a 500 -- not in the new code, one line after it. The download
filename was sanitised with `c.isalnum()`, which is True for Arabic, Hebrew and
CJK letters, so those survived into a `Content-Disposition` header, and HTTP
headers are latin-1. It now emits both RFC 6266 parameters: an ASCII `filename`
every client understands, and a UTF-8 `filename*` carrying the real name. That
had been broken for any non-Latin report name since the endpoint shipped; the RTL
work simply made it reachable.

**Still not a translation layer.** This changes how text is drawn, never what it
says: interface strings stay English, and there is no i18n framework.

#### ODBC: the escape hatch, reported honestly

The 45th connector exists for backends with no SQLAlchemy dialect of their own --
legacy ERPs, Progress, Informix, older Sybase. SQL Server is deliberately NOT one
of them: it connects through `pymssql`, a self-contained wheel, and keeps full
DirectQuery. Routing it through ODBC would trade a working path for a worse one.

**No SQL family and no dialect, on purpose.** What sits behind a DSN is unknown,
so claiming a family would push generated SQL at a backend that may not speak it.
ODBC is import-only; `supports_directquery` stays False and the count of
DirectQuery-capable connectors is unchanged at 37.

**The probe is the interesting part.** `driver_module="pyodbc"` would have been a
LIE. pyodbc is a binding, not a driver: it can import successfully while no
driver manager (unixODBC) and no vendor driver are present, so the catalog card
would advertise a connector that fails at connect time on every host.
`_odbc_usable` asks `pyodbc.drivers()` instead -- what the driver manager
actually has registered, which is the question a reader of the card is really
asking. An empty list means the binding is installed and useless, which reports
as not-installed.

It catches `Exception`, not `ImportError`, and this image proves why: with the
wheel installed but `libodbc.so.2` absent, `import pyodbc` itself raises. A
narrower catch would have 500'd the whole connector catalog. The card reads
not-installed instead, joining the five cloud warehouses whose drivers the
operator supplies -- per-vendor, often licence-gated, and not weight every
air-gapped deployment should pay for.

#### CALC: filter context, without building a language

The capability audit's modelling row says "no CALCULATE-equivalent **filter-context
manipulation**" -- not "no language". `CALC(expr, "filter")` closes exactly that:
evaluate an aggregate under a different row filter than the visual's, then
compare the two.

    SUM(revenue) / CALC(SUM(revenue), "`segment` == 'Enterprise'")

**The filter reuses the grammar that already exists** -- the one
`apply_filter_expr` and every row-security rule speak. That is the design rather
than a convenience: it is already safety-validated by `_validate_expr_safety`,
already familiar to anyone who has written a filter or an RLS rule, and already
translatable to SQL by `sql_expr` for DirectQuery pushdown. A second filter
language would have meant a second parser, a second validator, and a second
thing to keep in step.

**Security comes from where it sits, not from a new control.** `df` reaching the
shapers is already row-security-filtered -- the base-frame choke-point test pins
that -- so a CALC filter can only narrow the slice the caller may already see.
No expression widens it back to rows RLS removed.

**The alignment rule is the real semantic question,** and the obvious
implementation gets it wrong. When the filter constrains a GROUPING column the
result is per-group, and groups the filter excluded are genuinely outside the
context (NaN, not 0 -- 0 would assert "this group had none", a different and
false claim). When the filter does NOT mention the grain, the filtered context
does not vary by group: it is a fixed comparison base and broadcasts to every
group. Reindexing unconditionally -- which is what a first pass does -- produces
that second case as NaN everywhere but one row, which looks like missing data
rather than a wrong alignment. Live probing caught this; the unit tests were
written afterwards and fail under the reindex-always version.

**A broken filter raises.** `apply_filter_expr` defaults to `silent=True`, which
returns the frame UNFILTERED on error -- here that would compute an unrestricted
total and present it as a filtered one. `CALC` passes `silent=False`; a test
fails if that is flipped back, and the same flip also punches a hole in the
expression sandbox.

CALC joins TOTAL and BYGROUP as a context function, so the existing no-nesting
rule covers it: each has its own grain, and composing them needs a nested
group-then-regroup this engine deliberately does not model.

**What this is not.** There is still no M/Power Query equivalent, no ALL/RELATED,
no evaluation-context model. The audit's row moves from gap to partial, not to
have -- competing with DAX on its own ground remains a bad trade, and the note
says exactly how far this goes.

#### Inferential statistics: is the difference real?

The eight analyses that came before describe, forecast, cluster or flag. Every
one can say THAT two groups differ; none could say whether the difference would
survive another sample. Four tests now close that:

  compare_groups     Welch's t-test (2 groups) / one-way ANOVA (3+)
  test_independence  chi-square with Cramer's V
  correlation_test   Pearson or Spearman with a p-value
  regression         OLS with a full coefficient table

**scipy and statsmodels were already in the image** -- they shipped for the
forecasting and profiling code and sat unused for inference. So this exposes
capability already paid for rather than buying SAS-scale breadth, and the
air-gapped guarantee is untouched: nothing new is downloaded.

**The way this feature would lie, and the rule that stops it.** With a
two-million-row import cap a p-value alone is nearly content-free: at n=100,000
a 0.1% difference in means is "highly significant" and completely irrelevant.
Every test therefore returns an EFFECT SIZE beside p -- Cohen's d, eta squared,
Cramer's V, r -- and a plain-language `interpretation` naming both. A
significant result with a negligible effect says so in words, because that is
the normal outcome at large n and a reader who sees only the asterisk will act
on nothing.

**Welch, not Student, as the non-negotiable default.** Student's t assumes the
groups share a variance, which business data rarely does -- a large region and a
small one differ in spread as well as level -- and the wrong assumption yields
an OVERCONFIDENT p. Offering `equal_var=True` as a toggle would be offering a
foot-gun, so it is not offered.

**Below a row floor a test is refused, not weakened.** A p-value from five rows
is not a weak answer; it is a meaningless one, and a number is exactly what a
reader acts on. Same stance as `influencers.MIN_ROWS`.

The insights engine gained the same discipline. Its `standout` and `correlation`
detectors previously asserted a pattern with no test behind it; both now carry a
p-value, and a finding that fails its test is DEMOTED in the ranking rather than
hidden -- the pattern is real in these rows, it is simply not evidence about
anything beyond them, and saying so is more useful than silence. A measure that
can go negative (profit, variance) is never chi-square tested for uniformity:
it is not a frequency, and testing it as one would be arithmetic dressed as
inference.

**What this is not.** No GLM, no mixed models, no survival analysis, no
multiple-comparison correction. SAS's statistical breadth remains a different
order of investment and is still not recommended; these are the four tests a
business analyst actually reaches for, and the row moves from partial toward
have without claiming parity.

#### Advanced models, and correcting our own findings

Four more capabilities, all from statsmodels -- which, like scipy, was already
in the image. Nothing new is downloaded:

  glm_logistic          odds ratios for a yes/no outcome
  mixed_model           repeated measurements within groups
  survival              Cox proportional hazards, censoring included
  pairwise_comparisons  which pairs differ, corrected for how many were tested

**Logistic regression, not OLS, for a binary target.** OLS can predict
probabilities below zero and above one, and its standard errors are meaningless
there. The headline is the ODDS RATIO, not the coefficient: a log-odds of 0.34
means nothing to the person asking "does the discount reduce churn", while an
odds ratio of 1.4 means "40% higher odds". Perfect separation is REFUSED rather
than reported -- statsmodels returns enormous coefficients with enormous
standard errors instead of raising, and passing that through would be emitting
garbage with a p-value attached.

**Mixed models exist because ordinary regression is wrong on panel data.**
Twelve months from each of forty stores is 480 rows but nothing like 480
independent observations; OLS treats them as if they were, the standard errors
come out too small, and everything looks significant. The effect size is the
intraclass correlation -- the share of variation between groups rather than
within them -- because "does the grouping matter at all" is the question that
motivates the model.

**Survival analysis is about CENSORING.** A customer who has not churned yet is
not a customer who never will; they are information about "at least this long".
Dropping them understates lifetimes and counting them as events overstates
churn. Cox uses them correctly, and the caveat states how many rows were
censored. The floor here is on EVENTS, not rows: ten thousand subjects with
three churns carries the information of three observations.

**The insights engine was itself a multiple-comparison problem.** It runs a
standout test per (category x measure) and a correlation test per measure-pair
-- easily twenty tests on one dataset, where roughly one reaches p < 0.05 by
chance alone. Findings are now corrected across the whole run before ranking,
by Benjamini-Hochberg rather than Bonferroni: this is exploratory scanning, not
a confirmatory trial, and Bonferroni would suppress most true findings along
with the false ones. A finding that does not survive is DEMOTED and annotated,
not deleted -- the pattern is real in those rows, it is simply not evidence
about anything beyond them.

Verified the way it should be: a frame of six random measures and three random
categories now yields ZERO significant findings, while genuine patterns among
the same noise survive. Before the correction, random data produced confident
claims.

**What this is still not.** No GLM families beyond binomial, no random slopes,
no time-varying covariates, no proportional-hazards diagnostic. SAS ships
hundreds of procedures and that remains a different order of investment -- these
are the models a business analyst actually reaches for, and the row moves
without claiming parity.

#### Reaching an object's settings

An object picker sits above the properties panel, listing every object on the
page and the page itself. Selecting on the canvas still works; the picker is
for the cases where it does not — a widget inside a container, a small one, or
one sitting under another in a precision layout.

**A control for a column a list cannot serve.** `slicer_mode: 'text'` draws a
text input instead of a value list, for columns like Customer ID. The point is
not the smaller widget: `shape_slicer` returns before any grouping, because on
a column with hundreds of thousands of distinct values BUILDING the list is
the cost, and a control that skipped the list while still paying for it would
be the same expense wearing a smaller control. An empty box clears the filter
rather than filtering on `""`, which would match nothing and read as a broken
page. `auto` never resolves to text — a reader who can see their options
should be shown them.

#### Generated prose, and why it is never load-bearing

`narrate_one` turns one already-computed finding into one sentence. Two
guards make it safe to show: a **digit guard** discards any reply stating a
number the evidence does not contain, and a shared **breaker** stops asking a
model that just failed for two minutes.

The automated explanation now offers such a sentence beside its factors —
SAS's version speaks, and ours returned bars and a plot. The rule that keeps
it honest is that narration is an ADDITION to an answer, never a precondition
for one: the endpoint computes the factors, then tries for a sentence, and
swallows every failure. An air-gapped install has no model at all, so the
absent case is the normal one — it returns `null`, not `""`, because a blank
string renders as a sentence that failed to load rather than one never
offered. When a sentence is shown it is labelled as generated: the numbers
beside it are computed, that line is not, and anyone acting on it should know
which is which.

Cost when the model is down: one timeout (8s) per breaker window, then free.
Measured on the running stack — first call 8.4s, the next three 0.0s.

#### Composed graphs

`custom_graph` is a chart built from PLOT LAYERS — what SAS calls Graph
Builder. The catalogue already held three fixed combinations (dual-axis bar,
line and bar-line); what this adds is that the combination is the author's:
how many layers, which mark each draws, which aggregation, which axis.

Two rules carried over from `shape_dual_series` and generalised. **Each layer
aggregates in its own right** — the numbers on a multi-layer chart are not the
same kind of number, which is why it has two axes, so "encounters counted,
wait averaged" has to be expressible per layer. And **layers are keyed by
position** (`s0`, `s1`), never by measure name: one column read two ways is a
common pair, and keying by name collapses it into a single series, drawing one
line where the author asked for two.

A layer whose column has gone is reported in `skipped` and named by the
renderer rather than silently absent. An unrecognised mark draws as a bar on
both sides — marks come from stored config, which outlives the list either end
knows — and `GRAPH_MARKS` is mirrored into `types/report.ts` and pinned, so
the panel cannot offer one the shaper will quietly change.

Reuse comes free: an object template already stores a configured widget, so a
composed graph saved as one is a reusable graph rather than a single chart.

#### Hierarchies: six layouts, one shaper

Tree, sunburst, icicle, dendrogram, org chart and circle packing all come from
`shape_hierarchy`. That is the same rule small multiples follows: a layout that
computed its own totals would be a second aggregation path, and two paths drift.
The renderers differ only in how they draw one nested
`{name, value, children, omitted}` contract.

**Two input modes, because hierarchies arrive in two shapes.** LEVEL COLUMNS
(`country -> region -> city`) nest by successive grouping, aggregating a measure
at every node. PARENT-CHILD (`id_col`, `parent_col`) reads an org chart or a
bill of materials, where the depth is data rather than schema.

**Partition charts refuse non-additive aggregations.** A sunburst draws value as
an ANGLE and an icicle as a WIDTH: the parent's wedge is the sum of its
children's. Feed either an average and the geometry states something false --
children that visibly do not fill their parent, with nothing to tell the reader
the picture is wrong rather than the data. A tree, dendrogram or org chart
prints the number instead of encoding it, so any aggregation is fine there, and
the refusal names the alternative.

**Children always reconcile to their parent.** Beyond twelve, the remainder
folds into an "Other" node carrying its real total -- decomposition's rule,
because a breakdown whose parts do not sum to the whole is worse than none.
Depth, breadth and a total-node ceiling are all capped, and every omission is
counted rather than silent: twelve children at eight levels would be 12^8 nodes,
and a large company's org chart is tens of thousands.

**Cycles are refused by name; orphans become roots.** A manager chain that loops
has no root and no depth, so following it hangs the renderer and silently
breaking it invents a hierarchy that does not exist -- the refusal names the
looping id. A row whose parent is absent is different: most often the parent was
removed by row-level security, so the honest rendering is a FOREST whose visible
subtrees root where the caller's permission begins. Erroring there would tell a
restricted user their data is broken.

**The tree is also the control.** Its nodes carry checkboxes and broadcast the
checked set as a multi-value filter through the same `emitMultiFilter` path a
slicer uses -- so "tree view", "tree grid" and "tree list box" are one widget
rather than three renderers over identical data differing only in whether a
checkbox is drawn. Multi-column tree grids remain a follow-up.

Drawn with divs and inline SVG. No new charting library, so the offline bundle
is unchanged.

#### Slicers offer search sooner

The auto threshold moved from 40 values to 10. Scanning a thirty-item checkbox
list for one value means reading all thirty, and the list is only as tall as its
widget, so most of it is scrolled out of sight. Search only ADDS a filter box:
enabling it early costs a reader nothing, while a wall of checkboxes costs them
the value they came for. Under five values it is still a button bar, and five to
ten a plain list -- a search box over six items is clutter.

#### The authoring path, not just the render path

Five hierarchy widgets once shipped in the palette with renderers, shapers, tests and
demo content — and **no config panel**. `shape_hierarchy` needs `levels` (or
`id_col`/`parent_col`); nothing in the UI wrote them, so every user-created
sunburst failed with *"Choose the columns that form the hierarchy"* — advice the
interface gave no way to follow. Only seed data set those keys, which is exactly
why the tests passed: they exercised the shaper, never the authoring path.

The panel now offers both input modes behind a radio pair, because the shaper's
branch is genuinely exclusive (`if id_col and parent_col:`). **Switching mode
deletes the other mode's keys** — a config carrying both would silently render
as parent-child, ignoring the levels the user just picked. That deletion is what
the test pins, not merely that the right keys appear.

Levels reuse the ordered multi-select already in the panel, whose `#n` ordinals
make "click order is nesting order" visible rather than something to be
explained.

**Sunburst, icicle and circle packing only offer adding-up aggregations.**
Their geometry encodes value as an angle, a width, or the area a parent circle
must contain, so a parent's extent IS the sum of its children's; an average draws children that visibly fail to fill their parent,
with nothing to say the picture is wrong rather than the data. Filtering the
select means the user never picks one the shaper will refuse. A tree prints the
number instead, so it accepts anything.

Small multiples had the same shape of gap with a quieter failure: without
`facet_by` the shaper degrades to one panel, so the widget silently became an
ordinary bar chart. `forecast_periods` was likewise unsettable while `method`
was.

**Mirrored constants are pinned.** The panel needs the shaper's limits to build
an honest form, so `HIER_MAX_DEPTH`, `ADDITIVE_AGGREGATIONS`, `FACET_MAX_PANELS`
and the forecast bounds exist twice. `tests/test_frontend_constant_mirrors.py`
reads the TypeScript and asserts each against Python — a drifted copy is worse
than no copy, because the panel would promise what the shaper then rejects.

#### "We could not ask" is not "there is nothing"

Several pages conflated the two. `Lineage` caught a failed fetch and set an
EMPTY GRAPH, rendering a backend outage as a confident claim that the org owns
no data assets. `Reports` and `Connections` had no catch at all, so a 500
cleared `loading` and fell through to "No reports yet" — which invites a user to
recreate work that already exists. `ReportBuilder` and `DatasetDetail` left
"Loading…" on screen forever.

All five now distinguish loading, error and empty. The shared `LoadError` is
deliberately not styled like an empty state: empty states here are inviting, with
an icon and a call to action, whereas this is an interruption with a retry,
because the correct next action is to try again rather than to create something.

Each test asserts **both** that the error appears and that the empty-state copy
is absent. The second assertion is the one that bites — a test checking only for
an error message still passes when the empty state renders beside it, which was
the bug.

`PagePropertiesPanel` swallowed the save of **page visibility**, a security
control: a failed write left the panel showing a page as restricted to certain
roles while the server still had it visible to everyone. It now reverts the
optimistic state and says so.

#### The statistics screen is one screen, not eight

Eight inferential analyses shipped with working endpoints and **no frontend
entry point at all** — half the registry was reachable only by the agent, which
can mention an analysis but not invoke one.

They get ONE screen because two facts make that correct: every endpoint takes a
flat body of column names, and every one returns the same `TestResult` envelope.
So a picker, a form built from each spec's `params_schema`, and one result card
cover all eight — and a ninth appears on its own rather than needing a ninth
screen.

The picker reads `GET /analysis/registry`, which previously had zero callers,
and filters to `result_kind === 'statistical_test'`. Its descriptions are
already written as the question a user would ask — *"Is a measure genuinely
different across groups?"* — so they are shown verbatim rather than paraphrased.

**The registry carries no route**, deliberately: it is descriptive capability
metadata, and widening it would turn that endpoint into an invocation contract.
The name-to-slug map therefore lives in `api.ts`, guarded from both directions.
`tests/test_frontend_constant_mirrors.py` fails when a statistical analysis is
registered with no frontend entry, when an entry names an analysis that no
longer exists, and when a slug does not match a served route. Registering a
ninth analysis now **cannot ship unreachable** — which is the trap this codebase
had hit five times.

**The result card gives the effect size at least the weight of the p-value.**
That is not styling. With a two-million-row import cap a p-value alone is nearly
content-free — at large n almost any difference reaches significance — so a card
leading with the asterisk would be a machine for manufacturing confident trivia.
Caveats are rendered as part of the answer rather than a footnote, because
"correlation is not causation" and "computed on a sample" change what the number
means.

#### Connection handling

- `services/connections.py` — credential storage and connection lifecycle
- `services/secrets.py` — secret material, kept out of API responses
- `services/net_guard.py` — egress control, enforcing the air-gap boundary

#### Engine registry

`services/engines.py` holds pooled SQLAlchemy engines keyed by connection identity,
so a widget render reuses a pooled connection instead of paying `create_engine` per
request. Two data sources sharing a connection string share one engine — the key is
the built URL, not the raw config — except for `:memory:` databases, where every
instance is distinct and sharing would merge their data.

| Function | Pool |
|----------|------|
| `get_engine()` | Interactive renders |
| `get_metadata_engine()` | Background catalogue sampling, `max_overflow=0` |
| `dispose_engine()` | Drop a pool before its source's storage is replaced |

The two pools are deliberately separate: sampling a catalogue several objects at a
time would otherwise occupy most of the interactive pool and surface as a stall on
someone's report. `max_overflow=0` on the metadata pool makes the sync's connection
footprint exactly `metadata_sample_concurrency` — a number someone chose rather than
one that emerged.

`dispose_engine` exists because a pool holding a file-backed SQLite source makes
unlinking it fail outright on Windows, and on POSIX keeps serving the deleted inode.

**Contract to Layer 2:** a validated, capability-described connection handle.

---

### Layer 2 — Ingestion & Metadata

**Owns:** turning a reachable source into a described, profiled, trustworthy dataset.

#### Upload path

`routers/datasets.py` accepts CSV, XLSX, JSON, and Parquet up to 100 MB (plus XML
when `lxml` is present — `SUPPORTED` registers a reader only if its parser imports).
`services/ingest.py` owns this layer's two primitives: `load_file()`, which reads
through the process-local frame memo so the same bytes are parsed once per process
rather than once per widget, and `detect_types()`, which classifies every column as
numeric, categorical, datetime, or text.

#### Metadata package

`services/metadata/` is the source-of-truth pipeline for connected sources:

| Module | Responsibility |
|--------|----------------|
| `introspect.py` | Read the source's own schema |
| `sample.py` | Pull representative rows without full scans |
| `profile.py` | Column statistics, cardinality, null rates |
| `infer_keys.py` | Primary/foreign key inference |
| `infer_semantic.py` | Semantic typing (identifier, measure, geography…) |
| `catalog_sync.py`, `sync.py` | Reconcile catalog against the live source |
| `drift.py` | Detect schema change since last sync |
| `store.py`, `cache.py` | Persist and cache metadata |

Key inference is accuracy-tested, not merely smoke-tested — see
`tests/test_infer_keys_accuracy.py`, which asserts precision/recall floors.

#### PII masking

`services/pii.py` detects personal data in a sample and masks it **before** anything
is written to the sample cache or sent to the model. There is no path where a raw
personal value reaches either — a self-hosted endpoint is still a disclosure, and a
cache is still a copy.

The mask carries a hash rather than being shape-preserving (`a****@c***.com`), because
foreign-key inference measures value overlap between columns in the masked sample:
shape-only masking would collapse distinct values together and invent relationships
that do not exist.

#### Refresh

`services/dataset_refresh.py` re-imports a dataset from its source and invalidates the
cached frame. Scheduling lives at Layer 6 (`refresh_scheduler.py`), which composes this
with alerts and delivery.

**Contract to Layer 3/4:** a dataset with typed columns, inferred keys, declared
relationships, a profile, and no unmasked personal data.

---

### Layer 3 — Storage & Persistence

**Owns:** durable state, cached state, and schema evolution.

#### Relational store

PostgreSQL 16 Alpine. **79 tables** defined in `models/models.py` via async
SQLAlchemy, grouped by concern:

| Group | Representative tables |
|-------|----------------------|
| Datasets | `datasets`, `dataset_columns`, `dataset_shares`, `analysis_results` |
| Reports | `reports`, `report_pages`, `report_widgets`, `report_parameters`, `bookmarks`, `report_user_grants`, `recent_views` |
| Security | `row_security_rules`, `report_capability`, `org_units`, `user_org_units` |
| Modelling | `relationships`, `hierarchy_nodes`, `data_views`, `common_filters` |
| Sources | `data_sources`, `source_objects`, `source_columns`, `source_relationships` |
| Identity | `organizations`, `users`, `roles`, `api_keys`, `org_idps`, `org_parents` |
| Governance | `row_security_rules`, `column_security_rules`, `object_row_policies`, `audit_log`, `admin_audit` |
| Sharing | `share_links`, `share_link_access`, `embed_configs`, `report_classifications` |
| Delivery | `report_schedules`, `deliveries`, `data_alerts`, `notifications` |
| Agent | `conversations`, `agent_messages`, `agent_runs`, `agent_steps`, `agent_feedback` |
| Retrieval | `retrieval_embeddings`, `entities`, `glossary_terms`, `query_examples` |
| Ops | `sync_runs`, `schema_versions`, `column_stats`, `materializations`, `quotas`, `query_runs` |

Schema changes go through **Alembic** (`backend/alembic/`, 34 revisions).
`postgres/init.sql` provides the initial schema and indexes.

#### Cache

`services/cache_backend.py` defines a `CacheBackend` interface with two
implementations — `InProcessCache` for single-process or test runs, and
`ValkeyCache` for the deployed stack. `services/frame_cache.py` caches computed
result frames; `core/rate_limit.py` uses the same backend for throttling.

The cache is an optimisation, never a source of truth: every cached value is
reproducible from Postgres and the source systems.

#### File storage

Uploads land in the `uploaded_files` volume, referenced by path from `datasets`.

---

### Layer 4 — Query & Semantic

**Owns:** translating widget intent into SQL that is correct, governed, and safe.

This is the layer where a request becomes a query. It has three responsibilities.

#### 1. Aggregation engine

`services/widget_data.py` turns a widget config into a result set. The config
contract is:

```
{ dimension, measure, aggregation, filters, limit, sort, sort_by, running }
```

**24 aggregations** in three groups:

- **Numeric** — `sum`, `avg`, `median`, `min`, `max`, `std`, `variance`, `range`, `p25`, `p75`, `p90`, `p95`
- **Count** — `count`, `countd`, `frequency`, `pct`
- **Statistical** — `stderr`, `skewness`, `kurtosis`, `cv`, `uss`, `css`, `tstat`, `pvalue`

  SAS offers these on any measure, so an evaluator looks for them by name. Each
  returns `None` rather than a number when the sample cannot support it — a
  t-statistic on one row, a coefficient of variation about a zero mean — because
  a fabricated statistic is worse than an empty cell.

Plus two post-aggregation metrics applied over the ordered result: `running_sum`
and `running_avg`.

#### 2. SQL construction

`services/query_builder.py` builds dialect-correct SQL from a model definition:
`build_sql(model, dialect, known, …)`, with `_quote()` handling per-dialect
identifier quoting and `introspect_tables()` validating that referenced tables and
columns actually exist before emission.

`services/sql_expr.py` and `measure_eval.py` evaluate user-authored expressions
and calculated measures. `services/parameters.py` binds report parameters.

#### 3. Governance

`core/rls.py` is the enforcement point:

| Function | Purpose |
|----------|---------|
| `apply_user_context()` | Bind the acting user to the query context |
| `resolve_rls_expr()` | Resolve the row-filter expression for this user + dataset |
| `expand_author_expressions()` | Expand author-defined rule expressions |
| `resolve_denied_columns()` | Determine columns this user may not see |

RLS is applied **during query construction**, not by filtering results afterward.
Column denial removes columns from the projection rather than blanking them.

`services/query_log.py` records executed queries; `services/display_rules.py`
resolves conditional formatting; `services/data_views.py` manages the saved
Dimensions/Measures/Dates/Text hierarchy.

`services/prep.py` belongs to this layer rather than to ingestion: it applies the
user's transformation pipeline (authored in `PrepPipelinePanel.tsx`) *and* the same
RLS machinery — `resolve_rls_expr`, `resolve_denied_columns`, `apply_rls_filter` — so
a prepared frame is governed exactly like a widget query.

#### Two execution paths

The same widget config resolves through one of two engines:

| | Import-mode | Import + DuckDB | DirectQuery |
|---|---|---|---|
| Module | `widget_data.py` | `duck_agg.py` | `direct_query.py` |
| Aggregation | pandas `groupby` | DuckDB over the file | pushed into SQL |
| Source rows loaded | whole frame, capped by `import_row_cap` | streamed, never materialised | bounded by `row_cap` |
| RLS | applied to the frame | ineligible — falls back | pushed into the `WHERE` clause |

#### DuckDB pre-aggregation

`services/duck_agg.py`, behind settings.widget_duckdb_pushdown (default **on** since 2026-08-29),
aggregates eligible import-mode queries with DuckDB and hands the small result to the
same shaper — the pattern `run_direct_query` already uses.

Eligibility is deliberately narrow: a plain dimension + measure + grain-safe aggregation
with basic filters, and none of column denial, RLS, prep steps, filter expressions,
calculated columns or measure definitions, each of which is a pandas transformation of
the full frame. Anything else, and **any** DuckDB failure, falls back to pandas.

That fallback is what makes the feature safe: unlike DirectQuery — which must raise,
having no local frame — the worst case here is the path that existed before it. Slower,
never wrong.

Measured on a 422 MB / 2M-row / 30-column CSV: **1545 MB → 60 MB** of query RSS with a
parquet sidecar present (8.4× without one, where the CSV is re-parsed).

Two semantics required explicit handling. SQL `GROUP BY` keeps NULL as a group where
pandas drops NaN keys, so the plan adds `WHERE dim IS NOT NULL`. And `total` means
*source rows*, which the shaper would otherwise derive as the group count from a
pre-aggregated frame, so the plan counts separately — after filters, before the null
drop.

Aggregated values may differ from pandas in the last bits of a float: two engines summing
one column in different orders cannot agree bit-for-bit (measured worst relative
difference 1.43e-14 over 2M rows). Group names, ordering, row counts and totals match
exactly. This is the same property DirectQuery has always had against Postgres and MySQL.

**The import path materialises the whole frame**, which is the platform's main scale
limit. Measured on 2026-08-28: a 406 MB / 2M-row / 30-column CSV costs **~1.8 GB of
RSS** to answer a five-row question — roughly 4.5× the file — and every concurrent
render holds its own frame.

`settings.import_row_cap` bounds it. The cap **refuses** rather than truncating: a
truncated frame would produce totals over an arbitrary subset with no way to say so in
the result, and a confident wrong number is worse than an error. Over the cap the
request returns **413** naming both the dataset size and the limit. It defaults to
**2,000,000 rows** — roughly where the measured 1.8 GB-per-render cost stops being
survivable on a shared box. An operator with the memory to spare can still set `0` to
disable it.

Both hand their result to the **same shaper**, `get_widget_data_from_df`, which is why
`direct_query.py` rejects aggregations that are not grain-safe: the shaper re-runs its
groupby over an already-aggregated frame, and only `sum/avg/min/max/median/percentiles`
survive that second pass unchanged. `count`, `countd`, `std`, `variance` and `range` do
not, so they are refused rather than silently computed wrong.

The unbounded source load in the import-mode column is the platform's main scale limit;
see the hardening plan, Phase 2.

**Contract to Layers 5/6:** a governed result frame, with provenance.

---

### Layer 5 — Analytics & AI

**Owns:** everything that produces an insight rather than a value.

#### Statistical analysis

`services/analytics.py` provides descriptive statistics, outlier detection,
correlation, and chi-square testing. The `services/analysis/` package adds:

| Module | Capability | Library |
|--------|-----------|---------|
| `anomaly.py` | Isolation Forest, ECOD | PyOD |
| `segment.py` | KMeans segmentation | scikit-learn |
| `registry.py` | Analysis registration and dispatch | — |

Forecasting uses **AutoETS** via `statsforecast`, surfaced as a forecast widget.
`services/insights.py` and `explain.py` generate narrative explanations of results.

#### Dashboard suggestion

Two paths, answering different questions.

`services/suggest_dashboard.py` starts from a **connection catalog** — someone
has attached a database and does not know which tables to join — and returns SQL
plus a widget list.

`services/suggest_dataset_dashboard.py` starts from a **dataset that already
exists** and a person's own description of their job, and returns whole
dashboards for that person. It is fenced three ways, because a model handed 64
widget types will otherwise propose tiles that render blank:

1. `services/dataset_profile.py` builds what the model is told — per-column
   role, cardinality, missing data, range and commonest values, plus coordinate
   pairs, parent-child references, nestings and the date span — and the menu is
   filtered by what that profile supports.
2. `services/widget_roles.py` holds `REQUIRED_ROLES`, the server-side mirror of
   the frontend `ROLE_SPECS`, pinned by a parity test. Nothing missing a
   required field survives validation.
3. Every surviving widget is **executed** through `get_widget_data` and dropped
   if the shaper reports nothing to draw.

`services/suggest_from_insights.py` is the third path, and the one that uses no
model at all. An **empty goal** means there is nothing to tailor to, so
`generate_insights` picks the charts instead and they go through the same three
gates: ~4 seconds against ~28, deterministic, and every caption is the finding's
own sentence. The response carries `source: "insights" | "model"` so the UI can
say which engine answered.

Both paths also return `relations` — pairs of widgets sharing a DIMENSION, which
the browser applies as cross-filter actions in a second pass once the real widget
ids exist. Interactions themselves persist in `widget.config.interaction`
(hydrated by `CrossFilterProvider`); before 2026-09-10 they were React state only
and were lost on every reload.

Surfaced at `POST /datasets/{id}/suggest-dashboards`, from the dataset row's ⋯
menu. It proposes only; the browser creates.

Heavy libraries are **lazily imported** — several tests assert that PyOD,
scikit-learn, and statsforecast are *not* loaded at application import, keeping
cold start fast for deployments that never use them.

#### NL→SQL agent

`services/agent/` implements natural-language querying as an explicit graph, not
a prompt chain. The pipeline (`graph.py`):

```
classify → (clarify) → context → plan → DAG[ generate → ladder → policy
                                            → execute → sanity ] → explain
```

| Module | Role |
|--------|------|
| `classify.py` | Determine question type |
| `clarify.py` | Ask back when the question is underspecified |
| `context.py` | Assemble schema context for the model |
| `plan.py` | Decompose into ordered steps |
| `dag.py`, `executor.py` | Run the step graph |
| `generate.py` | Emit candidate SQL |
| `policy.py` | Enforce what the generated SQL may do |
| `validate.py` | Structural and semantic validation |
| `explain.py` | Render the answer |
| `memory.py`, `state.py` | Conversation state |

Two design decisions are worth stating explicitly:

1. **The repair loop lives inside a node**, not as a graph edge. At most
   `MAX_ATTEMPTS` generations, each retry fed the specific validation rung that
   rejected the previous attempt. This keeps the graph acyclic and the executor
   small.

2. **The agent inherits RLS.** `graph.py` imports `resolve_rls_expr` from
   `core.rls` directly, so generated SQL is filtered by the same rules as a
   hand-built widget. A user cannot ask the agent for data their account cannot see.

#### Model client

`services/llm.py` targets a **self-hosted OpenAI-compatible endpoint** (vLLM),
configured in `core/config.py`:

```python
llm_base_url = "http://…/v1"     # self-hosted
llm_model    = "qwen3.5"
llm_enabled  = True              # False → platform runs with no AI at all
llm_max_concurrency     = 12
llm_reserved_interactive = 2
```

The client treats the endpoint as unreliable by design — it may be rebooted,
reimaged, or saturated — and degrades to a documented failure rather than
propagating an exception. `services/retrieval.py` handles embedding-based
retrieval against the embeddings container, with a circuit breaker.

---

### Layer 6 — API & Services

**Owns:** the HTTP surface, identity, and everything that leaves the system.

#### Routers

**25 router modules**, mounted with 26 `include_router` calls in `main.py` --
`analysis` and `metadata` each expose a second router. All under `/api/v1`
except the agent:

| Router | Surface |
|--------|---------|
| `datasets` | Upload, CRUD |
| `analysis` (+ `registry`) | Run and retrieve analyses |
| `widget_data` | Live widget queries |
| `reports` | Reports, pages, widgets |
| `hierarchy` | Data-view tree |
| `data_sources` | Connections |
| `relationships` | Model relationships |
| `metadata` (+ `stats`) | Catalog and profiling |
| `auth`, `sso` | Login, SAML/OIDC, provisioning |
| `admin`, `platform` | Administration, tenancy |
| `shared`, `embed` | Public links, embedded reports |
| `widget_templates`, `demo` | Templates, demo content |
| `workspace` | Report-navigation tree (folders + filed reports) |
| `notifications` | User notifications |
| `agent` | NL query (mounted at root) |

#### The automation chain

`services/automation_runner.py` runs an unattended seven-step pipeline, one
step per scheduler tick, resumable at the step that failed. `STEPS` is the
single source of truth for both the names and their order.

| # | Step | State |
|---|------|-------|
| 1 | `profile` | real — profiles the subject dataset as the run's creator, and persists the secured frame |
| 2 | `describe` | real — column roles, semantic types, provenance-aware write |
| 3 | `scan` | real — insight scan over the frame, with the recorded roles |
| 4 | `propose` | real — model or deterministic, branch recorded |
| 5 | `review` | real — deterministic gate over the proposals; below the pass ratio the run stops at `needs_review` and the creator is told |
| 6 | `compose` | real — the report, from the accepted widgets only; structural name, row values redacted from persisted text |
| 7 | `notify` | real — one in-app notification to the creator, rendered from the typed record |

##### Step 4 is where customer data leaves the chain

Two paths, and **which one ran is part of the artifact**, because step 5 judges
a model proposal and a statistical one by different standards:

| `llm_enabled` | Path | Recorded as |
|---|---|---|
| `False` | `suggest_from_insights` — deterministic, no model | `path: "insights"`, `model_attempted: false` |
| `True`, model answers | `suggest_for_dataset` | `path: "model"` |
| `True`, model fails *any* way | falls back to `suggest_from_insights` | `path: "insights"`, `model_attempted: true`, `model_error: "…"` |

"Any way" means endpoint down, timeout, malformed or non-conforming JSON, or an
empty proposal. The run continues — but **the fallback is recorded, never
swallowed**. A degraded proposal that is indistinguishable from a deliberate one
is the precise failure this chain exists to prevent, so `model_attempted` and
`model_error` travel with the artifact whether or not anything reads them yet.

**What reaches the model is masked at the boundary.** Step 1 dropped the
creator's denied columns, but *samples* are a separate exposure: a column nobody
denied can still hold addresses and phone numbers, and the profile carries
example values precisely so the model can tell what a column means.
`masked_profile_for_model` runs every sample through `pii.py` and returns a
copy, so the profile on disk and the profile the model saw stay distinguishable.

It adds a per-**value** pass that `build_profile` cannot do: classification is a
majority verdict over a column, so a column that is mostly city names and
occasionally an email address is not personal as a whole, while the individual
sampled value still is.

**Free-text columns whose sentences embed PII are not masked, deliberately.**
A `notes` column reading "emailed a.person@example.com about the invoice"
reaches the model with that address in it.

This is an accepted boundary, not a gap. `pii.py`'s patterns are anchored and
its majority rule exists for exactly this case — "one email address inside a
free-text notes column must not turn the whole column into PII — masking it
would destroy real data to protect one value." Prose is the thing a model most
needs in order to understand a dataset, and blanket redaction removes the signal
with the address.

If that trade-off ever has to tighten, **the change belongs at the payload edge
(`masked_profile_for_model`), not in `pii.py`.** That function is the one place
customer data crosses out of the chain, so an unanchored scan added there
narrows only what a model sees. The same scan inside `pii.py` would also reach
column classification, sample masking and the preview path, and would start
destroying prose on surfaces that were never the concern.

##### Row values reaching persisted text, and what to do if it happens

The first real run of the chain produced a report **named after a customer's
email address**. The address was in one row of a free-text `notes` column;
`insights.py` builds finding titles out of a categorical column's actual values
(`f"{low_name} trails the other {cat} values on {m}"`), and the composer took
that title verbatim. It landed in `reports.name`, `reports.description` and a
summary widget — an indexed column, Recents, and every list a report appears in.

Two boundaries now stand where one was assumed:

- `redact_row_values` scrubs text at the point it is **persisted or displayed**,
  on both the model and the deterministic path. Its patterns are derived from
  `pii._PATTERNS` with the anchors stripped, so there is one definition. Bare
  digit runs (card, national id) are excluded on purpose: matched unanchored in
  prose they would redact order numbers, years and row counts.
- The report **name is structural** — dataset, finding columns, finding kind.
  Redaction alone would leave it one new phrasing in `insights.py` away from
  leaking again, so the name is built only from things that cannot carry a row
  value.

**If this reaches real data,** deleting the reports is the wrong answer — that
destroys work a customer may depend on, and the automated ones may already be
filed, shared or embedded. The procedure is:

1. Find the affected rows: `reports.name`, `reports.description`, and
   `report_widgets.config` for any widget of type `text`, plus `notifications`.
   Scope to `reports.origin = 'automation'`; a person's own report name is
   theirs and must not be rewritten under them.
2. Re-derive each name with `_compose_name`, which is now structural, and scrub
   descriptions and text widgets with `redact_row_values`. Both are pure
   functions and can run as a data migration.
3. Leave the **source dataset untouched.** The address in the uploaded file is
   the customer's own data, correctly stored; only the derived metadata was
   wrong.

The two reports from the first run were deleted rather than repaired because
they were throwaway test output from a synthetic fixture, minutes old, and
referenced by nothing. That is not the general answer.

##### The secured frame, and what a run leaves behind

Steps 3–5 need the **rows**, not a description of them. Step 1 therefore writes
`frame.parquet` beside `profile.json`, holding the frame it already secured, and
records its address in the profile as `frame_ref`.

The alternative was each of those steps re-reading the dataset and re-applying
RLS, denied columns and prep in the right order — three more copies of the
ordering `test_rls_base_frame_choke_point` exists to protect, and the third copy
is the one somebody gets wrong.

That makes it the most dangerous artifact the chain produces: the profile holds
samples, the frame holds **every row the creator may see**. Three consequences:

- **Temp name, then `os.replace`.** A half-written parquet behind a committed
  `output_ref` is truncated customer data reaching a model in step 4 — strictly
  worse than a half-written description. Pinned by a test that kills the write
  partway and asserts nothing exists at the final name.
- **A size ceiling** (`automation_frame_max_mb`, default 256). Over it the step
  **refuses** and writes nothing, the same call `import_row_cap` makes; `0`
  disables it for an operator with the disk.
- **`discard_run_artifacts` removes the run directory when the run reaches
  `done`** — in one place, the way `dataset_cleanup.py` removes what a dataset
  leaves behind. A mid-flight run keeps its artifacts, because the next step
  reads them. Cleanup never raises: a file left behind is a disk problem, an
  exception there would turn a finished run into a failed one.

##### The structured record: what a run produced, in typed columns

`discard_run_artifacts` deletes a run's directory the moment it reaches `done`.
The first real run composed a report with a meaningless lead KPI, and by the
time anyone looked, the 17 proposals it was chosen from were gone — the gate
fix could not be checked against the proposals that had actually passed it.
**Model output is not reproducible**: the same dataset and prompt produced a
materially different set on the next run. An uncaptured proposal set is gone
for good, and it is the only material that makes a later quality claim
checkable.

So the record lives on `AutomationRun`, in typed columns (migration 0032):

| Column | Written by | Why a column |
|---|---|---|
| `proposal_path` | step 4 | Home filters "what did the model produce" |
| `raw_proposals` | step 4 | the set the gate judged — stored *before* the gate, whole |
| `widgets_accepted`, `widgets_rejected` | step 5 | ordering by how much was rejected |
| `rejection_reasons` | step 5 | per-widget `{title, widget_type, reason}` |
| `result_report_id`, `result_report_name` | step 6 | what to open |
| `error` | steps 5, review exit | why it stopped |

One writer, `record_run_result(session, run_id, **fields)`, refuses a field that
is not a column. That guard exists because `run.error` was assigned in three
places and persisted in none: the model had no such column, Python allowed the
attribute, SQLAlchemy dropped it on commit, and the test that checked it read
the in-memory value in the same session. Every `needs_review` reason and every
rejection reason was silently lost until 0032.

**Typed columns are the source of truth.** `describe_run` derives a sentence
from them at render time; nothing parses a sentence back. Tests for the record
read every value back after `expunge_all()`, never from the session that wrote
it — the only assertion that can tell a persisted column from a Python
attribute.

`AnalysisResult` gained `run_id`, `params` and `created_by` in the same
migration: a saved regression whose predictors are not recorded is
uninterpretable, and a result with no run cannot be reached from the run that
made it.

##### Step 7: the notification is a rendering, not a record

`describe_run(run) -> (text, link)` derives one sentence from the typed
columns above, every time it is called. `notify_run(session, run)` passes that
sentence to the existing `services/notifications.notify` as kind
`"automation"` — the one in-app channel; there is no second one — for the
run's **creator only**. The report was composed from the creator's rows, so a
colleague's copy of the link would 404 or open numbers that are not theirs.

The notification row carries a *copy* of the sentence because that is what a
notification is. It is never read back by anything: Home filters and orders
by the columns and calls `describe_run` for the words, so the bell and Home
say the same thing without either parsing the other.

Two callers, one code path. Step 7 (`_notify_step`) runs for a run that
composed; it consumes the record, not merely step 6's ref — a compose ref
with no `result_report_id` behind it is refused, not announced. Step 5's
hold calls the same `notify_run` the moment it sets `needs_review`, because
the run leaves the active set there and step 7 never runs for it; a run that
stops for a decision and tells nobody is work nobody knows exists. The two
sentences differ on purpose — one is something to open, the other something
to decide — and a held run's link is `None` until runs have a page of their
own, because a link to nowhere is worse than no link.

Step 7 returns a `db://notifications/...` ref rather than an artifact: the
row is the output, and the ref commits in the same transaction as the row,
so a crash between them re-runs both or neither — one row per run, not one
per tick. The bell (`NotificationsBell.tsx`) renders an unknown kind with its
default icon and navigates on `link`, so no frontend change was needed.

##### Relationship access outside a request

Anything a step reaches through an ORM relationship must be **eagerly loaded**.
Under async SQLAlchemy an implicit relationship access is not slow, it is
illegal — `MissingGreenlet` — and it only fails when the related row is not
already in the session's identity map. So it passes in tests that built the rows
moments earlier and fails on a cold scheduler tick.

This module has been bitten twice: `_fail` reading `step.attempts` after
`rollback()` expired it, and `can_read_dataset` opening with
`user.role.is_org_admin`. The second is fixed in **one** place —
`_load_creator` — because eager-loading at six call sites means forgetting it at
one. A test that clears the identity map with `expunge_all()` is the only kind
that catches this.

Four properties hold for every step, real or stub:

- it runs as the run's **`created_by`**, never headless — RLS here is
  per-user, so a headless step would compose a dashboard from rows the
  creator cannot see, and it would look like a success;
- it **consumes the previous step's `output_ref`** rather than recomputing;
- it writes a real `output_ref` or raises `StepRefused` — never a ref it did
  not earn, which is the invariant resume depends on;
- it reads on the loop and wraps blocking work in `asyncio.to_thread`, so one
  step cannot stall the shared tick. `test_step_and_analysis_contracts` pins
  this: a step either threads, or is named in `DB_ONLY_STEPS` with its reason.

##### Step 2 bridges the identifier concept into the analyses

This step exists because of a specific, visible failure: **Key influencers
ranked `student_id` as a top driver**, having cut an identifier into quantile
ranges. Ranges of an identifier describe row order.

The detection was never missing. Four copies of it existed —
`infer_semantic.classify_role` (canonical: name pattern *or* near-uniqueness),
`widget_data._is_id_like_column` (name only, used by the profile),
`columnRole.ts` (the frontend mirror), and `influencers`' own level-count rule.
What was missing was a path from any of them to the place analyses read.

Two gaps caused that, and step 2 closes both:

1. **`registry.run_analysis` never passed `column_meta`**, and all 18 runnable
   handlers would have raised `TypeError` if it had. `AnalysisSpec` now carries
   `consumes_column_meta`, declared per analysis with **no default**;
   `run_analysis` forwards roles only to a spec that asked for them. Handing it
   to every handler was rejected deliberately: a paired t-test has no use for
   roles, and a parameter that every handler accepts while most ignore it
   cannot be told apart from one that is consulted.
2. **`Dataset.column_meta` had no `identifier` role to read.**
   `insights.effective_roles` maps to `categorical`/`numeric`/`datetime` only,
   so even with the data in hand it could not express the case. Step 2 writes
   `classify_role`'s answer into `column_meta` through
   `metadata.store.apply_inferred_column_semantics`, which owns the
   `confirmed > declared > inferred` ladder. **A field with a value but no
   source marker is treated as confirmed**, not as unmarked-and-free —
   everything written before this function existed was authored by a person
   through the Fields pane.

`influencers._usable_factors` now calls `classify_role` **before** the
numeric/categorical split, because the bug was branch-specific: the
categorical branch had a check and the numeric branch never reached one.

Step 2 consumes step 1's `profile.json` and never re-reads the dataset file.
That is a security property, not an optimisation: step 1 filtered the frame by
the creator's RLS and dropped their denied columns *before* profiling, so a
second read would be a second, unsecured path to the same data.

#### Workspace tree

Reports carry `org_id` and nothing positional, so `workspace_nodes` supplies the
navigation menu: one row per folder or filed report, ordered by `position` within a
parent. Folders and reports share one sibling sequence, so an author can put an
important report above a folder.

**Pages are not stored.** The tree renders folders → reports → pages, but `ReportPage`
rows already have their own ordering and the tree endpoint joins them at read time --
persisting copies would leave the menu stale whenever a page is added in the builder.
A report node likewise stores no name, reading through to the report so a rename is a
single edit.

Two contracts protect user work, both tested by removing the guard and watching the
tests fail:

- **Deleting a folder never deletes a report.** `parent_id` is `ON DELETE CASCADE`, so
  children are re-parented to the deleted node's parent first -- the same fix
  `routers/hierarchy.py::delete_node` carries, whose comment records the bug that
  produced it. Removing a *report* node unfiles the report; the report reappears at root.
- **A node cannot move into its own subtree.** `hierarchy.py` has no such guard (small
  hand-built trees), but a cycle in the org's navigation menu hangs the renderer for
  everyone. The ancestor walk is bounded by node count, so an already-cyclic tree cannot
  hang the request trying to fix it.

Every report is reachable: one with no node is returned under `unfiled`. The tree is
navigation, not an optional tag.

**Creating is open; changing and removing belong to the author.** Any member may make
folders and file reports — gating that would mean nobody but an admin can organise their
own reports, which is how a folder tree ends up unused. Editing or deleting a node is
limited to whoever created it (`created_by`) and to org admins, who need a way to tidy
up after people who have left.

`created_by` is nullable and set to NULL when its user is deleted, so a folder outlives
the person who made it. An unowned node is **admin-only**: “nobody owns it” must not read
as “anybody may delete it”.

#### Who sees which folders

A folder can be restricted to roles (`workspace_folder_roles`). **No rows = visible to
everyone in the org** — grants restrict, they are not a licence that must first be
issued. Any other default would empty every non-admin menu the day it shipped, which is
the same reasoning `PageRoleVisibility` and `ReportCapability` record in their own
docstrings.

Restriction is **subtree-effective**: a report filed inside a folder the viewer cannot
see is absent from their tree entirely — not relocated to `unfiled`, which would defeat
the restriction by moving the entry rather than hiding it. Admins and the folder's
creator always see it: an admin locked out could not administer the lock, and an author
who cannot find what they filed would simply make another copy.

Filtering happens **server-side**. Sending the whole tree and hiding parts in the client
would make the response itself the leak.

> **This is menu visibility, not access control.** `GET /reports/{id}` returns a report
> to any member of the org regardless of where it is filed, so someone who knows a
> report id can still open it. Report ACCESS is `ReportCapability`; row and column
> access are the RLS rules. Hiding a menu entry is tidiness and least-astonishment.
> `TestVisibilityIsNotAccessControl` asserts this deliberately, so that turning the menu
> into an ACL breaks a test rather than quietly making this paragraph wrong.

#### Identity and authorisation

| Module | Responsibility |
|--------|----------------|
| `core/security.py` | Password hashing, JWT issuance/verification |
| `core/api_keys.py` | Programmatic access |
| `core/capability.py` | Capability checks |
| `core/org_scope.py` | Organisation scoping on every query |
| `services/sso.py`, `saml.py` | SAML and OIDC |
| `services/auth_provisioning.py` | Just-in-time user provisioning |
| `services/org_access.py` | Cross-organisation access rules |

Authorisation is layered: **organisation scope** (Layer 6) constrains which rows
are reachable at all; **RLS** (Layer 4) constrains which of those the user may see.

#### Outbound

- `services/pdf_export.py` — server-side PDF rendering
- `services/delivery.py` — scheduled distribution
- `services/alerts.py` — data-condition alerts
- `services/notifications.py` — in-app notifications
- `services/eval_schedule.py` — scheduled evaluation runs

#### Sharing and embedding

`routers/embed.py` issues token-addressed embed configs with **origin
allow-listing** (`_origin_allowed`) and per-widget visibility resolution
(`_visible_widget`), evaluated against the *creator's* permissions. There is no
per-viewer licence concept.

Both public surfaces shape their pages through **one** function,
`_shape_page` in `routers/shared.py` — the embed reaches it via
`visible_pages_for_creator`. A page publishes a derived **`interaction_mode`**
string rather than its `mobile_layout` blob: the mode is the only part of that
JSON a viewer needs, and publishing a whole internal blob to an anonymous
surface is how fields leak. Unrecognised values collapse to `manual`, because
`mobile_layout` is author-written and an unknown mode reaching the frontend's
union would silently mean *no* interactions rather than an error anyone sees.

This field exists because the viewers previously received no mode at all, so
every published page fell back to manual and each widget obeyed its own
setting — the exact opposite of what an automatic page mode means. The same
omission left saved per-widget interactions unhydrated in both viewers.

#### Middleware

CORS is configured in `main.py`. The global exception handler is registered
**after** `CORSMiddleware` so it sits inside it — otherwise a 500 would carry no
`Access-Control-Allow-Origin` header and the browser would report a misleading
CORS violation instead of the real error.

#### Health probes

Three endpoints, with a deliberate split:

| Endpoint | Semantics | Touches dependencies? |
|----------|-----------|----------------------|
| `/health` | Liveness. The original path; compose and external monitors point here | No |
| `/health/live` | Alias of `/health`, named for the k8s convention | No |
| `/health/ready` | Readiness — is this replica servable right now? | Yes |

Liveness is static **by design**: a liveness probe that opens a database connection
turns a 30-second Postgres blip into a restart loop across every replica, which is
worse than the outage it detects.

`/health/ready` grades its dependencies rather than treating them alike. Postgres is
required — unreachable returns 503. Valkey is optional and only probed when
`valkey_url` is set; because `ValkeyCache` fails soft onto an in-process cache behind
a circuit breaker, a broken Valkey reports `degraded` and still returns 200. Migration
state is read from a `_STARTUP_COMPLETE` flag set at the end of lifespan, so a replica
still running Alembic reports `not_ready`.

Failure bodies carry the exception **type name only** — connection errors can embed the
DSN, and this endpoint is unauthenticated.

**A dead SOURCE is not a dead server.** A DirectQuery dataset queries the
customer's database on every render, and when that is unreachable the failure
is not this application's. `run_direct_query` translates connection-level errors
(`OperationalError`, `InterfaceError`) into `SourceUnavailable`, which the widget
path answers with a **502 naming the source** — previously it escaped to the
generic handler and a reader saw "Internal server error" on their widget,
sending them to our logs for somebody else's outage.

Translated in the SERVICE rather than in each router: there are four call
sites and they would drift. Only connection-level failures are caught — a bug in
the shaping code, or a table the source no longer has, still escapes as a 500
(the first version caught `DBAPIError`, the parent of every SQL error, and
reported a renamed table as an unreachable database), because turning every exception into
"the source is down" is a comfortable lie that hides our own faults. The
driver's text is dropped rather than reformatted, for the reason this section
already gives: a connection error embeds the DSN and a DSN embeds the
password.

#### Error contract on the widget path

Every error a widget render can produce carries a **code** beside its text, on
both channels a widget receives:

```json
{"detail": "<the same text as before>", "code": "row_cap"}
{"type": "error", "code": "measure_error", "message": "...", "rows": [], "total": 0}
```

`detail` is unchanged and still a string, so nothing that read it before
changes; `code` is additive. The set is closed and lives in
`services/error_codes.py` (pure data — a service may not import FastAPI);
the exception is `core/widget_errors.py`, and its `widget_error(status,
code, text)` is the one way
the widget router raises, it refuses a code not in the set, and
`tests/test_widget_error_codes.py` pins structurally that no bare
`HTTPException(` remains in `routers/widget_data.py`. The one widget-path
error that is not an HTTPException — `QuotaExceeded`, translated by its own
handler in `main.py` — writes its code there, and is pinned at the endpoint.

| code | status | means | retry? |
|------|--------|-------|--------|
| `parameter` | 400 | a report parameter is missing, unknown or the wrong type | no |
| `unsupported` | 400 | the feature does not exist here (a DirectQuery engine, an export format) | no |
| `forbidden_column` | 403 | the widget references a column this role cannot see | no |
| `forbidden` | 403 | this role may not read the dataset | no |
| `not_found` | 404 | the dataset, or its file on disk | no |
| `row_cap` | 413 | the import row cap; names the size and the limit | no |
| `source_unavailable` | 502 | the customer's database could not be reached | **yes** |
| `measure_error` | 200 | a measure expression could not be evaluated (second channel) | no |
| `internal` | 500 | ours | no |
| `quota` | 429 | the org's daily query quota; `Retry-After` says when | **yes** |

The second channel existed before the code did, and nothing on the frontend
read it: a measure that failed to evaluate came back as a 200 with empty rows
and the widget drew an empty chart, message discarded. `WidgetRenderer` now
renders both channels, and offers **Try again** for `source_unavailable` only —
the one code whose answer can differ a second later.

---

### Layer 7 — Presentation

**Owns:** authoring and rendering reports.

React 18 · TypeScript · Vite · Recharts.

#### Pages

**16 pages** in `frontend/src/pages/`:

| Page | Purpose |
|------|---------|
| `ReportBuilder.tsx` | The designer — the largest module in the codebase |
| `DatasetDetail.tsx` | Analysis viewer |
| `Dashboard.tsx`, `Reports.tsx` | Dataset and report lists |
| `Upload.tsx` | Drag-and-drop ingestion |
| `Connections.tsx` | Data source management |
| `SourceReview.tsx` | Metadata review and approval |
| `Lineage.tsx` | Model lineage graph (`reactflow`) |
| `SharedReport.tsx`, `EmbeddedReport.tsx` | Public and embedded views |
| `ReportPrint.tsx` | Print/PDF layout |
| `Home.tsx` | Landing page — recents, dashboards, datasets as card sections |
| `Dashboard.tsx` | The dataset list (route `/datasets`) |
| `AskAI.tsx` | The agent's own page — scope picker over `ChatPane` |
| `InsightsHub.tsx` | One front door to the analysis capabilities (links into `DatasetDetail` anchors) |
| `Login.tsx`, `SsoCallback.tsx` | Authentication |
| `admin/` | Administration screens |
| `monitoring/` | Monitoring screens — jobs, deliveries, activity (admin-gated) |

#### Widget system

**67 widget types** declared in `types/report.ts` as `WidgetType` and catalogued
in `WIDGET_CATALOG` (the source of truth — do not maintain a parallel list):

| Category | Types |
|----------|-------|
| **Charts** | bar, line, step, dot plot, needle, histogram, butterfly, area, funnel, ribbon, pie, donut, scatter, treemap, four dual-axis variants, comparative/numeric series, bubble (+change), correlation matrix, heatmap, parallel coordinates, box plot, waterfall, gauge, schedule (Gantt), vector plot, word cloud, forecast, sankey, network |
| **Controls** | KPI, card, table, crosstab, matrix, list, text, image, shape, button, slicer, web content, custom visual, container |
| **Maps** | choropleth, points, bubbles, lines, clusters, pie, layers, density, network |

Rendering is dispatched by `WidgetRenderer.tsx` to per-type modules in
`components/report/chartRenderers/`. Maps render through `d3-geo` and
`topojson-client` against a bundled `world-atlas` — a deliberate choice that keeps
geospatial working without external tile services, and therefore offline.

#### Interaction model

`CrossFilterContext.tsx` holds page-level filter state. Each widget declares an
interaction mode:

| Mode | Emits | Receives |
|------|-------|----------|
| Two-way ⇄ | yes | yes |
| Broadcast → | yes | no |
| Receive ← | no | yes |
| Isolated — | no | no |

Active filters surface in `FilterBar.tsx` with individual clear controls. The
strip renders on the builder, on a shared link and inside an embed, and stays
visible when nothing is filtering — an empty strip and no strip at all look
identical, and only one of them tells the reader the page can be filtered.

**Edge integrity.** Per-pair actions (`config.interaction.actions`) address
their targets by widget id, so an edge can outlive what it points at. Two
things keep the graph honest, because a dead edge neither throws nor logs —
the selection is dropped by one of `getFiltersFor`'s early returns and the
author, who tested the path they wired, never sees it:

- `_prune_actions_targeting` in `routers/reports.py` strips edges aimed at a
  widget as it is deleted. It runs on the SERVER because the copilot, the
  composer and the API all delete widgets without touching builder state, and
  it leaves widgets with no `actions` untouched — writing an empty list onto
  one would change its meaning from "reaches everything" to "reaches only the
  targets listed here, of which there are none".
- `reviewReport` in `ReviewPane.tsx` reports the edges that survive anyway: a
  target that no longer exists, one on another page (page-scoped filters never
  arrive), one set not to receive, per-pair actions on a page whose automatic
  mode ignores them, and a page where nothing will react at all.

**A column can carry a geography role.** `column_meta[col] = {role:
'geography', boundary_set_id}` says which boundaries a column draws with, and
it belongs on the COLUMN because that is where the fact lives — the same
column is a map in every report that uses it. Resolution order at render time
is `config.boundary_set_id` (a deliberate per-widget override) → the column's
classification → countries.

It is published to shared links and embeds as a derived `geography` mapping,
never as `column_meta` itself, which also carries `__prep_steps__` — the same
rule `interaction_mode` follows. Resolution is deliberately NOT done inside
`get_widget_data`: that result is cached on its inputs, and `column_meta` is
not one of them, so a reclassified column would serve the old shapes until the
cache turned over.

Two consequences worth keeping: dropping a classified column onto the canvas
produces a `map_choropleth` rather than a bar of counts (that is what the role
is FOR, and without it the classification was invisible), and deleting a
boundary set clears the classifications that referenced it — a dead id would
silently fall back to countries while the column still called itself geography.

**Map pins are outside all of this, on purpose.** `config.pins` holds
author-placed annotations drawn by `GeoPointMapRenderer` on the coordinate
maps. They are not rows, so the whole pin group is `pointerEvents: none` and
never enters `markers` — which is what keeps them out of both the click path
and `markersWithin`, the lasso's membership test. A pin that could broadcast
would filter the page to a label no row holds, and every other widget would
answer "no rows" with nothing on screen to explain why. Pins join the
projection's fit, though: an annotation outside the data's extent would
project off-canvas, present in the DOM and invisible.

#### Supporting modules

`contexts/AuthContext.tsx` holds session state. `services/api.ts` is the Axios
client. `lib/` contains pure helpers — `sqlWhere.ts`, `simpleExpr.ts`,
`displayRules.ts`, `columnRole.ts`, `pptExport.ts` (client-side PowerPoint export),
`widgetImage.ts` — each with a colocated test.

---

### Cross-cutting concerns

These deliberately span layers rather than sitting in one.

| Concern | Implementation | Spans |
|---------|---------------|-------|
| **Security** | `core/rls.py`, `org_scope.py`, `capability.py`, `security.py`, `api_keys.py` | 3–7 |
| **Audit** | `services/audit.py`, `admin_audit.py`, `audit_log` table | 3–6 |
| **Observability** | `core/telemetry.py` (OpenTelemetry traces + metrics), `query_log.py`, health probes in `main.py` | 1–6 |
| **Rate limiting & quotas** | `core/rate_limit.py`, `services/quotas.py` | 3, 6 |
| **PII handling** | `services/pii.py` (masking runs at sampling time, Layer 2) | 2 |
| **Caching** | `cache_backend.py`, `frame_cache.py`, `metadata/cache.py` | 2–4 |
| **Offline operation** | `net_guard.py`, `scripts/build_offline_bundle.ps1` | all |

#### Observability

`core/telemetry.py` exports **traces and metrics** over OTLP, opt-in via
`otel_enabled` (default off). Disabled is a hard no-op: nothing imports
`opentelemetry`, and both the tracer and the metric instruments are pure-Python
null objects, so the hot path pays an attribute lookup and a discarded call.

| Instrument | Answers | Labels |
|-----------|---------|--------|
| `widget.query.duration` | is it slow, and where? | executor, cache_hit |
| `widget.query.total` | how much traffic, how much failing? | executor, cache_hit |
| `cache.operations` | is the cache working, or are we recomputing? | result |
| `quota.rejections` | are tenants hitting limits? | quota |

Deliberately few: metrics are cheap to emit and expensive to maintain. Labels are
low-cardinality by design — quota rejections are labelled by *kind*, never by message,
since storage-quota text interpolates the limit and would mint a series per value.

Two isolation rules, both learned from the tracer. Metrics setup sits in its own `try`,
so a collector that takes traces but rejects metrics degrades to "tracing works" rather
than losing both. And instruments are module attributes reassigned at setup, so call
sites must write `telemetry.widget_query_total` — a `from` import would freeze the
disabled no-op forever.

Spans additionally pass through a `_QuerystringScrubber` that strips query strings from
every span before export, because the embed surface carries a live host-signed token in
its URL.

#### Offline / air-gapped operation

The platform is designed to run with no internet access:

- Frontend assets are bundled, not CDN-loaded — pinned by `offlineAssets.test.ts`
- Map geography ships with the image (`world-atlas`)
- The model endpoint is self-hosted; `llm_enabled=False` removes the AI layer
- `scripts/build_offline_bundle.ps1` produces image tarballs plus a `MANIFEST.json`
  recording exact image IDs and digests for transfer across the air gap

See `docs/OFFLINE_DEPLOYMENT.md`.

#### Durable state

Two volumes must survive; everything else is reconstructible.

| Store | Volume | Loss means |
|-------|--------|-----------|
| PostgreSQL | `postgres_data` | Total loss — every report, dataset, user, rule |
| Uploaded files | `uploaded_files` | Import-mode datasets cannot render |
| Valkey cache | container-local | Nothing; rebuilt on demand |
| Embeddings model | baked into the image | Nothing; redeploy the image |

The two durable volumes must be captured **as a pair, files first**. A database
restored without `uploaded_files` looks intact — datasets listed, reports openable —
and fails at the first import-mode widget render.

`scripts/backup.ps1` and `scripts/restore.ps1` implement the procedure, including
the ordering rule (files first on backup, database first on restore) that makes a
stray file the only possible inconsistency. Backup verifies the dump's `PGDMP`
header before rotating, so a run of failures cannot delete the last good backup.

See `docs/BACKUP_AND_RECOVERY.md` for procedures and the verification drill.

---

### Request lifecycles

#### A widget renders

```
WidgetRenderer (7)
  → api.ts POST /api/v1/datasets/{id}/widget-data (7→6)
    → routers/widget_data.py: authn, org scope (6)
      → services/widget_data.py: parse config (4)
        → core/rls.py: resolve row filter + denied columns (4)
          → query_builder.py: build dialect SQL (4)
            → frame_cache (3) or direct_query (4)
              → source engine or Postgres
        ← result frame
      ← aggregation + running metrics applied (4)
    ← JSON
  ← chartRenderers/<Type>Renderer.tsx (7)
```

#### A natural-language question

```
Agent pane (7)
  → routers/agent.py (6)
    → services/agent/graph.py (5)
        classify → clarify? → context (schema from metadata store, 2/3)
        → plan → DAG:
            generate SQL (llm.py → self-hosted vLLM)
            → ladder/policy/validate (5)
            → resolve_rls_expr (4)  ← governance inherited
            → execute (4→3, or 1 for a live source)
            → sanity check (5)
          [bounded repair loop on rejection]
        → explain (5)
    ← answer + provenance, persisted to agent_runs/agent_steps (3)
```

---

### Testing

| Suite | Scope | Count |
|-------|-------|-------|
| Backend | `backend/tests/` | ~4,600 tests across 360 modules |
| Frontend | colocated `*.test.ts(x)` | 2,297 tests across 172 files |
| Evals | `backend/evals/` | Agent quality gates (`run_eval_gate.ps1`) |
| Conformance | `tests/test_layer_conformance.py` | Enforces the layer boundaries above |
| Doc audit | `tests/test_architecture_doc.py` | Enforces the *counts* in this document |

**One level the suites cannot reach.** Every frontend test runs in jsdom,
which has no layout (everything measures 0×0), a thin `PointerEvent` and no
real CSS — so "it renders" and "a person can use it" are different questions.
`backend/scripts/ui_walkthrough.py` answers the second by driving the served
app in Chromium and photographing each surface. Its first run found six
defects that every green test had missed, including two forms offered on
datasets that cannot run them.

It needs the PYTHON Playwright in a venv of its own (the Node package wants
Node 20; this environment has 18), and it must point at the SERVED app —
an origin outside `allowed_origins` is blocked by CORS, which the login page
reports as "Invalid email or password".

`backend/scripts/compat_check.py` runs the same journey in **Chromium,
Firefox and WebKit** and records each engine separately, because the useful
output is the difference between them. First run: no engine-specific defect —
identical control counts, 55 charts, zero console errors, zero 5xx in all
three.

It found something better than an engine bug. The builder header was a
non-wrapping flex row inside a parent with `overflow:hidden`, so at 1366×850 —
one of the commonest laptop resolutions — the "Edit mode" button sat 150px
past the window edge with **no scrollable ancestor and no document overflow**.
Not awkward to reach: unreachable. `flexWrap` on that row is therefore
load-bearing, and the guard test says so, though jsdom cannot measure the
overflow it prevents.

**This document is tested.** Every count above — connectors, tables, widgets,
aggregations, pages, router modules, Alembic revisions — is re-derived from the tree
and compared against both `ARCHITECTURE.md` and `ARCHITECTURE.html`. Change the code
without updating the prose and the build fails; change one document without the other
and it fails too.

That test exists because on 2026-08-28 this document claimed 46 connectors while the
registry held 43. The wrong figure came from reading the spec list by eye, and it had
already reached a second document and a published comparison before anyone re-derived
it. Prose rots silently because nothing reads it.

Counts are derived, never hard-coded: the assertion is "whatever the registry holds is
what the document says", so adding a connector fails the test until the document
follows — rather than the test needing an edit that nobody reads.

Backend tests run against **in-memory SQLite** (`tests/conftest.py`) — no live
Postgres required. Both suites are green.

#### Environment notes

Two environment issues affect local runs:

1. ~~**Console encoding.**~~ **Fixed 2026-08-28.** `test_infer_keys_accuracy.py`
   printed box-drawing characters in its report header, which Windows' default
   `cp1252` console cannot encode — raising `UnicodeEncodeError` before the
   assertions ran. The header is now ASCII; the suite passes on a stock Windows
   shell with no environment overrides.

2. **Run from a virtualenv built from `backend/requirements.txt`.** A missing
   `pytest_asyncio` makes `tests/conftest.py` fail to import; pytest then exits
   **4** and collects nothing. The exit code is correct, but note that a wrapper
   around pytest may collapse it to 0 — an RTK-proxied invocation did exactly
   that here, reporting "No tests collected" with a zero exit. Trust pytest's
   own exit code, not a wrapper's.

   `backend/conftest.py` (rootdir) additionally asserts a minimum collected-test
   count, so a run that silently loses most of the suite fails instead of passing.
   It stands down for deliberate subset runs (`-k`, `-m`, `--lf`, explicit paths,
   or `DATALYTICS_ALLOW_PARTIAL_COLLECTION=1`).

---

### Extension points

| To add… | Touch |
|---------|-------|
| A data source | Append a `ConnectorSpec` to `_ALL_SPECS` in `connectors.py` |
| An upload format | A reader in `SUPPORTED` (`ingest.py`) — or, for a container of many tables, its own path like `services/mdb.py` |
| A widget type | `WidgetType` + `WIDGET_CATALOG` in `types/report.ts`, a renderer in `chartRenderers/`, config in `WidgetConfigPanel.tsx` |
| An aggregation | `AGGREGATIONS` in `types/report.ts` and the engine in `services/widget_data.py` |
| An analysis | Register in `services/analysis/registry.py` |
| An agent capability | A node in `services/agent/nodes/`, wired in `graph.py` |
| A schema change | An Alembic revision in `backend/alembic/versions/` |
