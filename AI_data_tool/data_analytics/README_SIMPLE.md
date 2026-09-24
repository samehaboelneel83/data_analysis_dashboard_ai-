# Datalytics, explained simply

Datalytics is a web app for looking at data without writing code. You bring
data in — a file you upload, or a database you connect — and then you can
build dashboards from it, ask it questions in plain language, and let it
find things worth noticing on its own. Everyone sees only the rows and
columns they are allowed to see; that rule is applied once, underneath
everything, so no page can leak what another page hides.

It runs as three containers: a **PostgreSQL** database, a **Python/FastAPI**
backend and a **React** frontend. `docker compose up` starts all three.
(Setup, ports and the API are in [README.md](README.md); the full technical
design is in [ARCHITECTURE.md](ARCHITECTURE.md).)

---

## The idea in one picture

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

## The pages, and what each one is for

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

## How "Ask AI" turns a question into an answer

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

## Security, in two sentences

**Row rules** say which rows a person may see (a regional manager sees their
region). **Column rules** say which columns (nobody in Support sees salary).
Both are set once in Admin and enforced in one place, so dashboards, Ask AI,
Insights, exports and shared links all obey them without being told.

---

## Sharing

A dashboard can be shared by link, embedded in another site, printed to PDF,
or delivered by email on a schedule. Every one of those goes through the same
security as the page itself.

---

## Where to go next

- **Try it:** [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md)
- **The dashboard builder in detail:** [docs/DASHBOARDS_PAGE.md](docs/DASHBOARDS_PAGE.md)
- **The Insights page in detail:** [docs/INSIGHTS_PAGE.md](docs/INSIGHTS_PAGE.md)
- **Running it without internet:** [docs/OFFLINE_DEPLOYMENT.md](docs/OFFLINE_DEPLOYMENT.md)
- **Backups:** [docs/BACKUP_AND_RECOVERY.md](docs/BACKUP_AND_RECOVERY.md)
- **How it is built, layer by layer:** [ARCHITECTURE.md](ARCHITECTURE.md)
