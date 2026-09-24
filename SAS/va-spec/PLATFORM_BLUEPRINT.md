# Platform blueprint — building a professional data analytics product

An original full-stack design, informed by seventeen sessions of observing a mature commercial BI product. Nothing here is copied from that product: the observations told us which problems are real and which solutions earn their keep; the design below is the one I would build.

Read `RECOMMENDATIONS.md` first for the product judgement. This is the engineering.

---

## 0. The one-paragraph architecture

A **semantic layer** turns physical tables into typed data items. A **query compiler** turns an object's role assignment into a query plan and pushes aggregation to the warehouse. A **session-scoped executor** runs plans, dictionary-encodes strings, and returns results inline when small and by reference when large. A **document service** stores report definitions as versioned JSON, separate from results. A **thin client** holds the document, asks for one result per object, and renders through a single drawing layer that also serves export and mobile. Everything else — identity, authorization, content, preferences, localization, fonts — is a small service behind one gateway.

---

## 1. Layer map

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLIENTS         web app · embedded SDK · PWA/mobile · export worker │
├─────────────────────────────────────────────────────────────────────┤
│  EDGE            gateway · authn · rate limit · tenant routing       │
├─────────────────────────────────────────────────────────────────────┤
│  APP SERVICES    documents · query · exports · thumbnails            │
│                  content · identity · authorization · preferences    │
│                  localization · fonts · maps · notifications         │
├─────────────────────────────────────────────────────────────────────┤
│  SEMANTIC        data sources · data items · relationships · policy  │
├─────────────────────────────────────────────────────────────────────┤
│  QUERY ENGINE    plan compiler · cache · executor pool · governor    │
├─────────────────────────────────────────────────────────────────────┤
│  DATA PLANE      warehouse / lakehouse · in-memory tier · object store│
└─────────────────────────────────────────────────────────────────────┘
```

Build the **document service, semantic layer, query engine and one client** first. Everything else is replaceable.

---

## 2. Data plane

**Do not build a storage engine.** Sit on DuckDB (single-node and embedded), ClickHouse (self-hosted scale) or the customer's Snowflake/BigQuery/Databricks. Your value is the semantic layer and the interaction model, not another columnar store.

**Three tiers, chosen per data source:**

| Tier | When | Mechanism |
|---|---|---|
| **Live** | source is fast, or data must be current | compile to SQL, push everything down |
| **Accelerated** | dashboards over a slow source | materialise a columnar extract on a schedule; keep the semantic layer identical |
| **In-memory** | interactive exploration over ≤ a few hundred million rows | load into DuckDB/Arrow per session, hash-encode strings once |

The subject's headline capability is sub-second interaction over 2.3M rows; that is unremarkable for a columnar engine today. **Choose the tier per source and make the choice visible to the author**, because it determines whether a filter is instant or takes ten seconds.

**Row-level security belongs here, not in the client.** Every compiled query carries the caller's identity and the policy predicates get `AND`-ed into the `WHERE` clause server-side. A filter the client can remove is not security.

---

## 3. Semantic layer

This is the heart of the product. Two rules decide whether the rest works:

> **Rule 1 — a data item is a mapping, and both halves are visible.** Label and physical column are distinct fields. Users rename freely; queries never break.
>
> **Rule 2 — role schemas are data, not code.** Objects declare their roles in a registry. A custom template can add an object type with its own named roles without a deploy.

```jsonc
// DataItem
{
  "id": "di_7f3",
  "label": "Customer Age",           // what the user sees and renames
  "columnName": "CUST_AGE",          // physical, never shown in titles
  "sourceId": "ds_retail",
  "classification": "measure",       // category | measure | date | geography | hierarchy
  "semanticType": "age",             // ← see §3.1. drives aggregation + veto
  "defaultAggregation": "average",   // inferred, never blindly "sum"
  "format": {"type":"number","decimals":0},
  "sensitivity": "quasi-identifier", // propagates to derived items
  "cardinality": 74,                 // cached, refreshed on profile
  "nullCount": 1694312,
  "derivation": null                 // set for calculated items, hierarchies, geography
}
```

### 3.1 Semantic typing is the highest-value thing you will build
Every serious defect in the subject traces back to one missing concept: **the system knows a column is numeric but not what it means.** It sums latitudes, sums years, sums identifiers, and recommends charts built from them.

On profile, classify each column into a `semanticType`: `latitude`, `longitude`, `year`, `identifier`, `code`, `postal`, `currency`, `count`, `ratio`, `percentage`, `duration`, `age`, `score`, `unknown`. Derive it from name patterns, value range, cardinality-to-row ratio, uniqueness and format. Then enforce:

| Semantic type | Default aggregation | Sum allowed? | Eligible as a measure in auto-selection? |
|---|---|---|---|
| `latitude` / `longitude` | none — it is a coordinate | **never** | **no** |
| `identifier` / `code` | `distinctCount` | **never** | **no** |
| `year` | none — it is a date part | **never** | **no** |
| `age` / `score` / `ratio` | `average` | warn | yes |
| `currency` / `count` | `sum` | yes | yes |
| `percentage` | `average` (weighted if a weight exists) | **never** | yes |

**This one table removes roughly a third of the subject's catalogued defects** — the summed latitudes, the summed years, the nonsense suggestions, the meaningless auto-charts.

### 3.2 Aggregation is a first-class expression
Store `{ column, aggregation, filterContext, scope }`, not a string. Non-additive aggregations (`distinctCount`, `median`, percentiles) must be **recomputed at each level**, never summed from displayed cells — subtotals, grand totals and "other" buckets all query at their own grain. The subject gets this right and it is worth the cost.

### 3.3 Calculated items
An expression AST, not a string, with a small typed function library. Store the AST; render the text. Validate on every keystroke, and report errors with a position. Let an item declare a `scope` (`row`, `groupBy`, `fixed`, `grandTotal`) — the "fixed group-by context" idea is genuinely useful and most tools lack it.

---

## 4. Query engine

### 4.1 Compilation
```
Object + RoleAssignment + FilterStack + RankStack
  → logical plan (dimensions, measures, filters, ranks, limits)
  → physical plan (SQL or DuckDB relation)
  → result set + string dictionary
```

Compile **per object**, not per page: objects have different filter stacks. But **execute a page's plans in one request** — the subject's one-job-per-object stream is its clearest protocol mistake.

### 4.2 The wire protocol

Copy the shape, fix the details.

```http
POST /v1/sessions                          → 201 {sessionId, expiresAt}
DELETE /v1/sessions/{id}                   → 204

POST /v1/sessions/{id}/query               → 200
{
  "requests": [                            // ← batch: a whole page in one call
    {"ref":"obj_a","plan":{…},"maxRows":5000},
    {"ref":"obj_b","plan":{…},"maxRows":5000}
  ],
  "stringEncoding": "dictionary",
  "inlineLimit": 262144,                   // bytes; larger results spill
  "waitMs": 30000                          // long-poll, not a poll loop
}

→ {
  "results":[
    {"ref":"obj_a","status":"ok","inline":{"columns":[…],"rows":[…],"dictionary":[…]},
     "truncation":{"applied":false},"rowsScanned":2339245,"rowsReturned":6,"elapsedMs":412},
    {"ref":"obj_b","status":"ok","href":"/v1/results/r_88f1","expiresAt":"…",
     "truncation":{"applied":true,"limit":5000,"total":748213,"reason":"rowLimit"}}
  ]
}
```

Non-negotiables in that payload:

- **`truncation` is always present**, with the limit, the true total and the reason. Never a tiny ⓘ.
- **`rowsScanned` vs `rowsReturned`** — so an object can honestly print *"646K of 2.3M"*, and so two objects on one page can be detected as describing different populations.
- **Dictionary-encoded strings** — the subject's `indexStrings=true`, and it is the right call.
- **Inline when small, by reference when large** — the subject's `embeddedData=limited`, also right.
- **Long-poll with an explicit `waitMs`**, and `202 + Retry-After` when the work outlives it. **Never a non-standard status**; the subject's `449` on session creation is a trap.
- **Idempotency key per request** so a retry cannot double-run an expensive plan.

### 4.3 Caching, at three levels
1. **Plan cache** — identical logical plan + identical policy context → reuse the result id.
2. **Result cache** — keyed by plan hash and data-source version; invalidated by a version bump, never by TTL alone.
3. **Dictionary cache** — string dictionaries are stable per column and per session; send them once.

### 4.4 Governor
Per-tenant and per-user concurrency caps, a wall-clock budget per query, a scanned-bytes budget, and a **cancel** endpoint wired to the client so navigating away kills the work. Surface the budget in the error: *"stopped after 30 s and 4.2 GB scanned"* beats *"query failed"*.

---

## 5. Document service

Report definitions are **versioned JSON documents**, completely separate from results.

```jsonc
{
  "id":"rep_9k2","version":47,"schemaVersion":3,
  "title":"Q3 Retail Review",
  "dataSources":[{"id":"ds_retail","ref":"…","items":[…]}],
  "parameters":[…],
  "commonFilters":[…],
  "pages":[{
    "id":"pg_1","type":"basic","layout":{"mode":"grid","cells":[…]},
    "prompts":[…],
    "objects":[{
      "id":"obj_a","type":"bar","title":{"mode":"auto"},
      "roles":{"category":["di_dept"],"measure":["di_sales"]},
      "filters":[…],"ranks":[…],"displayRules":[…],"options":{…}
    }]
  }],
  "actions":[{"source":"obj_a","target":"obj_b","mode":"filter"}]
}
```

- **Separate definition from results, always.** The subject does this and it is why one definition can render in a browser, a PDF and a phone.
- **Version every save**; keep a bounded history; make restore one click.
- **Autosave by diff, not by whole-document PUT.** The subject PUTs the entire content on essentially every change. Send a JSON patch, debounce at ~750 ms, and keep a local mirror so a network blip is invisible.
- **Migrate on read** with `schemaVersion`. You will change this schema ten times in year one.

---

## 6. Rendering

The subject's single most consequential decision is a 13 MB WebAssembly engine drawing every visual to a 2D canvas. It buys one renderer for browser, export and mobile — and costs it the accessibility layer entirely.

**Take the benefit, refuse the cost. Render twice from one scene graph:**

```
Data + encoding spec → scene graph → ├── canvas/WebGL painter   (pixels, fast, exportable)
                                     └── DOM/ARIA projector     (a real accessible table)
```

The scene graph is the contract. The painter handles millions of marks; the projector emits a `<table>`, a summary, and focusable marks in the same order. **Both are generated from one model, so they cannot drift.** This is the accessibility answer the subject never found, and it is cheap if you design for it on day one and impossible to retrofit later.

Practical guidance: SVG up to ~2k marks (crisp, inspectable, free accessibility), canvas beyond, WebGL beyond ~100k. Bin before you draw — and when you bin, **say so on the object** ("binned: 748K points"), which the subject does not.

**One naming function** produces the object title, the accessible name and any undo label. The subject has at least three and they disagree.

---

## 7. Client architecture

| Concern | Choice |
|---|---|
| Framework | anything mainstream — React or Svelte. Do **not** write a component framework; the subject did and it shows in the payload |
| State | one normalised document store + a separate results cache keyed by plan hash. Never mix definition and data in one tree |
| Undo | a **command log** over the document, not state snapshots. Every command carries a human sentence: **verb, item, role, object, value**. One grammar — the subject has seven |
| Budget | **≤ 2 MB initial JS**, route-split, renderer lazy-loaded on first object, analytics chunks on demand. The subject ships 45 MB of JS and a 13 MB WASM before a single query |
| Localization | one locale, split by route. The subject loads 2.7 MB of bundles up front |
| Offline | a service worker for the shell; an IndexedDB mirror of the open document |
| Routing | **real URLs** — `/reports/{id}/pages/{pageId}?mode=view&filters=…`. The subject has a single route and no history, and it cannot be retrofitted |

### 7.1 Responsive, properly
Absolute placement *and* a reflow mode, chosen per page by the author. Below the breakpoint: stack the prompt bar, wrap control bars, give each object a minimum legible size and let the page scroll vertically. The subject scrolls its prompt strip sideways at phone width and never reflows the canvas — do the opposite.

---

## 8. Platform services

Keep them small, boring and behind one gateway.

| Service | Notes |
|---|---|
| **Identity** | OIDC. `@currentUser` convenience routes are a good idea |
| **Authorization** | **`POST /v1/authorization/decisions:batch`** — the single best API idea observed. A toolbar asks once for fifty decisions. Every decision returns a **reason code** (`not_saved`, `no_permission`, `not_licensed`, `no_content`, `no_selection`) so the UI can say *why* a control is disabled. The subject has five distinct causes behind one undifferentiated grey |
| **Content** | folders, favorites, recents, shortcuts, recycle bin, search facets. One RQL-ish grammar (`filter=and(eq(a,b))`, `sortBy=f:desc`, `start`/`limit`) — but **page everything**; never `limit=32767` |
| **Preferences** | per-user, read and written back |
| **Localization** | message bundles per locale per route |
| **Fonts** | a font service keeps browser, PDF and mobile typography identical |
| **Maps** | basemap catalogue; **make the default theme-aware** (swap to a high-contrast tileset under the high-contrast theme — the subject does this and it is excellent). Third-party providers behind explicit, revocable consent stored per user |
| **Thumbnails / Exports** | async job services with a poll-or-webhook contract, rendering through the **same** scene graph |
| **Notifications / Alerts** | subscriptions on an object plus a threshold, evaluated server-side |

---

## 9. Security and tenancy

- **Row-level policy in the compiler**, never in the client.
- **Column-level sensitivity** on the data item, inherited by every derived item, surfaced as a badge with a plain-language explanation, and enforceable as a redaction policy. The subject shows the badge but does not enforce anything.
- **Tenant isolation** at the connection and the cache key. A plan hash without a tenant id is a data leak waiting to happen.
- **Audit** every query with user, plan hash, rows scanned, policies applied.
- **Embedding**: signed, scoped, short-lived tokens for a single report and a single filter context.

---

## 10. Build plan

| Phase | Ships | Done when |
|---|---|---|
| **1. Spine** (6–10 wks) | semantic layer with semantic typing · plan compiler · session/query API with truncation contract · document service with versioned autosave · one client: bar, line, table, crosstab · typed roles with filtered pickers · command-log undo | a user builds a four-object page over a real warehouse table without writing SQL |
| **2. The loop** (6–8 wks) | filter stack (object/page/report) · controls as filter sources · cross-object actions · prompt bars · **one inspectable filter stack shown identically to author and reader** | a reader can answer *why am I seeing this?* without asking |
| **3. Depth** (8–12 wks) | calculated items + expression editor · display rules · ranks · non-additive totals at grain · export via the shared scene graph · real URLs | a finance team replaces a spreadsheet |
| **4. Differentiators** (ongoing) | geography with a **live mapping validation panel** · map layer stack · forecasting with scenario/goal-seek · the statistical family with model headers and model comparison | an analyst stops exporting to Python |
| **5. Assistive** (last) | suggestions · automatic chart selection · outlier advisor · linter — **one resolver, reproducible, explainable, with a semantic veto** | a recommendation can always answer *why this chart?* |

**Do phase 5 last and gate it.** Every assistive surface in the subject is its weakest work, for one reason: they act without explaining. An assistive feature that cannot justify itself costs more trust than it earns.

---

## 11. Ten invariants to enforce in code review

1. No aggregation without a `semanticType` check.
2. Every result carries `rowsScanned`, `rowsReturned` and a `truncation` object.
3. Every refusal returns a reason code; no silent no-ops.
4. Every disabled control renders a reason.
5. No substitution of what the user asked for without a visible note on the object.
6. Every mutation produces one undo command with the shared sentence grammar.
7. Every visual emits both a painter pass and an ARIA projection from one scene graph.
8. Every mapping step (geography, join, category) reports a match rate and names its failures before commit.
9. Every collection endpoint pages; no unbounded `limit`.
10. Object title, accessible name and undo label all come from one naming function.

---

## 12. What this blueprint does not know

Honest gaps, carried forward from `observed_architecture.md`:

- **Request and response bodies were never read** — how a role assignment becomes a query on the wire is inferred from behaviour, not observed. The §4.2 protocol is my design, not a transcription.
- **Authentication internals are unknown** — token exchange, lifetimes and refresh were deliberately not captured.
- **No performance instrumentation** — the latency figures quoted anywhere in this bundle are wall-clock observations, not measurements.
- **Export, sharing and embedding output** were never produced, so §8's export contract is designed from first principles.

Treat these four as design decisions you own, not as facts to copy.
