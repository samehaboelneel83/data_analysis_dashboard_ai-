# Datalytics

Datalytics is a self-hosted data analytics platform. You bring in your data, explore it, ask questions in plain language, and build interactive dashboards — without sending the data to a third-party BI cloud.

The running application lives in [`data_analytics/`](data_analytics/).

---

## What it is

Think of it as an in-house analytics workspace:

1. **Get data in** — upload files, or connect to a live database.
2. **Understand it** — profiles, insights, statistics, and an AI chat that answers from *your* data.
3. **Show it** — build dashboards with charts, maps, tables, and filters.
4. **Share it safely** — users, roles, row/column security, publish/grant, share links, and embeds.

It is multi-organization: each organization has its own users, data, and dashboards. A platform super-admin can create and manage organizations.

The UI is available in **English** and **Arabic** (right-to-left layout).

---

## How it works

```
Browser (React)  →  API (FastAPI)  →  PostgreSQL
                         │
                         ├── uploaded files (CSV, Excel, …)
                         ├── live databases (DirectQuery)
                         ├── optional LLM  (Ask AI, descriptions)
                         ├── Valkey        (shared chart cache)
                         └── embeddings    (better search for Ask AI)
```

| Piece | What it does |
|---|---|
| **Frontend** | The web app you use. Default address after Docker: `http://localhost:3001` |
| **Backend** | The API. Stores metadata, runs queries, security, schedules. Default: `http://localhost:8000` |
| **PostgreSQL** | App database (users, orgs, dashboards, connections). Host port `5433` |
| **Valkey** | Optional shared cache for widget results. If it is down, charts still work from an in-process cache |
| **Embeddings** | Optional local model used to improve Ask AI retrieval. If it is down, a simpler search is used instead |
| **LLM** | Optional. Needed for Ask AI and for auto-generated table/column descriptions. Sync and dashboards still work without it |

**Two ways data is used**

- **Import** — a copy is stored on the server (good for files and for analyses that need the full table in memory).
- **DirectQuery** — charts query the live database each time (good when the source is large or must stay current).

Security is applied on every read: organization isolation, then row-level and column-level rules for the signed-in user.

---

## Start it

You need Docker.

```bash
cd data_analytics
docker compose up --build
```

Then open **http://localhost:3001**.

The first time there is no login account until you create one. Copy the seed script into the backend container and run it (from `data_analytics/`):

```bash
docker cp scripts/seed_dev_accounts.py datalytics_backend:/tmp/seed_dev_accounts.py
docker exec -it datalytics_backend python /tmp/seed_dev_accounts.py
```

It creates these accounts (password for all: `demo-password`):

| Email | Role |
|---|---|
| `admin@datalytics.local` | Platform / org admin |
| `admin@contoso.invalid` | Org admin (Contoso) |
| `analyst@contoso.invalid` | Analyst |
| `admin@northwind.invalid` | Org admin (Northwind) |
| `analyst@northwind.invalid` | Analyst |

After login, on **Datasets** you can click **Load demo content** to get sample datasets and dashboards.

API health: `http://localhost:8000/health` (alive) and `http://localhost:8000/health/ready` (database ready).

---

## First hour in the product

1. Sign in (email + password, or SSO if an admin configured it).
2. Open **Datasets → Upload** and drop a CSV/Excel file, *or* **Datasets → Connections** and point at a database.
3. Open the dataset. Look at the profile, then try **Insights** or **Ask AI**.
4. Open **Dashboards**, create a dashboard, drop widgets onto a page, save.
5. Publish or share when you are ready.

---

## What you can do today

### Data in

- **File upload** — CSV, Excel (`.xlsx` / `.xls`), JSON, XML, Parquet. Microsoft Access (`.mdb` / `.accdb`) becomes one dataset per table. You can upload several files at once (separate datasets, or append). Default per-file limit is 100 MB.
- **Live connections** — PostgreSQL (and many Postgres-wire databases), MySQL/MariaDB family, SQL Server / Azure SQL, Oracle, SQLite, DuckDB, Access, a generic SQLAlchemy URL, ODBC, and a Web API. Cloud warehouses (Snowflake, BigQuery, Databricks, ClickHouse, Trino) appear in the catalog when their driver is installed; they are import-only unless the driver is present.
- **Query builder** — visual join / filter / aggregate over a connection, saved as a dataset (the design is kept so you can edit it later).
- **Import or DirectQuery** — copy the data in, or leave it in the source.
- **Scheduled refresh** — imported datasets can refresh on an interval.
- **Connection catalog** — after a sync, Datalytics samples tables, infers types and likely relationships, and can draft descriptions (if an LLM is configured). You review and confirm on the connection’s **Review** page.
- **Relationships** — declared or inferred joins between datasets, used by dashboards and Ask AI.

### Prepare and model

See [Prepare and model — what it means, and how to try it](#prepare-and-model--what-it-means-and-how-to-try-it) below. Short version: this is **not** a machine-learning model. It is the *shape* you give your data (clean, join, calculated fields, measures) so charts and Ask AI can use it.

### Ask questions (Ask AI)

Open **Ask AI**, pick a dataset or a live connection, and ask in plain language.

Behind the scenes the agent classifies the question, may ask for clarification, writes SQL, checks it against a safety ladder, injects row-security, runs it, and explains the result. You can see the SQL. It can work on imported files or on a live source.

Answers stay inside your organization and respect the same security as charts.

### Insights and statistics

See [Insights and statistics — in plain language](#insights-and-statistics--in-plain-language) below. Short version: the product can scan a table for interesting facts, and it can run real statistical tests. None of that needs an LLM.

### Dashboards

Called “Dashboards” in the UI; URLs still use `/reports`.

- Drag-and-drop **report builder**: multiple pages, page types (normal, hidden, popup, tooltip, drill-through), desktop and mobile layout.
- **Themes**, display rules, bookmarks, comments, parameters, common filters, cross-filtering, slicers.
- **Auto-compose / suggest widgets** from the dataset.
- **Page templates** and reusable widget templates.
- **Workspace tree** — folders of dashboards, with publish and role access.
- **Draft vs published**, plus **grants** to specific people (`view` / `edit` / `data`).
- **Capability by role** on a dashboard: view, edit, or full data authoring.
- **Page visibility** per role.
- **Sensitivity labels** — Public, Internal, Confidential, Restricted.
- **Translations** per locale (used together with the English/Arabic UI).
- Export a dashboard as **PDF** or **PowerPoint**, or print. Individual widgets can export as an image or as data (CSV / TSV / Excel / PDF), subject to export policy.

**Visual types available now**

Charts: bar, line, area, pie, donut, scatter, treemap, step, histogram, waterfall, funnel, ribbon, butterfly, dual-axis (bar, line, bar-line, time series), comparative time series, bubble, bubble-change, heatmap, correlation matrix, parallel coordinates, box plot, gauge, Gantt/schedule, vector, word cloud, needle, dot plot, numeric series.

Maps: choropleth, points, bubbles, lines, clusters, pie, layers, density, geo network.

Analytics visuals: forecast, Sankey, network graph, decomposition tree, tree, sunburst, icicle, dendrogram, org chart, small multiples.

Controls / layout: KPI, card, table, crosstab, matrix, list, text, image, shape, button, slicer, web content, custom visual, container.

### Share and deliver

- **Share links** — a public (or token) URL to a dashboard; can be pinned to a snapshot.
- **Embed a dashboard** — iframe in another site (not the same as “embeddings”). See [Two different words that both say “embed”](#two-different-words-that-both-say-embed).
- **Email schedules** — SMTP (`smtplib`) or a Teams/Slack webhook. See [Email schedules and data alerts](#email-schedules-and-data-alerts--do-they-work).
- **Data alerts** — fire once when a condition becomes true. Backend + scheduler work; demo seeds an example. See the same section.
- **Notifications** in the app (bell).

### Security and admin

| Area | What it covers |
|---|---|
| **Users & roles** | Create users (including CSV bulk), roles, org-admin flag |
| **Organization chart** | Org units; used by hierarchical row-security (`MYSCOPE()`) |
| **Row security** | Filter expressions per role/dataset, including auto-generate |
| **Column security** | Hide columns from a role |
| **Export policy** | Block all exports, specific formats, or auto-block when security rules exist |
| **SSO** | Per-org OIDC or SAML |
| **API keys** | Long-lived keys that act as the user (for scripts / MCP) |
| **Audit trail** | Admin actions |
| **Monitoring** | Refresh jobs, dataflows, report schedules, alerts; email deliveries; activity |
| **Platform** | Super-admins manage organizations, quotas, and org hierarchy |

Connection passwords are encrypted at rest. Private/loopback hosts can be blocked for connectors in production.

### Home

Home is a landing page: recent dashboards you actually opened, datasets, and tiles you pinned — not a dump of everything in the org.

---

## How the app learns a database when there is no LLM

**It does not use static SQL templates to invent the schema.** It **reads the real database catalog**, the same way any SQL tool does.

When you save a connection and open **Datasets → Connections → Metadata** (`/connections/:id/review`), a **sync** runs. That sync talks to the source with ordinary database introspection (SQLAlchemy Inspector):

| Stage | Needs an LLM? | What you get |
|---|---|---|
| List tables and views | No | Names, kinds (table vs view) |
| Columns, types, primary keys | No | Mapped to integer / numeric / text / datetime / boolean / json |
| Foreign keys **declared in the database** | No | Treated as facts, full confidence |
| Sample rows + statistics (nulls, distinct counts, top values) | No | Used later for charts, review, and Ask AI |
| Infer extra joins by value overlap | No | Proposed relationships you confirm |
| Semantic type (email, phone, currency-looking names, …) | No | Local regex / statistics |
| Measure vs dimension vs identifier | No | From uniqueness and distinct counts |
| “This table looks deprecated” (`_old`, `_bak`, …) | No | A flag, not a deletion |
| **Plain-language descriptions** of tables/columns | **Yes** | Skipped if LLM is off or unreachable |
| Ask AI answers in English/Arabic | **Yes** | The chat fails honestly: “the model endpoint could not classify the question” |

If the LLM is down:

- Sync **still completes**. You still see tables, columns, types, keys, samples, and proposed joins.
- Description fields stay empty (or keep an older human-confirmed description).
- Dashboards, uploads, prep, insights, and statistics **keep working** — they never ask the LLM for SQL (see below).
- Ask AI **cannot answer** — it will not guess SQL from a canned template.

The LLM is an optional extra sentence on top of a catalog the database already provided.

### How charts / prep / insights run with no AI

**Ask AI is the only feature that needs a model to invent SQL from English.** Everything else already knows the columns, because **you picked them in the UI**.

Think of Excel: you never need ChatGPT to draw a pivot table. You choose “Region” and “Sum of Revenue”; Excel does `GROUP BY`. Datalytics is the same idea.

**Charts (imported file)**  
The widget stores a small config, for example `{ dimension: "region", measure: "revenue", aggregation: "sum" }`. The backend loads the CSV/Excel into memory (pandas) and groups/sums **in Python**. No LLM, and often **no SQL at all**. For large CSVs it may run an equivalent DuckDB statement that **code assembled** from that same config (`SELECT region, SUM(revenue) … GROUP BY region`) — still not generated by a model.

**Charts (DirectQuery / live database)**  
Same widget config. Python fills a SQL **template**:

```sql
SELECT "region", SUM("revenue") AS "revenue"
FROM ( … your table or saved query … ) AS src
GROUP BY "region"
ORDER BY 2 DESC
LIMIT 50
```

The words `region` and `revenue` came from the fields you dropped on the chart, not from an AI. Filters, row-security, and the table name are plugged in the same way. Unsupported aggregations are refused rather than guessed.

**Prep**  
Each step is a JSON recipe you built (`rename`, `filter_rows`, `join`, …). The engine applies them with pandas (filter this column, join that file). No SQL invention.

**Insights and statistics**  
Load the file (with your security rules), then run ordinary stats: means, correlations, clustering, t-tests. The “narrative” on an insight scan is a **filled-in sentence template** with those numbers, not a chat model.

| Feature | Who decides the columns? | How numbers are computed |
|---|---|---|
| Chart / table widget | You, in the builder | pandas, or SQL **built from your config** |
| Prep / dataflow | You, as steps | pandas following the saved recipe |
| Insights / statistics | Automatic scan, or you pick columns for a test | pandas / scipy / sklearn |
| Ask AI | The model, from your question | LLM writes SQL → safety checks → run |

**Try it:** Connections → **+ New Connection** → Test → save → **Browse** (see tables without any AI) → **Metadata** → **Run sync**. On the review page, confirm the high-confidence joins. That confirmed graph is what Ask AI is later allowed to join on.

---

## Prepare and model — what it means, and how to try it

### What “the model” is

In BI products, a **model** is the *business shape of the data*, not a neural network:

- which columns are categories vs numbers
- calculated fields (`revenue - cost`)
- measures used in charts (`SUM(sales)`, `% of total`)
- joins between tables
- folders/hierarchies in the field list

Excel has a table. A **model** is “this table, cleaned, related to that other table, with a profit column and a Year-Month hierarchy, ready to drop onto a chart.”

**Prepare** = clean and reshape rows (Power Query style).  
**Model** = name the fields, calculations, and relationships charts will use.

### Try each piece in the UI

You need at least one **imported** dataset (upload a CSV, or **Load demo content**). DirectQuery datasets skip the prep pipeline (there is no local file to transform).

1. **Prep pipeline** (clean / join / aggregate)  
   Open **Datasets** → click a dataset → tab **Data**. On the left, the transform pipeline. **Add** a step (filter, sort, remove duplicates, rename, change type, split, trim, case, find & replace, remove columns, drop/fill empties, join another dataset, aggregate). A live preview shows rows in → rows out. Click **Save pipeline**. The original file is never overwritten; turning a step off restores the old values.

2. **Save as a new dataset (materialize)**  
   On the same panel, after a preview you like, click **Save as new dataset…**. That writes a *snapshot* dataset. Open it later and click **Rebuild** to replay the same recipe on current source data.

3. **Dataflows**  
   Left rail → **Dataflows** → **New dataflow** (pick a source dataset). A dataflow owns the recipe, can produce several outputs, has its own schedule and who may edit it. **Run** it from that page. Outputs appear as normal datasets.

4. **Calculated columns** (row-by-row)  
   Same **Data** tab, **Calculated columns**. Example: `revenue - cost`. Preview, then save. These exist on every row before a chart aggregates.

5. **Group & bin**  
   Directly under calculated columns. Turns a number or many categories into buckets (age groups, price bands). Saved as a calculated column.

6. **Measures** (after aggregation)  
   Same tab, **Measures**. Example: `SUM(sales) / TOTAL(SUM(sales))` for percent of total. These are what a bar chart uses, not a new column in the table.

7. **Global filter**  
   Same tab, **Global Filter**. An expression applied to every dashboard that uses this dataset (for example `region == 'North'`). **Test** shows how many rows pass, then save.

8. **Preview filters**  
   The **Filters** box above that only filters the table you are looking at on this page. It does not change reports.

9. **Hierarchies**  
   Open a **Dashboard** in the builder. Left field panel → **Hierarchy** → **Auto-generate** (from column types), or edit the tree. Drag a hierarchy onto the canvas to chart its first level.

10. **Relationships**  
    Confirmed on **Connections → Metadata** (inferred + declared FKs), and also as dataset-to-dataset relationships the builder can use.

11. **Lineage**  
    Left rail → **Lineage**. Three columns: connections → datasets → dashboards. Click a node to see what feeds it and what would break if you deleted it.

12. **Query builder** (from a live connection, not from a file)  
    **Datasets → Connections → Query builder**. Pick tables, joins, filters, grouping. Save as a dataset (import or DirectQuery). Open the dataset later and you can edit the same design.

---

## Insights and statistics — in plain language

These features **compute on your numbers**. They do not ask the LLM. Insight scan and segmentation need an **imported** file (not DirectQuery).

Open **Insights** in the left rail, pick a dataset, then a card — or open the dataset and use the **Overview** / **Statistics** tabs.

### Insight scan (Overview → Insights)

Click **Generate insights** (or the Insights hub card). The engine walks the table and writes ranked findings. The summary paragraph is **template text with real figures**, not ChatGPT.

| Kind | Everyday meaning | Example |
|---|---|---|
| **trend** | This period vs the average of earlier periods | “March revenue is 40% above the prior months” |
| **standout** | One category carries an unusually large share | “West is 62% of total sales” |
| **laggard** | The weakest member of an otherwise even group | “Store 4 is far below the other stores” |
| **correlation** | Two numbers move together | “Discount and units sold rise together” |
| **outlier_impact** | Extreme rows and how much of the total they are | “12 rows are outliers and hold 18% of revenue” |
| **data_quality** | Missing values or holes in dates | “31% of `end_date` is empty” |

Each card has a score (how interesting) and can be **pinned** to Home. In the dashboard builder, the Insights pane can turn a finding into a chart or **auto-compose** a page.

### Anomalies

Overview → **Anomalies** / **Inspect outliers**. Flags unusual rows in a numeric column.

- **IQR** — classic “box plot fences” (default, simple).
- **Isolation Forest** — a tree method that hunts odd combinations of values.
- **ECOD** — scores how rare a row is compared with the rest of the distribution.

You also see how much those rows move the total.

### Key influencers

Overview → pick an **outcome** column → **What drives this?**  
“When `plan` is Premium, churn is 1.9× the baseline.” This is **association**, not proof of cause. The UI prints that caveat.

### Patterns (association rules)

Overview → **Values that travel together**.  
“Customers on Premium also pick Express shipping more often than chance.” Reports **lift**, **confidence**, and row counts. Co-occurrence, not causation.

### Segments

Overview → **Segments**. Groups similar rows with K-means (k chosen automatically, 2–8). You get cluster sizes, centroids, and a silhouette score (how cleanly the groups separate). Import-only.

### Statistical tests (dataset → Statistics tab)

These answer “is this difference real?” Every result includes an **effect size** next to the p-value (with huge tables, p-values alone are almost always “significant”).

| Test in the UI | Question it answers |
|---|---|
| **compare_groups** | Is a number different across groups? (t-test or ANOVA) |
| **pairwise_comparisons** | After ANOVA, *which pairs* differ? |
| **test_independence** | Are two categories related? (chi-square) |
| **correlation_test** | Do two numbers move together more than noise? |
| **regression** | How much does each predictor move a numeric target? |
| **glm_logistic** | What changes the odds of a yes/no outcome? |
| **mixed_model** | Repeated measures inside groups (stores, patients) |
| **survival** | What changes *how long* something takes? (Cox; keeps unfinished rows) |

Pick a test, fill the column names, **Run**. Errors name the real problem (“only 3 events; Cox needs about 10 per predictor”).

### Forecast (on a dashboard, not the Insights hub)

In the report builder, add a **Forecast** widget. Methods: AutoETS (default) or a simpler Holt–Winters fallback.

---

## Two different words that both say “embed”

They are unrelated. Mixing them up is the usual confusion.

### 1. Embeddings (Ask AI search quality)

An **embedding** is a list of numbers that represents the *meaning* of a sentence. “Customer invoices by month” and “فواتير المبيعات الشهرية” can land near each other even when the words look different.

Datalytics uses that **only to rank which tables/columns to show the LLM** when you ask a question. It does not answer the question by itself. See [Ask AI retrieval](#ask-ai-retrieval-lexical-vs-embeddings) below.

### 2. Embed a dashboard in another website

This is an **iframe**, like embedding a YouTube video.

**Try it**

1. Open a dashboard in the builder → **Share**.
2. In the embed section, **Create embed config**. Copy the **secret** (shown once).
3. Your *other* website’s server signs a short-lived JWT (max 24 hours) with that secret. The snippet in the dialog shows Python (`pyjwt`).
4. The iframe URL is `/embed?token=THAT_JWT` (for example `http://localhost:3001/embed?token=...`).

The browser is not trusted to pick the rows. The host’s signed token can add extra filters. Row security still uses the **admin who created the embed**, so the iframe can never show more than that person could see.

A **share link** (`/shared/:token`) is simpler: the URL itself is the ticket, no host app required.

---

## Email schedules and data alerts — do they work?

**Yes, the code path is real.** Sending mail uses Python’s built-in **`smtplib`** (standard SMTP). There is no SendGrid/Mailgun SDK. Teams/Slack **incoming webhooks** (`https://...`) can be pasted as recipients too (text + link, no file attached).

Configure SMTP in the backend environment (`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from`, `smtp_starttls`). If `smtp_host` is empty, a run is **recorded as** `SMTP is not configured` instead of crashing. The schedule still exists; nothing arrives in an inbox.

### Email a dashboard on a calendar

1. Open a dashboard → right panel **Schedule** (clock).
2. Recipients (emails and/or `https://` webhooks), daily/weekly/monthly (or an interval), timezone, Excel or PDF.
3. **Add schedule**, then **Run now** to test without waiting.
4. Status under the schedule says what happened (`emailed 2`, or the SMTP error).
5. **Delivery history** is on the same panel; org-wide: **Monitoring → Deliveries**.
6. **Subscribe** in the dashboard header lets a person add themselves.

The attachment is built as the **schedule creator** (their row security), never as “nobody, so show everything.”

### Data alerts

Backend + scheduler are live: a condition such as `AVG(margin_pct) < 25` is checked on an interval. Email is sent **once when it becomes true**, then silence until it clears and fires again. The in-app bell also rings (so you still see it with no SMTP).

**How to see one today:** **Load demo content** seeds `Demo — margin below target` on the demo sales dataset (interval is set so it does not spam). **Monitoring → Refresh & jobs** lists it. Creating a new alert is `POST /api/v1/datasets/{id}/alerts` (name, expression, interval, recipients). There is not a full “New alert” form in the UI yet; monitoring and the bell are the viewer.

---

## MCP server — can this app be used as MCP now?

**The FastAPI app itself is not an MCP server.** Docker Compose does not start MCP.

What exists: a **separate small process** at `data_analytics/backend/mcp_server/`. It speaks MCP over **stdio** (the usual Claude Desktop / Claude Code pattern) and is a thin HTTP client of your already-running API.

So: Claude (or any MCP client) can use **your Datalytics**, as **your user**, if you start that process. It cannot bypass org isolation or row security.

**How to run it**

1. App already up (`docker compose up`).
2. Log in, or create an **API key** (Admin → API keys). That bearer token is the identity.
3. On a machine with Python:

```bash
pip install -r data_analytics/backend/mcp_server/requirements.txt
```

```json
{
  "mcpServers": {
    "datalytics": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "…/data_analytics/backend",
      "env": {
        "DATALYTICS_URL": "http://localhost:8000/api/v1",
        "DATALYTICS_TOKEN": "paste-login-or-api-key-here"
      }
    }
  }
}
```

Tools today: `list_datasets`, `get_dataset_schema`, `query_data`, `list_reports`, `list_data_sources`, `list_connectors`, `create_report`, `add_widget`, `create_data_source`.

---

## Ask AI retrieval: lexical vs embeddings

When you ask “how many cancelled orders?”, the agent must **pick the right tables** from a large catalog before it writes SQL. That ranking is **retrieval**. It is not the LLM answering; it is “which schema lines go at the top of the prompt.”

### Backend A — lexical (always on)

TF-IDF over **words** plus **character 3–5-grams**, in pure numpy. No extra container. Good when the question and the table name share tokens (`orders` ↔ `orders`). Character n-grams help Arabic and coded names (`st_cd`). A question token that matches an enum **label** (e.g. “cancelled” → `st_cd=3`) gets a small score boost.

If ranking fails completely, the prompt falls back to a **fixed catalog order**. The ask still runs.

### Backend B — embeddings (Docker Compose, default on)

Compose starts `datalytics_embeddings`: a local ONNX model (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions). The backend POSTs to `http://embeddings:8000/v1/embeddings`.

Usefulness: the question and the table **description** can match by **meaning**. Arabic descriptions vs an English question, or “monthly sales invoices” vs a table named `v_inv_m`. Lexical search often ranks the wrong near-duplicate table; embeddings reduce that.

If the embeddings container is down, slow, or the vector size does not match: the code **logs once, opens a circuit, and uses lexical search**. Ask AI does not 500.

Embeddings **do not replace the LLM**. No LLM → still no chat answer. Embeddings only improve *which* tables the LLM sees first.

### How to see which path is used

**1. Is the embeddings container healthy?** (from the host; that port is not published, so exec in)

```bash
docker compose exec embeddings python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

Expect `"status": "ok"` and `"dim": 384`.

**2. Does the backend have it configured?** Compose sets `EMBEDDING_BASE_URL`. Inside the backend:

```bash
docker compose exec backend python -c "from app.core.config import settings; print(settings.embedding_base_url, settings.embedding_model, settings.embedding_dim)"
```

**3. Built-in comparison (best demo)** — ranks a tiny fake catalog, prints lexical vs embeddings side by side (Arabic discrimination):

```bash
docker compose exec backend python scripts/smoke_embeddings.py arabic
```

You want Backend B’s top hit to be the table whose **description** matches the question, not merely the one that shares a word.

**4. Prove fallback**

```bash
docker compose stop embeddings
docker compose exec backend python scripts/smoke_embeddings.py killcheck
```

Ranking must still return a result (lexical), not hang or raise. Start it again with `docker compose start embeddings`.

**5. See it in the product**

Ask AI needs a working **LLM**. With both LLM + embeddings: ask something that does not share the table’s English name (synonym, or Arabic). Open the SQL / steps on the answer: the chosen table should be the semantically right one. Then `docker compose stop embeddings` and ask again — chat still works, but table choice may get worse on messy catalogs.

**6. Logs**  
Backend logs mention falling back to lexical scoring when Backend B fails. Embeddings logs show `/v1/embeddings` traffic when it is used.

---

## Project layout

```
AI_data_tool/
└── data_analytics/
    ├── docker-compose.yml     # postgres, backend, frontend, valkey, embeddings
    ├── frontend/              # React + TypeScript (Vite)
    ├── backend/               # FastAPI app (app/), tests, Alembic
    ├── embedding_server/      # local multilingual embeddings (ONNX)
    ├── postgres/              # first-boot SQL
    └── scripts/               # e.g. seed_dev_accounts.py
```

Environment defaults live in `data_analytics/.env.example`. Copy to `.env` next to `docker-compose.yml` if you need to change secrets, upload size, or the LLM endpoint.

---

## What it is not

- Not a hosted SaaS. You run the containers.
- Ask AI is not magic: it writes and runs SQL against the data you scoped. No LLM means no chat answers (the rest of the product still runs).
- Insight scan and segmentation need an **imported** dataset, not DirectQuery.
- Cloud warehouse connectors need their Python drivers installed on the backend image before they can connect.
- The web app is not an MCP server. MCP is an optional sidecar process you start yourself.
