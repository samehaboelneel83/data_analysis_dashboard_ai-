# Datalytics — agent notes

This file is for an AI agent (Claude Code or similar) working in this repository.

## What this app is

Datalytics is a local BI web app: upload or connect data, explore datasets, build dashboards, ask questions in Ask AI, scan Insights. There is **no public Sign Up**. Users are seeded or created by an admin.

## Install and start

From the repo root (`data_analytics`):

```powershell
copy .env.example .env
docker compose up --build -d
```

Wait until the API is ready (do not guess with a fixed sleep):

```powershell
# repeat until HTTP 200
Invoke-WebRequest http://localhost:8000/health/ready
```

Then seed users and demo content (idempotent):

```powershell
.\qa\seed.ps1
```

That script calls `scripts/demo_up.ps1` (Compose + bootstrap admin + `POST /api/v1/demo/seed`) and then runs `scripts/seed_dev_accounts.py` inside `datalytics_backend` so `admin@datalytics.local` exists.

In the running app you can also use **Settings → Load demo content** after signing in.

### URLs

| Service | URL |
|---|---|
| App (Compose maps host 3001 → container 3000) | **http://localhost:3001** |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |

If you run the frontend on the host with `npm run dev` inside `frontend/`, the app is http://localhost:3000 and still talks to the API on 8000.

## Log in

Use seeded accounts only (see `qa/TEST_DATA.md`).

| | |
|---|---|
| **Email** | `admin@datalytics.local` |
| **Password** | `demo-password` |

Fallback if that user was never created: `admin@example.invalid` / `demo-password` (from `demo_up.ps1`).

Other logins (same password `demo-password`):

- `demo-global@example.invalid` — all demo rows
- `demo-emea@example.invalid` — Europe only, no `cost` column

## Browser QA (required when testing the product)

To test the app, follow `qa/TEST_PLAN.md` in the browser and write results to `qa/REPORT.md` using `qa/REPORT_TEMPLATE.md`.

Those two files also sit at the **repo root** so a filesystem search finds them:

- `TEST_PLAN.md`
- `REPORT_TEMPLATE.md`
- `QA_BROWSER_PACK.md` (both documents in one file — attach this in Claude.ai)

Absolute folder: `data_analytics/qa/`

- Click like a human. Do not drive the UI with CSS selectors.
- Watch the browser console for errors.
- Open datasets and dashboards **by name**, not by numeric id.
- Short run order is at the bottom of `qa/TEST_PLAN.md`.
- Upload fixture: `qa/fixtures/qa_sample.csv`.

## Seed script

```powershell
.\qa\seed.ps1
```

Needs Docker. It:

1. Starts Compose if containers are down.
2. Waits for `/health/ready`.
3. Ensures an admin and demo seed (`scripts/demo_up.ps1 -SkipBuild` when images already exist).
4. Runs `scripts/seed_dev_accounts.py` in `datalytics_backend` for `admin@datalytics.local` and extra orgs.

## Do not

- Commit `.env`, real passwords, or `qa/REPORT.md` with production data.
- Force-push, skip git hooks, or change git config.
- Treat Ask AI refusing to edit dashboards as a bug (page copilot on `/reports/:id` is the editor).
