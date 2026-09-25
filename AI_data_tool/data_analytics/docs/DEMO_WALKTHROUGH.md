# Demo walkthrough

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

## 0 · The workspace menu

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

### Your workspaces, and the ones you were given

Roots are grouped under **MY WORKSPACES** and **SHARED WITH ME** once a user has
some of each — the headings are suppressed entirely when everything falls into
one group, so an admin who owns nothing is not told the whole org's tree was
"shared" with them. The grouping keys on *ownership*, not on whether you may
edit it: an admin can manage every folder in the org, so "can I change this?"
cannot answer "is this mine?".

### Seeing two different menus

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

## Demo logins

Two accounts exist so row-level security can be *shown* rather than described.

| Login | Password | Sees |
|-------|----------|------|
| `demo-emea@example.invalid` | `demo-password` | Europe rows only, no `cost` column |
| `demo-global@example.invalid` | `demo-password` | Everything |

Not secrets: they exist only inside the demo org, see only demo data, and are
deleted on unseed. A login nobody can use demonstrates nothing.

---

## 1 · "Which regions are underperforming, and why?"

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

## 2 · "Can I trust this data?"

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

## 3 · "Who is allowed to see what?"

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

## 4 · "What needs attention right now?"

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

## Actions worth showing that no seeder can create

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

## Uploading several files, and Microsoft Access

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

## Cleaning up

`DELETE /api/v1/demo/seed` removes everything — datasets, reports, both logins,
the share link, the embed config, the schedule and the alert.

Teardown deletes the grants **before** the identities that own them. Those tables
cascade from `users.id`, so deleting users first works on PostgreSQL and silently
orphans on SQLite. For a live share token that is not a detail worth leaving to
the database's configuration.
