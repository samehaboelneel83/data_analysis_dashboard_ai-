# Architecture

Datalytics is a containerised, self-hostable analytics platform: connect a data
source, model it, and build multi-page interactive reports with cross-filtering,
row-level security, and natural-language querying against a self-hosted model.

This document describes the system as **seven layers in data-flow order** — the
path a byte takes from a source system to a pixel on screen. Each layer states
what it owns, where its code lives, and the contract it exposes to the layer above.

> **Scope.** `README.md` is the quick start and feature tour. This document is the
> architecture reference. Where the two disagree, this file is authoritative.

---

## Contents

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

## The seven layers at a glance

| # | Layer | Owns | Principal code |
|---|-------|------|----------------|
| 1 | **Data Sources & Connectivity** | Reaching external systems; dialect capability; pooled engines | `services/connectors.py`, `connections.py`, `engines.py`, `secrets.py`, `net_guard.py` |
| 2 | **Ingestion & Metadata** | Turning raw sources into described, profiled datasets | `services/ingest.py`, `services/metadata/`, `routers/datasets.py`, `services/pii.py` |
| 3 | **Storage & Persistence** | Durable state and cached state | `models/models.py`, `alembic/`, `services/cache_backend.py` |
| 4 | **Query & Semantic** | Translating widget intent into safe, governed SQL | `services/query_builder.py`, `widget_data.py`, `widget_shaping.py`, `direct_query.py`, `duck_agg.py`, `prep.py`, `sql_expr.py`, `core/rls.py` |
| 5 | **Analytics & AI** | Statistics, forecasting, anomaly detection, NL→SQL | `services/analysis/`, `services/agent/`, `analytics.py` |
| 6 | **API & Services** | HTTP surface, authn/authz, delivery, sharing | `routers/` (29 modules), `core/security.py`, `services/delivery.py`, `refresh_scheduler.py`, `services/automation_runner.py` |
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

## Runtime topology

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

## Layer 1 — Data Sources & Connectivity

**Owns:** reaching external systems, and knowing what each one can do.

### Connector registry

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

### Joining datasets, and keeping the result

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

### Aggregate datasets

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

### Key influencers

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

### Saved models, and scoring with one

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

### Decomposition tree

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

### Paginated output and subscriptions

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

### Small multiples, and transformations that keep themselves current

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

### Dataflows: a transformation as a first-class object

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

### Right-to-left, app-wide

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

### The shared cache is now wired up

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

### Subscriptions became reachable

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

### Right-to-left reaches the PDF

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

### ODBC: the escape hatch, reported honestly

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

### CALC: filter context, without building a language

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

### Inferential statistics: is the difference real?

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

### Advanced models, and correcting our own findings

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

### Reaching an object's settings

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

### Generated prose, and why it is never load-bearing

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

### Composed graphs

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

### Hierarchies: six layouts, one shaper

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

### Slicers offer search sooner

The auto threshold moved from 40 values to 10. Scanning a thirty-item checkbox
list for one value means reading all thirty, and the list is only as tall as its
widget, so most of it is scrolled out of sight. Search only ADDS a filter box:
enabling it early costs a reader nothing, while a wall of checkboxes costs them
the value they came for. Under five values it is still a button bar, and five to
ten a plain list -- a search box over six items is clutter.

### The authoring path, not just the render path

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

### "We could not ask" is not "there is nothing"

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

### The statistics screen is one screen, not eight

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

### Connection handling

- `services/connections.py` — credential storage and connection lifecycle
- `services/secrets.py` — secret material, kept out of API responses
- `services/net_guard.py` — egress control, enforcing the air-gap boundary

### Engine registry

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

## Layer 2 — Ingestion & Metadata

**Owns:** turning a reachable source into a described, profiled, trustworthy dataset.

### Upload path

`routers/datasets.py` accepts CSV, XLSX, JSON, and Parquet up to 100 MB (plus XML
when `lxml` is present — `SUPPORTED` registers a reader only if its parser imports).
`services/ingest.py` owns this layer's two primitives: `load_file()`, which reads
through the process-local frame memo so the same bytes are parsed once per process
rather than once per widget, and `detect_types()`, which classifies every column as
numeric, categorical, datetime, or text.

### Metadata package

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

### PII masking

`services/pii.py` detects personal data in a sample and masks it **before** anything
is written to the sample cache or sent to the model. There is no path where a raw
personal value reaches either — a self-hosted endpoint is still a disclosure, and a
cache is still a copy.

The mask carries a hash rather than being shape-preserving (`a****@c***.com`), because
foreign-key inference measures value overlap between columns in the masked sample:
shape-only masking would collapse distinct values together and invent relationships
that do not exist.

### Refresh

`services/dataset_refresh.py` re-imports a dataset from its source and invalidates the
cached frame. Scheduling lives at Layer 6 (`refresh_scheduler.py`), which composes this
with alerts and delivery.

**Contract to Layer 3/4:** a dataset with typed columns, inferred keys, declared
relationships, a profile, and no unmasked personal data.

---

## Layer 3 — Storage & Persistence

**Owns:** durable state, cached state, and schema evolution.

### Relational store

PostgreSQL 16 Alpine. **81 tables** defined in `models/models.py` via async
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
| Authoring | `report_versions`, `report_comments`, `report_translations`, `page_templates`, `page_role_visibility`, `widget_templates`, `pinned_tiles`, `org_review_settings`, `org_themes`, `watermarks` |
| Maps | `boundary_sets`, `org_map_settings` |
| Models | `prediction_models` |
| Workspace | `workspace_nodes`, `workspace_folder_roles`, `workspace_folder_grants` |
| Pipelines | `dataflows`, `dataflow_capabilities`, `automation_runs`, `automation_steps`, `custom_connectors`, `schedule_failures` |
| Platform | `saml_authn_requests`, `org_mcp_access`, `eval_runs` |
| Ops | `sync_runs`, `schema_versions`, `column_stats`, `materializations`, `quotas`, `query_runs` |

Schema changes go through **Alembic** (`backend/alembic/`, 37 revisions).
`postgres/init.sql` provides the initial schema and indexes.

### Cache

`services/cache_backend.py` defines a `CacheBackend` interface with two
implementations — `InProcessCache` for single-process or test runs, and
`ValkeyCache` for the deployed stack. `services/frame_cache.py` caches computed
result frames; `core/rate_limit.py` uses the same backend for throttling.

The cache is an optimisation, never a source of truth: every cached value is
reproducible from Postgres and the source systems.

### File storage

Uploads land in the `uploaded_files` volume, referenced by path from `datasets`.

---

## Layer 4 — Query & Semantic

**Owns:** translating widget intent into SQL that is correct, governed, and safe.

This is the layer where a request becomes a query. It has three responsibilities.

### 1. Aggregation engine

`services/widget_data.py` turns a widget config into a result set. The config
contract is:

```
{ dimension, measure, aggregation, filters, limit, sort, sort_by, running }
```

**25 aggregations** in three groups, plus `none`:

- **Numeric** — `sum`, `avg`, `median`, `min`, `max`, `std`, `variance`, `range`, `p25`, `p75`, `p90`, `p95`
- **Count** — `count`, `countd`, `frequency`, `pct`
- **Statistical** — `stderr`, `skewness`, `kurtosis`, `cv`, `uss`, `css`, `tstat`, `pvalue`
- **None** — `none` lists the rows unaggregated

Arithmetic is refused on a column that is not a quantity: summing a year, a
coordinate or an identifier returns `422 semantic_veto` naming the aggregation
that does mean something (`services/semantic_guard.py`, enforced in
`_resolve_widget_data` so every surface — builder, share link, embed, export,
API — gets the same answer). Marking the column a measure is the override.

  SAS offers these on any measure, so an evaluator looks for them by name. Each
  returns `None` rather than a number when the sample cannot support it — a
  t-statistic on one row, a coefficient of variation about a zero mean — because
  a fabricated statistic is worse than an empty cell.

Plus two post-aggregation metrics applied over the ordered result: `running_sum`
and `running_avg`.

### 2. SQL construction

`services/query_builder.py` builds dialect-correct SQL from a model definition:
`build_sql(model, dialect, known, …)`, with `_quote()` handling per-dialect
identifier quoting and `introspect_tables()` validating that referenced tables and
columns actually exist before emission.

`services/sql_expr.py` and `measure_eval.py` evaluate user-authored expressions
and calculated measures. `services/parameters.py` binds report parameters.

### 3. Governance

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

### Two execution paths

The same widget config resolves through one of two engines:

| | Import-mode | Import + DuckDB | DirectQuery |
|---|---|---|---|
| Module | `widget_data.py` | `duck_agg.py` | `direct_query.py` |
| Aggregation | pandas `groupby` | DuckDB over the file | pushed into SQL |
| Source rows loaded | whole frame, capped by `import_row_cap` | streamed, never materialised | bounded by `row_cap` |
| RLS | applied to the frame | ineligible — falls back | pushed into the `WHERE` clause |

### DuckDB pre-aggregation

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

## Layer 5 — Analytics & AI

**Owns:** everything that produces an insight rather than a value.

### Statistical analysis

`services/analytics.py` provides descriptive statistics, outlier detection,
correlation, and chi-square testing. The `services/analysis/` package adds:

| Module | Capability | Library |
|--------|-----------|---------|
| `anomaly.py` | Isolation Forest, ECOD | PyOD |
| `segment.py` | KMeans segmentation | scikit-learn |
| `registry.py` | Analysis registration and dispatch | — |

Forecasting uses **AutoETS** via `statsforecast`, surfaced as a forecast widget.
`services/insights.py` and `explain.py` generate narrative explanations of results.

### Dashboard suggestion

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

### NL→SQL agent

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

### Model client

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

## Layer 6 — API & Services

**Owns:** the HTTP surface, identity, and everything that leaves the system.

### Routers

**29 router modules**, mounted with 31 `include_router` calls in `main.py` --
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
| `authz` | Batched "may I, and why not" decisions for the UI |
| `review` | Report review, publish gate, performance evaluation |
| `report_copilot` | Copilot edits to a report (versioned, undoable) |
| `semantic` | Governed semantic-layer API (datasets, measures, RLS) |
| `prediction_models` | Train, save and score models |
| `boundary_sets`, `map_settings` | Region boundaries, starter packs, basemap tiles |
| `pins` | Pinned tiles |
| `dataflows`, `custom_connectors` | Reusable prep flows, admin-defined connectors |
| `agent` | NL query (mounted at root) |

### The automation chain

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

#### Step 4 is where customer data leaves the chain

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

#### Row values reaching persisted text, and what to do if it happens

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

#### The secured frame, and what a run leaves behind

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

#### The structured record: what a run produced, in typed columns

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

#### Step 7: the notification is a rendering, not a record

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

#### Relationship access outside a request

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

#### Step 2 bridges the identifier concept into the analyses

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

### Workspace tree

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

### Who sees which folders

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

### Identity and authorisation

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

### Outbound

- `services/pdf_export.py` — server-side PDF rendering
- `services/delivery.py` — scheduled distribution
- `services/alerts.py` — data-condition alerts
- `services/notifications.py` — in-app notifications
- `services/eval_schedule.py` — scheduled evaluation runs

### Sharing and embedding

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

### Middleware

CORS is configured in `main.py`. The global exception handler is registered
**after** `CORSMiddleware` so it sits inside it — otherwise a 500 would carry no
`Access-Control-Allow-Origin` header and the browser would report a misleading
CORS violation instead of the real error.

### Health probes

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

### Error contract on the widget path

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

## Layer 7 — Presentation

**Owns:** authoring and rendering reports.

React 18 · TypeScript · Vite · Recharts.

### Pages

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

### Widget system

**74 widget types** declared in `types/report.ts` as `WidgetType` and catalogued
in `WIDGET_CATALOG` (the source of truth — do not maintain a parallel list):

| Category | Types |
|----------|-------|
| **Charts** | bar, line, step, dot plot, needle, histogram, butterfly, area, funnel, ribbon, pie, donut, scatter, treemap, four dual-axis variants, comparative/numeric series, bubble (+change), correlation matrix, heatmap, parallel coordinates, box plot, waterfall, gauge, schedule (Gantt), vector plot, word cloud, forecast, sankey, network |
| **Controls** | KPI, card, table, crosstab, matrix, list, text, image, shape, button, slicer, web content, custom visual, container |
| **Hierarchies** | tree, sunburst, icicle, dendrogram, org chart, circle pack (one shaper, six layouts), decomposition tree |
| **Composed** | small multiples, custom graph, script |
| **Models** | linear regression, logistic regression, decision tree, clustering, model comparison (one shared held-out split), saved-model scoring |
| **Maps** | choropleth, points, bubbles, lines, clusters, pie, layers, density, contour, network, network map |

Any bar, line, area, scatter, step or dot plot can also be drawn as a
lattice (small multiples by one or two fields) or animated over a field.

Rendering is dispatched by `WidgetBody.tsx` (inside `WidgetRenderer.tsx`) to per-type modules in
`components/report/chartRenderers/`. Maps render through `d3-geo` and
`topojson-client` against a bundled `world-atlas` — a deliberate choice that keeps
geospatial working without external tile services, and therefore offline.

### Interaction model

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

### Supporting modules

`contexts/AuthContext.tsx` holds session state. `services/api.ts` is the Axios
client. `lib/` contains pure helpers — `sqlWhere.ts`, `simpleExpr.ts`,
`displayRules.ts`, `columnRole.ts`, `pptExport.ts` (client-side PowerPoint export),
`widgetImage.ts` — each with a colocated test.

---

## Cross-cutting concerns

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

### Observability

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

### Offline / air-gapped operation

The platform is designed to run with no internet access:

- Frontend assets are bundled, not CDN-loaded — pinned by `offlineAssets.test.ts`
- Map geography ships with the image (`world-atlas`)
- The model endpoint is self-hosted; `llm_enabled=False` removes the AI layer
- `scripts/build_offline_bundle.ps1` produces image tarballs plus a `MANIFEST.json`
  recording exact image IDs and digests for transfer across the air gap

See `docs/OFFLINE_DEPLOYMENT.md`.

### Durable state

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

## Request lifecycles

### A widget renders

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

### A natural-language question

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

## Testing

| Suite | Scope | Count |
|-------|-------|-------|
| Backend | `backend/tests/` | ~5,300 tests across 382 modules |
| Frontend | colocated `*.test.ts(x)` | ~2,800 tests across 212 files |
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

### Environment notes

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

## Extension points

| To add… | Touch |
|---------|-------|
| A data source | Append a `ConnectorSpec` to `_ALL_SPECS` in `connectors.py` |
| An upload format | A reader in `SUPPORTED` (`ingest.py`) — or, for a container of many tables, its own path like `services/mdb.py` |
| A widget type | `WidgetType` + `WIDGET_CATALOG` in `types/report.ts`, a renderer in `chartRenderers/`, config in `WidgetConfigPanel.tsx` |
| An aggregation | `AGGREGATIONS` in `types/report.ts` and the engine in `services/widget_data.py` |
| An analysis | Register in `services/analysis/registry.py` |
| An agent capability | A node in `services/agent/nodes/`, wired in `graph.py` |
| A schema change | An Alembic revision in `backend/alembic/versions/` |
