# Demo Showcase: insight-led use cases exercising every action

**Date:** 2026-08-28
**Goal:** Demos that show what the platform *does for someone*, not just what it can
render — and that exercise the features a widget catalogue cannot: sharing, RLS,
alerting, prep, parameters, the agent.

---

## What already exists (measured, not assumed)

| | Coverage |
|---|---|
| Widget types | **57 / 57 — complete** |
| Actions / features | **5 / 18** |

Five demo datasets (sales, metrics, projects, feedback, routes) and five reports
(Sales Overview, Distributions, Time & Change, Projects & Feedback, World Sales Map),
seeded by `services/demo_content.py` and reachable at `POST /api/v1/demo/seed`.

**The gap is actions and narrative, not widgets.** Demonstrated today: cross-filter
interaction modes, bookmarks, calculated columns, display rules, the drill hierarchy.
Not demonstrated:

| Missing | Why it matters |
|---------|----------------|
| Share links | The thing you asked to publish and share |
| Embed configs | The commercial differentiator vs Power BI |
| RLS rules | The enterprise gate |
| Prep steps | The self-service story |
| Post-aggregation measures | Non-additive metrics (ratios, margins) |
| Report parameters | What-if analysis |
| Relationships | Multi-dataset modelling |
| Alerts, schedules | Unattended operation |
| Slicer sync, comments, translations | Collaboration surface |

---

## Design decision: add a layer, do not rebuild

The five existing reports stay exactly as they are. They are the **widget-coverage
bed**: `test_demo_reports.py` and `test_demo_features.py` assert against their specs,
and they are the config corpus the DuckDB sweep runs through — the set that caught the
`measure2` eligibility bug. Rewriting them to be "insight-led" would churn tested
specs and lose that corpus for no gain.

Insight-led is delivered by **adding** `seed_demo_use_cases()` alongside them, following
the module's own established pattern (`seed_demo_features`, `seed_demo_ux_showcase`):
marker-tagged, idempotent, with a matching remover wired into `remove_demo_content`.

---

## Two hazards found before designing, which shape the work

**1. A seeded schedule would actually fire.** `refresh_scheduler.py:321` selects every
`ReportSchedule` (and `DataAlert`) with `interval_minutes IS NOT NULL` and runs it.
Neither model has an enabled/disabled column, so **the only safe seed is
`interval_minutes = NULL`** — excluded by the scheduler's own `WHERE`, present and
inspectable in the UI. A demo must never send mail to whatever address it invented.

**2. Demo seeding creates no `User` rows today.** RLS needs at least two identities to
mean anything ("this role sees EMEA only"). That makes the RLS use case the one
expensive item here, and it drags a real obligation: **any seeded user is a credential
and must be removed on unseed.**

A third, from the existing code: an embed token is the same up-to-24h host-signed
credential the telemetry query-string scrubber exists to protect. Seeded embed configs
get a localhost-only origin allowlist; seeded share links get a short `expires_at`
(the column exists, alongside `revoked_at`).

---

## The use cases

Four reports, each a question someone actually asks, each carrying specific features.

### 1. "Which regions are underperforming, and why?"
**Features:** slicer + sync-across-pages · report parameters (target threshold) ·
post-aggregation measure (margin %, non-additive) · display rules on the variance ·
**share link**

The what-if path: move the target parameter, watch the variance colouring move with it.

### 2. "Can I trust this data?"
**Features:** prep pipeline steps · relationships between datasets · calculated
columns · data-quality KPIs

Shows the raw feed, the prep steps applied, and the same figures before and after —
the self-service preparation story end to end.

### 3. "Who is allowed to see what?"
**Features:** RLS rules · two demo roles/users · column denial · **embed config**

The one that needs seeded identities. The walkthrough gives both logins, and the same
report is opened as each to show the rows change.

### 4. "What needs attention right now?"
**Features:** alert definition (paused) · schedule definition (paused) · comments ·
KPI/gauge status · translations

Operational monitoring. Both scheduled objects seeded with `interval_minutes = NULL`.

---

## Runtime actions belong in a walkthrough, not a seeder

Cross-filter clicks, drill-down, bookmark switching, asking the agent a question — none
of these are database rows. The seeder creates the **preconditions** (interaction modes,
hierarchy, agent-visible dataset); `docs/DEMO_WALKTHROUGH.md` gives the click path and
the insight that appears at each step.

The agent step is marked as requiring `llm_enabled` and a reachable endpoint, since an
air-gapped install without a model cannot run it.

---

## Tasks

### Phase 1 — seeders and teardown

| # | Task | Effort |
|---|------|--------|
| 1.1 | `seed_demo_use_cases()` + `_remove_existing_use_cases()`, mirroring `seed_demo_ux_showcase` | M |
| 1.2 | Use cases 1 and 2 (no new identities — cheapest, highest value) | M |
| 1.3 | Use case 4 (alert + schedule, both `interval_minutes=NULL`) | S |
| 1.4 | Use case 3: demo users, roles, RLS rules, embed config | M |
| 1.5 | Share links with short expiry; embed origins localhost-only | S |
| 1.6 | Wire into `routers/demo.py` and `remove_demo_content` | S |

**Acceptance:** seed → unseed leaves **zero** demo-marked rows of every new type,
asserted per type. A leaked share link or demo user is a live credential, not clutter.

### Phase 2 — coverage test and walkthrough

| # | Task | Effort |
|---|------|--------|
| 2.1 | `test_demo_action_coverage.py`: derived feature list, asserts a seeded org contains each | M |
| 2.2 | `docs/DEMO_WALKTHROUGH.md`: per use case, click path → insight | M |
| 2.3 | Update `ARCHITECTURE.md`/`.html` demo counts (the doc audit will enforce them) | S |

**2.1 follows this session's pattern** — same shape as `test_architecture_doc.py`. It
fails when someone adds a feature the demos do not exercise, so the showcase cannot
silently fall behind the product.

---

## Verification

```bash
python -m pytest tests/test_demo_*.py -q          # existing render assertions
python -m pytest -q                                # full suite
DATALYTICS_TEST_DUCKDB_PUSHDOWN=1 python -m pytest -q   # new configs are new sweep inputs
```

The sweep matters: every demo config is a DuckDB eligibility input by construction, and
that is exactly how the `measure2` gap surfaced.

---

## Done 2026-08-28

**Action coverage went from 5/18 to 17/18.** The one gap left is page templates,
which has no natural home in these four narratives.

`services/demo_use_cases.py` seeds two reports plus the identity and grant layer.
Use cases 3 and 4 deliberately do **not** add reports: "who can see this?" and
"what needs attention?" are questions *about* a report, and answering them on one
somebody has already read beats inventing two more dashboards.

**41 tests** — 24 in `test_demo_use_cases.py`, 17 in `test_demo_action_coverage.py`.
The coverage test asserts against the **seeded database**, not source text:
grepping the seeder for a class name proves someone typed it, while querying the
org proves a user opening the demo will find the feature there.

### The inert-schedule constraint was wrong twice before it was right

First reading: seed `interval_minutes = NULL`, since `refresh_scheduler` selects
on `isnot(None)`. **Wrong** — the column is `nullable=False` on both models, so
that seed cannot exist; the filter is defensive against impossible data.

The real mechanism is one layer down: `is_due` returns False for
`interval_minutes <= 0`. So **0** is the only inert spelling, and it was verified
directly rather than read: `is_due(0, never_run)` is False, `is_due(60,
never_run)` is True.

The test now asserts against `schedule_is_due`/`is_due` themselves rather than
the column value, so a change to that predicate fails the test instead of
silently starting to send mail.

### Teardown order is the safety property

Share links, embed configs, schedules and alerts all carry a NOT NULL creator FK
to `users.id` with `ON DELETE CASCADE`. Deleting the demo users first *would*
remove them — on PostgreSQL. Under SQLite with foreign keys off they would
survive as orphans, which for a live share token is not a detail. The remover
deletes grants first, then identities, so teardown behaves the same on either
database.

Everything a grant creates is asserted to exist **and** to disappear:
`test_remove_demo_content_takes_every_grant` sweeps all six tables plus the
logins, and `test_it_does_not_delete_a_real_user` proves the removal is scoped.

### `docs/DEMO_WALKTHROUGH.md`

Click paths for all four use cases, both demo logins, and the runtime actions no
seeder can create (cross-filter, drill-down, bookmarks, agent questions). Its
claims were checked against the code — which caught it overstating the report
count as nine when the seed produces eight.

---

## Out of scope

- **A showcase artifact.** Sharing is done with the platform's own share/embed features,
  as asked — not a published page about them.
- **Rebuilding the five existing reports.** They are the widget-coverage bed and the
  sweep corpus; see the design decision above.