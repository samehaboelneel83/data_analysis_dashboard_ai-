# Project Workflow — Data Analysis Dashboard AI

This document explains how the pieces fit together and how to use them day to day.

---

## 1. Big picture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  Browser    │────▶│  prompt.py   │────▶│  Qwen LLM   │     │  PostgreSQL  │
│  chat.html  │     │  FastAPI     │     │  :8000/v1   │     │  192.168...  │
└─────────────┘     └──────┬───────┘     └──────▲──────┘     └──────▲───────┘
                           │                    │                   │
                           │  1) schema + ask   │                   │
                           │  2) get SQL ◀──────┘                   │
                           │                                        │
                           │  3) run SQL via Wren CLI               │
                           └────────────────────────────────────────┘
                                    maps_project (MDL + profile)
```

**Roles:**

| Piece | Role |
|--------|------|
| `chat.html` | Chat UI — you type questions |
| `prompt.py` | Orchestrator — NL → SQL → execute → answer |
| Qwen (`10.125.18.189:8000`) | Generates SQL from your question + schema |
| Wren CLI + `maps_project` | Semantic layer + runs SQL on Postgres |
| PostgreSQL | Real data store |

---

## 2. Folder map

```
data_analysis_dashboard_ai/
├── prompt.py              # FastAPI server (chat + legacy prompt API)
├── chat.html              # Main chat frontend  → http://localhost:5000/
├── index.html             # Raw LLM prompt tester → /prompt-ui
├── requirements.txt
├── maps_project/          # Wren project (your DB semantic layer)
│   ├── .env               # DB credentials (gitignored)
│   ├── connection.yml     # Profile template
│   ├── wren_project.yml   # Project config (profile: maps_project)
│   ├── generate_mdl.py    # Rebuild models from Postgres schema
│   ├── models/            # One folder per table (MDL YAML)
│   ├── relationships.yml  # Foreign keys / joins
│   ├── knowledge/         # Business rules + NL→SQL memory
│   └── target/mdl.json    # Compiled schema used by chat + Wren
└── WrenAI/                # Upstream WrenAI source (reference only)
```

---

## 3. Main runtime workflow (chat)

**Start:**

```powershell
conda activate db
cd "D:\Omda 2025\projects\data_analysis_dashboard_ai"
python prompt.py
```

Open: **http://localhost:5000**

**What happens when you send a message:**

1. Browser `POST /api/chat` with your natural-language question.
2. `prompt.py` loads table/column summary from `maps_project/target/mdl.json`.
3. It calls Qwen (`/v1/chat/completions`) with:
   - system prompt = schema + “return one SELECT in a sql block”
   - user message = your question
4. It extracts the SQL from the model reply.
5. It blocks anything that is not read-only (`SELECT` / `WITH` only).
6. It runs: `wren query --sql "..." -o json` inside `maps_project`.
7. Wren uses the MDL + profile to hit PostgreSQL.
8. Rows come back; Qwen briefly summarizes them.
9. UI shows: **answer + generated SQL + results table**.

```
You ask
  → Qwen writes SQL (using MDL schema)
    → Wren executes SQL
      → Postgres returns rows
        → Qwen summarizes
          → Chat shows answer + SQL + table
```

---

## 4. Setup workflow (already done once)

These steps created `maps_project`. Re-run only when DB schema changes.

| Step | Command / action | Result |
|------|------------------|--------|
| 1. Install | `pip install "wrenai[postgres,memory,main]"` in conda `db` | Wren CLI available |
| 2. Credentials | `maps_project/.env` | Host, user, password |
| 3. Profile | `wren profile add maps_project --from-file connection.yml` | Saved in `~/.wren/profiles.yml` |
| 4. Init | `wren context init --empty` | Project scaffold |
| 5. Bind | `wren context set-profile maps_project` | Project ↔ Postgres |
| 6. Generate MDL | `python generate_mdl.py` | `models/*` + `relationships.yml` |
| 7. Validate | `wren context validate` | Checks MDL |
| 8. Build | `wren context build` | Writes `target/mdl.json` |

**Refresh schema after DB changes:**

```powershell
conda activate db
cd maps_project
python generate_mdl.py
wren context validate
wren context build
```

Then restart (or rely on) `python prompt.py` so chat uses the new `mdl.json`.

---

## 5. Two UIs

| URL | File | Purpose |
|-----|------|---------|
| `http://localhost:5000/` | `chat.html` | **Main product** — ask → SQL → Wren → results |
| `http://localhost:5000/prompt-ui` | `index.html` | Raw prompt to Qwen only (no Wren / no DB) |

Use **chat** for data questions. Use **prompt-ui** only to debug the LLM.

---

## 6. Wren without the chat UI

Useful for debugging SQL / connection:

```powershell
conda activate db
cd maps_project

wren profile debug
wren query --sql "SELECT COUNT(*) FROM maps_states" -o json
wren context show
```

---

## 7. Data flow (who talks to whom)

| From | To | Protocol |
|------|----|----------|
| Browser | `prompt.py` | HTTP `POST /api/chat` |
| `prompt.py` | Qwen vLLM | HTTP `POST .../v1/chat/completions` |
| `prompt.py` | Wren CLI | subprocess `wren query` |
| Wren | PostgreSQL | Postgres (profile from `.env`) |

Qwen **never** connects to the database. Only Wren (via your machine) does.

---

## 8. Environment checklist

| Need | Value |
|------|--------|
| Conda env | `db` |
| LLM | `http://10.125.18.189:8000/v1/chat/completions`, model `qwen3.5` |
| DB | `postgresql://...@192.168.50.165:5432/postgres` (in `.env`) |
| Wren project | `maps_project` |
| App port | `5000` |

---

## 9. Typical daily loop

1. Activate env → start `python prompt.py`
2. Open chat at `http://localhost:5000`
3. Ask questions (e.g. “How many maps_states?”, “Top institutes by students”)
4. Check generated SQL if the answer looks wrong
5. If tables/columns changed in DB → regenerate MDL (section 4) and try again

---

## 10. Troubleshooting (quick)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Chat empty / 502 to model | Qwen server down | Check `10.125.18.189:8000` |
| SQL generated, Wren error | Bad SQL or MDL outdated | Fix question / rebuild MDL |
| Connection failed | Wrong `.env` or DB offline | `wren profile debug` |
| Schema missing in prompts | No `target/mdl.json` | `wren context build` in `maps_project` |
| Non-SELECT blocked | Safety filter in `prompt.py` | Ask for read-only analytics only |
