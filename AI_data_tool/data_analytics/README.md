# Datalytics v2 — Containerised Data Analytics Platform

> New here? Read [README_SIMPLE.md](README_SIMPLE.md) first — what the app is,
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

## Quick start

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

## Features

### Datasets
- Upload CSV · XLSX · JSON · Parquet (up to 100 MB)
- Auto-detect column types: numeric, categorical, datetime, text
- Full statistical analysis: descriptive stats, outliers, correlations, chi-square

### Report Builder
- Multi-page reports with named, reorderable pages
- 12 widget types on a 12-column grid canvas:
  - **Charts:** Bar, Line, Pie, Donut, Scatter, Treemap
  - **Controls:** KPI Card, Table, Crosstab, List, Text, Button
- **Properties panel** per widget: dimension, measure, aggregation, sort, limit

### Aggregations (16 options)
| Group   | Options |
|---------|---------|
| Numeric | Sum, Average, Median, Min, Max, Std Deviation, Variance, Range, P25, P75, P90, P95 |
| Count   | Count, Count Distinct, Frequency, Percentage % |

Plus **Running Sum** and **Running Average** post-aggregation metrics for bar/line/list.

### Cross-filtering
Click any chart bar / pie slice / table row to filter all other widgets on the page.
Each widget has an **Interaction mode** (set in Properties):
- **Two-way ⇄** — emits and receives filters
- **Broadcast only →** — filters others, ignores incoming
- **Receive only ←** — reacts to others, never emits
- **Isolated —** — completely independent

Active filters shown in the **Filter Bar** with individual clear buttons.

### Data View Hierarchy
Saved per-dataset folder tree (Dimensions / Measures / Dates / Text).
- Auto-generate from detected column types
- Add folders, rename nodes, change node type and aggregation
- Persistent in PostgreSQL

---

## Stack

| Layer    | Technology |
|----------|-----------|
| Database | PostgreSQL 16 Alpine |
| Backend  | Python 3.12 · FastAPI · SQLAlchemy async · asyncpg |
| Analysis | pandas · numpy · scipy |
| Frontend | React 18 · TypeScript · Vite · Recharts |
| Infra    | Docker · Docker Compose |

---

## Project structure

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

## API reference

### Datasets
```
GET    /api/v1/datasets
POST   /api/v1/datasets            multipart: file, name, description
GET    /api/v1/datasets/{id}
DELETE /api/v1/datasets/{id}
```

### Analysis
```
POST   /api/v1/datasets/{id}/analysis   body: { analysis_type: "full|numeric|categorical|datetime" }
GET    /api/v1/datasets/{id}/analysis
```

### Widget data (live query)
```
POST   /api/v1/datasets/{id}/widget-data
body: { config: { dimension, measure, aggregation, filters, limit, sort, sort_by, running } }
```

### Reports
```
GET/POST        /api/v1/reports
GET/PATCH/DELETE /api/v1/reports/{id}
POST/PATCH/DELETE /api/v1/reports/{id}/pages/{pid}
POST/PATCH/DELETE /api/v1/reports/{id}/pages/{pid}/widgets/{wid}
```

### Hierarchy
```
GET/POST        /api/v1/datasets/{id}/hierarchy
PATCH/DELETE    /api/v1/datasets/{id}/hierarchy/{node_id}
POST            /api/v1/datasets/{id}/hierarchy/auto-generate
```

---

## Development (without Docker)

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

## Reset everything
```bash
docker compose down -v   # drops the postgres volume
docker compose up --build
```
