# Observed system architecture — session 17

Everything here was read from the running client: resource timings, network request lines, DOM/runtime structure. **No source code, tokens, cookies or session identifiers were captured**, and the one browser API that would have exposed query strings with identifiers refused to return them — noted where that leaves a gap.

---

## 1. Client payload — the headline number

| Measure | Value |
|---|---|
| **Total transferred** | **63.4 MB** |
| JavaScript | **45.5 MB across 135 files** |
| **WebAssembly** | **12.9 MB** (`ltjs-wasm.wasm`) + a 324 KB JS loader |
| CSS | 1.3 MB across 13 files |
| Fonts | 0.4 MB (4 × woff2) |
| Resources total | 250 |
| DOMContentLoaded | ~2.9 s · load ~3.1 s (warm cache, 20-core client) |

Largest single assets: the 13.2 MB `.wasm`, then JS chunks of **6.7 / 6.6 / 5.8 / 5.3 / 4.8 MB**.

**Bundling:** webpack code-splitting — `runtime.<hash>.js` plus numbered chunks (`83369.<hash>.js`, `11680.<hash>.bundle.js`), content-hashed for cache-busting.

**No mainstream UI framework was detectable** — React, Angular, Vue, Ember and Dojo all probed negative, and no `ng-version` attribute exists. The only app global is `sas`. Read as: a **proprietary in-house component framework**, not an off-the-shelf one.

---

## 2. The rendering engine is compiled, not scripted

`/SASVisualAnalytics/<build-hash>/ltjslib/ltjs-wasm.js` + `ltjs-wasm.wasm` — a **13 MB WebAssembly module** loaded at boot. Alongside it:

| Probe | Result |
|---|---|
| Canvas elements on a one-chart page | **1** |
| SVG elements on the same page | **335** (icons and chrome) |
| Canvas context | **2D** — not WebGL |
| Device-pixel vs CSS size | 402×446 vs 402×446 (DPR 1 on this display) |

So: **application chrome is DOM + SVG; every data visual is drawn by a WASM engine through the Canvas 2D API.** This single fact explains a cluster of behaviours documented across earlier sessions —

- no data values in the DOM or the accessibility tree (defect 30), because nothing is rendered as elements;
- objects carrying `role="application"` with only a descriptive name;
- pixel-identical output between the browser, PDF export and the mobile app, because one engine draws all of them;
- charts that redraw rather than reflow on resize.

It is a defensible trade: one renderer, every surface. The cost is accessibility, and the subject pays it in full.

---

## 3. Service topology

Every service is a flat top-level namespace on one host. Observed in a single session:

| Namespace | Calls | Owns |
|---|---|---|
| `SASVisualAnalytics` | 160 | The SPA itself — bundles, WASM, service workers |
| `localization` | 15 | `/localization/bundles` — **2.7 MB** of message bundles |
| `thumbnails` | 13 | `/thumbnails/jobs/<uuid>` — asynchronous report thumbnail generation |
| `reportTemplates` | 10 | `/reportTemplates/objects/<uuid>` — object and page templates |
| `drive` | 9 | `/drive/items`, `/drive/actions`, `/drive/ancestries/drive-recommendations` — the content tree and the Recommendations feed |
| `preferences` | 5 | `/preferences/preferences/@currentUser` — read **and written back** (`POST`) |
| `identities` | 5 | `/identities/users/@currentUser`, `/identities` |
| `fonts` | 4 | `/fonts/css`, `/fonts/families`, `/fonts/files/<id>` — a font *service*, not static assets |
| `authorization` | 4 | `/authorization/bulkDecision`, `/authorization/decisions` — **batch permission evaluation** |
| `SASLogon` | 3 | `/SASLogon/info`, per-service silent OAuth |
| `appRegistry` | 2 | `/appRegistry/applications/applicationTree`, `/appRegistry/types` |
| `reportData` | — | the query engine (below) |
| `maps` | 2 | `/maps/providers`, `/maps/providers/US%20County%20Data` |
| `reportImages` | — | `/reportImages/images/<id>.svg`, `defaultReportThumbnail.svg` |
| `files` | — | `/files/files/<uuid>/content` — **autosave** (below) |
| `notifications`, `catalog`, `featureFlags`, `deploymentData`, `reports`, `transfer` | — | notifications feed, `/catalog/search/facets`, `/featureFlags/enabled`, `/deploymentData/cadenceVersion` |

**Two patterns worth copying:**

1. **`/authorization/bulkDecision`** — permissions are evaluated in **batches**, not per object. A UI that greys dozens of commands needs dozens of decisions; asking once is the difference between a responsive toolbar and a chatty one.
2. **A `fonts` service with `/fonts/css` and `/fonts/families`** — typography is server-governed, so themes and exports stay consistent with the browser.

**Query grammar.** Collection endpoints use an RQL-like filter language, visible in the notifications call:

```
GET /notifications/notifications
      ?start=0&limit=32767
      &sortBy=creationTimeStamp:descending
      &filter=and(eq(read, false), eq(recipientId, '<user>'))
```

`start` / `limit` / `sortBy=<field>:<direction>` / `filter=and(eq(...), eq(...))`. One grammar across services is right. **`limit=32767` is not** — the client asks for 32,767 notifications rather than paging.

---

## 4. The query protocol, end to end

### 4.1 Session
```
POST   /reportData/executors              → 201   create a data-session executor
DELETE /reportData/executors/<uuid>       → 204   tear it down
```
One executor per data session. It is deleted when the report closes or the data source changes, and re-created immediately.

**An observed failure mode:** `POST /reportData/executors` → **`449`**, then an immediate retry → `201`. HTTP 449 ("Retry With") is a **non-standard Microsoft extension**, not in RFC 9110. Using it to mean "re-establish and try again" works, but any standards-compliant proxy or client library is entitled to treat it as an unknown 4xx and give up. **Use `409 Conflict` or `503` with `Retry-After` instead.**

### 4.2 Jobs
```
POST /reportData/jobs
       ?indexStrings=true
       &embeddedData=limited
       &executorId=<executor-uuid>
       &wait=30
       &jobId=<executor-uuid>_c<N>
       &sequence=<n>
       [&dataDefinitions=dd<NN>]           → 201
```

| Parameter | Meaning (inferred from behaviour — confidence High) |
|---|---|
| `indexStrings=true` | return strings as **dictionary indices** rather than repeated literals |
| `embeddedData=limited` | **embed the result in the response when it is small; spill to files when it is not** — this is why many jobs have no result fetch at all |
| `wait=30` | **long-poll**: hold the connection up to 30 s for the result rather than polling |
| `jobId=<executor>_c<N>` | `c<N>` is a **client-side monotonic counter that continues across executors** — a fresh executor was observed starting at `c429` |
| `sequence=<n>` | a **per-executor** counter, restarting at 1 |
| `dataDefinitions=dd<NN>` | present on the job that **registers or refreshes a definition**; absent on jobs that reuse one |

### 4.3 Results, when they spill
```
GET /reportData/results/<executorId>_<executorId>_c<N>/files/dd<NN>.csv       → 200
GET /reportData/results/<executorId>_<executorId>_c<N>/files/dd<NN>index.csv  → 200
```
Two files per data definition: the **result** and its **string index** (the dictionary that `indexStrings=true` produced). Note the composite key repeats the executor id twice.

### 4.4 A single chart creation, captured clean
Dropping one category on an empty canvas produced exactly **two** calls:

```
POST …&jobId=<exec>_c429&sequence=6                      → 201
POST …&jobId=<exec>_c430&sequence=7&dataDefinitions=dd69 → 201
```

and **no result fetch** — the bar chart's 6 rows came back embedded. Two round trips from gesture to rendered chart over a 2.3M-row table.

**The design to copy:** one long-lived session, one job per object, dictionary-encoded strings, results embedded when small and spilled to addressable files when large, and a long-poll instead of a poll loop. That is a well-shaped protocol.

**The design to fix:** a chatty job stream. Across one editing session the counter ran past **`c430`** with many jobs producing no fetched result. Batch the jobs for a page into one request.

---

## 5. Persistence: there is no client state

| Store | Contents |
|---|---|
| `localStorage` | **0 keys** |
| `sessionStorage` | **0 keys** |
| IndexedDB | one database, `product-aidr@1` |

**The client keeps nothing.** Unsaved work is pushed to the server continuously:

```
PUT /files/files/<uuid>/content   → 200
```

…observed **interleaved with the query jobs**, firing on essentially every change. That is the mechanism behind "unsaved state is persisted for crash recovery" and behind *Restore previous session* on the landing page. User preferences are written the same way (`POST /preferences/preferences/@currentUser`).

**Trade-off to make deliberately:** server-side autosave gives you crash recovery and cross-device continuity for free, and costs a write per keystroke-equivalent. A rebuild should debounce and diff rather than PUT whole content, and should keep a local mirror so an offline blip does not lose work.

---

## 6. Two service workers, and the PWA seam

```
scope /                        → /SASVisualAnalytics/pwa/root-service-worker.js
scope /SASVisualAnalytics/     → /SASVisualAnalytics/webapp-service-worker.js
```

A **root-scoped PWA worker** plus an **app-scoped worker**. This is the concrete mechanism behind the documented "consumption uses a PWA" story, and it is how a 63 MB client becomes tolerable on a second visit.

---

## 7. What this adds to the defect list

| # | Observed | Required in the rebuild |
|---|---|---|
| 77 | **A 63.4 MB client payload** — 45.5 MB of JavaScript in 135 files plus a 12.9 MB WebAssembly module, before any data is queried | Budget the initial bundle; defer the rendering engine and the analytics chunks until an object needs them |
| 78 | **`449` used as a retry signal on executor creation** — a non-standard status a compliant client may abandon on | `409` or `503` with `Retry-After` |
| 79 | **A chatty job stream** — one job per object per change, a counter past `c430` in a single session, many jobs producing no fetched result | Batch a page's jobs into one request; coalesce changes within a frame |
| 80 | **`limit=32767` on a collection fetch** instead of paging | Page every collection, and make the page size a server concern |
| 81 | **2.7 MB of localization bundles loaded up front** for one locale | Load one locale, and split messages by route |

---

## 8. Where the evidence stops

- **Request and response bodies were not read** — only methods, paths, query parameters, statuses and sizes. The job payload's internal shape (how a role assignment becomes a query) is therefore **inferred from behaviour, not observed**.
- **No authentication material was captured.** The per-service silent OAuth flow (`/SASLogon/oauth/authorize?client_id=sas.<service>`) is documented from URL shape alone; the token exchange, lifetimes and refresh behaviour are **UNKNOWN**.
- Precise job latencies are **not** reported: the browser's resource-timing buffer was full from page load, and the one API that would have returned the newer entries refused because the URLs carry identifiers. The qualitative figures from hands-on use — roughly 10–14 s for a first chart over 2.3M rows, 60–90 s for a Forest fit — are timings I measured by waiting, not by instrumentation.
