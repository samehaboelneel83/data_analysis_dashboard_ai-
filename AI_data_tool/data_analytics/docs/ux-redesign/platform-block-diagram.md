 #Datalytics — Platform Block Diagram

Extracted from `2026-09-13-application-analysis.md` only. Every block traces to a section; nothing is inferred beyond what that document states. Blocks marked **?** are listed in the document as UNKNOWN or unverified.

---

## 1. Deployment blocks — what runs where

Five containers on one Docker network, plus optional external endpoints. `llm_enabled=False` runs the whole platform with no AI at all. Nothing phones home: models, maps, fonts and drivers ship inside the images. *(§1.2, §2.1)*

```mermaid
flowchart TB
  subgraph CLIENTS["Clients"]
    BROWSER["Browser — React / Vite SPA<br/>32 pages behind 34 routes"]
    GUEST["Guest surfaces<br/>share link · embedded iframe"]
    MACHINE["Machine caller<br/>API key, e.g. an MCP server"]
  end

  subgraph NET["One Docker network — self-hosted, air-gap capable"]
    NGINX["nginx — production profile<br/>serves the built frontend"]
    API["FastAPI backend<br/>25 router modules · 27 include_router calls<br/>+ in-process scheduler loop, 60 s tick"]
    PG[("PostgreSQL 16<br/>77 tables · 29 migrations · head 0029")]
    VK[("Valkey — optional result cache<br/>fails soft, degrades to in-process")]
    EMBED["Embeddings service — local<br/>TF-IDF fallback when down"]
    VOL[["uploaded_files volume<br/>+ Parquet sidecar per dataset"]]
  end

  subgraph EXT["Outside the platform"]
    VLLM["vLLM — self-hosted, OpenAI-compatible<br/>OPTIONAL: llm_enabled=False removes all AI"]
    CUSTDB[("Customer databases and APIs<br/>45 connectors · 36 DirectQuery-capable")]
    MAIL["SMTP and https webhooks<br/>scheduled delivery"]
    IDP["OIDC and SAML 2.0 identity provider<br/>authenticates only, never provisions"]
    OTEL["OpenTelemetry collector — opt-in"]
  end

  BROWSER --> NGINX --> API
  GUEST --> API
  MACHINE --> API
  API --> PG
  API --> VK
  API --> EMBED
  API --> VOL
  API -.optional.-> VLLM
  API --> CUSTDB
  API --> MAIL
  BROWSER -.full-page redirect.-> IDP
  IDP -.token in URL fragment.-> BROWSER
  API -.opt-in.-> OTEL
```

| Block | Fact the document pins to it | § |
|---|---|---|
| Frontend | 32 page files · 34 routes · 67 widget types · 264 API functions in one file | §1.3 |
| Backend | 25 router modules, scheduler runs **in-process**, not as a separate container | §1.2, §1.3 |
| PostgreSQL | 77 tables, no soft delete anywhere — hard CASCADE / SET NULL / RESTRICT | §1.3, §10 |
| Valkey | optional; `/health/ready` reports `degraded`, renders continue | §1.2, §16 |
| Embeddings | local service; silent TF-IDF fallback | §1.2, §16 |
| vLLM | optional and external; down ⇒ "could not classify the question", narration returns null | §1.2, §16 |
| nginx | production serving profile (listed as a closed gap) | §1.4 |
| net_guard | SSRF guard on outbound connector traffic; metadata IPs always blocked | §16 |

---

## 2. Request-path blocks — one call from click to row

Every frontend call passes the same stack. All 264 calls go through **one** Axios instance; no other frontend file performs HTTP. Only 401 is handled centrally; there is no automatic retry anywhere.

```mermaid
flowchart TB
  UI["UI surface<br/>6 render surfaces share WidgetRenderer"]
  APIC["services/api.ts — single Axios instance<br/>264 functions in 67 *Api objects · base /api/v1<br/>widget-data: de-dup, 30 s TTL cache 100 entries, concurrency gate 6<br/>401 interceptor logs the session out; 403 has no handler"]
  RL["Rate-limit middleware — in-process<br/>300 req / 60 s per user · 60 for guests"]
  AUTH["Identity resolution — 18 identity classes<br/>JWT 7 d · API key · share token · embed session token"]
  ORG["Org scope — cross-tenant answers 404, never 403"]
  CAP["Capability resolution<br/>admin &gt; author &gt; user grant &gt; folder grant &gt; published &gt; none"]
  QUOTA["Quotas — 4 nullable per-org limits<br/>429 with Retry-After · 413 on storage"]
  ROUTER["Routers — 25 modules"]
  SVC["Service layer"]
  GOV{{"GOVERNANCE CHOKE POINT<br/>1. row rule applied over EVERY column<br/>2. denied columns dropped<br/>rules fail CLOSED — a broken rule returns zero rows"}}
  ENGINE["Execution engine — see diagram 3"]
  STORE[("Data")]

  UI --> APIC --> RL --> AUTH --> ORG --> CAP --> QUOTA --> ROUTER --> SVC --> GOV --> ENGINE --> STORE
  GOV -.audit.-> AUDIT["audit_log · admin_audit · query_runs · deliveries"]
```

Ordering inside the choke point — row rule first, column drop second — is a decision the document records as settled on 2026-09-13 and explicitly not to be reopened. *(§14.12)*

---

## 3. Execution-path blocks — the three engines

These three paths explain most of the code, and they are not interchangeable: the path decides what a widget can do and what "empty" means. *(§1.2, §14.6–14.9)*

```mermaid
flowchart LR
  REQ["Widget / question request"]

  subgraph IMPORT["Import mode"]
    I1["Data on the uploaded_files volume<br/>+ Parquet sidecar"]
    I2["pandas over the whole frame<br/>or DuckDB pushdown when eligible"]
    I3["row rule on the frame → denied columns dropped"]
  end

  subgraph DQ["DirectQuery mode"]
    D1["Data stays in the customer database<br/>5 SQL families"]
    D2["Aggregation pushed into dialect-correct SQL"]
    D3["row rule translated into WHERE<br/>denied column in a widget ⇒ 403, never silently dropped"]
    D4["NEVER falls back silently<br/>unsupported feature raises, visibly"]
  end

  subgraph AGENT["Agent mode"]
    A1["Sandboxed DuckDB over ALREADY-secured frames"]
    A2["Generated SQL through a six-rung validation ladder"]
    A3["inherits the same RLS<br/>object row policies injected into the parsed AST"]
    A4["Connection scope obeys CONNECTION row policies,<br/>not dataset rules — a separate system"]
  end

  REQ --> I1 --> I2 --> I3
  REQ --> D1 --> D2 --> D3 --> D4
  REQ --> A1 --> A2 --> A3 --> A4
```

**Aggregate datasets** are the bridge: a scheduled GROUP BY over a DirectQuery source, saved as an import dataset. They carry no rules of their own — the source's rules apply at read time, and the grain must cover every column a rule reads. *(§14.17)*

---

## 4. Subsystem blocks — the backend surface by router prefix

*(§9.3, §5.1)*

```mermaid
flowchart TB
  subgraph IN["Data in"]
    R1["/data-sources — connections, metadata, source review"]
    R2["/custom-connectors"]
    R3["/relationships"]
  end
  subgraph MODEL["Model and prepare"]
    R4["/datasets — datasets, analysis, hierarchy, widget-data,<br/>prediction models, metadata stats"]
    R5["/analysis — analysis registry"]
    R6["/dataflows"]
    R7["/boundary-sets"]
  end
  subgraph OUT["Consume and distribute"]
    R8["/reports — reports + report copilot"]
    R9["/widget-templates"]
    R10["/workspace"]
    R11["/pins"]
    R12["/shared"]
    R13["embed — /reports/{id}/embed-configs and /embed/*"]
    R14["/notifications"]
  end
  subgraph GOVBLK["Govern and operate"]
    R15["/auth — auth + SSO at /auth/sso"]
    R16["/admin"]
    R17["/platform"]
    R18["/agent"]
    R19["/demo"]
  end
```

Governance blocks that every read passes through, wherever it originates: row security, column security, capability levels, export policy and quotas — applied by **every** engine, including the AI. The document states there is no path that returns a row the viewer may not see. *(§2.1)*

---

## 5. Background blocks

```mermaid
flowchart LR
  TICK["In-process scheduler — 60 s tick<br/>advisory locks · per-item isolation · 5-minute floor"]
  F1["Dataset refresh<br/>DirectQuery datasets never refresh"]
  F2["Dataflow refresh — outputs refresh with the flow"]
  F3["Derived / aggregate rebuild"]
  F4["Schedules and subscriptions → SMTP / https webhook"]
  F5["Alerts — rising edge only, over the creator's secured frame"]
  BO{{"ScheduleFailure backoff<br/>5 → 15 → 60 → 240 → 720 → 1440 min, then daily forever<br/>success deletes the row"}}
  MON["Monitoring: Jobs · Deliveries · Activity"]

  TICK --> F1 --> BO
  TICK --> F2 --> BO
  TICK --> F3 --> BO
  TICK --> F4 --> BO
  TICK --> F5 --> BO
  BO --> MON
```

Metadata sync (`Run sync` on Source review) is **triggered, never scheduled**; a restart force-fails stuck `running` rows. *(§11.6)*

---

## 6. Identity blocks — who a query runs as

Not a hierarchy of three roles: the code distinguishes **18 identity classes**. The blocks that matter for a diagram are the ones where the executing identity is not the person at the screen. *(§4, §14.32–14.35)*

| Surface | Runs as |
|---|---|
| Signed-in app | the user |
| Share link, anonymous | the link's **creator** |
| Share link, viewer signed in to the same org | the **viewer** |
| Embedded report | always the config's **creator** |
| Scheduled delivery | the schedule's **creator** |
| Subscription | the **subscriber** (their own schedule) |
| Print view | the **printing user** |
| API key | the **issuing user**, no scopes |
| Org admin | bypasses row and column rules |

---

## Needs verification

- **Which metadata sync module is live** — `metadata/sync.py` and `metadata/catalog_sync.py` both write `SyncRun.status`; the document records which is live for which trigger as UNKNOWN. *(§10.3 item 6)*
- **Eval gate** — runs, but the document records no UI for it. *(§16)*
- **Base-map / tile provider** — none exists in this checkout; boundary sets ship as a bundled world atlas. *(§16)*
- **`postgres/init.sql`** — a stale 8-table bootstrap including a `charts` table with no model; the live schema is `create_all` plus 29 migrations. Do not draw it as part of the system. *(§10.3 item 1)*
