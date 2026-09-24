# Datalytics versus Apache Superset — Technical Comparison

**Date:** 2026-09-14
**Basis for Datalytics:** the full read-only survey of this repository completed on 2026-09-13 (`2026-09-13-application-analysis.md`), `ARCHITECTURE.md` (test-enforced), the scale plan and its measurements, the aggregate-datasets spec, and the code itself. Claims about Datalytics are Confirmed unless marked.
**Basis for Superset:** Apache Superset 4.x–5.x as released; feature availability is stated from general knowledge of the project and should be re-verified against the exact release you would deploy. Items marked *(verify)* are where the two projects move fast.

**What is missing to make this sharper:** no screenshots or a recorded walkthrough of Datalytics were provided (the analysis relied on code and the `ui_walkthrough.py` findings); no load test of Superset on comparable hardware; no measured accuracy figure from Datalytics' eval gate on a real customer dataset (the gate exists, threshold 0.5, opt-in); no user research on either product. The Superset target version was not specified; 5.x is assumed.

---

## 1. Product purpose and target users

| | Datalytics | Apache Superset |
|---|---|---|
| Primary purpose | A governed, air-gap-capable BI platform with an AI analyst built in; SAS Visual Analytics parity was the explicit design target | A general-purpose open-source BI and data-exploration platform; SQL-first, warehouse-first |
| Primary user | Business analysts and restricted viewers in one organisation; Arabic-first audiences; org admins who govern data | Data analysts and engineers who model datasets in SQL, then business users who consume dashboards |
| Business vs technical | Built for business users end to end: upload, prep pipeline, calculated columns, measures, custom categories, charts, sharing, natural-language questions | Technical first: datasets are SQL tables or virtual SQL; Explore is no-code but assumes a modelled dataset; SQL Lab is a SQL editor |
| Self-service | Strong: file upload, joins with key suggestions, prep steps, materialize, dataflows, insights, statistics, prediction models, all in the UI | Moderate: Explore and native filters are self-service; data preparation is expected upstream (dbt, the warehouse) |
| Data-engineering requirement | Low for files; moderate for DirectQuery (schema review, aggregates for scale) | High: you need a warehouse and a modelling layer before Superset is useful |
| Ease of use, learning curve | Low entry (upload and go); high ceiling and a large builder (17 panel modes, a 2,455-line properties panel, 67 widgets) | Moderate entry (Explore), steep for SQL Lab, Jinja, virtual datasets, native-filter scoping |

**Verdict.** Different centres of gravity. Superset assumes data is already modelled; Datalytics assumes it is not. That is the single most important product fact in this comparison.

---

## 2. Architecture

| Aspect | Datalytics | Superset |
|---|---|---|
| Frontend | React 18, TypeScript, Vite; Recharts and d3-geo; one Axios client file with 264 functions; 67 widget renderers; 2,265 tests | React, TypeScript, Redux; Ant Design 5 (5.x); ECharts and deck.gl chart plugins under `@superset-ui`; a chart-plugin build system |
| Backend | Python 3.12, FastAPI, async SQLAlchemy, Alembic (29 revisions), pandas, DuckDB; seven layers enforced by a conformance test; 25 routers, 77 tables | Python, Flask, Flask-AppBuilder, SQLAlchemy, Alembic; Celery workers and beat; Gunicorn; a metadata database |
| API | REST under `/api/v1`, one FastAPI app, OpenAPI docs; error contract with codes on the widget path | REST under `/api/v1` with OpenAPI; a mature CRUD API used by the UI itself; CLI for import/export |
| Database | PostgreSQL 16 for metadata; uploaded files on a volume with Parquet sidecars; Valkey optional result cache | Metadata DB (Postgres or MySQL); Redis for cache, Celery broker and results backend |
| Query execution | Three engines: pandas over the frame, DuckDB pushdown over the sidecar, dialect SQL to five families; RLS applied inside each; widget result cache keyed on inputs | One path: SQLAlchemy to the target database, `engine_spec` per dialect, optional async through Celery with a results backend; chart data cache |
| Background work | One in-process 60 s loop per worker, advisory locks, backoff 5→1440 min, per-item isolation, startup reapers | Celery workers and beat: async queries, alerts and reports, cache warm-up, thumbnails; horizontally scalable |
| Scalability | One host, `docker compose`, multi-worker with advisory locks; `Semaphore(4)` widget work gate; measured: 70 concurrent tier tests, 10-user dashboard within targets; import capped at 2M rows | Web tier and worker tier scale independently; Helm chart; the warehouse does the heavy lifting |
| Modularity | Clear layer boundaries (enforced); registries for connectors, analyses, widgets; extension points documented | Chart plugins, database engine specs, security manager override, Jinja macros, feature flags; a formal extensions framework is emerging in 5.x *(verify)* |
| Plugin architecture | Internal convention only (renderer registry); custom visuals run in a sandboxed iframe with a `postMessage` contract; server-side script tiles in a scrubbed subprocess | First-class: chart plugins are npm packages with a generator; the ecosystem exists |
| Deployment | Five containers, nothing fetched at runtime, offline bundle script, nginx profile | Docker Compose for dev, Helm for production, plus Redis, Celery, a headless browser for reports; many pip and npm dependencies |

**Strengths.** Datalytics: engine plurality with governance in each; enforced layering; a small deployment surface. Superset: separation of web and workers, a real plugin ecosystem, a battle-tested metadata model.

**Weaknesses.** Datalytics: single host, in-process scheduler (no queue, no mid-step resume), import-mode memory model (a 2M-row frame per render, measured at ~1.8 GB RSS for a 406 MB CSV), no chart-plugin packaging. Superset: operational weight (Celery, Redis, browser), a Flask synchronous request model that pushes anything slow into Celery, and no data-preparation layer of its own.

---

## 3. Data connectivity

| Aspect | Datalytics | Superset |
|---|---|---|
| Supported databases | 45 registered connectors in a declarative registry; 36 DirectQuery-capable across five SQL families (PostgreSQL, MySQL, SQL Server, Oracle, SQLite); cloud warehouses (Snowflake, BigQuery, Databricks, ClickHouse, Trino) import-only with operator-installed drivers; Access via mdbtools; ODBC and raw SQLAlchemy URL escape hatches; Web API connector; custom connector presets with locked fields | Any SQLAlchemy dialect with a DB-API driver, with an `engine_spec` for ~40 engines (Postgres, MySQL, ClickHouse, Trino, Presto, BigQuery, Snowflake, Databricks, Druid, Elasticsearch, and more); live query to all of them |
| Abstraction | `ConnectorSpec` (dialect, driver, capability sets `PERCENTILE_FAMILIES`, `STAT_FAMILIES`, `supports_directquery`), driver probes, fail-closed on unsupported functions | `BaseEngineSpec` with per-engine time grains, function support, cost estimation, SQL validation hooks |
| Files | Upload CSV/XLSX/JSON/XML/Parquet/Access as first-class datasets | CSV/Excel upload into a database table (feature-flagged), not a native file engine |
| Connection management | Encrypted config at rest, test button, per-source LLM-sampling opt-in, SSRF guard, pooled engines per identity | Encrypted URI, test, per-database settings (async, DML, CTAS, cost estimate), connection pooling via SQLAlchemy |
| Dataset management | Import datasets (files), DirectQuery datasets, saved queries via a visual query builder, materialized snapshots, dataflows, aggregates; measures and calculated columns per dataset | Physical datasets (tables) and virtual datasets (SQL); metrics and calculated columns per dataset; certification, owners, tags |
| Schema discovery and metadata | A full catalog sync: introspection, sampling with PII masking, profiling, key inference with accuracy tests, semantic typing, entities, glossary, drift detection with fingerprints, index advice | Table and column introspection on demand; column types; no profiling, no key inference, no drift detection |
| Multiple databases | Per org, many sources; a dataset belongs to one source; cross-dataset joins run in pandas (import mode) | Many databases; joins happen in SQL within one database |

**What Datalytics needs to reach Superset's connectivity.** Promote the cloud-warehouse connectors from import-only to DirectQuery by giving each a `sql_family` and an engine spec for its dialect (ClickHouse and Trino first; both are SQL-friendly and represent the scale case), add time-grain and function-support tables per family the way Superset's engine specs do, and expose the SQLAlchemy-URL escape hatch as a DirectQuery family with an explicit "unknown dialect" capability set. The registry already has the shape for this.

---

## 4. SQL and querying

| Aspect | Datalytics | Superset |
|---|---|---|
| SQL editor | A custom-SQL box inside the schema browser plus a visual query builder (`QueryBuilderDialog`) that compiles and previews; no dedicated editor page, no tabs, no autocomplete, no saved-query library | SQL Lab: multi-tab editor, autocomplete, query history, saved queries, results grid, CTAS/CVAS, async execution, cost estimation, Jinja templating |
| Query validation | Widget configs validated against the dataset's columns; DirectQuery refuses unsupported shapes explicitly; agent SQL passes a six-rung ladder (parse and SELECT-only, schema, join whitelist, row policies injected into the AST, dry run with timeout and row cap, column security) | Optional `SQL_VALIDATORS_BY_ENGINE` (e.g. Presto explain-based); DML blocked unless `ALLOW_DML`; sqlglot-based parsing in 4.x+ |
| Read-only enforcement | Agent: SELECT-only by parse; DirectQuery: generated by the platform, never user SQL at render time; custom SQL in the browser runs a preview with limits | DML disabled by default per database; CTAS gated |
| Query history | `query_runs` stores hashed SQL and column names only (deliberately no values) and feeds index advice and quotas; no user-facing history UI | Full query history per user in SQL Lab, with status and results links |
| Caching | Client widget cache (30 s, de-dup, concurrency gate 6); server widget cache (Valkey or in-process, fail-soft with circuit breaker); frame memo keyed on path+mtime+size; DirectQuery TTL cache keyed on `cache_epoch` bumped by drift | Flask-Caching (Redis) for chart data, dashboard filter state, thumbnails; per-database and per-chart cache timeouts; cache warm-up tasks |
| Async | `asyncio.to_thread` under a `Semaphore(4)`; no queue; long-running work is bounded rather than offloaded | Celery async queries with a results backend; Global Async Queries for charts; polling UI |
| Performance | Measured: governed 10M-row DirectQuery widget 0.56 s; cold import render 1.08 s after sidecar; aggregate dashboard 0.165 s cold; latency linear in source rows without indexes; index advice derived from observed runs | Depends on the warehouse; the platform adds little overhead; async removes UI blocking for slow queries |

**Natural language to SQL to validation to execution in Datalytics** (Confirmed: `services/agent/`): classify → clarify if underspecified → context (catalog, glossary, entities, confirmed examples, retrieval with TF-IDF and optional embeddings behind a circuit breaker) → plan → DAG of steps, each generate → ladder (V1 parse/SELECT-only, V6 column security before V2 schema, V3 join whitelist, V4 row policies injected into the parsed AST, V5 dry-run with statement timeout and hard row cap) → execute in sandboxed DuckDB over already-secured frames (dataset mode) or against the source with policies (connection mode) → sanity check → explain, with a bounded repair loop inside the node. Every run and step is persisted with hashed SQL. Superset has no equivalent path because it has no NL layer in core.

---

## 5. AI and natural-language analytics

| Aspect | Datalytics | Superset |
|---|---|---|
| Natural-language questions | Yes: Ask AI page scoped to a dataset or a live connection; a page copilot inside the builder that edits widgets or delegates data questions | No first-party feature in core *(verify: community assistants and the commercial Preset offering exist; not part of Apache Superset)* |
| Text-to-SQL | Yes, with schema context, glossary, entities, confirmed question→SQL examples, JSON-schema-enforced model output | No |
| LLM integration | `services/llm.py` against any OpenAI-compatible endpoint; concurrency gate with reserved interactive slots; failure returns `None` and degrades; a boot-time contract probe | None in core |
| Local LLM | Yes by design: self-hosted vLLM; `llm_enabled=False` runs with no AI at all; nothing leaves the network | n/a |
| Ollama | Ollama exposes an OpenAI-compatible API, so it should work by pointing `llm_base_url` at it; **not verified in this repo** (no test or doc mentions Ollama); JSON-schema enforcement (`complete_json`) may behave differently on Ollama than on vLLM | n/a |
| SQL validation and security | The six-rung ladder above; policies injected into the AST, never concatenated, never post-filtered; a policy that fails to parse refuses the query; column security refuses a denied name anywhere in the SQL; execution in a sandbox over secured frames; PII masked before any sample reaches the model | n/a |
| Result interpretation | `explain` node renders the answer; narration is digit-guarded (a sentence stating a number the evidence lacks is discarded) and labelled as generated; three answer kinds (`ok`, `needs_clarification`, `failed`) never blurred | n/a |
| Automatic visualisation | Three presentation kinds: a result grid, an analysis card (when the agent runs a registered analysis instead of SQL), and dashboard proposals (whole dashboards proposed from a dataset profile and executed before being offered, with cross-filter relations); `suggest_from_insights` builds charts with no model at all | Chart-type recommendation in Explore is heuristic (dataset shape); no AI generation in core |
| Conversational analytics | Conversations persisted with messages, runs, steps, feedback; scoped per dataset/source; resumable; run detail exposes SQL per step; CSV/XLSX/PDF export per answer | n/a |
| Context awareness | Catalog with confirmed relationships and entities, glossary with multilingual synonyms, confirmed examples (a verified question→SQL memory), retrieval scoring; Arabic questions supported | n/a |
| Quality control | An eval gate (`backend/evals/`, nightly opt-in, accuracy threshold) and 👍/👎 feedback stored per run | n/a |

**Does the AI approach provide a competitive advantage?** Yes, and it is the only durable one. Not because Superset cannot add an assistant (it can, and third parties have), but because Datalytics' assistant inherits row policies, column security, PII masking and quotas by construction, and because the same catalog that governs dashboards feeds the model. Bolting an LLM onto Superset gives you a SQL generator; it does not give you a governed analyst without rebuilding the policy layer.

**Concrete improvements that would make the AI experience clearly better than anything on Superset:**

1. **Answer with a chart, not only a grid.** The agent returns rows; the builder's shaper can already draw 67 widgets. Route an `ok` answer through the same automatic chart selection used by dashboard proposals so every answer arrives as the right visual with the grid behind it.
2. **"Add to dashboard" from a chat answer.** The memory note records this was deferred for lack of a SQL widget type. Introduce a `query` widget type whose config carries the validated SQL and the run id, executed through the same ladder on every render. This closes the loop from question to dashboard, which is the workflow Superset users do by hand.
3. **Verified examples as a first-class admin surface.** `query_examples` exist; give admins a page to review, confirm and retire them, with the accuracy gate's results beside each. That is the flywheel that makes accuracy climb per customer.
4. **Show the plan and the ladder in the UI.** The run detail already stores steps and repair attempts; render them as a "how I answered" timeline with the rung that rejected an attempt. Trust is the adoption barrier for NL analytics.
5. **Ask across datasets.** Dataset mode accepts a list of dataset ids; make the UI offer multi-dataset scope with the join suggestions from `infer_keys` feeding the context.
6. **Follow-up intents.** "Break that down by region", "same for last year": conversation state exists; add explicit intent handling for refine/compare/drill so follow-ups reuse the previous plan rather than replanning.
7. **Ollama and llama.cpp validation.** Add a contract test suite per endpoint type, since JSON-schema enforcement is the fragile part.
8. **Measured accuracy per source in Source review.** The eval gate is global; surface per-source accuracy so admins know where the catalog needs work.

---

## 6. Visualisation

| Aspect | Datalytics | Superset |
|---|---|---|
| Chart types | 67 widget types: charts (bar, line, step, dot, needle, histogram, butterfly, area, funnel, ribbon, pie, donut, scatter, treemap, four dual-axis variants, comparative/numeric series, bubble, correlation matrix, heatmap, parallel coordinates, box plot, waterfall, gauge, Gantt, vector, word cloud, forecast, sankey, network, composed graph layers), controls (KPI, card, table, crosstab, matrix, list, text, image, shape, button, slicer, web content, custom visual, container), maps (choropleth, points, bubbles, lines, clusters, pie, layers, density, network), hierarchies (tree, sunburst, icicle, dendrogram, org chart, circle packing), decomposition tree, small multiples | Roughly fifty plugins: ECharts time-series family, bar, pie, funnel, gauge, graph, treemap, sunburst, sankey, radar, waterfall, box plot, bubble, heatmap, histogram, table, pivot table, big number (with trendline), world and country maps, deck.gl layers (scatter, screengrid, hex, polygon, arc, path, geojson, contour, heatmap, multi-layer), calendar heatmap, chord, event flow, horizon, parallel coordinates, partition, nightingale, word cloud, handlebars, markdown |
| Configuration | A properties rail with eight tabs and ten groups; role fields typed by `roleAccepts`; formatting, display rules, sort/limit, ranking, actions, interactions; constants mirrored from the backend and pinned | Explore control panels per plugin; metrics and filters builders; customise tab; annotation layers; time comparison |
| Dashboards | 12-column grid, pages, containers, precision layout, mobile layout, page types (hidden, popup, tooltip, drillthrough) | 12-column grid with rows, columns, tabs, headers, markdown, dividers |
| Interactive filters | Slicers (buttons/list/search/text), report filters, parameters (typed, what-if sliders), bookmarks, synced slicers across pages, page-level prompt | Native filters (select, range, time, time column, time grain) with scoping, default values, dependencies, cascading; filter bar; URL params |
| Drill | Drill-down on authored hierarchies; decomposition tree; drillthrough pages; tooltip pages | Drill to detail; drill by (dimension swap) since 3.x |
| Cross-filtering | Per-widget modes (two-way, broadcast, receive, isolated), per-pair actions, page modes (manual, linked, one-way, two-way), edge pruning on delete, a review pane that reports dead edges | Dashboard-level cross-filters between charts (feature flag, on by default in recent releases), emitter/receiver scoping |
| Customisation | Themes (built-in and org palettes), display rules, per-column formats, RTL mirroring, custom visuals in a sandbox, script tiles | Dashboard theming and colour schemes; 5.x theming tokens; CSS templates |
| Recommendation | Auto-chart from a dropped field; suggestion pane; dashboard proposals from profile and persona; insights-driven composition | Explore picks a default viz type; "chart recommendations" are limited |
| AI-generated charts | Yes (proposals executed before offered, relations applied) | No |

**Which visualisation features to implement first.** Not more chart types; the breadth already exceeds Superset's. The gaps that matter are consistency and time-series depth: (1) a **time-series family with annotations, comparison periods and rolling windows** (Superset's ECharts time-series and its "time comparison" are what analysts miss most); (2) **pivot table v2 parity** (subtotals, conditional formatting on the crosstab); (3) **a base-map provider for coordinate maps** (world atlas only today; the SAS comparison lists this as a gap and no tile integration exists); (4) **filter-scoping** in the native-filter sense (which widgets a slicer reaches) exposed as a first-class control rather than through per-pair actions.

---

## 7. Dashboards

| Aspect | Datalytics | Superset | Gap |
|---|---|---|---|
| Creation and editing | Drag/resize, multi-select align and distribute, autosave with a stale-revision banner, version history with restore (50 kept), templates (page and object), copilot edits | Drag/resize, edit mode with explicit save, "properties" dialog, no autosave, no version history in core | Datalytics ahead on collaboration safety; behind on an explicit "publish this version" concept |
| Layout | Pages, containers, precision layout, mobile layout order/hidden | Rows, columns, tabs | Similar |
| Filters | See §6 | Native filters with dependencies and scoping | Superset's filter scoping and cascading are more explicit |
| Permissions | Capability levels (view/edit/data) per role; per-user grants; folder grants; page-role visibility; publish; classification | Owners and roles; dashboard RBAC (feature flag); dataset access governs what renders | Datalytics finer-grained |
| Sharing | Publish; per-person grants; workspace folders; expiring, revocable, pinned share links with access logs | Permalinks; roles; public role for anonymous access | Datalytics ahead on guest links |
| Embedding | Host-signed JWT exchanged for a 15-minute audience-pinned session token; origin allow-list; `frame-ancestors` CSP; creator identity | Embedded SDK with guest tokens carrying RLS rules; feature flag | Similar; Superset's guest-token RLS rules are per embed, Datalytics' filters only narrow |
| Exporting | Server PDF (banded, TOC, RTL-shaped), browser print, client PPTX, per-widget CSV/XLSX, agent answers to CSV/XLSX/PDF | CSV per chart, dashboard image or PDF through the reports pipeline (headless browser) | Datalytics ahead on PDF quality; PPTX unique; export policy does not yet cover PDF/PPT (a governance gap) |
| Scheduled reports | Schedules (interval or calendar, timezone, xlsx/pdf, email or https webhook), self-serve subscriptions resolved as the subscriber, alerts on the rising edge, in-app notifications, monitoring pages, backoff | Alerts and reports via Celery: SQL-condition alerts, scheduled screenshots or CSV to email/Slack; requires a headless browser | Similar coverage; Datalytics needs no browser; Superset supports Slack natively (Datalytics via webhook) |
| Import/export of definitions | None (no YAML/ZIP export of dashboards or datasets) | Full export/import of dashboards, charts, datasets, databases as ZIP; CLI | **Missing in Datalytics** |
| Tags, certification, favourites | Classification labels, pins, recents; no tags or certification | Tags, certified charts and datasets, favourites | Partial |

---

## 8. Security

| Aspect | Datalytics | Superset |
|---|---|---|
| Authentication | Password (bcrypt), OIDC with PKCE, SAML 2.0 (signature verification, replay protection), API keys; JWT 7 days, no refresh, no revocation; no self-signup; timing-safe login | Flask-AppBuilder: DB, LDAP, OAuth/OIDC, OpenID, REMOTE_USER; sessions with server-side logout; optional MFA via FAB |
| Authorisation | Org scoping (404, never 403); org admin bit; capability levels with a documented precedence; dataflow grants; dataset visibility per user; platform super-admin allowlist | FAB roles (Admin, Alpha, Gamma, sql_lab, custom) with fine-grained permissions on menus, databases, schemas, datasources; dashboard RBAC |
| Row-level security | Rules per role and dataset; dynamic tokens; hierarchical `MYSCOPE()`; fail-closed; evaluated before column drop; inherited by aggregates; applied inside every engine including the agent; separate connection-level object policies for the agent injected into the AST | RLS filters per dataset and role (regular and base filter types), applied as SQL predicates in generated queries; guest-token RLS for embeds |
| Column security | Native rules: denied columns dropped from projections and schema listings; DirectQuery refuses; agent refuses by name; models trained on a denied column refused | None native; achieved through virtual datasets or views |
| Dataset and database permissions | Dataset read resolved from ownership, shares and reachable reports; connection administration by admin or creator | Per-database and per-datasource permissions on roles; schema access |
| SQL injection | Platform-generated SQL with quoted identifiers and bound parameters; user expressions go through a sandboxed evaluator with an allowlist and a separate SQL translator; parameters typed and encoded as literals; agent policies injected as AST nodes | Parameterised where SQLAlchemy is used; Jinja templating is a known footgun and is disabled by default |
| LLM SQL security | The ladder in §4; sandbox execution; PII masking; per-source LLM-sampling opt-in; quotas on asks | n/a |
| Secrets | Encrypted connection config and SSO secrets at rest; API keys hashed; share tokens hashed; embed secrets encrypted and shown once; a rotation trap (rotating `secret_key` breaks stored secrets) | Fernet-encrypted database URIs; `SECRET_KEY` rotation tooling exists |
| Audit | Security-plane admin audit and general activity log, both with pages | Action log (`Log` table), audit via FAB, event logging to files or the DB |

**Security risks in Datalytics found in the survey (all Confirmed):**

1. Export policy is not applied to server PDF, PowerPoint, scheduled deliveries or agent run-file export.
2. JWTs live seven days with no server-side revocation; a deactivated user's token may still be valid (UNKNOWN whether `get_current_user` re-checks `is_active`).
3. The default `secret_key` is `change_me_in_production`; rotating it breaks stored connection secrets.
4. `connector_allow_private_hosts` defaults to true (the SSRF guard is lenient until an operator tightens it).
5. Rate limiting is in-process only; quotas' concurrent-ask counter is per process.
6. Empty embed origin allow-list means unrestricted; a request with no Origin or Referer is allowed.
7. The Connections UI hides administration from a creator who is allowed by the backend; Source review is reachable by URL to any member with an unverified backend gate.

---

## 9. Performance and scalability

| Aspect | Datalytics | Superset |
|---|---|---|
| Query execution | pandas frame (bounded by `import_row_cap` 2M), DuckDB pushdown (default on; 1.5 GB → 60 MB RSS measured), DirectQuery with server-side row cap and true totals | Warehouse does the work; Superset streams results with row limits |
| Concurrent users | Measured tiers at 70 concurrent: health 2 ms, auth 9 ms, cache-hit widget 24 ms; 10 users on one dashboard within the scale targets; the cost is per-request DB round trips, not the work gate | Scales with web workers; async queries decouple slow work; widely deployed at high concurrency |
| Large datasets | Aggregates (scheduled GROUP BY on the source) are the answer for 10M–100M rows; index advice from observed queries | Native: ClickHouse, Trino, BigQuery at any size |
| Async and background jobs | One loop, advisory locks, backoff, isolation; no queue; no mid-step resume | Celery with retries, beat, results backend |
| Caching | Multi-level (client, server, frame, DirectQuery epoch), fail-soft Valkey | Redis with warm-up |
| Horizontal scaling | Multi-worker on one host; files on a local volume (three couplings block object storage, recorded in `first-stop.md`) | Web and workers across nodes; metadata DB and Redis shared |

**Improvements required for production scale.** In order: (1) promote ClickHouse and Trino to DirectQuery families so scale lives in the warehouse; (2) build the storage seam (`first-stop.md` Phase 0) so uploads can move to object storage and multiple backend nodes can share them; (3) move the scheduler and long analyses onto a queue when a mid-step-resume or multi-node requirement appears (the document already gates this on a trigger); (4) shared rate limiting and concurrency counters in Valkey; (5) a results backend for long agent runs so the browser polls rather than holds a request open.

---

## 10. UX and UI

| Aspect | Datalytics | Superset |
|---|---|---|
| Asking a question | Two clicks from any dataset ("Ask about this data"); one scope select; conversations persist; the builder has an inline copilot | Not available in core; the nearest is SQL Lab |
| Clicks to a first chart | Upload → dataset detail → Dashboards → New → Insert widget → pick fields: five to six steps; or one click on "Suggest dashboards" | Connect DB → add dataset → Explore → pick viz and metric → save → add to dashboard: six to eight steps and a modelled dataset first |
| Technical complexity | Low entry; the builder is dense (17 rail modes, 10 property groups); expression grammar shared by filters, rules, measures | Explore is approachable; SQL Lab, Jinja, virtual datasets and filter scoping are technical |
| Non-technical accessibility | Strong: prep steps, custom categories, quick calcs, explain, insights | Moderate |
| Dashboard creation | Autosave, copilot, templates, suggestions; consistency debt (inline styles, three feedback conventions, eight native prompts, no 404, no profile page) | Mature, consistent Ant Design UI; explicit save; polished filter bar |
| Discoverability | Command palette; Insights hub as a front door; but several capabilities were shipped unreachable before (statistics, hierarchies) and one admin page is palette-only | Menus and a consistent chrome; feature flags hide a lot |
| AI interaction | Answer kinds distinguished; SQL shown on demand; feedback; downloads | n/a |
| Accessibility | 358 `aria-label`s, focus-visible ring, a shared focus trap enforced by a test; no skip link | Ant Design baseline; variable across plugins |
| RTL and i18n | RTL app-wide with mirrored charts; ~170 chrome keys in English and Arabic; content untranslated | Many UI translations; no RTL layout |

**UX improvements that would make Datalytics faster than Superset:** (1) a single "ask or build" entry on Home that accepts a question or a file; (2) an answer that is already a chart with an "Add to dashboard" button; (3) collapse the builder's 17 rail modes into task-oriented flows (Design, Data, Share, Automate) with the properties rail's eight tabs as the only object-level surface; (4) consistent state components and one confirmation dialog everywhere (the redesign contract lists the exact sites); (5) a 404 page, an account page, unsaved-draft handling for modal forms; (6) filter scoping visualised on the canvas (which widgets a slicer reaches), replacing the review pane's text list for that case.

---

## Feature comparison table

| Feature | Datalytics | Apache Superset | Winner | Notes / recommendation |
|---|---|---|---|---|
| Natural-language questions with governed SQL | Superior | Missing | Datalytics | The differentiator; keep investing |
| Page copilot that edits dashboards | Superior | Missing | Datalytics | Unique |
| Dashboard proposals from a dataset profile | Superior | Missing | Datalytics | Executed before offered |
| Local/self-hosted LLM, air-gap | Better | n/a | Datalytics | Validate Ollama |
| SQL editor (tabs, history, saved queries, autocomplete) | Partial | Superior | Superset | Build a SQL Lab-class editor only if technical users are a target |
| Async query execution with a results backend | Missing | Better | Superset | Needed for long agent runs and big DirectQuery |
| Live query to cloud warehouses (ClickHouse, Trino, BigQuery, Snowflake) | Partial (import-only) | Superior | Superset | Promote to DirectQuery families |
| Number of supported engines | Similar (45 registered) | Similar (~40 specs, any SQLAlchemy dialect) | Similar | Datalytics is stricter about capabilities |
| File upload as a native dataset | Superior | Partial | Datalytics | |
| Catalog sync, profiling, key inference, drift, PII masking | Superior | Missing | Datalytics | Unique at this depth |
| Business-user data preparation (prep steps, joins, materialize, dataflows) | Superior | Missing | Datalytics | Superset expects dbt |
| Semantic layer (datasets, metrics, calculated columns) | Similar | Better | Superset | Superset's virtual datasets and metrics are cleaner; Datalytics has measures with context functions (`TOTAL`, `BYGROUP`, `CALC`) |
| Chart type count | Superior (67) | Better (~50) | Datalytics | Breadth is not the gap |
| Time-series depth (comparison periods, annotations, rolling) | Partial | Superior | Superset | First visualisation gap to close |
| Pivot table | Partial (crosstab, matrix) | Superior (pivot v2) | Superset | Subtotals and conditional formatting |
| Maps | Better (choropleth, boundary sets, nine map types, no tiles) | Better (deck.gl layers, tiles) | Similar | Add a tile provider |
| Statistical and ML analyses in the UI | Superior (inferential tests, influencers, segments, anomalies, forecast, trees, prediction models with a store) | Missing | Datalytics | Unique |
| Cross-filtering model | Superior (modes, per-pair actions, page modes, edge review) | Better | Datalytics | Expose scoping visually |
| Native filters with scoping and cascading | Partial | Superior | Superset | |
| Drill to detail / drill by | Partial (hierarchies, decomposition, drillthrough pages) | Better | Superset | Add a generic "drill to rows" on any mark |
| Dashboard versioning and restore | Superior | Missing | Datalytics | |
| Autosave and concurrent-edit warning | Better | Missing | Datalytics | |
| Dashboard import/export (YAML/ZIP), CLI | Missing | Superior | Superset | Critical for migration and CI |
| Tags, certification | Missing | Better | Superset | |
| Share links with expiry, revoke, access log, pinned layout | Superior | Missing | Datalytics | |
| Embedding | Similar | Similar | Similar | Superset's guest-token RLS is more flexible per embed |
| Server PDF with RTL shaping, TOC, banded tables | Superior | Partial (screenshots) | Datalytics | Apply export policy to it |
| PowerPoint export | Better | Missing | Datalytics | Client-side; apply export policy |
| Alerts and scheduled reports | Similar | Similar | Similar | Superset needs a headless browser; Datalytics lacks native Slack (webhook works) |
| Self-serve subscriptions resolved as the subscriber | Superior | Missing | Datalytics | |
| Row-level security | Superior (fail-closed, tokens, hierarchy, aggregates, agent) | Better | Datalytics | |
| Column-level security | Superior | Missing | Datalytics | |
| Export policy | Partial (not on PDF/PPT/deliveries) | Missing | Datalytics | Close the gap |
| RBAC granularity | Better (capabilities, grants, folders) | Better (FAB permissions per object) | Similar | Different models |
| Authentication options | Partial (password, OIDC, SAML, API keys; no revocation, no MFA, no LDAP) | Better (FAB: LDAP, OAuth, OpenID, MFA) | Superset | Keycloak plan in `first-stop.md` |
| Session revocation, MFA | Missing | Better | Superset | Critical for enterprise |
| Audit trails | Better (two logs, two pages) | Similar | Similar | |
| Multi-tenancy | Superior (organisations, quotas, org hierarchy, per-org MCP switch) | Missing | Datalytics | Unique |
| Quotas | Superior | Missing | Datalytics | |
| Caching | Similar | Similar | Similar | |
| Horizontal scaling | Partial | Superior | Superset | Storage seam first |
| Background jobs | Partial (in-process loop) | Superior (Celery) | Superset | Trigger-gated |
| Plugin ecosystem for charts | Partial (sandboxed custom visual, script tile) | Superior | Superset | Package the renderer contract |
| Theming | Partial (palettes, dark/light, MCAIT tokens) | Better (5.x theming) | Superset | Redesign scope |
| RTL layout and mirrored charts | Superior | Missing | Datalytics | Unique |
| UI translations | Partial (170 keys, en/ar) | Superior (many languages) | Superset | |
| Test discipline (enforced layering, doc audits, constant mirrors, walkthroughs) | Superior | Better | Datalytics | |
| Deployment simplicity, offline bundle | Superior | Partial | Datalytics | |
| Community, longevity, hiring pool | Missing (single team) | Superior | Superset | The structural risk |

---

## Competitive analysis

1. **Is Datalytics a competitor to Superset?** In the general-purpose BI market, only partially: it loses on warehouse-scale querying, SQL tooling, import/export, authentication breadth and ecosystem, and it wins on governance depth, preparation, analysis, RTL, PDF quality, multi-tenancy and the AI analyst. Head-on against Superset for a SQL-literate data team with a warehouse, Superset wins on cost and risk.
2. **Or an AI layer on top of Superset?** No. The AI layer's value comes from the catalog, the security resolvers and the sandbox that Datalytics owns; on top of Superset it would have to re-implement them against Superset's metadata model and would lose the preparation and statistics surfaces. Your own orientation document reached the same conclusion for the opposite direction (Superset as a component).
3. **Niche that makes it unique.** Governed, Arabic-first, air-gapped self-service analytics with an AI analyst that inherits every rule, for organisations that cannot use cloud BI and whose users are not SQL authors: public sector, regulated finance and health in the Gulf and MENA, defence-adjacent, any tenant that runs "one box, no internet".
4. **Focus instead of copying Superset.** Do not build SQL Lab, a plugin marketplace, forty engine specs or Celery for their own sake. Build: chart answers and add-to-dashboard from chat; verified examples and per-source accuracy; ClickHouse/Trino DirectQuery; dashboard import/export; export policy everywhere; token revocation and MFA (via the Keycloak plan); a consistent UI.
5. **Strongest differentiators.** The governed agent; the preparation and catalog stack (profiling, key inference, drift, PII masking); column security, export policy and multi-tenancy; RTL with Arabic PDF; statistics and prediction models in the UI; deployment as five containers with nothing fetched.

---

## Gap analysis

### Critical gaps (before "production-ready" can be claimed to an enterprise)

- Export policy on server PDF, PowerPoint, scheduled deliveries and agent exports.
- Session revocation and a refresh model (or an identity broker), MFA, LDAP/AD.
- Dashboard and dataset import/export with a CLI (migration between environments, backup of definitions, CI).
- Shared storage seam for uploads and shared rate limiting, or an explicit single-node support statement.
- A 404 route, unsaved-draft handling on modal forms, confirmations on the four unguarded deletes, and error handling on the six silent delete handlers.

### Important gaps (competitiveness)

- DirectQuery for ClickHouse and Trino (then BigQuery, Snowflake).
- Async execution with a results backend for long DirectQuery and agent runs.
- Time-series depth: comparison periods, annotations, rolling windows.
- Native-filter scoping and cascading as first-class controls.
- Generic drill to detail on any mark.
- Pivot-table parity.
- Chart answers and "add to dashboard" from chat; `query` widget type.
- Verified-example management and per-source accuracy.
- Tags, certification, favourites.
- Base-map tile provider for coordinate maps.
- UI consistency pass (the redesign contract).

### Nice to have

- SQL Lab-class editor with history and saved queries (only if technical users become a target).
- Chart plugin packaging beyond the sandboxed custom visual.
- Slack as a native delivery transport (webhooks already work).
- More UI translations beyond chrome.
- Dashboard theming tokens per org beyond palettes.
- Object storage backend, Temporal-class workflow engine (trigger-gated per `first-stop.md`).

---

## Prioritised roadmap

Complexity: S (days), M (weeks), L (a quarter of one engineer). Impact is on the niche above.

### Phase 1 — Immediate improvements

| Feature | Why | Priority | Complexity | Dependencies | Impact |
|---|---|---|---|---|---|
| Export policy on PDF, PPT, deliveries, agent exports | A governance product with a bypass is not credible | Critical | S–M | `_policy_dataset`, delivery pipeline | Closes the one security gap an auditor will find first |
| Chart answers in Ask AI | Every answer arrives as a visual; the largest visible UX win | High | M | dashboard-proposal shaper, `WidgetRenderer` | Makes the differentiator obvious in a demo |
| `query` widget + "Add to dashboard" from chat | Closes question → dashboard | High | M | validation ladder on render, widget catalog | The workflow Superset users do by hand |
| UI consistency pass (state components, one dialog, 404, account page, delete guards) | Removes the debt catalogued in the redesign contract | High | M | redesign contract | Perceived quality |
| Ollama/llama.cpp contract tests | Local-LLM claim must be true on the endpoints customers run | Medium | S | `services/llm.py` | Credibility of "runs on your box" |
| Verified-examples admin page + per-source accuracy | Turns the eval gate into a flywheel | Medium | M | `query_examples`, eval gate | Accuracy per customer |

### Phase 2 — Competitive features

| Feature | Why | Priority | Complexity | Dependencies | Impact |
|---|---|---|---|---|---|
| ClickHouse and Trino DirectQuery families | Removes the scale ceiling; the stacked strategy | Critical | M | connector registry, `direct_query.py` capability sets, index advice | Competes at warehouse scale |
| Dashboard/dataset import/export + CLI | Migration, backup, CI, multi-environment | Critical | M | serialisers for report/page/widget/dataset/rules | Enterprise adoption blocker |
| Async execution with a results backend | Long queries and agent runs without held requests | High | L | Valkey, scheduler, frontend polling | Concurrency headroom |
| Time-series depth (comparison, annotations, rolling) | Most-requested analyst feature Superset has | High | M | shapers, renderers, config panel | Analyst satisfaction |
| Native-filter scoping and cascading | Superset's filter bar is the benchmark | High | M | cross-filter context, review pane | Dashboard usability |
| Generic drill to detail | Expected by every BI user | Medium | S–M | widget-data with a row query | Trust in numbers |
| Pivot parity (subtotals, conditional formats) | Crosstab is the most used business visual | Medium | M | crosstab shaper | Finance users |
| Tags, certification, favourites | Content governance at scale | Medium | S | models, list pages | Discoverability |
| Tile provider for maps | Recorded SAS gap | Medium | S–M | configurable tile URL, offline tile pack | Geo customers |

### Phase 3 — Advanced AI analytics

| Feature | Why | Priority | Complexity | Dependencies | Impact |
|---|---|---|---|---|---|
| "How I answered" timeline (plan, rungs, repairs) | Trust is the adoption barrier | High | M | `agent_runs/steps` | Adoption |
| Follow-up intents (refine, compare, drill) | Conversation quality | High | M | agent state, planner | Retention |
| Multi-dataset questions with key suggestions | Real questions cross tables | High | M | `infer_keys`, dataset mode | Coverage |
| Agent invokes analyses and prediction models with narrated results | Nobody else has a governed statistician in chat | Medium | M | analysis registry (already dispatchable), narration guard | Category-defining |
| Proactive insights delivered by schedule (anomaly digest) | Insights exist; deliver them | Medium | M | insights engine, delivery | Stickiness |
| Per-tenant fine-tuning data export (confirmed examples, feedback) | Customers want their own model | Low | S | `query_examples`, feedback | Enterprise AI story |

### Phase 4 — Enterprise readiness

| Feature | Why | Priority | Complexity | Dependencies | Impact |
|---|---|---|---|---|---|
| Identity broker (Keycloak) with provisioning, revocation, MFA, LDAP | The authentication gap | Critical | L | `first-stop.md` Phase 1 plan | Enterprise gate |
| Storage seam → object storage | Multi-node and versioning | High | L | frame cache keys, DuckDB paths, materialization records | Horizontal scale |
| Shared rate limiting and concurrency counters | Correctness across workers | Medium | S | Valkey | Ops |
| Secret rotation tooling | The rotation trap | Medium | S | `services/secrets.py` | Ops safety |
| Queue-backed scheduler with mid-step resume (trigger-gated) | Durability | Medium | L | trigger per `first-stop.md` | Reliability |
| SOC-style audit export and retention | Compliance | Low | S | audit tables | Compliance |

---

## Final evaluation

### Overall score (1–10)

| Dimension | Datalytics | Superset | Basis |
|---|---|---|---|
| AI analytics | 8 | 1 | Governed NL→SQL with a ladder, sandbox, catalog context, proposals, copilot; loses points for grid-only answers, no add-to-dashboard, unvalidated Ollama |
| Data connectivity | 6 | 9 | Registry is good and file-first; warehouses import-only; catalog depth is ahead but live scale is behind |
| Visualisation | 8 | 8 | More types and richer interaction model; less time-series depth and pivot maturity; consistency debt |
| Dashboarding | 8 | 8 | Autosave, versions, share links, PDF ahead; import/export, filter scoping, tags behind |
| Security | 8 | 7 | Governance depth ahead; authentication breadth, revocation and the export-policy gap behind |
| Scalability | 5 | 9 | Single host, in-process jobs, 2M import ceiling; aggregates and DuckDB mitigate |
| UX | 6 | 7 | Faster to a first answer; dense builder and consistency debt; RTL ahead |
| Extensibility | 5 | 8 | Registries and enforced layers, sandboxed visuals; no plugin packaging or ecosystem |
| Enterprise readiness | 5 | 8 | Multi-tenancy, quotas, audits ahead; identity, import/export, horizontal scale, single-team risk behind |

### Datalytics' five biggest advantages

1. A natural-language analyst that inherits row policies, column security, PII masking and quotas by construction, executes in a sandbox, and persists every step.
2. Business-user data preparation and a catalog pipeline (profiling, key inference with accuracy tests, drift, PII masking, index advice) that Superset does not attempt.
3. Governance depth: column security, export policy, capability precedence, folder grants, aggregates that inherit rules, multi-tenancy with quotas.
4. Arabic and right-to-left end to end, including server PDFs, and a five-container offline deployment.
5. Analysis breadth inside the product: inferential tests, key influencers, segmentation, anomalies, forecasting, decision trees, a prediction-model store, small multiples, hierarchies, decomposition, 67 widgets.

### Datalytics' five biggest weaknesses

1. Scale: a 2M-row import ceiling, warehouses import-only, one host, an in-process scheduler.
2. Identity: seven-day tokens without revocation, no MFA or LDAP, no self-service password flow.
3. Portability: no dashboard or dataset import/export, no CLI, no plugin packaging.
4. UI consistency and the answer surface: grid-only AI answers, a dense builder, three feedback conventions, native prompts, no 404 or account page.
5. Structural risk: one team, no community, a codebase whose discipline is high but whose bus factor is real.

### Top 10 features to build next

1. Export policy applied to PDF, PowerPoint, deliveries and agent exports.
2. Chart answers in Ask AI, with "Add to dashboard" through a `query` widget.
3. ClickHouse and Trino as DirectQuery families.
4. Dashboard and dataset import/export with a CLI.
5. Identity broker with revocation, MFA and LDAP.
6. Async execution with a results backend.
7. Time-series depth: comparison periods, annotations, rolling windows.
8. Native-filter scoping and generic drill to detail.
9. Verified-examples management and per-source accuracy in Source review.
10. The UI consistency pass from the redesign contract.

### Strategic recommendation

Do not build a full Superset alternative. On the axes where Superset is strong (warehouse scale, SQL tooling, ecosystem, community) you would spend years to reach parity with a free product that already has it, and every hour spent there is an hour not spent on the axes where you are ahead by a distance.

Build the AI-first, governed, Arabic-capable analytics platform that Superset does not solve well, and put a warehouse under it rather than competing with one: promote ClickHouse and Trino to live query, keep the preparation and catalog stack for the data that is not yet modelled, and make the analyst answer with charts that land on dashboards. Close the three enterprise gaps that would stop a purchase (export policy everywhere, identity, import/export), then let the rest of Superset's feature list go.

The evidence for this is in your own repository: the architecture is built around governance in the query path, the agent is the only component whose design has no equivalent in Superset, and the recorded decision on Superset ("reject as a block, study as a reference for the semantic layer") already points the same way.
