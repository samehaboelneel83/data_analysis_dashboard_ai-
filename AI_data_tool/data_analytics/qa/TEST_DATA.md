# Test data

Use **only** these seeded / fixture values. Never use a real person’s email, a production password, or live customer files.

## App URLs

| What | URL |
|---|---|
| App (Docker Compose frontend) | http://localhost:3001 |
| App (local Vite, if you run `npm run dev` in `frontend/`) | http://localhost:3000 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health/ready |

Default for this pack: **http://localhost:3001**.

There is **no Sign Up**. Accounts come from seed scripts.

## Accounts

All demo / QA passwords below are **not secrets**. They exist only on a local stack and are wiped by unseed.

| ID | Email | Password | Role | Use for |
|---|---|---|---|---|
| ADMIN | `admin@datalytics.local` | `demo-password` | Platform Admin (super-admin allowlist + org admin) | Most tests, Admin, Platform |
| BOOTSTRAP | `admin@example.invalid` | `demo-password` | First admin created by `demo_up.ps1` if no users existed | Fallback if ADMIN is missing |
| GLOBAL | `demo-global@example.invalid` | `demo-password` | Demo — Global analyst | All regions, `cost` visible |
| EMEA | `demo-emea@example.invalid` | `demo-password` | Demo — EMEA analyst | Europe rows only, no `cost` |
| CONTOSO_ADMIN | `admin@contoso.invalid` | `demo-password` | Contoso Admin | Extra org (after `seed_dev_accounts.py`) |
| CONTOSO_ANALYST | `analyst@contoso.invalid` | `demo-password` | Contoso Analyst | Non-admin member |
| NORTHWIND_ADMIN | `admin@northwind.invalid` | `demo-password` | Northwind Admin | Extra org |
| NORTHWIND_ANALYST | `analyst@northwind.invalid` | `demo-password` | Northwind Analyst | Non-admin member |

**Primary tester login:** ADMIN.  
**Security contrast pair:** GLOBAL then EMEA on the same dashboard.

If ADMIN does not exist, run `qa/seed.ps1` (see CLAUDE.md). If only BOOTSTRAP exists, use that and treat it as admin.

## Invalid / empty auth inputs

| Case | Email | Password |
|---|---|---|
| Both empty | *(leave blank)* | *(leave blank)* |
| Email only | `admin@datalytics.local` | *(leave blank)* |
| Password only | *(leave blank)* | `demo-password` |
| Not an email | `not-an-email` | `demo-password` |
| Unknown user | `nobody@example.invalid` | `demo-password` |
| Wrong password | `admin@datalytics.local` | `wrong-password` |
| SQL-ish junk | `' OR 1=1 --` | `' OR 1=1 --` |

## Named demo datasets (after Load demo content)

Open by **name**, never by a hard-coded numeric id (ids change per machine).

| Name |
|---|
| Demo — Sales |
| Demo — Metrics |
| Demo — Projects |
| Demo — Feedback |
| Demo — Routes |
| Demo — Live Orders (DirectQuery) |

## Named demo dashboards

| Name | Why it is in the plan |
|---|---|
| Demo — World Sales Map | Maps, clipping, resize |
| Demo — Sales Overview | Cross-filter, bookmarks |
| Demo — Distributions | Charts |
| Demo — Time & Change | Time series |
| Demo — Projects & Feedback | Multi-dataset |
| Demo — Live Orders (DirectQuery) | Live query tiles |
| Use case — Regional performance review | Slicer, RLS contrast, parameters |
| Use case — Can I trust this data? | Prep vs raw, model |
| UX Showcase (demo) | Page types, prompt, drillthrough |

Workspace folders after seed: **Use cases**, **Widget gallery**.  
EMEA sees both folders. GLOBAL typically sees Widget gallery only (Use cases is role-restricted).

## New records created during tests

Use unique suffixes so re-runs do not collide. Replace `NN` with the time (e.g. `1621`).

| Kind | Value |
|---|---|
| Dashboard name | `QA Dashboard NN` |
| Dashboard description | `Created by browser QA` |
| User email | `qa.user.NN@example.invalid` |
| User password | `QaPass-NN-demo` |
| Role name | `QA Role NN` |
| API key name | `QA Key NN` |
| Connection name | `QA Conn NN` |
| Org name (platform) | `QA Org NN` |
| Org admin email | `qa.admin.NN@example.invalid` |
| Org admin password | `QaOrg-NN-demo` |

Do **not** delete seeded Demo / Use case dashboards. You may delete records whose names start with `QA `.

## Upload fixtures

| File | Path | Purpose |
|---|---|---|
| Valid CSV | `qa/fixtures/qa_sample.csv` | Happy-path upload |
| Not a dataset | `qa/fixtures/qa_not_a_dataset.txt` | Rejected / error list stays on the page |

`qa_sample.csv` columns: `region`, `country`, `revenue`, `units`, `date`.

## Ask AI prompts

Use against **Demo — Sales** unless a step says otherwise.

| ID | Prompt | Expect |
|---|---|---|
| Q_HI | `hi` | Short chat; no data table of invented numbers |
| Q_WHAT | `what is this data` | Catalog-style description of the dataset |
| Q_TOTAL | `total revenue by region` | Sentence + rows; totals match the table |
| Q_CHART | `show that as a bar chart` | Reuses last result as a chart (no wild new query required) |
| Q_CREATE | `create a dashboard with a KPI` | Refusal — Ask AI does not build dashboards |

## Dashboard copilot prompts

Use on an editable dashboard (a `QA Dashboard NN` you created, not a shared view-only one).

| ID | Prompt | Expect |
|---|---|---|
| C_BAR | `add a bar chart of revenue by region` | A bar widget appears |
| C_KPI | `add a KPI for total revenue` | A KPI widget appears |
| C_FX | `add a calculated column named qa_margin as revenue minus cost if those columns exist` | Copilot may create/edit fx columns |
| C_SUM | `sum revenue on the KPI` | Aggregation applied, not refused |
| C_NONE | `show individual values, no aggregation` | Obeys; does not invent a double-sum |

## Map checks (visual)

On **Demo — World Sales Map**:

- **Shipping routes** — whole world in the tile; Asia / Europe not cut off on the right.
- **Origin density** — bubbles fully inside the tile.
- **Routes as a network** — city labels (London, Tokyo, Sydney, Los Angeles) fully readable.

Pacific looking like empty ocean is **not** a fail. Clipped city names or half a continent **is** a fail.

## Browser sizes

| Name | Width × height | When |
|---|---|---|
| Desktop | 1440 × 900 | Default |
| Tablet / drawer | 890 × 800 | Below 900px the rail becomes a drawer |
| Mobile | 390 × 844 | Phone-width pass |

## What is not a bug

- Ask AI refusing to create or edit dashboards.
- Demo schedules / alerts that never fire (`interval` inert by design).
- A folder missing from one user’s menu while a direct URL still opens the report (menu is navigation, not access control).
- “Loading map…” for a moment while a chart chunk loads.
- No Sign Up button — there is none on purpose.
