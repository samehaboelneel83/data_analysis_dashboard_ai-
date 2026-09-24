# Architecture vs. Implementation — Full Comparison

**Target document:** [ARCHITECTURE.md](ARCHITECTURE.md) — *AI Data Analytics Platform*, 8 layers
**Implementation:** [data_analytics/](data_analytics/) — *Datalytics v2*, FastAPI + React + PostgreSQL
**Compared on:** 2026-08-24 · re-scored after the Layer 1 build (08-24), the sync-performance build (08-25), the Layer 4 build (08-26), the hardening pass (08-26), the all-layers gap-closure pass (08-26, fourth re-scoring), and now **the UX+ETL+security pass (branch `ux-etl-security`, 33 commits) · fifth re-scoring 2026-08-27** (the doc's own running count — see the "what changed" entries below; the task that requested this pass called it "fourth," which double-counts the 08-26 all-layers pass already on record) · **sixth re-scoring 2026-08-28 — a full recompute**: every layer's checklist re-derived from ARCHITECTURE.md and re-verified against code at `91abe25` (`ux-etl-security` == master), nothing incremented on trust · **seventh re-scoring 2026-08-28 (Tier 1+2 foundations & retrieval)**: Alembic migrations adopted, declared-FK seeding, a deliveries log + schedule timezone, and an agent feedback table + opt-in scheduled eval gate (master `ea19243..12b9d1d`), plus a Tier-2 retrieval pass — lexical TF-IDF ranking, a pluggable (opt-in, circuit-broken) embeddings backend, and an `entities` table with grain (branch `tier2-retrieval` == master `ae227f0`) · **eighth re-scoring 2026-08-29 (Tier 3: embeds, quotas, OTel)**: a merged `tier3-tenancy` branch closes Layer 7's largest named gap (embeds) and Layer 8's quotas gap outright, and adds opt-in OpenTelemetry (master @ `cff27fe`) · **ninth re-scoring 2026-08-29 (Tier 4: offline readiness, Valkey, materializations)**: a merged `tier4-offline-scale` branch makes the platform offline-complete for its actual production target (an isolated network), closes an opt-in shared Valkey cache tier and substantially closes the materialization-store gap (master @ `b093f78`) · **tenth re-scoring 2026-08-30 (Tier 5: analysis depth)**: a merged Tier-5 analysis pass closes five of Layer 5's six numbered gaps — StatsForecast AutoETS, standardized clustering, a PyOD detector catalogue, a tool registry, and a uniform result contract — leaving only the by-design-absent sandbox (master @ `ad1e574`) · **eleventh re-scoring 2026-08-30 (embeddings service)**: a merged `embeddings-service` branch closes the EMBEDDINGS half of Layer 3's last numbered gap outright — a self-hosted, air-gap-buildable ONNX embedding server, Backend B enabled by default in compose (circuit-broken, lexical fallback), and restart-stable persistence — while pgvector itself remains the named absent half (master @ `8000f2f`)

---

## Verdict, in one paragraph

**These are two different products, and the difference is deliberate rather than accidental.**

ARCHITECTURE.md specifies an **AI-agent NL→SQL platform**: a user asks a question in natural
language, an LLM agent retrieves semantic context, generates SQL, validates it through a ladder,
executes it, and picks a chart. Its own text says *"Layers 3 and 4 decide whether the product
works."*

Your project is a **self-serve BI tool in the Power BI / SAS Visual Analytics mould**: connect a
source or upload a file, define measures and hierarchies, drag widgets onto a report canvas,
cross-filter, secure by row and column, schedule and share. It is mature — 56 tables, 18 routers,
2448 backend tests (4 skipped), 897 frontend tests, SSO/SAML, DirectQuery pushdown, RLS.
*(These counts were three passes stale — "1769 backend tests, 208 frontend files" — until the sixth
re-scoring recounted them.)*

**Layer 4 — the one the architecture calls make-or-break — is now built and measured**
(2026-08-26, 23 commits, ~60 new tests): the full loop — classify → clarify-when-ambiguous →
plan → task-parallel step DAG → SQL generation under a grammar-enforced contract → the V1–V5
validation ladder (V3 admits confirmed/declared joins only; V4 injects row policies into the
sqlglot AST) → bounded repair → bounded execution → sanity → answer with provenance — behind a
chat pane in the report builder, over **all three data modes** (DirectQuery, import, multi-file
uploads via DuckDB). Measured live against `maps`: **100% conditional accuracy** (every completed
run matched its golden SQL's results exactly), 16% end-to-end completion gated by a
deliberately-cautious clarification threshold (72% of questions asked for clarification), median
2.8s. Spec + measured appendix:
[`2026-08-25-layer-4-agent-orchestration-design.md`](data_analytics/docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md).
Still absent from the architecture's Layer 4 list: Langfuse tracing (agent_steps is the
stand-in), Spider/BIRD external evals, CI wiring for the eval gate (a feedback table and an
opt-in scheduled eval-gate run now exist — see below). Layer 3's retrieval half is now
**substantially built**: entities with grain, lexical TF-IDF ranking, graph expansion and enum
injection are all wired into the agent's context render. **Embeddings are now closed**
(eleventh re-scoring): a self-hosted ONNX embedding service is enabled by default in compose
(circuit-broken, lexical fallback), with vectors persisted in `retrieval_embeddings` keyed by
`(text_hash, model)` — a restart re-embeds nothing. What remains absent is **pgvector itself**
(cosine similarity runs in-process over the cached vectors, exact and fast at current scale; the
table is the seam pgvector slots into without rework) and Spider/BIRD/Langfuse.

An LLM *is* now called, in one pipeline: Stage 5 writes the database overview, a
kind-aware description of every table and **view** (a view is described as the question it
answers, not as storage), and a sentence per column — through
[`services/llm.py`](data_analytics/backend/app/services/llm.py) against your self-hosted Qwen
endpoint, opt-in per source and degrading to a no-op when unreachable. On the live source that
is 82/82 objects and 1354/1354 columns described. Nothing on a user's query
path touches a model. The one thing that still *sounds* like AI and is not,
[insights.py](data_analytics/backend/app/services/insights.py), still says so in its own
docstring: six deterministic detectors producing *"template prose rather than an LLM's."*

**The honest framing:** the architecture doc is dated **today (2026-08-24)**; your project's own
design specs run **June–August 2026**. This is not a spec you failed to follow — it is a newly
proposed target, and your project already answered two of its **Open Decisions** the other way:

| Open decision in ARCHITECTURE.md | Architecture assumes | Your project chose |
|---|---|---|
| **#1 — Who owns the connection?** | Customer-hosted production databases | **Both** — uploads *and* live SQL sources (5 families, ~20 named connectors) |
| **#8 — Is the primary v1 surface chat, or dashboards?** | Leans chat-first (Phase 1: "no dashboards") | **Dashboards.** No chat surface at all |
| **#4 — May sample data reach the LLM?** | Needs a written policy | **Answered in Layer 1** — `allow_llm_sampling`, per source, default **off**, and only ever masked samples |
| **#7 — Arabic as a first-class query language?** | Glossary + embeddings | **Partly** — RTL widgets + `report_translations`, but no NL query |

> ## What changed since the first scoring
>
> **Layer 1 has been built.** All twelve gaps closed, following
> [`2026-08-24-layer1-connectors-ingestion-design.md`](data_analytics/docs/superpowers/specs/2026-08-24-layer1-connectors-ingestion-design.md).
> The backend suite went from **1297 to 1610 tests** (+313), all passing, with no
> existing test weakened. Layer 1 moved from ~40% to ~90%; Layers 3 and 8 picked
> up partial credit from it. Overall alignment: **~45% → ~55%**.
>
> The headline is not the percentage. It is that the platform now has a
> **metadata plane** — a cached, masked, provenance-tracked description of every
> connected source — which is the substrate Layers 3 and 4 were always going to
> need.
>
> ## What changed in the second re-scoring (2026-08-25)
>
> **The metadata plane got fast, complete, and honest about failure.** The
> sync went from ~16 minutes to ~5.5 warm (bounded parallel sampling on a
> dedicated pool, a schema memo that cut inference 239s→35s, chronic-timeout
> views remembered and skipped with a Retry control). Chasing those numbers
> surfaced four silent-degradation bugs — geometry blobs blowing the context
> window, fixed `max_tokens` truncating wide tables, views described as
> tables, failures recorded without their cause — all fixed, all tested.
> Backend tests: **1610 → 1769**.
>
> **And Layer 4 stopped being hypothetical.** Its design spec is written and
> awaiting review; the endpoint's constrained decoding was verified
> empirically (`response_format: json_schema` is grammar-enforced;
> `guided_json` is silently ignored — a finding that changes the
> implementation). Overall alignment: **~55% → ~60%**.
>
> ## What changed in the third re-scoring (2026-08-26, later the same day)
>
> **The agent was built, then hardened, then measured — twice.** The Layer 4
> plan ran to completion (23 commits) and a hardening pass followed (10 more):
> the V1–V5 ladder closed a CTE blind spot, dataset-mode execution gained an
> interrupt watchdog, row policies gained an admin management API, and the
> answer-synthesis node was structurally grounded in the DAG's **sink steps**
> after a measurement caught it doing its own wrong arithmetic over
> intermediate rows — that exact regressed question now returns all 8 golden
> IDs, live-verified. Measured on the 25-question `maps` golden set:
>
> | metric | baseline | after hardening |
> |---|---|---|
> | end-to-end completion | 16% | **48%** |
> | clarification stops | 72% | **32%** |
> | conditional accuracy (value-verified) | 100% of 4 | **75% of 12** |
> | median latency | 2.8s | 2.8s |
>
> Two honest residuals, both semantics problems rather than agent bugs: one
> wrong answer persists because its ground truth lives in a curated
> precomputed table the agent has no way to know is canonical, and the
> completion ceiling is set by genuine near-duplicate ambiguity in the
> catalog. Both are the architecture's own claim playing out — *"retrieval
> quality caps agent accuracy regardless of model size"* — which is why the
> remaining-gap section below now leads with Layer 3. (Caveat: n=25; treat
> the percentages as direction, not precision.) Overall alignment:
> **~60% → ~72%** (the intermediate Layer-4-build scoring was ~70%).
>
> ## What changed in the fourth re-scoring (2026-08-26, the all-layers pass)
>
> **One targeted gap closed in every layer**, merged as 13 reviewed tasks:
> canonical-source flags, enum-value labels (LLM-drafted, human-confirmed,
> editable), a glossary with Arabic synonyms, join-path resolution,
> `query_runs` telemetry, the drift→cache-invalidation wire, a forecast
> upgrade with confidence bands, the MCP client fix, an eval report + gate
> script, the popup overlay renderer, share-link layout pinning, and a
> guest-share security fix (hidden pages no longer served to anonymous
> viewers). Suites: **2039 backend + 733 frontend green**.
>
> **Live verification earned its keep twice.** It caught a telemetry
> helper corrupting the shared connection pool (invisible to 2,031 green
> tests — only a long-lived server exhibits it) and then caught the enum
> labels inflating the agent's schema prompt past its budget, silently
> truncating whole tables out of the model's view. Both fixed structurally
> (dedicated sync engine; breadth-before-depth two-pass render that can
> never drop an object).
>
> **Measured (round 6, same 25-question golden set):** completion
> 16% → **88%**, clarification stops 72% → 8%, end-to-end correct answers
> **4/25 → 17/25**, value-verified conditional accuracy **77% — above the
> 75% benchmark for the first time**, after a six-fix series (parent-facts
> truncation honesty, all-NULL column exclusion, skeleton descriptions,
> three human-confirmed relationships, refused-join degradation, a
> one-query planner rule) plus a ~20% latency recovery (classify on the
> compact render).
> Residuals, named honestly: the golden set itself is inconsistent about
> raw-vs-curated counts on one question pair; the answer-synthesis
> grounding bug recurred twice in new forms; one question regressed on a
> table-name slip; median latency doubled to 6.7s (the bigger prompt).
> Overall alignment: **~72% → ~76%**.
>
> ## What changed in the fifth re-scoring (2026-08-27, the UX + ETL + security pass)
>
> **33 commits on `ux-etl-security`, 14 batches, every batch independently
> reviewed** (spec check + quality check, fix rounds where findings
> landed) and checkpointed against full suites four times. Backend
> **2170 → 2198 tests** (0 skipped beyond the pre-existing 4), frontend
> **836 → 864**, both green, plus a same-day follow-up fix commit
> (`d41329a`) that closed three bugs live review missed: a SQL-identifier
> injection risk in the new incremental-refresh cursor column (now
> allowlisted + quote-escaped), guest rate-limit buckets shared across a
> link's colleagues instead of per-viewer, and `ORGNAME()` failing closed
> on whitespace the substitution regex already tolerated.
>
> **The named, closable gaps actually closed** (verified against code,
> not the plan's intent): Layer 1's `watermarks` table — "exists, not yet
> driven" — is now driven end to end
> ([`services/dataset_refresh.py`](data_analytics/backend/app/services/dataset_refresh.py):
> full replace / incremental append-past-cursor, transactional, falls
> back to full on a bad cursor config). Layer 8's rate-limiting gap is
> closed ([`core/rate_limit.py`](data_analytics/backend/app/core/rate_limit.py):
> per-user token bucket + a stricter per-guest-link bucket, LRU-capped,
> 429 + `Retry-After`, `/health` exempt). The Layer-4-spec caveat about
> the import path's post-hoc RLS filtering turned out to be **stale, not
> open** — S1's own audit found a prior refactor had already moved every
> import-path call site to base-frame filtering; the one real bug it
> found and fixed was `alerts.py` evaluating filters fail-*open*
> (`apply_filter_expr(silent=True)`) instead of fail-closed, now pinned
> by a structural choke-point test
> (`backend/tests/test_rls_base_frame_choke_point.py`). Layer 7's
> share-link revision-pin, credited done in the fourth pass but never
> updated in the Layer 7 section itself, is corrected here; S3 extends it
> so a pinned snapshot also freezes page role-visibility at pin time.
>
> **New capability, not gap-closure — read honestly:** self-serve system
> parameters (`ORGID()`/`ORGNAME()` alongside the existing
> `USEREMAIL()`/`USERID()`, expanded for the *viewing* user in ordinary
> author filters, not just RLS); a codeless RLS rule builder that
> suggests email/org-ish columns and can auto-generate proposals an admin
> reviews before applying (`RowPolicy.auto_generated`, cleared on manual
> edit so a re-run never clobbers a human's change); in-org viewer
> identity on shared reports (an authenticated in-org viewer now sees
> *their own* row subset, not the creator's — guests unchanged by
> design); a guest-link access log + export-policy closure on guest
> routes; a persisted, re-editable query model with a Design|SQL toggle
> and PowerBuilder-style column checkboxes on the query canvas; a
> transform-pipeline editor (sort/dedupe added to the existing fail-soft
> step engine, live per-step preview, a disable toggle that does not
> silently delete steps); `.xml` extraction; ETL fields on the lineage
> graph (extract/transform/load badges, freshness coloring); dataset
> sharing to another org user (`DatasetShare`, additive — read was
> already org-wide); and an app-wide `ActionMenu.tsx` popup as an
> alternative to icon clusters. `query_runs` did gain refresh telemetry
> (`source_kind='refresh'` rows written by the new refresh endpoint) —
> an extension of the table closed in the fourth pass, not a new table.
>
> **What this pass does *not* close:** Langfuse, Spider/BIRD evals, CI
> infra, pgvector/embeddings, the glossary, `join_paths` (all closed or
> still-absent exactly as the fourth pass left them), and Valkey — the
> new rate limiter and the guest access log are explicitly in-process
> and per-worker, the same non-shared-cache caveat as everywhere else in
> Layer 8. **And one honest compounding, not a fix:** `DatasetShare` is
> a *sixth* bolt-on to the role-string authorization model (after
> `org_parents`, `page_role_visibility`, `report_capability`,
> `column_security_rules`, `RowPolicy.auto_generated`) — the
> architecture's D8.1 prediction keeps getting more evidence, not less.
> Overall alignment: **~76% → ~80%** (the summary table's prior figure
> of ~78% was already inconsistent with this blockquote's own ~76%
> endpoint; ~80% resolves forward from the higher of the two, since both
> Layer 7 and Layer 8 moved up this pass).
>
> ## What changed in the sixth re-scoring (2026-08-28, full recompute)
>
> **Nothing new was built; everything was re-verified.** Each layer's
> checklist was re-derived from ARCHITECTURE.md itself and checked
> against code at `91abe25`. Only two commits landed since the fifth
> pass — `a647372`/`91abe25`: id-like numeric columns (`state_id`,
> `student_id`) now read as categories, not measures, in the widget
> config panel and the bubble shapers — a D6.2 chart-rule-quality fix,
> not a scope change. Suites: backend **2204 passed / 4 skipped**
> (2202 + 2 sort-order pins), frontend **871**. Net corrections, in
> both directions:
>
> - **Claimed-missing-but-built:** Layer 4's eval row still said "no
>   `report.py`, no CI at all" — `evals/report.py` (per-intent
>   breakdown + threshold exit code) and `run_gate.py` /
>   `run_eval_gate.ps1` have existed since the all-layers pass; only
>   CI *infrastructure* is absent. Layer 4 ~80% → **~82%**.
> - **Stale-in-place:** Layer 1's "Still open" table still listed
>   `watermarks` as unused, contradicting its own closed row 11 twenty
>   lines above; the verdict paragraph still said "1769 backend tests,
>   208 frontend files" (three passes stale; now 54 tables, 2204/871);
>   Layer 2's "You do not use sqlglot" is now true only of the BI
>   path — sqlglot 30.17.0 is pinned and load-bearing on the agent path;
>   and the Layer 4 section itself still quoted **round-3** measurements
>   (48% completion, 75% accuracy, 2.8s) two passes after round 6
>   recorded 88% / 77% / 6.7s — the make-or-break layer's own numbers
>   were the stalest thing in the document.
> - **Recount, not regression:** Layer 1 ~96% → **~92%** — the four
>   genuinely open stage requirements (live `Inspector` discovery,
>   the `pg_stats` fast path, declared-FK seeding at stage 4.1, the
>   nightly resync cron — `refresh_scheduler.py` still drives
>   report/data refresh only, no catalog resync) were under-weighted
>   by a score that effectively graded only the twelve-gap list.
> - **Re-verified as still absent, none silently closed:** Langfuse,
>   Spider/BIRD, CI infra, pgvector/embeddings/R.1–R.7, `entities`,
>   the `feedback` table, embeds (D7.1), a `deliveries` log, schedule
>   timezones, OpenFGA, OTel/Prometheus, `quotas`, `users.locale`,
>   Valkey — each confirmed by grep, not carried forward on trust.
>
> Overall alignment: **~80%, unchanged** — the Layer 1 trim and the
> Layer 4 bump offset; this pass's product is internal consistency,
> not movement.
>
> ## What changed in the seventh re-scoring 2026-08-28 (Tier 1+2 foundations & retrieval)
>
> **Two merged passes, both against master.** Tier 1 foundations
> (`ea19243..12b9d1d`, 7 commits): **Alembic adopted** —
> baseline `0001_baseline.py` plus revisions 0002–0005, an
> adoption-stamps-head fix (stamping `0001` while the same boot's
> `create_all` provisioned later tables pinned `alembic_version`
> forever and orphaned every future revision), and a VARCHAR(32)
> revision-id pin — found by a **real live-Postgres failure**
> (`StringDataRightTruncation` on descriptive 37-char ids; SQLite's
> unenforced varchar length let the suite miss it entirely). The
> stack-divergence table's Migrations row — *"Missing — and you're
> already paying for it"* — is now closed and matched. Declared-FK
> seeding is wired for the per-Dataset DirectQuery sync path
> (`metadata/sync.py`'s `stage_infer_keys`, ahead of value-overlap
> inference so declared always wins) — Layer 1's still-open row
> closes. A `deliveries` log table (one row per schedule/alert
> delivery, fire-and-forget, the same dedicated-sync-engine contract
> as `query_runs`) and `ReportSchedule.timezone` close Layer 7 gaps
> #3 and #4. An `AgentFeedback` table (owner-only 👍/👎, wired into
> `ChatPane`) plus an opt-in nightly `eval_schedule.py` run
> (`eval_gate_enabled`, default off, ERROR-logs on regression) close
> Layer 4's "feedback table absent" row — stated honestly: this is a
> **documented CI stand-in, not CI itself**, which remains absent.
>
> Tier 2 retrieval (`5c593ce..ae227f0`, branch `tier2-retrieval` ==
> master, 5 batches, each independently reviewed): a new
> [`services/retrieval.py`](data_analytics/backend/app/services/retrieval.py)
> scores every retrievable thing against the question — **Backend A
> (default): lexical TF-IDF over word tokens plus character
> 3–5-grams**, pure numpy, cosine similarity, memoized per catalog
> fingerprint — Arabic and code-ish identifiers (`st_cd`) score
> correctly because of the char n-grams. **Backend B (opt-in): an
> OpenAI-compatible embeddings endpoint**, circuit-broken with a 3s
> timeout and a once-per-process failure log; verified live that the
> self-hosted vLLM endpoint serves `/v1/models` but **404s
> `/v1/embeddings`**, so Backend A is what actually runs today. The
> ranking is wired into the agent's context render (relevance-ordered
> enrichment ahead of the static fallback order, 1-hop join-graph
> expansion promoting neighbors of top-ranked objects, the H7
> breadth guarantee pinned byte-identical when no question is given)
> and into query-example recall (`agent/memory.py` now recalls by
> similarity, not recency alone). A new `entities` table (name,
> business name, grain, description, `source` provenance) is drafted
> by the sync's LLM pass, confirmed on the existing metadata review
> surface, survives resync under the same ladder discipline as enum
> labels, and is rendered as a budget-reserved block plus retrieved
> as a document. This closes/partials Layer 3's retrieval-half rows:
> entities (#1 → built), the R.1–R.7 pipeline (#5 → substantially
> built, lexical rather than embedding-based), graph expansion + enum
> injection (#6 → built).
>
> **Measured, honestly — parity, not lift.** Before merge, the round-6
> eval gate (`-ValueVerified`, 25-question `maps` golden set) was
> re-run and hand-verified the same way: **strict 12/25 (48%),
> identical to the round-6 baseline; value-verified 16/25 vs 17
> baseline; conditional accuracy 76% vs 77%.** On this 82-object
> catalog — small enough that the H7 two-pass render already gets
> every object name into the prompt — retrieval reorders what gets
> enriched but does not change which objects were already visible, so
> no lift was expected and none appeared. This is exactly what the
> pass's own design spec predicted going in (*"retrieval mostly buys
> headroom on larger catalogs"*) and is reported as parity, not
> inflated as a win. Full ledger:
> [`.superpowers/sdd/2026-08-28-tier2-retrieval/progress.md`](data_analytics/.superpowers/sdd/2026-08-28-tier2-retrieval/progress.md).
>
> Suites: backend **2304 passed / 4 skipped** (pre-fix full run; the
> `ae227f0` fix-round commit — a circuit breaker, a score≤0 static-order
> fallback, and a sync-stage rollback guard — was verified green on
> the focused retrieval/agent suites rather than a second full run).
> Frontend **877**.
>
> **What this pass does *not* close, stated exactly as before:**
> pgvector (the `retrieval_embeddings` table stores a JSON vector, no
> pgvector column or extension — Postgres here is stock
> `postgres:16-alpine`), real embeddings (endpoint absent), Spider/BIRD,
> Langfuse, CI infrastructure, OpenFGA, OTel/Prometheus, `quotas`,
> `users.locale`, Valkey.
>
> **Score adjustments, derived from the above, not asserted:** Layer 3
> moves substantially, ~60% → **~72%** — the retrieval half went from
> "whole thing missing" to "built and measured, minus the one
> infra-blocked piece (embeddings/pgvector) and the two evals nobody
> has run (Spider/BIRD)." Layer 1 +2 (declared-FK seeding closes the
> last stage-level gap named in the sixth pass's own four-item list;
> Alembic closes a stack-divergence row): ~92% → **~94%**. Layer 4 +2
> (feedback table + CI stand-in close a named-absent row; the
> retrieval measurement is parity so it does not itself move Layer 4,
> but the gate now has a scheduled non-CI runner): ~82% → **~84%**.
> Layer 7 +3 (two Layer 7 gaps closed outright): ~79% → **~82%**. The
> stack-divergence table's Migrations row moves from Missing to
> Closed; its join-paths/NetworkX row is unaffected (still F1-by-BFS,
> no NetworkX).
>
> Overall alignment: **~80% → ~82%.** Recomputed the way this document
> always has — not a flat average of the eight layer numbers (that
> arithmetic mean is ~76%, same gap below the stated figure as every
> prior pass, because Layers 2 and 5 are scored against requirements
> the project deliberately declined, not gaps it failed to close) but
> weighted toward the two layers the architecture itself calls
> make-or-break. Layer 3's 12-point move is the one substantial swing
> this pass; Layers 1, 4 and 7 each moved a couple of points on named,
> closed gaps. Net: **+2** overall, smaller than Layer 3's own move,
> because the round-7 measurement is explicit that retrieval bought
> architecture-completeness, not yet accuracy, on this catalog.

> ## What changed in the eighth re-scoring 2026-08-29 (Tier 3: embeds, quotas, OTel)
>
> **A `tier3-tenancy` branch, three batches (E1/E2/E3), each independently
> spec-reviewed and quality-reviewed, plus a final full-suite review** —
> merged to master at `cff27fe`. This pass targets exactly the two named
> gaps the seventh re-scoring's own scorecard called out as largest:
> Layer 7's embeds (D7.1, *"the largest single missing feature in an
> otherwise strong layer"*) and Layer 8's quotas (#5 on its numbered gap
> list), plus opt-in OpenTelemetry (#2 on that same list).
>
> **Layer 7 gap #1 — embeds — closed.**
> [`routers/embed.py`](data_analytics/backend/app/routers/embed.py) +
> `EmbedConfig` (`created_by`, `secret_encrypted` shown once, `allowed_origins`,
> `enabled`): a host application signs its own HS256 JWT against that secret;
> the router verifies with the algorithm pinned and expiry mandatory
> (`options={"require_exp": True}`, capped ≤24h at mint time), and injects
> filters **only from the verified JWT claims** — the browser is never
> trusted with scope, D7.1's own framing. This was not free: the first
> review round caught a **High-severity RLS bypass** — the embed path had
> resolved through an admin-branch identity, skipping RLS and column
> security entirely, letting a row-restricted editor mint an embed exposing
> every row. The fix landed creator-base resolution (parity with
> `shared.py`'s anonymous-guest model, the escalation path pinned dead by
> a value-verified test) plus page role-visibility parity with guest links.
> `viewer_email`/`viewer_org` claims expand `USEREMAIL()`/`ORGID()` inside
> the creator's own author-filter expressions only, never substituting for
> RLS. A CSP `frame-ancestors` directive and per-IP + per-token rate
> buckets (narrowed to IP-only in final review after a cfg-enumeration/LRU
> finding) close it out, with an `EmbeddedReport` page and share-dialog
> Python/Node token samples on the frontend. **Honest gap against D7.1:**
> no revision pinning on `embed_configs` — an embed always serves the live
> report, the same still-open gap the doc already names for `share_links`.
>
> **Layer 8 gap #5 — quotas — closed.** `Quota` (one row per org, four
> nullable limits, unlimited by default) + `services/quotas.py`: per-org
> daily query and agent-ask caps (429 + `Retry-After`), a storage cap (413)
> on `Dataset.file_size`, and a per-worker concurrent-ask slot limiter.
> Enforcement is coherent across app users, guests, and embeds — all three
> charge the **data-owning org**, not the viewer's — plus platform-admin
> CRUD and a usage UI. Honest caveats, ledgered at review rather than
> hidden: concurrency limiting is per-worker, not cluster-wide; the quota
> cache carries up to 30s of cross-worker staleness after a `SET`;
> re-import-in-place has a known storage-accounting gap (old file size not
> subtracted before the new one is added), ruled low-severity and
> documented, needing a temp-file refactor to close properly.
>
> **Layer 8 gap #2 — OpenTelemetry — closed, opt-in.**
> [`core/telemetry.py`](data_analytics/backend/app/core/telemetry.py):
> default-off, lazy-imported (no cost when disabled), FastAPI + SQLAlchemy
> auto-instrumentation plus manual spans on agent nodes, DirectQuery and
> refresh, exporting OTLP/HTTP. Span attributes are sha256-only, and every
> exported span has its HTTP URL query string scrubbed (`_QuerystringScrubber`,
> added in final review after finding the embed bearer token itself was
> leaking through `http.url`'s query string — verified fixed on the pinned
> `opentelemetry` 1.27.0). Prometheus/Grafana (#3) and GlitchTip (#7)
> remain absent.
>
> **The OpenFGA row's bolt-on count grows again, honestly.** `EmbedConfig`
> and `Quota` are access-control tables in their own right — one gates who
> may mint scoped report access, the other gates how much an org may
> consume — so the tally of separate bolt-ons to the role-string
> authorization model moves from six to **eight** (`org_parents`,
> `page_role_visibility`, `report_capability`, `column_security_rules`,
> `RowPolicy.auto_generated`, `DatasetShare`, `EmbedConfig`, `Quota`). The
> architecture's D8.1 prediction keeps accumulating evidence, not shrinking.
>
> Suites: backend **2347 passed / 4 skipped** (the same 4 pre-existing
> skips carried since the fourth re-scoring), frontend **888**.
>
> **Score adjustments, derived from the above:** Layer 7 ~82% → **~87%** —
> its largest named gap (embeds) is closed outright, leaving only the
> Playwright-renderer divergence (#2) and the embed/share-link revision-pin
> gap (#5, now shared by both features rather than unique to share links).
> Layer 8 ~74% → **~78%** — two of its eight numbered gaps close outright
> (quotas, OTel-opt-in), on top of rate limiting already closed the prior
> pass; OpenFGA (#1), Prometheus (#3), GlitchTip (#7) and `users.locale`
> (#8) remain, and the bolt-on count against #1 grew rather than shrank.
>
> Overall alignment: **~82% → ~83%.** Neither Layer 7 nor Layer 8 is one
> of the architecture's make-or-break layers (that's still 3 and 4,
> unchanged this pass), so a 5-point and 4-point layer move each translates
> to a small overall step — consistent with how every prior pass in this
> document has weighted the recompute.

> ## What changed in the ninth re-scoring 2026-08-29 (Tier 4: offline readiness, Valkey, materializations)
>
> **A `tier4-offline-scale` branch, three batches (O1/O2/O3), each independently
> spec-reviewed and quality-reviewed, plus a final full-suite review** — merged
> to master at `b093f78`. This pass starts from a new, binding fact about the
> deployment target rather than a named architecture gap: **production runs on
> an isolated network with no internet access.** An audit for that constraint
> found exactly one runtime internet dependency in the whole stack — a Google
> Fonts `@import` in `frontend/src/styles/mcait/fonts.css` — plus the standing
> question of whether an operator could actually stand the stack up with no
> registry/CDN reachable at all.
>
> **Deployment: air-gapped — closed.** O1 replaced the Google Fonts import
> with the three faces (Syne, Manrope, JetBrains Mono) vendored as genuine
> variable-font woff2 binaries under `frontend/src/assets/fonts/`, served via
> local `@font-face` rules
> ([`styles/mcait/fonts.css`](data_analytics/frontend/src/styles/mcait/fonts.css))
> and fingerprinted through the existing Vite build — reviewer-verified via
> `fontTools` that the `fvar` variable axes actually survived vendoring, not
> just that a file exists at the path. A regression test pins the build output
> free of `fonts.googleapis.com`. None of the three faces carry Arabic glyphs,
> so RTL/Arabic rendering is unaffected either way — it already falls through
> to system fonts. On top of that,
> [`scripts/build_offline_bundle.ps1`](data_analytics/scripts/build_offline_bundle.ps1)
> (`docker save` of every image the compose stack needs, real-run verified at
> **~567MB total**) plus
> [`docs/OFFLINE_DEPLOYMENT.md`](data_analytics/docs/OFFLINE_DEPLOYMENT.md)
> give an operator a load-and-run path with zero internet touches. Frontend
> image is documented as dev-mode by default, with a prod-nginx alternative
> named honestly rather than silently assumed. **This closes the platform's
> only outstanding runtime internet dependency — everything else (the LLM
> endpoint, OTel export, compose images) was already internal or opt-in.**
>
> **Layer 2 gap #10 — Valkey/Redis — closed, opt-in.**
> [`services/cache_backend.py`](data_analytics/backend/app/services/cache_backend.py):
> one `CacheBackend` interface, two implementations — `InProcessCache` (the
> pre-existing `OrderedDict` LRU, unpacked into a reusable class, **byte-identical
> default behavior** when `settings.valkey_url` is unset, no serialization
> round-trip, existing tests untouched) and `ValkeyCache` (keys sha256-hashed
> before crossing the wire — the existing cache keys embed RLS expression text
> verbatim, load-bearing for RLS isolation, so hashing at this boundary is what
> keeps that raw text in-process — TTL support, and a circuit breaker that logs
> once and falls back to in-process for a cooldown window on any connection
> failure). `docker-compose.yml` gains a `valkey/valkey:8-alpine` service with
> **no host ports published** and `maxmemory 256mb --maxmemory-policy
> allkeys-lru`, not depended on by `backend` so a deployment that never sets
> `VALKEY_URL` is unaffected by the service merely existing. When enabled, the
> widget-result cache and DirectQuery result cache move to a **single shared
> tier** for coherence rather than staying split. The frame-parse memo in
> `frame_cache.py` stays deliberately process-local — documented, not an
> oversight: it memoizes parsed DataFrames keyed on `(path, mtime_ns, size)`,
> and sharing that across workers was out of this pass's scope.
> **A real bug, caught by review rather than shipped:** the first cut of
> `ValkeyCache` stringified `Timestamp`/`date` values via `json.dumps(...,
> default=str)` only on the Valkey path — a genuine type-drift bug where a
> value read back from Valkey differed in type from the same value served by
> `InProcessCache`. Fixed at the source in `_safe` (ISO-stringifies datetime
> kinds consistently, correct `NaT` ordering) and pinned by cell-by-cell
> round-trip equality tests covering Arabic text, `NaN`, and `NaT` — not
> patched over at the call site.
>
> **Layer 2 gap #5 — materialization store — substantially closed.** A new
> `Materialization` manifest table
> ([`models/models.py`](data_analytics/backend/app/models/models.py), one row
> per dataset, unique on `dataset_id`): `kind` (full/incremental), `row_count`,
> `columns`, and the `watermark_value` active at write time — queryable
> without touching the filesystem, which is what the lineage graph's
> `materialized`/`row_count` fields now read from. Written by **both** refresh
> paths in `services/dataset_refresh.py`. It deliberately **reuses** the
> existing parquet sidecar file (`write_parquet_sidecar`/`sidecar_path()`)
> rather than writing a second copy — no double write per refresh — and the
> loader's preference for a fresh sidecar over a CSV re-parse was already
> wired and tested; this pass adds the manifest, not a new parquet path.
> Superseding is update-in-place per dataset (a new unique index caught an
> insert-then-delete race during review, fixed structurally rather than
> worked around). **Honest, unchanged gap:** the architecture's #6 —
> byte-scanned caps / "refuse before sending" for metered warehouse
> sources — has no counterpart anywhere in the codebase; this pass did not
> touch it, and there is still no code that estimates or caps bytes scanned
> before a query runs against a metered source.
>
> Suites: backend **2384 passed / 4 skipped** (the same 4 pre-existing skips
> carried since the fourth re-scoring), frontend **890** (one flake, two
> consecutive clean runs), `tsc` clean. Live deploy verified: image rebuilt
> with the Redis client present, all four compose services (backend, frontend,
> db, valkey) came up healthy on a clean no-op boot, `VALKEY_URL` left unset in
> the live deployment (in-process cache remains the default; Valkey stays
> documented opt-in). Full ledger:
> [`.superpowers/sdd/2026-08-29-tier4-offline-scale/progress.md`](data_analytics/.superpowers/sdd/2026-08-29-tier4-offline-scale/progress.md).
>
> **Score adjustments, derived from the above:** Layer 2 ~55% → **~65%** —
> two of its ten numbered gaps close (#10 Valkey, opt-in; #5 materialization,
> substantially), on top of drift-invalidation and `query_runs` already closed
> in earlier passes. Still absent, unchanged: the DuckDB local execution
> engine, Ibis, Arrow streaming, cross-source joins, sqlglot cache-key
> normalization, and byte-scanned caps (#6) — five of the ten gaps stand
> exactly as before, so Layer 2 moves to the mid-60s rather than further.
>
> Overall alignment: **~83% → ~84%.** Layer 2 is not one of the architecture's
> make-or-break layers (still 3 and 4), so a 10-point layer move translates to
> a small overall step, consistent with how every prior pass in this document
> has weighted the recompute. The more consequential fact this pass adds
> isn't a percentage: it's that the platform can now actually be deployed
> where it is meant to run.

> ## What changed in the tenth re-scoring 2026-08-30 (Tier 5: analysis depth)
>
> **A merged Tier-5 analysis pass**, four batches (A1 contract, A2 segment, A3
> forecast+anomaly, A4 registry), each independently spec-reviewed and
> quality-reviewed, plus a final full-suite review that caught and fixed one
> real bug before merge — closes five of Layer 5's six numbered gaps outright.
> This is the first pass targeting Layer 5 directly since the doc's first
> scoring called it out as the architecture's most under-built area next to
> Layers 3 and 4.
>
> **Gap #1 — `forecast` via StatsForecast — closed.** `shape_forecast`'s
> default `method` is now per-series **StatsForecast `AutoETS`**, with
> additive lo/hi confidence intervals. The hand-rolled `simple`
> exponential-smoothing path this document previously credited as the only
> forecasting logic in the repo is **kept, not discarded** — it is the tested
> fallback on fit failure or a degenerate series, reached by dedicated tests
> rather than left as dead code. StatsForecast is lazily imported
> (`sys.modules` pins prove no heavy import happens at startup), and its
> `numba`/`llvmlite` transitive chain is pinned explicitly (`numba==0.67.0`,
> `llvmlite==0.49.0`) rather than left to the resolver — load-bearing for the
> air-gapped deployment target the ninth re-scoring closed. **Honest cost, not
> hidden:** the first ETS render on a cold process pays numba's JIT warmup in
> real seconds; the fallback covers fit *failure*, not first-render *slowness*
> — noted and accepted, not fixed.
>
> **Gap #2 — `segment`, clustering with automatic k — closed.**
> [`services/analysis/segment.py`](data_analytics/backend/app/services/analysis/segment.py):
> standardized-feature KMeans, silhouette-scored auto-k search over 2..8,
> seeded (`RANDOM_STATE`), a seeded 10k-row sample on large frames (documented
> deviation, not silent), and an RLS-filtered base frame built as a
> byte-for-byte mirror of `run_analysis`'s existing row-policy path — the
> segment endpoint cannot see rows a user's row policies would hide. New
> route `POST /datasets/{id}/segment` plus a Segment panel on DatasetDetail.
> Final review caught the one real bug of this pass: the first cut returned
> **full-frame rows** with segment labels (unsampled compute plus a
> ~30MB unread JSON payload at 1M rows) — fixed before merge to sample like
> `run_analysis` and gate row output behind an opt-in, capped
> `include_rows` flag.
>
> **Gap #3 — PyOD — closed, opt-in.**
> [`services/analysis/anomaly.py`](data_analytics/backend/app/services/analysis/anomaly.py)
> gains a `detector` param: `"iqr"` (default, **byte-identical** to the
> pre-existing fence logic when omitted), `"iforest"` (PyOD IsolationForest,
> seeded), `"ecod"` (PyOD ECOD, distribution-free). A fixed contamination rate
> turns each PyOD detector's continuous score into the same boolean mask shape
> the `"iqr"` path already produced, so callers that never pass `detector` see
> no behavior change at all.
>
> **Gap #5 — `registry.py`, a tool catalogue exposed to Layer 4 — closed.**
> [`services/analysis/registry.py`](data_analytics/backend/app/services/analysis/registry.py):
> a single-source catalogue registering every analysis tool (describe,
> correlate, forecast, segment, detect-anomalies, compare-periods) with no
> heavy imports at import time, a new authenticated
> `GET /analysis/registry`, and a budget-capped (1200-character) block folded
> into the agent's prompt in `generate.py`. Reviewed and accepted as a static
> catalogue rather than `context.py`'s dynamic-retrieval machinery — the tool
> set is small and fixed, so the added machinery wasn't judged worth it. One
> Low finding from review (forecast bounds hand-copied into the registry
> rather than imported) was fixed inline: constants now live once in
> `widget_data` and the registry imports them, pinned by a new test.
>
> **Gap #6 — uniform `AnalysisResult` contract — closed, additively.**
> [`services/analysis_contract.py`](data_analytics/backend/app/services/analysis_contract.py):
> one envelope wrapping every analysis service's return value. All four
> pre-existing wire shapes this document has tracked since the first scoring
> (including `run_full_analysis`'s dict and the DirectQuery additions) are
> **golden-pinned byte-preserved** — the contract adds an envelope around the
> existing response, it does not reshape it. Noted and accepted, not hidden:
> the envelope is measurably larger on the wire (bounded ~2x) than the raw
> shape it wraps; a lazy-envelope flag is named as a future option, not built.
>
> **Gap #4 — the sandbox — stays N/A by design, unchanged.** It exists in the
> architecture only to run LLM-written code; this product has no
> LLM-written-code path, so nothing in this pass touches it — same reasoning
> this document has given every prior pass.
>
> **Ops hardening riding along:** `_run_alembic`'s self-heal (from the Tier 1
> foundations pass) gained an explicit precondition — it only stamps the
> Alembic head on the `DuplicateTable`-class failure *and* verified presence
> of every managed table, documented in the docstring as unsafe once real
> data migrations exist, rather than a blanket catch. Not new work this pass,
> but re-verified as part of the same full-suite review.
>
> Suites: backend **2434 passed / 4 skipped** (the same 4 pre-existing skips
> carried since the fourth re-scoring; one full run overlapped an
> environment disk-space incident mid-pass, so the final fix's own files were
> separately re-verified green 17/17 post-fix), frontend **897**, `tsc`
> clean. All new ML dependencies (`scikit-learn==1.5.1` already pinned;
> `statsforecast==2.1.1`, `pyod==3.6.5`, `numba==0.67.0`, `llvmlite==0.49.0`
> newly pinned) hold the existing `numpy==1.26.4` pin — no forced bump. Full
> ledger:
> [`.superpowers/sdd/2026-08-29-tier5-analysis/progress.md`](data_analytics/.superpowers/sdd/2026-08-29-tier5-analysis/progress.md).
>
> **Score adjustments, derived from the above:** Layer 5 ~55% → **~84%** —
> five of its six numbered gaps close outright, the sixth (sandbox) is
> N/A-by-design and was already excluded from the "real" gap count by this
> document's own 🔀 Different reasoning in every prior pass. What keeps this
> in the mid-80s rather than higher: `registry.py` is a static catalogue, not
> a dynamic tool-retrieval system; the `AnalysisResult` envelope is additive
> rather than a full reshape; `method` (forecast) and `forecast_method`
> naming overlap is ledgered for a later naming pass rather than fixed here;
> and first-ETS-render JIT cost is accepted, not eliminated.
>
> Overall alignment: **~84% → ~86%.** Layer 5 is not one of the architecture's
> make-or-break layers (still 3 and 4), so even a 29-point layer move — the
> largest single-layer swing since Layer 1's original build — translates to a
> small overall step, consistent with how every prior pass in this document
> has weighted the recompute. What changes is the shape of what's left: of
> the architecture's eight layers, only Layer 3 (embeddings/pgvector,
> infra-blocked) and Layer 2 (byte-scanned caps, gap #6) now carry numbered
> gaps this document has not closed or explicitly ruled N/A.

> ## What changed in the eleventh re-scoring 2026-08-30 (embeddings service)
>
> **A merged `embeddings-service` branch closes the EMBEDDINGS half of Layer 3's last remaining
> numbered gap** (row 4, "pgvector + real embeddings"). Two batches, each spec-reviewed and
> quality-reviewed, plus a fix round on two review-caught Lows. Full design in ARCHITECTURE.md's
> new [§ The embeddings service — concrete design](ARCHITECTURE.md#the-embeddings-service-concrete-design),
> ledger:
> [`.superpowers/sdd/2026-08-30-embeddings-service/progress.md`](data_analytics/.superpowers/sdd/2026-08-30-embeddings-service/progress.md).
>
> **M1 — the server.** [`embedding_server/`](data_analytics/embedding_server/): a dedicated
> compose-network-only container serving `paraphrase-multilingual-MiniLM-L12-v2` as an ONNX
> export — chosen prefix-free (E5-family models want `query:`/`passage:` prefixes an
> OpenAI-compatible `/v1/embeddings` contract can't express) and multilingual for the Arabic ↔
> English glossary. ONNX Runtime + `tokenizers` + numpy, **no torch** — a CPU image a few hundred
> MB where a torch layer alone runs ~2GB, load-bearing for the docker-save air-gap bundle. Weights
> are downloaded inside a Dockerfile `RUN` layer at build time, never at runtime, so the container
> never touches the internet once deployed. Built to the client's actual contract
> (`retrieval.py` Backend B), not the other way round: Spearman 1.0 vs fp32 on an
> Arabic-inclusive fixture, re-verified live by review. Smoke 4/4.
>
> **M2 — wiring and persistence.** Retrieval Backend B is now **enabled by default** in compose
> (`EMBEDDING_BASE_URL` set, no `depends_on` coupling) — safe because of the fallback ladder: a
> circuit breaker in the client plus the pre-existing lexical TF-IDF scorer means a dead or slow
> embeddings service degrades ranking quality within one request, never availability. Requests are
> chunked to ≤256 documents per POST (the M1 review's ledgered finding — the server 413s past
> that), with whole-rank fallback on a partial chunk failure. A dim guard rejects a
> model/dimension mismatch rather than silently corrupting cosine math. Vectors persist in the
> pre-existing `retrieval_embeddings` table, read-through/write-back keyed by `(text_hash,
> model)` — a restart re-embeds nothing, and a model tag change invalidates naturally. Verified
> live: 136 rows stable across a restart.
>
> **Honest measurement, pre-committed before the branch was built (not gated on it):** a live
> Arabic smoke run — semantic ranking beats lexical on the customers case; the invoices case still
> ranks a semantically-adjacent view first. This is the expected small-catalog headroom this
> document has called out since the seventh re-scoring (retrieval measured parity, not lift, on
> this 82-object catalog), reported honestly rather than gated behind a passing threshold. No
> eval-gate run was added for this pass by design — it closes the infra gap; parity is expected on
> the current small live catalog, with headroom on larger ones.
>
> **What review caught and fixed:** the true full-suite run (2448/4/0) showed the implementer's
> reported "6 failed" was a wrong-container artifact (the compose `backend` service has no
> `/frontend` mount and an empty `VALKEY_URL`), not a real regression — corrected via a process
> note. Two Lows were dispatched and fixed: the restart-persistence test called the real health
> endpoint unmocked; the Arabic smoke gate conflated small-catalog headroom with an actual defect
> (`8000f2f` splits it into separate gate/headroom modes).
>
> **What stays open.** **pgvector itself is the named absent half** — the retrieval math runs
> in-process (cosine over cached vectors), which is exact and fast at the platform's current
> catalog size; `retrieval_embeddings` is the seam pgvector slots into without rework, not a
> pgvector column or extension. A separate whole-branch review was waived — the branch has exactly
> one cross-task seam (M1 server ↔ M2 client contract), and the M2 review verified it field-by-
> field plus reran the full standard-harness suite. Suites: backend **2448 passed / 4 skipped**
> (same pre-existing skips), frontend **897**.
>
> **Score adjustments, derived from the above:** Layer 3 ~72% → **~78%** — the retrieval half is
> now embedding-backed by default rather than lexical-only, closing the specific reason this
> document has held Layer 3 back since the seventh re-scoring; what keeps the layer in the
> high-70s rather than higher is pgvector's continued absence and the R-pipeline remnants
> (Spider/BIRD eval, canonical-preference tuning) tracked in Block B below.
>
> Overall alignment: **~86%, unchanged at the rounded figure.** Layer 3 was this document's
> smallest of the eight layers by score before this pass and remains one of two layers (with
> Layer 2) still carrying a numbered gap this document has not closed or explicitly ruled N/A —
> a real, evidence-based step within Layer 3 that is too small a slice of the eight-layer average
> to move the headline number, consistent with how this document has weighted every prior
> single-layer pass.

> **Note:** your repo already contains a gap analysis —
> [`docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md`](data_analytics/docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md)
> (117 KB, 13 categories, 277 rows). It benchmarks datalytics against **SAS Visual Analytics and
> Power BI** — a *different* yardstick. This document is complementary, not a duplicate: it measures
> you against ARCHITECTURE.md only.

---

## Scorecard by layer

| Layer | Architecture's purpose | Status | Coverage |
|---|---|---|---|
| **1 — Connectors & Ingestion** | Connect anything, extract structure | 🟢 **Built, migrations adopted** | ~94% |
| **2 — Storage & Query Engine** | Decide where a query runs, run it | 🟡 **Partial / Different — Valkey (opt-in) and materializations closed** | ~65% |
| **3 — Metadata & Semantic** | Structure → business meaning | 🟢 **Retrieval half embedding-backed by default; entities shipped; pgvector absent** | ~78% |
| **4 — AI Agent Orchestration** | Question in, correct SQL out | 🟢 **Built, hardened, measured ×7 — retrieval parity, not lift** | ~84% |
| **5 — Analysis & Execution** | Beyond plain SQL | 🟢 **Five of six numbered gaps closed — sandbox N/A by design** | ~84% |
| **6 — Visualization & Dashboards** | Results → charts → dashboards | 🟢 **Achieved, differently** | ~90% |
| **7 — Publishing & Sharing** | Get the work outside the product | 🟢 **Embeds closed — its largest named gap — sharing hardened, ETL gaps closed** | ~87% |
| **8 — Platform Core** | Who can do what; is anything on fire | 🟡 **Quotas closed, OTel opt-in, RLS gap closed, rate-limited** | ~78% |

Legend: 🟢 achieved · 🟡 partial or built differently · 🔴 mostly missing · ⚫ absent

**The shape of it:** you were strong exactly where the architecture calls the work
*conventional* (6, 7, 8) and empty where it calls the work *hard and decisive* (3, 4).
That shape has now inverted on both hard layers, to different degrees: Layer 4's runtime is
**built, hardened and measured** — the make-or-break layer answers questions with an
88% completion rate (round 6), 77% value-verified accuracy on what it completes, and a
refusal posture that never returned a fabricated join. Layer 3's **retrieval half is now
substantially built** — entities with grain, lexical TF-IDF ranking (word + character
3–5-gram, Arabic-capable), 1-hop join-graph expansion and enum injection are wired into
the agent's context render — but a round-7 measurement on this 82-object catalog found
**parity, not lift**: strict 12/25 (identical to round 6), value-verified 16/25 vs 17
baseline, conditional accuracy 76% vs 77%. Read exactly as intended, not inflated:
retrieval buys headroom for catalogs too large to fit in one prompt; it does not lift
accuracy on one that already fits after the H7 breadth guarantee. What remains hard and
undone is narrower still: **pgvector** (embeddings themselves are closed as of the eleventh
re-scoring — a self-hosted ONNX embedding service runs as retrieval Backend B, enabled by
default, with vectors persisted in `retrieval_embeddings`; only the pgvector column/extension is
still absent, a scale-up item rather than a live-endpoint blocker) and Spider/BIRD/Langfuse. The
architecture said
*"retrieval quality caps agent accuracy regardless of model size"*; the round-7 numbers
say the lexical half of that quality is not, on this catalog, the binding constraint —
which is itself evidence for the same claim, not against it.

---

# Layer 1 — Connectors & Ingestion

**Built.** Specified in
[`2026-08-24-layer1-connectors-ingestion-design.md`](data_analytics/docs/superpowers/specs/2026-08-24-layer1-connectors-ingestion-design.md),
implemented additively — no table renamed, no service rewritten, no dependency removed.

### The twelve gaps, closed

| # | Gap | Where it lives now |
|---|---|---|
| 1 | Two planes — metadata vs data | Six-stage sync against a local cache; no per-question source traffic |
| 2 | Persisted `column_stats` | `column_stats` table + [`metadata/profile.py`](data_analytics/backend/app/services/metadata/profile.py) |
| 3 | **`top_k` enum extraction** | Computed wherever `distinct_count < 100`; exposed on the stats API |
| 4 | DuckDB sample cache | [`metadata/cache.py`](data_analytics/backend/app/services/metadata/cache.py) — LRU, byte-budgeted, persists across restarts |
| 5 | PII masking before samples leave | [`services/pii.py`](data_analytics/backend/app/services/pii.py) — classify, mask, *then* cache |
| 6 | **FK inference with evidence** | [`metadata/infer_keys.py`](data_analytics/backend/app/services/metadata/infer_keys.py) |
| 7 | Semantic inference | [`metadata/infer_semantic.py`](data_analytics/backend/app/services/metadata/infer_semantic.py) — regex, roles, deprecation, LLM descriptions |
| 8 | Schema drift + fingerprinting | [`metadata/drift.py`](data_analytics/backend/app/services/metadata/drift.py) + `schema_versions` |
| 9 | `confidence` + `source` provenance | [`metadata/store.py`](data_analytics/backend/app/services/metadata/store.py) — one enforcement point |
| 10 | Human confirmation UI | [`SourceReview.tsx`](data_analytics/frontend/src/pages/SourceReview.tsx) + React Flow join graph |
| ~~11~~ | ~~`sync_runs` + `watermarks`~~ | ✅ **`watermarks` now driven (UX+ETL+security pass).** [`services/dataset_refresh.py`](data_analytics/backend/app/services/dataset_refresh.py): `refresh_dataset(id, mode)` — full re-runs the stored query/SQL, incremental appends rows past `cursor_value` and advances the watermark transactionally; a bad `cursor_column` falls back to full with a warning (validated against an allowlist of the dataset's real columns after the follow-up fix in `d41329a` closed a SQL-identifier injection risk in that fallback path). `sync_runs` per-stage observability unchanged. |
| 12 | Envelope encryption | `enc:v2:` inside [`secrets.py`](data_analytics/backend/app/services/secrets.py) |

### The measured result — M1.4

The architecture says M1.4 is *"where you discover whether the metadata model is rich
enough, and you want that finding while the schema is still cheap to change."* It did
exactly that. `test_infer_keys_accuracy.py` runs the real pipeline over an eight-table
schema built to be hard, and reports:

```
precision 100.00%   recall 100.00%   F1 100.00%
proposed 7 / 7 true          overlap queries: 21
```

**It failed at 50% precision on the first run**, and both defects were real rather than
cosmetic:

| Defect | Why overlap could not catch it |
|---|---|
| `orders.status_code` proposed as a key into `categories.id` | Status codes hold 1–4; so does the category table. Overlap scored a **genuine 1.0** — the evidence really did point the wrong way |
| Every table's `id` paired with every other table's `id` | Surrogate keys are small integers from 1, so `customers.id` (1–100) is *wholly contained* in `orders.id` (1–200) |

Both are structural, not thresholdable. A wrong join does not fail loudly: it silently
multiplies rows and quietly corrupts every aggregate built on it. Both are now rejected
by name rules, and the fix also cut overlap queries from 132 to 21.

### Provenance — the rule the layer turns on

`confirmed` > `declared` > `inferred`, enforced in **one function**. Every inference
stage writes through it, so a resync cannot revert a human's decision. Pre-existing
relationships migrated to `declared`/`1.0` — a person typed them, so they outrank
anything inference later proposes.

### Still open in Layer 1

| Gap | Note |
|---|---|
| **Live schema introspection** | `stage_discover` reads datasets already registered in the catalog. Pointing at a connection and enumerating its tables via SQLAlchemy `Inspector` is not wired — you still add tables through the existing connection flow |
| **`pg_stats` fast path** | `from_pg_stats_row` and `build_profile_sql` are written and tested, but `stage_profile` computes from the cached sample instead. Correct, and marked `exact=False`; it just is not yet the millisecond path the doc recommends |
| ~~**Declared FK seeding**~~ | ✅ **Closed (Tier 1 foundations pass).** [`metadata/sync.py`](data_analytics/backend/app/services/metadata/sync.py)'s `stage_infer_keys` now calls `_read_declared_fks`/`_seed_declared_keys` (`inspect(engine).get_foreign_keys(...)`) ahead of value-overlap inference, so a real catalog foreign key seeds a `declared` relationship instead of waiting to be guessed at `inferred` confidence. `catalog_sync.py` already did this for its own path; this closes the gap in the per-Dataset DirectQuery sync pipeline specifically — `test_declared_fk_seeding.py`. |
| ~~`watermarks`~~ | ✅ Closed (UX+ETL+security pass) — see row 11 above. This row sat here stale through the fifth re-scoring, contradicting the closed row twenty lines up; caught by the sixth-pass recompute |
| **Scheduled resync** | Sync is manual. The nightly cron the doc specifies is not wired to the existing scheduler |
| Composite foreign keys | Out of scope by design — `relationships` is single-column and `prep.py` / `query_builder.py` assume that |

### Still different, deliberately

- **pandas, not Arrow** (Principle 6). A Layer 2 concern; changing it breaks `widget_data.py`.
- **psycopg2, openpyxl** — stack swaps, not missing logic.
- **Statistics come from the sample, not the engine** — see `pg_stats` above.

---

# Layer 2 — Storage & Query Engine

### ✅ Achieved

| Architecture requirement | Your implementation |
|---|---|
| **Query router — pushdown vs local** | [`services/direct_query.py`](data_analytics/backend/app/services/direct_query.py) (998 lines) — `plan_query` decides push-down vs materialize |
| **Routing on capability flags** | `DIRECTQUERY_FAMILIES` / `PERCENTILE_FAMILIES` / `STAT_FAMILIES` gate what can push down |
| **Result cache** | [`services/frame_cache.py`](data_analytics/backend/app/services/frame_cache.py) + widget-data cache (`_widget_data_cache_get/set`) |
| **Governor — row caps** | `test_direct_query_row_capped.py`, `test_direct_query_row_capped_execution.py` |
| **Connection pooling** | `test_engine_pool.py` |
| **Federated vs materialized modes** | `datasets.mode` = `import \| directquery` — the architecture's federated/materialized split, two of its three modes |
| **Query correctness discipline** | The **grain invariant** in `direct_query.py` (`GRAIN_SAFE_AGGREGATIONS`) — rejecting `count`/`countd`/`std`/`variance`/`range` rather than silently computing them wrong. Genuinely rigorous engineering the architecture doesn't even anticipate. |

### 🔴 Missing

| # | What's absent |
|---|---|
| 1 | **DuckDB as the local execution engine.** Local work is **pandas**, not DuckDB. |
| 2 | **Cross-source joins.** D2.3 (pull the small side, refuse if both exceed budget) has no counterpart. Joins are within one source: [`services/prep.py`](data_analytics/backend/app/services/prep.py) |
| 3 | **sqlglot normalization for cache keys** (D2.2). Your cache keys are hash-of-config, not normalized-SQL hash — so two semantically identical configs may miss. |
| ~~4~~ | ~~Cache invalidation on schema drift~~ ✅ **Closed (all-layers pass).** A drift-detected change bumps `DataSource.cache_epoch` in the same transaction; the epoch is folded into the DirectQuery result-cache key, so stale entries become unreachable and the LRU evicts them. File datasets (no source) unaffected. |
| ~~5~~ | ~~**Materialization store** — Parquet + manifest, incremental refresh via watermarks~~ | 🟢 **Substantially closed (Tier 4 offline/scale pass, O3).** `Materialization` model (one row per dataset, unique on `dataset_id`): `kind` (full/incremental), `row_count`, `columns`, `watermark_value` at write time — queryable without touching the filesystem, feeding the lineage graph's `materialized` flag. Written by both refresh paths in [`services/dataset_refresh.py`](data_analytics/backend/app/services/dataset_refresh.py). Deliberately **reuses** the existing parquet sidecar (`write_parquet_sidecar`) rather than a second write; the loader's mtime-based sidecar preference pre-dates this pass and was already tested. This is the manifest half of the architecture's requirement — still no separate incremental *strategy* beyond watermark-driven full/incremental refresh, which is the same mechanism Layer 1's watermarks row already closed. |
| 6 | **Byte-scanned caps / metered-source refusal** — "refuse before sending" for metered warehouses. Unchanged by the Tier 4 pass — no code anywhere estimates or caps bytes scanned before a query runs against a metered source. |
| ~~7~~ | ~~`query_runs` telemetry table~~ ✅ **Closed (all-layers pass).** [`services/query_log.py`](data_analytics/backend/app/services/query_log.py): per-query executor/rows/duration/cache-hit, sql-hash only (never SQL text), fire-and-forget on a dedicated sync engine — the first version corrupted the shared async pool by spinning a loop per call, caught only by live verification and fixed structurally. Known gap: two sync-in-loop router paths (`analysis.py`, `datasets.py`) log via the same helper now but pre-date the async refactor that would make them first-class. **Extended (UX+ETL+security pass):** the new refresh endpoint writes `query_runs` rows with `source_kind='refresh'` ([`routers/datasets.py:1334`](data_analytics/backend/app/routers/datasets.py#L1334)) — refresh runs now show up in the same telemetry table as query executions, not a separate log. |
| 8 | **Ibis** — no multi-backend expression layer. |
| 9 | **Arrow RecordBatch streaming** — results are pandas DataFrames → JSON. |
| ~~10~~ | ~~**Valkey / Redis**~~ | ✅ **Closed, opt-in (Tier 4 offline/scale pass, O2).** [`services/cache_backend.py`](data_analytics/backend/app/services/cache_backend.py): one `CacheBackend` interface, two implementations. `InProcessCache` is the pre-existing `OrderedDict` LRU unpacked into a reusable class — **byte-identical default behavior** when `settings.valkey_url` is unset, so every deployment that never sets `VALKEY_URL` is unaffected. `ValkeyCache` opts a deployment into a real Redis-protocol shared tier: keys sha256-hashed before crossing the wire (the raw keys embed RLS expression text, load-bearing for RLS isolation), TTL support, and a circuit breaker that falls back to in-process for a cooldown window on connection failure. `docker-compose.yml` adds a `valkey/valkey:8-alpine` service with no host ports and `allkeys-lru` eviction. When enabled, the widget-result and DirectQuery result caches move to a **single shared tier** for coherence. The frame-parse memo in `frame_cache.py` stays deliberately process-local by design — documented, not a gap. A real type-drift bug (Timestamps stringified only on the Valkey path) was caught in review and fixed at the source, pinned by round-trip equality tests. **Honest residual:** the shared tier is opt-in, not the default — a deployment that never sets `VALKEY_URL` still has the same non-shared-cache profile as before, unchanged for the isolated-network target which typically won't enable it. |

### 🔀 Different — and this is the important one

**Principle 4: "One exit point for SQL — every outbound query is parsed by `sqlglot`, checked,
limited, and re-rendered. Never string concatenation."**

You do **not** use sqlglot *on the BI query path* — though since the Layer 4 build,
`sqlglot==30.17.0` is pinned (deliberately, for parse-shape stability) and load-bearing on the
agent path (the V1–V5 ladder, policy injection), so adopting it here is now a port, not a new
dependency. The BI path's own translator:
[`services/sql_expr.py`](data_analytics/backend/app/services/sql_expr.py) —

- Parses the filter expression with Python's **`ast`** module
- Gates it through `widget_data._validate_expr_safety`'s AST allowlist
- Applies a **second, stricter** gate: only the subset with a direct SQL row-predicate equivalent
- Emits a **parameterized** WHERE fragment — values are **bound parameters**, not concatenated

**Assessment:** you meet the *security intent* of Principle 4 (real AST, allowlisted, parameter
binding — see `test_expression_sandbox_escape.py`, `test_sql_expr.py`), on a **narrower grammar**
and **without dialect portability**. sqlglot would give you 25+ dialects and cache-key
normalization for free; your version is hand-maintained per family. This is a defensible trade,
not a defect — but it is the largest single "different" in the codebase.

**Deployment: air-gapped (Tier 4 offline/scale pass).** The architecture's stack discussion
above implicitly assumes normal internet reachability for whatever it recommends (Valkey
images, DuckDB, Ibis, etc.); this project's actual production target is an **isolated
network with no internet access**, and as of this pass the running stack has no outstanding
runtime internet dependency — the one that existed (a Google Fonts `@import`) is now vendored
locally, and `scripts/build_offline_bundle.ps1` + `docs/OFFLINE_DEPLOYMENT.md` give an
operator a `docker save`/load path (~567MB) to stand the whole compose stack up with zero
registry or CDN reachability. See the ninth re-scoring blockquote above for detail.

---

# Layer 3 — Metadata & Semantic Layer

> *"This layer and layer 4 decide whether the product works."* — ARCHITECTURE.md

### ✅ Achieved

| Architecture requirement | Your implementation |
|---|---|
| **Metrics are formulas, validated — not free text** (D3.3) | [`services/measure_eval.py`](data_analytics/backend/app/services/measure_eval.py) (313 lines) + `test_measures_api.py`, `test_measure_eval.py`, `test_measure_bygroup.py`. Genuine formula engine with time-intelligence (`test_time_intelligence_functions.py`, `test_time_intelligence_periods.py`), text functions, date/stat functions. **This is the single strongest overlap with L3.** |
| **`entities` table with business names, grain, descriptions** | ✅ **Closed (Tier 2 retrieval pass, Task R3).** `Entity` model + `0005_entities` migration: name, business name, grain (*"one row per…"*), description, `primary_object`, `source` provenance. Drafted by the sync's LLM pass, confirmed/edited on the existing metadata review surface, survives resync under the same confirm-outranks-inferred ladder as enum labels. Rendered as a budget-reserved "Entities:" block in the agent's schema context and included as a retrieval document. |
| **Entities / roles** (measure · dimension · date · text) | `hierarchy_nodes` + [`routers/hierarchy.py`](data_analytics/backend/app/routers/hierarchy.py), auto-generate from detected types |
| **Row policies attached to entities** | `row_security_rules` + [`core/rls.py`](data_analytics/backend/app/core/rls.py) — including `USEREMAIL()` / `USERID()` dynamic context, which is exactly the architecture's `"tenant_id = :current_tenant"` idea generalized. **Extended (UX+ETL+security pass):** `ORGID()`/`ORGNAME()` join the same token family, and expansion now runs for the *viewing* user in ordinary author filter expressions too, not only RLS — a widget filter `owner == USEREMAIL()` narrows per-viewer without an admin writing per-viewer rules. A codeless RLS builder (`AdminRowSecurityRules.tsx`) suggests email/org-ish columns and can auto-generate rule proposals (`RowPolicy.auto_generated`, cleared on manual edit) — D3.1's draft-then-confirm pattern applied to security rules, not just the catalog. |
| **Join graph** | `relationships` table, `test_relationship_model.py`, `test_prep_join.py` |
| **Saved semantic views** | `data_views` + [`services/data_views.py`](data_analytics/backend/app/services/data_views.py) |
| **Multilingual** | `report_translations`, RTL widget support — partial answer to the Arabic ↔ English concern |
| **Semantic types on columns** | *New in Layer 1.* `dataset_columns.semantic_type` — email, phone, currency, percentage, IBAN, national ID |
| **Generated descriptions at every level** | Database overview + per-object + per-column via the offline Qwen endpoint, opt-in per source. **Kind-aware since 2026-08-25**: a view is described as the question it answers and what it derives from, never as storage — 48 of the live source's 82 objects are views, so this was the majority of the catalog. Verified complete: 82/82 objects, 1354/1354 columns. |
| **Draft-generate-then-confirm** (D3.1) | **Closed for the catalog.** The sync auto-drafts relationships, semantic types and descriptions as `inferred`; [`SourceReview.tsx`](data_analytics/frontend/src/pages/SourceReview.tsx) is the confirm surface; confirmed items are never overwritten by resync. Measures and hierarchies remain hand-authored — see Different below. |
| **`source = inferred \| confirmed` provenance** | **Closed.** [`metadata/store.py`](data_analytics/backend/app/services/metadata/store.py) enforces `confirmed > declared > inferred` at a single choke point. |
| **`top_k` enum values** | *New in Layer 1.* `column_stats.top_k` is the raw material for the enum dictionary — the values exist, the `raw_value → label` mapping does not |

### 🔴 Missing — down to pgvector itself

| # | What's absent | Consequence |
|---|---|---|
| ~~1~~ | ~~`entities` table with business names, grain, descriptions~~ | ✅ **Closed (Tier 2 retrieval pass)** — moved to Achieved above. |
| ~~2~~ | ~~`enum_values` dictionary~~ | ✅ **Closed (all-layers pass).** `SourceColumn.enum_labels` + `enum_labels_source` provenance: the sync LLM-drafts labels for low-cardinality columns (320 columns labelled on the live source), humans confirm/edit in the review UI, confirmed labels survive resync, and the agent's schema prompt renders them (`st_cd (1=new, 2=paid, 3=cancelled)`). |
| ~~3~~ | ~~`glossary_terms` + synonyms + Arabic aliases~~ | ✅ **Closed (all-layers pass).** `glossary_terms` table (term, definition, synonyms incl. Arabic, maps-to object/column) + admin CRUD; question-matched terms are injected into the agent's classify/generate prompts. Arabic matching verified by test and live. |
| 4 | **pgvector + real embeddings** | 🟡 **Split — EMBEDDINGS closed, pgvector still absent (eleventh re-scoring, embeddings-service branch).** [`embedding_server/`](data_analytics/embedding_server/) is a self-hosted, compose-network-only ONNX embedding service (`paraphrase-multilingual-MiniLM-L12-v2`, int8, no torch, weights baked into the image at build time for the air gap). Retrieval Backend B in `services/retrieval.py` is **enabled by default** in compose — circuit-broken with lexical TF-IDF fallback, requests chunked ≤256 docs, a dim guard against model/dimension mismatch. Vectors persist in `retrieval_embeddings` keyed by `(text_hash, model)` — verified live: 136 rows stable across a restart, so nothing re-embeds on redeploy. What remains absent is **pgvector itself**: cosine similarity runs in-process over the cached vectors (exact and fast at the current catalog size), and Postgres here is stock `postgres:16-alpine` with no pgvector extension — `retrieval_embeddings` is the seam pgvector slots into without rework, not a `vector(N)` column. Live Arabic smoke: semantic ranking beats lexical on the customers case; the invoices case still ranks a semantically-adjacent view first — expected small-catalog headroom, reported not gated. |
| ~~5~~ | ~~The whole R.1–R.7 context retrieval pipeline~~ | 🟢 **Substantially built, lexical not embedding-based (Tier 2 retrieval pass).** `services/retrieval.py`: TF-IDF over word tokens + character 3–5-grams (Arabic-capable), cosine similarity, memoized per catalog fingerprint, wired into `SchemaContext.render`'s enrichment ordering and into `agent/memory.py`'s example recall. D3.2's claim — *"retrieval quality caps agent accuracy regardless of model size"* — was tested directly: on this 82-object catalog, retrieval measured parity (76% vs 77% conditional), not lift, because H7's breadth guarantee already gets every object into the prompt. The embedding-based half of R.1–R.7 (row 4) is now also closed, running alongside this lexical scorer as Backend B's default; only pgvector (row 4's remaining half) is left. |
| ~~6~~ | ~~Graph expansion + enum injection (R.4, R.5)~~ | ✅ **Closed (Tier 2 retrieval pass).** After top-k ranking, any object one confirmed/declared join-hop from a top-3 object is promoted into the enriched render tier — the "orders question pulls order_lines in" behavior the architecture names. Enum labels were already injected (all-layers pass); a question token matching a label now also boosts that object's rank. |
| ~~7~~ | ~~`join_paths` — shortest confirmed path~~ | ✅ **Closed (all-layers pass).** BFS over the confirmed/declared whitelist in `agent/context.py` (`join_path`, `suggest_join_route`) — no NetworkX needed at this scale; F1 holds by construction; multi-table questions get the route as a prompt hint. |
| ~~8~~ | ~~`query_examples` — verified question→SQL memory~~ | ✅ **Closed by Layer 4.** `query_examples` table + [`agent/memory.py`](data_analytics/backend/app/services/agent/memory.py) `recall`/`remember`, wired into the agent's generate prompt as few-shot and written only on sane single-step successes. The *retrieval* side (embedding-based recall) is still the R-pipeline's job. |
| ~~9~~ | ~~Draft-generate-then-confirm workflow (D3.1)~~ | ✅ **Closed for relationships, types and descriptions** (moved to Achieved). Still hand-authored: measures and hierarchies. |
| ~~10~~ | ~~`source = inferred \| confirmed` provenance~~ | ✅ **Closed** (moved to Achieved). |

### 🔀 Different

The architecture's target is **"a correct semantic model in under ten minutes"** via auto-draft +
confirm. For the *catalog* half — objects, columns, types, relationships, descriptions — that
target is now essentially met: one sync (~5.5 minutes warm) drafts it and the review page
confirms it. For the *business* half — measures and hierarchies — your model remains authored by
an analyst, with no time claim. Different users, different promise, and the line between the two
halves is now exactly where D3.1 drew it.

### Measured — retrieval's effect on agent accuracy (Tier 2 retrieval pass)

Before merging the retrieval pass, the round-6 eval gate was re-run against the same 25-question
`maps` golden set, hand-verified the same way (`-ValueVerified`): **strict 12/25 (48%), identical
to the round-6 baseline; value-verified 16/25 vs 17 baseline; conditional accuracy 76.2% vs 77.3%
baseline** — parity on this 82-object catalog, not a regression and not a lift. Say exactly what
that means and no more: retrieval reorders *which* objects get the enrichment budget, but H7's
two-pass render already guarantees every object *name* reaches the prompt regardless of catalog
size, and at 82 objects the fuller enrichment was already reaching everything that mattered. The
pass's own design spec called this outcome before building it — *"retrieval mostly buys headroom
on larger catalogs; improvement is hoped for, not promised"* — and the measurement confirms that
framing rather than overselling a null result as a win. The retrieval machinery (ranking, graph
expansion, entities, the embeddings seam) is real, tested, and load-bearing infrastructure for a
catalog too large to fit in one prompt; it is not, today, the reason this 82-object catalog's
accuracy is 77%.

---

# Layer 4 — AI Agent Orchestration

### 🟢 Built, hardened, measured (2026-08-26)

The runtime exists — ~1,270 lines across [`app/services/agent/`](data_analytics/backend/app/services/agent/),
141 tests in 15 files, implemented per the
[spec](data_analytics/docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md)
(which now carries three appended measurement rounds), behind a chat pane in the report
builder, over **all three data modes**: DirectQuery, import-from-source, and multi-file
uploads (frames registered into DuckDB, dialect-correct, RLS applied to base frames
before registration).

| Architecture component | Status |
|---|---|
| `graph.py` — the state machine | ✅ hand-rolled asyncio step-DAG executor (deliberate S5 divergence from LangGraph — the repo's own gather+semaphore idiom, ~80 lines, one bounded gate per run) |
| `nodes/classify.py` — intent + ambiguity (D4.3) | ✅ enforced `json_schema` contract; clarify-don't-guess; tuned from a measured 72% → 32% false-clarification rate |
| `nodes/clarify.py` / `plan.py` — question, decomposition | ✅ plan degrades to single-step on planner failure, never kills a run |
| `nodes/generate.py` — SQL gen w/ constrained decoding (D4.2) | ✅ via `response_format: json_schema` — the ONE mechanism verified grammar-enforced on this endpoint (`guided_json` is silently ignored; a startup probe guards the contract, union-typed field included after that exact class of failure shipped once) |
| `validate.py` — **the V1–V5 ladder** (D4.1) | ✅ parse → SELECT-only → schema → **joins on confirmed/declared provenance only** (the F1 rule; inferred edges are proposals) → policy → EXPLAIN dry run. CTE/alias handling closed after live measurement found the gaps |
| `policy.py` — row-policy AST injection | ✅ predicates parsed, injected pre-aggregation, fail-closed; **plus an admin management API** (`GET/POST/DELETE /agent/row-policies`, dialect-aware validation) — the security-critical flow is no longer configurable only by SQL |
| repair (D4.4) | ✅ bounded at 3 total generations, each retry fed the specific rung+detail; first mid-budget recovery observed in measurement round 3 |
| `executor.py` + sanity | ✅ statement timeouts, injected row caps (existing LIMITs floored to the cap), poisoned-connection invalidation, a race-guarded interrupt watchdog for DuckDB, `enable_external_access=false` |
| `nodes/explain.py` — NL answer + provenance | ✅ **grounded in the DAG's sink steps only** — a measured regression (correct SQL, confidently wrong prose synthesized from intermediate rows) forced the structural fix; deterministic fallback when prose fails |
| `memory.py` — query_examples | ✅ recall as few-shot, remember on sane success; skipped in dataset mode (measured cross-mode pollution) |
| `conversations` / `messages` / `agent_runs` / `agent_steps` tables | ✅ per-user scoped (an org-wide read leaked policy-injected SQL until the final review caught it) |
| `evals/` — execution-accuracy harness + golden sets | 🟡 `run_eval.py` (results-not-strings) + 25 execution-verified `maps` pairs + a fixture set, [`evals/report.py`](data_analytics/backend/evals/report.py) (per-intent table, `--min-accuracy` non-zero exit) plus `run_gate.py` / `run_eval_gate.ps1` (the one-command live gate) — **and, new this pass, `services/eval_schedule.py`**: an opt-in (`eval_gate_enabled`, default off) nightly run of the gate in a background thread, writing one `eval_runs` row and ERROR-logging on a regression below `eval_gate_min_accuracy`. Stated honestly, as the task that added it documents: this is **a CI stand-in, not CI** — it runs the gate on a schedule inside the running app, not on every commit in an isolated environment. What is genuinely still absent is CI infrastructure to run any of this in: no `.github/`, no pipeline of any kind |
| ~~`feedback` table~~ · Langfuse tracing · Spider 2.0 / BIRD | ✅ **`feedback` table closed (Tier 1 foundations pass).** `AgentFeedback` (owner-only 👍/👎 per run, upserted on `run_id`+`user`) + `POST /agent/conversations/{id}/feedback`, wired into `ChatPane`. Langfuse tracing (`agent_steps` remains the stand-in) and Spider 2.0/BIRD external evals are ⚫ still absent |

**Measured** (25-question golden set, live `maps`, six rounds — this
paragraph carried round-3 numbers until the sixth re-scoring caught it):
completion 16% → **88%**, clarification stops 72% → **8%**, end-to-end
correct **17/25**, conditional accuracy **77%** value-verified, median
6.7s (the bigger prompt; n=25, direction not precision) — and the
failure posture the spec demanded held:
across every round, **no fabricated join was ever executed** (the one
provenance refusal observed was correct), and the residual wrong answer is a
canonical-source semantics gap, not an agent bug. Full per-question detail
lives in the spec's measurement appendices. **A seventh round (Tier 2 retrieval
pass)** re-ran this same golden set after wiring lexical retrieval ranking,
graph expansion and entities into the context render, and measured **parity**:
strict 12/25 (identical), value-verified 16/25 vs 17, conditional 76% vs 77% —
see Layer 3's Measured section for the honest reading of why.

### ✅ Also in Layer 4's stack: the MCP tool surface

| Requirement | Your implementation |
|---|---|
| **MCP — "expose the platform as tools so external agents can call it"** | [`backend/mcp_server/`](data_analytics/backend/mcp_server/) — `server.py`, `client.py`, `mcp>=1.4` |
| Machine/agent auth for it | `api_keys` table + [`core/api_keys.py`](data_analytics/backend/app/core/api_keys.py) — SHA-256 stored, prefix lookup, key shown once, **inherits the issuing user's org, role, RLS and report capabilities** |
| Per-org MCP gating | `org_mcp_access` table |

**Both answers to Open Decision #8 now exist.** The platform is a tool server any
external agent can drive (authorization inherited, not re-implemented) *and* it now
carries its own internal agent. The MCP server's long-standing wart — a fresh `httpx.Client` per tool call — is
**fixed** (lock-guarded singleton client, atexit-closed; all-layers pass).

### 🔀 Partial credit elsewhere

- **`query_builder.py`** (278 lines) gives users structured query construction — the *human*
  version of what `generate.py` does for the model. **Matured (UX+ETL+security pass):** the
  compiled model now persists (`Dataset.query_model`, JSON) and is re-editable — the dialog
  reopens pre-loaded instead of only ever writing SQL once — and the query canvas gained
  PowerBuilder-style column checkboxes/aggregation badges plus a Design|SQL tab that hands
  script-mode users an editable-textarea escape hatch (explicitly one-way: reverting to Design
  regenerates from the model and discards manual SQL edits, never reverse-parses SQL back into
  the graph).
- **`explain.py`** (86 lines) — result explanation, but deterministic, not a generated narrative.
- **`insights.py`** (286 lines) — six deterministic detectors with 0–1 interest scores, plus
  `suggest_widgets_from_findings`. This is the architecture's D6.2 ("rules first, model second")
  taken to its logical end: *rules only, no model*.

---

# Layer 5 — Analysis & Execution

### ✅ Achieved

| Architecture tool | Your implementation |
|---|---|
| `describe` — summary statistics, distributions, missingness | [`services/analytics.py`](data_analytics/backend/app/services/analytics.py) — descriptive stats, outliers, correlations, chi-square |
| `correlate` — pairwise + significance | ✅ `test_shape_correlation_matrix.py`; `scipy`, `statsmodels` pinned |
| `detect_anomalies` | ✅ IQR-fence outliers (default) plus opt-in PyOD `iforest`/`ecod` (Tier 5 analysis pass) — `test_outlier_details.py`, `outlier_impact` detector in `insights.py`, `services/analysis/anomaly.py` |
| `compare_periods` — growth + contribution | ✅ `test_yoy_growth_json_safe.py`, `test_time_intelligence_periods.py`, quick-calcs |
| **Structured facts the agent can narrate** (`AnalysisResult`) | ✅ Closest match in the repo: `insights.py` findings carry *"the figures its sentence states, so the UI can show exactly what the words claim"* |
| **D5.1 — deterministic tools first, free-form code last** | ✅ **Fully honoured.** Everything is a named deterministic operation. |
| Trend/regression | `test_compute_fit_line.py` |
| Goal seek | `test_goal_seek.py` — *not in the architecture at all* |
| ~~`forecast` via StatsForecast (gap #1)~~ | ✅ **Closed (Tier 5 analysis pass).** `shape_forecast`'s default `method` is now per-series **StatsForecast `AutoETS`** (additive lo/hi confidence intervals), lazily imported (`sys.modules` pins keep startup cost at zero). The hand-rolled `simple` exponential-smoothing path is kept, not discarded — it is the tested fallback on fit failure/degenerate series, exercised by dedicated tests rather than left as dead code. |
| ~~`segment` — clustering with automatic k (gap #2)~~ | ✅ **Closed.** [`services/analysis/segment.py`](data_analytics/backend/app/services/analysis/segment.py): standardized-feature KMeans, silhouette-scored auto-k over 2..8, seeded (`RANDOM_STATE`), 10k-row seeded sampling on large frames, RLS-filtered base frame (byte-for-byte mirror of `run_analysis`'s row policy), `POST /datasets/{id}/segment` + a DatasetDetail Segment panel. |
| ~~PyOD (gap #3)~~ | ✅ **Closed.** [`services/analysis/anomaly.py`](data_analytics/backend/app/services/analysis/anomaly.py): a `detector` param — `"iqr"` (default, byte-identical to the pre-existing fence logic), `"iforest"` (PyOD IsolationForest, seeded), `"ecod"` (PyOD ECOD, distribution-free). Opt-in; nothing changes for a caller that doesn't pass it. |
| ~~`registry.py` — a tool catalogue exposed to Layer 4 (gap #5)~~ | ✅ **Closed.** [`services/analysis/registry.py`](data_analytics/backend/app/services/analysis/registry.py): a single-source catalogue of the analysis tools (describe/correlate/forecast/segment/detect-anomalies/compare-periods), `GET /analysis/registry`, and a budget-capped (1200-char) block folded into the agent's prompt in `generate.py` — a static catalogue rather than `context.py`'s dynamic-retrieval machinery, accepted as the right-sized answer for a fixed, small tool set. |
| ~~Uniform `AnalysisResult` contract (gap #6)~~ | ✅ **Closed.** [`services/analysis_contract.py`](data_analytics/backend/app/services/analysis_contract.py): a single-source envelope wrapping every analysis service's output, golden-pinned so all four pre-existing wire shapes (including `run_full_analysis` and the DirectQuery additions) are byte-preserved — additive, not a breaking reshape. |

### 🔴 Missing

| # | What's absent |
|---|---|
| 4 | **The entire sandbox** (D5.2) — `packages/sandbox/`, gVisor/Firecracker, syscall policy, audit of executed code. **Stays N/A by design** (unchanged from every prior pass): it exists in the architecture only to run LLM-written code, and this product has no LLM-written-code path — see 🔀 Different, below. It is now the *only* one of Layer 5's six numbered gaps still open. |

### 🔀 Different

The sandbox's absence is **not a gap in your product** — it exists in the architecture only to run
LLM-written code. With no LLM, D5.2 doesn't apply. Your expression evaluator is sandboxed at the
AST level instead (`test_expression_sandbox_escape.py`), which is the right control for
*user*-written expressions.

---

# Layer 6 — Visualization & Dashboards

**Your strongest layer, and the one that most exceeds the architecture in breadth.**

### ✅ Achieved

| Architecture requirement | Your implementation |
|---|---|
| **Chart recommendation from data shape** (D6.2) | `insights.suggest_widgets_from_findings`, `test_suggest_widgets.py` |
| **Dashboard canvas, widgets, layout persistence** | `reports` → `report_pages` → `report_widgets`, 12-column grid, [`ReportBuilder.tsx`](data_analytics/frontend/src/pages/) |
| **Global filters** | `common_filters` table, `test_common_filters.py`, FilterBar |
| **Cross-filtering** | `CrossFilterContext.tsx` — with **4 interaction modes** (two-way / broadcast / receive / isolated). *Richer than the architecture's single "click a bar, filter siblings".* |
| **Versioning on save** (D6.3) | `test_report_revision.py` |
| **Geospatial** | `components/report/geo/`, `test_shape_geo.py`, `test_geo_pies_layers.py`, `test_geo_network_and_explain.py`, `d3-geo` + `topojson` + `world-atlas` |
| **Large grids / tables** | `test_table_multi_sort.py`, `test_table_totals.py`, crosstab/matrix (`test_matrix_widget_type.py`) |
| **Theme** | `org_themes` table, `test_report_theme.py`, MCAIT design system |
| `query_spec` is semantic, not raw SQL | ✅ `report_widgets` stores a config object resolved at query time — exactly the architecture's rationale |

### 🟢 Chart coverage — you *exceed* the spec

The architecture's rule table names ~11 chart shapes. Your shaper test suite covers at least 20:
`box_plot`, `bubble`, `bubble_animated`, `card`, `correlation_matrix`, `dual_series`, `gantt`,
`gauge`, `geo`, `heatmap`, `histogram`, `parallel_coordinates`, `series_target`, `vector_plot`,
`waterfall`, `xy_numeric`, `area/funnel`, treemap, pie/donut, matrix. Plus formatting and display
rules (`test_display_rules*.py` ×3, `test_report_display_rules_api.py`) — an area the architecture
covers in one word ("theme").

### 🔀 Different — the biggest stack divergence in the project

**D6.1 — "Vega-Lite JSON specs, generated against a schema and validated before render. Not chart
code. Generated React code is none of those things."**

You use **Recharts** — React chart components. The architecture rejects this approach by name.

| | Vega-Lite (specified) | Recharts (yours) |
|---|---|---|
| Spec is validatable JSON | ✅ | ❌ (config object, not a portable grammar) |
| Server-side renderable for exports | ✅ | ⚠️ You solved it separately with `playwright` (devDependency) + `pdf_export.py` (reportlab/matplotlib) |
| Diffable / versionable | ✅ | 🟡 your config is versioned, but not a standard grammar |
| Machine-generatable by an LLM against a schema | ✅ | ❌ |

**Why it matters beyond taste:** Vega-Lite is chosen in the architecture *because an LLM can emit
it against a JSON Schema and you can validate before render*. With no LLM, that justification
evaporates — and Recharts gives you better React ergonomics. **But** it also means that if you ever
add Layer 4, chart generation is the piece you'd have to rebuild, and your PDF/PNG export path is
maintained twice (browser Recharts + server matplotlib/reportlab), which is exactly the divergence
D7.3 warns about.

### 🔴 Missing — including two facts the UX Showcase demo verified live (2026-08-26)

A seeded "UX Showcase" demo report now exercises every interactive facility with real
data — button actions (navigate/url), hierarchical drill-down over the option tree,
cross-filter modes, bookmarks, prompt pages — all verified rendering in the browser.
The same verification pinned down two page-type gaps precisely:

| # | Verified gap | Fourth re-scoring |
|---|---|---|
| A | Popup pages had no floating-overlay renderer in view mode | ✅ **Built** ([`PopupOverlay.tsx`](data_analytics/frontend/src/components/report/PopupOverlay.tsx)): modal overlay with backdrop/Esc/close, popup pages excluded from view-mode tabs, demo copy updated |
| B | Tooltip and drillthrough "not triggerable" | ✅ **Fully closed.** Drillthrough was stale documentation (the trigger pre-existed). Tooltip pages are now hover-triggered in view mode (`TooltipPageOverlay.tsx`, 300ms delay, near-cursor floating panel; the `tooltipPageId` binding already existed end-to-end — a repeated pattern: page types were half-wired and undocumented). Every page type is now fully triggerable; datapoint-filter carry into tooltips is the noted follow-up. |

### 🔴 Missing (as before)

- Vega-Lite / vega-embed / ECharts
- `react-grid-layout` (you built the grid yourself)
- Perspective (WASM pivot grids), uPlot (dense time series), MapLibre / deck.gl, TanStack Table
- JSON-Schema validation of specs before render

---

# Layer 7 — Publishing & Sharing

### ✅ Achieved

| Architecture requirement | Your implementation |
|---|---|
| **Signed share links — expiry + revocation** (M7.1) | `share_links` table (`token_hash` unique, `expires_at` NOT NULL, `revoked_at`), [`routers/shared.py`](data_analytics/backend/app/routers/shared.py), `test_share_links.py`, `SharedReport.tsx`. *Token is stored hashed — good.* No `password_hash`, no `row_filters` pinned at share time. |
| **Schedules + delivery + delivery log** (M7.5) | `report_schedules` + `data_alerts`, [`services/delivery.py`](data_analytics/backend/app/services/delivery.py), [`services/alerts.py`](data_analytics/backend/app/services/alerts.py), `test_scheduled_delivery.py`, `test_refresh_schedule.py`. **Delivery log + schedule timezone closed (Tier 1 foundations pass):** a `Delivery` row per attempt (status, error, artifact_kind, duration_ms) and `ReportSchedule.timezone` (NULL = UTC) — both named gaps in the row below are now satisfied here, not just closed there. |
| **PDF export** | [`services/pdf_export.py`](data_analytics/backend/app/services/pdf_export.py), `test_pdf_export.py` |
| **CSV / XLSX export** | `test_widget_export.py`, `openpyxl` |
| **Export policy control** | `test_export_policy_granular.py` — *finer than the architecture specifies* |
| **Publish a specific version, not "latest"** (D7.2) | ✅ **Closed (all-layers pass, 2026-08-26)** — credited in the Tier-2 list below but the row here was never updated until now. `share_links.snapshot` + `pinned`: a pinned link freezes layout at share time (data stays live, labelled so). **Extended (UX+ETL+security pass, S3):** the snapshot now also freezes the page's role-visibility list *at pin time*, so deleting the live page after pinning can no longer widen what a role-holding viewer sees — the edge case the S3 task named directly. |
| **Viewer identity on shared reports** *(new this pass)* | An authenticated in-org viewer of a shared report now resolves RLS as **themselves**, not the link's creator ([`routers/reports.py`](data_analytics/backend/app/routers/reports.py) — `resolve_rls_expr(db, current_user, ds.id)`, not the creator's id). Guest/anonymous viewers keep creator semantics by design — the share dialog says so plainly ("Guest viewers see data with YOUR data permissions"). A guest-link access log (`share_link_id`, ts, salted `ip_hash`, truncated user-agent) is written fire-and-forget on guest render, and export routes on guest paths now go through the same server-side 401 as everywhere else, not just UI-hiding. |

### 🟡 / 🔴 Gaps

| # | Gap |
|---|---|
| ~~1~~ | ~~**Embeds (D7.1)** — no `embed_configs`, no host-app-signed JWT, no `allowed_origins`, no filter injection.~~ ✅ **Closed (Tier 3 tenancy pass, E1).** [`routers/embed.py`](data_analytics/backend/app/routers/embed.py) + `EmbedConfig` (`embed_configs`: `created_by`, `secret_encrypted` — enc:v2, shown once — `allowed_origins`, `enabled`). A host application signs its own HS256 JWT with that secret; `embed.py` verifies with `jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require_exp": True})` — algorithm pinned, expiry mandatory, capped ≤24h at mint time. Filters are injected server-side **only from the verified JWT claims** — the browser is never trusted with scope, exactly the D7.1 mandate — and this was not free: the first review round found a **High-severity RLS-bypass** (the embed path resolved through an admin-branch identity, skipping RLS and column security entirely; a row-restricted editor could mint an embed exposing every row). The fix landed creator-base resolution — an embed can never expose more than its *creator's* own row/column slice, matching `shared.py`'s anonymous-guest model exactly — with the escalation path pinned dead by a value-verified test, plus page role-visibility parity with guest links (`visible_pages_for_creator`, extracted from `shared.py` and applied to both structure and widget resolution). `viewer_email`/`viewer_org` claims expand `USEREMAIL()`/`ORGID()` in the creator's own author-filter expressions (narrower than RLS, never a substitute for it); a CSP `frame-ancestors` directive and per-IP + per-token rate buckets (the per-token bucket was narrowed to IP-only in final review after a cfg-enumeration/LRU-churn finding) round it out. Frontend: an `EmbeddedReport` page plus a share-dialog Embed section with copy-paste Python/Node token-minting samples. **What D7.1 still lists that this pass does not add:** no revision pinning on `embed_configs` (an embed always serves the live report, unlike a pinned `share_links` snapshot) — the same gap #5 below names for share links, just not yet closed for embeds either. |
| 2 | **Playwright as the one server-side renderer (D7.3)** | `playwright` is a **frontend devDependency** (tests), not a backend render service. PDF export goes through reportlab + matplotlib — a *second* renderer, which is precisely the divergence D7.3 exists to prevent: your PDF will not look like your screen. |
| ~~3~~ | ~~**`deliveries` log table**~~ | ✅ **Closed (Tier 1 foundations pass).** `Delivery` (id, org_id, `schedule_id`/`report_id` nullable, kind `schedule\|alert\|manual`, status `ok\|error`, error, artifact_kind, duration_ms) logs one row per delivery attempt from both `delivery.py`'s `run_schedule` and `alerts.py`'s `check_alert`, written fire-and-forget via `log_delivery_sync` on the same dedicated-sync-engine contract as `query_runs`/`share_link_access` — a logging failure can never fail the delivery it describes. |
| ~~4~~ | ~~**Timezone handling on schedules**~~ | ✅ **Closed (Tier 1 foundations pass).** `ReportSchedule.timezone` (String(64), nullable, NULL = UTC) — the architecture's explicit-`timezone`-on-`schedules` requirement. |
| 5 | **Share link pins a revision** (D7.2) — see above. Cheap fix: add `revision_id` to `share_links`. |

### 🟢 Beyond the spec

**PowerPoint export** — `pptxgenjs` + `lib/pptExport.ts`. Not in the architecture at all, and in a
BI product often the *most* requested export format.

---

# Layer 8 — Platform Core

**Everything the architecture buys off the shelf, you built yourself.**

**Deployment: air-gapped.** The operational reality behind every row below is that this
platform's production target is an isolated network with no internet access. The Tier 4
offline/scale pass (2026-08-29) audited the whole stack for runtime internet dependencies,
found exactly one (Google Fonts), and closed it — see the ninth re-scoring blockquote and the
Layer 2 note above. Everything else in this layer (LLM endpoint, OTel export, SSO/SAML
metadata) was already internal-only or opt-in, so this pass is what makes that true end to end
rather than by omission.

### ✅ Achieved (in-house)

| Architecture requirement | Architecture's tool | Your implementation |
|---|---|---|
| Identity / OIDC / SSO | Keycloak / Zitadel | [`routers/sso.py`](data_analytics/backend/app/routers/sso.py), [`services/sso.py`](data_analytics/backend/app/services/sso.py), [`services/saml.py`](data_analytics/backend/app/services/saml.py) + `signxml`/`lxml`, `org_idps`, `saml_authn_requests`, `test_sso.py`, `test_saml.py` |
| Auto-provisioning from IdP | SCIM | [`services/auth_provisioning.py`](data_analytics/backend/app/services/auth_provisioning.py), `test_auth_provisioning.py` |
| API keys / service accounts | — | `api_keys`, `test_api_keys.py` |
| **Row-level security in the SQL predicate, not post-filter** (D8.2) | Layer 4 policy injection | ✅ **Implemented for DirectQuery**, and the import path's base-frame filtering — flagged as still-open work in the fourth re-scoring (line 780 of that pass) — turned out to already be closed by a prior refactor, not this one: the UX+ETL+security pass's own S1 audit (`backend/tests/test_rls_base_frame_choke_point.py`, allowlist + structural pin) verified all 17 import-path call sites already filter the base frame pre-aggregation. The one real bug S1 found and fixed was narrower but genuine: `alerts.py` evaluated its filter fail-*open* (`apply_filter_expr(silent=True)` — a broken expression let rows through) instead of fail-closed like every other RLS path; now routed through `apply_rls_filter` like the rest. [`core/rls.py`](data_analytics/backend/app/core/rls.py) + [`services/sql_expr.py`](data_analytics/backend/app/services/sql_expr.py) push RLS into a **parameterized SQL WHERE fragment** for DirectQuery. Tests: `test_rls_fail_closed.py`, `test_rls_user_context.py`, `test_widget_data_rls_enforcement.py`, `test_analysis_rls.py`, `test_data_preview_rls.py`, `test_filter_preview_rls.py`, `test_get_widget_data_rls.py`, `test_calculated_column_preview_rls.py` |
| **Column-level security** | *not in the architecture* | `column_security_rules`, `test_column_security.py` |
| Tenancy — scoping on every table | `tenant_id` | `org_id` + [`core/org_scope.py`](data_analytics/backend/app/core/org_scope.py), `org_parents` (**hierarchical orgs — beyond the spec**), `test_org_scope.py` + 5 `*_org_scoping.py` test files |
| **Append-only audit log** | `audit_log` | ✅ `audit_log` table + [`services/audit.py`](data_analytics/backend/app/services/audit.py), `test_audit_log.py`. **Extended (UX+ETL+security pass):** a dedicated `admin_audit` table (org, actor, action, target, ts, hash-safe detail) records security-relevant admin mutations specifically — RLS rule changes, row-policy edits, share create/revoke, export-policy changes, API keys — read-only in the admin UI, same append-only principle. |
| Roles / permissions | OpenFGA | `roles` table + `report_capability`, `page_role_visibility`, `test_admin_roles.py`, `test_resolve_roles.py`, `test_report_capabilities.py`, `test_page_visibility.py` |
| Capability model | — | [`core/capability.py`](data_analytics/backend/app/core/capability.py) |
| Secrets | OpenBao | [`services/secrets.py`](data_analytics/backend/app/services/secrets.py), `test_secrets.py` |
| **Envelope encryption** (stage 0.3) | OpenBao | *New in Layer 1.* `enc:v2:` — a per-secret data key wrapped by the master, so rotation re-wraps short keys instead of decrypting every secret. `enc:v1:` still decrypts, so a live database keeps working |
| Health checks | `health.py` | `main.py` lifespan + advisory-lock startup |

### 🔴 Missing

| # | Gap | Impact |
|---|---|---|
| 1 | **OpenFGA / relationship-based authz (D8.1)** | You use role strings + capability flags — exactly what the architecture predicts *"will collapse under that within months"* as folders/nesting grow. You've already hit the pressure: `org_parents`, `page_role_visibility`, `report_capability`, `column_security_rules`, `RowPolicy.auto_generated`, `DatasetShare`, and now (Tier 3 tenancy pass) **`EmbedConfig` and `Quota`** — arguably authz-adjacent bolt-ons in their own right (`EmbedConfig` gates *who* can mint scoped access to a report; `Quota` gates *how much* an org may consume) — bringing the honest tally to **eight** separate bolt-ons to a role enum, up from six. **This is the architecture's sharpest prediction about your codebase, and it keeps getting more evidence, not less.** |
| ~~2~~ | ~~**OpenTelemetry** — no traces, no span propagation~~ | ✅ **Closed, opt-in (Tier 3 tenancy pass, E3).** [`core/telemetry.py`](data_analytics/backend/app/core/telemetry.py): default-off (env-gated), lazy-imported so the dependency costs nothing when disabled, FastAPI + SQLAlchemy auto-instrumentation plus manual spans on agent nodes, DirectQuery and refresh, exporting OTLP/HTTP. Span attributes are **sha256-only** — no raw SQL or query strings — and a `_QuerystringScrubber` strips query strings from every exported HTTP span's URL attribute (added in final review after finding the embed bearer token was leaking through `http.url`'s query string; verified real on the pinned `opentelemetry` 1.27.0). D8.4's own case for installing this in layer 1 to avoid a retrofit is exactly what this pass did in reverse — a real retrofit, at real cost, is now paid. Still absent: Prometheus/Grafana (#3), GlitchTip (#7). |
| 3 | **Prometheus / Grafana** — no metrics endpoint | |
| 4 | **Langfuse** — N/A without an LLM | |
| ~~5~~ | ~~**`quotas` table** — no per-tenant limits on queries, tokens, storage, concurrency~~ | ✅ **Closed (Tier 3 tenancy pass, E2).** `Quota` model (one row per org, all four limits nullable = unlimited by default, byte-preserved for every org with no row) + [`services/quotas.py`](data_analytics/backend/app/services/quotas.py): per-org daily query and agent-ask caps (429 + `Retry-After`), a storage cap (413) summing `Dataset.file_size`, and a per-worker concurrent-ask slot limiter. Enforcement is coherent across all three access paths — app users, guests, and embeds all charge the **data-owning org**, not the viewer's — plus platform-super-admin CRUD and a usage UI (`PlatformOrgs`). Honest caveats, ledgered at review: concurrency is **per-worker**, not cluster-wide (same non-shared-cache caveat as rate limiting); the quota cache has up to **30s cross-worker staleness** after a `SET`; re-import-in-place has a known storage-accounting gap (old file size isn't subtracted before the new one is added) needing a temp-file refactor, ruled low-severity and documented rather than blocking. |
| ~~6~~ | ~~Rate limiting (`ratelimit.py`)~~ | ✅ **Closed (UX+ETL+security pass).** [`core/rate_limit.py`](data_analytics/backend/app/core/rate_limit.py): a per-user token-bucket middleware on authenticated routes plus a stricter per-guest-link bucket on guest routes, in-process/per-worker (honest about not being Valkey-backed — see Block C), LRU-capped bucket dict, 429 + `Retry-After`, `/health` exempt. Follow-up fix (`d41329a`) corrected guest buckets from keying on the share token alone (one link's colleagues sharing one ceiling) to keying on (token, viewer identity/IP). **Extended (Tier 3 tenancy pass):** embed paths get their own rate buckets too — per-IP and per-token, the per-token half narrowed to IP-only in final review after a finding that per-token buckets let an attacker enumerate embed configs unthrottled while churning the LRU. |
| 7 | **GlitchTip / error tracking** | |
| 8 | **`locale` on users** (`en \| ar`) | You have report translations, not per-user locale |

### 🟢 Beyond the spec

`notifications`, `report_comments`, `bookmarks`, `page_templates`, `widget_templates`,
`report_classifications` (Public/Internal/Confidential/Restricted sensitivity labels),
`report_parameters`, `org_themes`. **New this pass (Tier 3 tenancy):** `EmbedConfig` and `Quota`
— see the closed gaps above; also counted in the OpenFGA bolt-on tally since both are
authz-adjacent access-control tables, not pure product features. **From the prior pass:**
`DatasetShare` — in-org dataset sharing to another user (additive: dataset read was already
org-wide, so this is metadata + a "shared with you" surface, not a new access grant — verified by
the reviewer during S0's batch); a codeless RLS-rule builder with auto-generate proposals; a
guest-link access log; an admin-mutation audit trail (`admin_audit`) alongside the pre-existing
`audit_log`.

---

# Stack divergence — side by side

| Concern | ARCHITECTURE.md specifies | Your project uses | Verdict |
|---|---|---|---|
| Web framework | FastAPI | ✅ FastAPI 0.111 | **Match** |
| Validation | Pydantic v2 | ✅ pydantic-settings 2.2 | **Match** |
| ORM | SQLAlchemy 2.0 | ✅ SQLAlchemy 2.0.30 async | **Match** |
| Postgres driver | **psycopg 3** | psycopg2-binary + asyncpg | Different |
| **Migrations** | **Alembic** | ✅ Adopted (Tier 1 foundations pass) — baseline `0001_baseline.py` + revisions `0002`–`0005`, `create_all` retained alongside as an adoption-safe fallback | **Closed** — found via a real live-Postgres failure (`StringDataRightTruncation` on a >32-char revision id; SQLite's unenforced varchar length hid it from the whole suite), plus an adoption-stamps-head fix so a fresh boot's `create_all` and Alembic's `alembic_version` no longer race |
| **SQL parsing / guard** | **sqlglot** (25+ dialects) | Custom `ast`-based translator | Different (secure, narrower) |
| **Local engine** | **DuckDB** | **pandas** for queries; **DuckDB** for the metadata cache | **Partly closed** — DuckDB is now a real dependency doing real joins, just not on the query path |
| **Type system** | **Arrow end-to-end** | **pandas** + pyarrow at the edges | **Different — violates Principle 6** |
| DB→Arrow | ConnectorX | pandas `read_sql` | Different |
| Excel reader | python-calamine | **openpyxl** (architecture *rejects* it) | Different |
| Background jobs | ARQ + Valkey | In-process `refresh_scheduler` w/ PG advisory locks | Different (simpler, no Redis) |
| Cache | Valkey | ✅ `valkey/valkey:8-alpine` via `cache_backend.py`, opt-in (`VALKEY_URL`); in-process `OrderedDict` remains the byte-identical default | **Match (opt-in)** |
| Self-hosted embeddings | (implied by pgvector + embeddings requirement) | ✅ [`embedding_server/`](data_analytics/embedding_server/) — ONNX MiniLM, int8, no torch, air-gap-buildable, Backend B on by default (eleventh re-scoring) | **Match** |
| Vectors | pgvector | ❌ | Missing (in-process cosine over cached vectors is the seam's current implementation) |
| **Self-hosted inference** | **vLLM** | ✅ [`services/llm.py`](data_analytics/backend/app/services/llm.py) → Qwen, verified live | **Match** |
| **Constrained decoding** | XGrammar / Outlines | `complete_json` — validate-and-retry | Different (honest stand-in; no token-level grammar on a plain OpenAI-compatible endpoint) |
| **Join-graph review UI** | **React Flow** | ✅ `reactflow` 11.11.4 | **Match** |
| Join paths | NetworkX | ❌ | Missing |
| Agent | LangGraph | ❌ | Missing |
| Inference | vLLM | ✅ *(see above)* | **Match** |
| Constrained decoding | XGrammar / Outlines | 🟡 *(see above)* | Partial |
| LLM tracing | Langfuse | ❌ | Missing |
| Eval | promptfoo / Ragas / Spider / BIRD | ❌ | Missing |
| Forecasting | StatsForecast | ✅ StatsForecast `AutoETS`, default `method`, lazy-imported (Tier 5 analysis pass) | **Match** |
| Anomaly | PyOD | ✅ opt-in `iforest`/`ecod` alongside the byte-identical default `iqr` (Tier 5 analysis pass) | **Match (opt-in)** |
| Clustering | scikit-learn | ✅ `services/analysis/segment.py` — KMeans, silhouette auto-k (Tier 5 analysis pass) | **Match** |
| Code sandbox | gVisor | ❌ (N/A) | Missing by design |
| Web fonts | — | ✅ Self-hosted vendored woff2 (Tier 4 offline/scale pass) — was a Google Fonts `@import`, now zero external font requests | **Closed** — the only runtime internet dependency in the stack |
| **Charts** | **Vega-Lite + vega-embed** | **Recharts** | **Different — architecture rejects this by name** |
| Canvas | react-grid-layout | Custom 12-col grid | Different |
| Large grids | Perspective | Custom table/matrix | Different |
| Geo | MapLibre / deck.gl | d3-geo + topojson + world-atlas | Different |
| Join review UI | React Flow | ✅ *(see above)* | **Match** |
| Server render | **Playwright (one renderer)** | reportlab + matplotlib (**second** renderer) | Different — D7.3 warns against exactly this |
| Excel export | XlsxWriter | openpyxl | Equivalent |
| Embed tokens | PyJWT | ✅ `python-jose` (HS256, `EmbedConfig`) | **Closed** — different library, same guarantee |
| Identity | Keycloak / Zitadel | **In-house OIDC + SAML** | Different (built, not bought) |
| **Authorization** | **OpenFGA (Zanzibar)** | **Role strings + capabilities** | **Different — architecture predicts this collapses** |
| Tracing | OpenTelemetry | ✅ [`core/telemetry.py`](data_analytics/backend/app/core/telemetry.py) — opt-in, default off | **Closed (opt-in)** |
| Metrics | Prometheus | ❌ | Missing |
| Secrets | OpenBao | In-house `secrets.py` | Different |
| Tenant key | `tenant_id` | `org_id` (+ `org_parents` hierarchy) | Equivalent, richer |
| **PPT export** | — | **pptxgenjs** | **Beyond spec** |
| **MCP server** | Listed for L4 | ✅ **Built** | **Match** |

---

# What your project has that the architecture doesn't

The architecture is silent on all of this. Much of it is table stakes for a real BI product:

**Identity & governance**
- Full **SAML 2.0** IdP integration with signed AuthnRequests (`signxml`, `saml_authn_requests`)
- **Hierarchical organizations** (`org_parents`) — parent-org visibility
- **Column-level security** in addition to row-level
- **Report sensitivity classifications** (Public / Internal / Confidential / Restricted)
- **Granular export policy** — who may export what, in which format
- **Per-page role visibility**

**Collaboration**
- **Notifications** + bell UI (`notifications`, `NotificationsBell.tsx`)
- **Report comments** (`report_comments`, `CommentsPane.tsx`)
- **Bookmarks** (saved filter/selection states — a Power BI staple)
- **Lineage view** (`Lineage.tsx`)

**Authoring productivity**
- **Page templates** + **widget templates**
- **Report parameters** (`report_parameters`, `test_report_parameters.py`)
- **Common filters** across pages
- **Prep steps** — a transformation pipeline (`services/prep.py`, `PrepStepsPanel.tsx`), now with
  **sort/dedupe step kinds, a card-based pipeline editor with live per-step preview, and a
  disable toggle that greys a step instead of deleting it** (UX+ETL+security pass, F2)
- **Query builder dialog** — visual query construction, now **persisted and re-editable**
  (`Dataset.query_model`) with a **Design|SQL toggle** and PowerBuilder-style column
  checkboxes/aggregation badges on the canvas (D1–D3)
- **Load-mode control** — full vs. incremental refresh driven off `watermarks`, refresh history in
  `query_runs`, org-scoped (F3)
- **`.xml` extraction** via `pd.read_xml` (F1), and **ETL visibility on the lineage graph** —
  extract/transform/load badges, per-dataset transform-step count, freshness coloring (F4)
- **Command palette** — now indexes connections, not just pages/reports/datasets (A1)
- **Codeless expression builder**, shared across calculated columns, measures, dataset filters,
  prep filters and RLS rules — a Simple/Advanced toggle over one component, plus a "System"
  palette group for `USEREMAIL()/USERID()/ORGID()/ORGNAME()` (C1/C2/S0)
- **App-wide `ActionMenu.tsx`** — a "⋯" popup menu alternative to icon clusters, adopted at every
  major icon-action surface (U1)
- **Custom category expressions**, **quick calcs**, **rank modes**, **series having**, **custom sort**
- **Display / formatting rules** engine, vectorized
- **Mobile layout** per report page (`test_report_page_mobile_layout.py`)
- **RTL widgets** + report translations

**Analysis**
- **Goal seek**
- **Hierarchy drill-down** with auto-generated date hierarchies
- **Dimension granularity** control

**Engineering practice the architecture doesn't mention**
- **~190 backend test files** and a large frontend test suite
- **Benchmark harness** — `bench_http.py`, `bench_widget_data.py`, `bench_equivalence.py`,
  `bench_common.py`. `bench_equivalence.py` in particular guards the import-vs-DirectQuery
  equivalence invariant.
- **Pipeline validation script** — `scripts/validate_pipeline.py`
- **Demo content system** — `demo_content.py` (1893 lines), seeded datasets and reports
- **Thread offload for CPU-bound work** (`test_widget_data_thread_offload.py`) and a
  multi-worker-safe startup path
- **Cache-below-security invariant**, documented and enforced — `frame_cache.py` caches only
  pre-RLS frames keyed on bytes-of-file identity, with mandatory copy-on-hit, precisely so a
  post-RLS frame can never serve one user's row visibility to another. The architecture never
  raises this hazard; you found it and wrote the reasoning down.

## Two stale docstrings worth correcting

| File | Says | Reality |
|---|---|---|
| [`direct_query.py`](data_analytics/backend/app/services/direct_query.py) lines 7–9 | *"Admin-only in Phase 1: row-level security pushdown (Phase 2) isn't implemented yet"* | **Phase 2 landed.** `translate_filter_expr` is imported (line 43) and used (lines 231, 616), backed by 8 RLS test files. The docstring understates your own security posture. |
| [`README.md`](data_analytics/README.md) / `README2.md` | A ~12-widget uploader | See below — describes roughly 30% of the product |

---

# Documentation gap

[`README.md`](data_analytics/README.md) and [`README2.md`](data_analytics/README2.md) are
**near-identical and substantially out of date**. They describe:

- 12 widget types → you have **20+**
- 5 routers → you have **15**
- 5 services → you have **32**
- "Datasets · Report Builder · Cross-filtering · Data View Hierarchy"

They make **no mention** of: DirectQuery, RLS, column security, SSO/SAML, API keys, the MCP server,
measures & time intelligence, prep steps, alerts, schedules, share links, PDF/PPT export,
notifications, comments, bookmarks, insights, geo widgets, display rules, org hierarchy, audit log,
or report classifications.

Anyone reading your README will badly under-estimate the product. **This is the cheapest
high-value fix on this entire list.**

---

# The remaining gap, distilled

Everything still open, across all eight layers, collapses into **four blocks** — ordered by how
much of the architecture's promise each one unlocks, with the evidence for each already in this
document.

### Block A — Layer 4's runtime ✅ DONE (2026-08-26)

Built, hardened and measured — see the Layer 4 section above and the three
measurement appendices in the
[spec](data_analytics/docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md).
What Block A left behind for later blocks: the eval harness needs CI wiring
(Block C), and the accuracy ceiling it measured is Block B's argument.

### Block B — Layer 3's retrieval half *(now measurably the accuracy ceiling)*

The catalog now *describes* everything; it cannot yet *resolve* a business question to the right
columns. The architecture's claim — *"retrieval quality caps agent accuracy regardless of model
size"* — is no longer a prediction; it is what the measurements show. The agent's one persistent
wrong answer chooses a raw table where the ground truth lives in a curated precomputed one — a
**canonical-source metadata** problem no generation heuristic can solve (a blanket "prefer base
tables" rule was tried and is provably wrong for exactly this case). And most residual
clarification stops are genuine near-duplicate ambiguity that enum meanings and a glossary would
break. Block B is where the next accuracy points live:

| Piece | What exists to build on |
|---|---|
| ~~`enum_values` with meanings~~ | ✅ shipped: LLM-drafted + human-confirmed labels, in the agent's prompt |
| ~~`glossary_terms` + synonyms + Arabic aliases~~ | ✅ shipped, incl. question-matched prompt injection |
| ~~`entities` with grain~~ | ✅ shipped (Tier 2 retrieval pass): LLM-drafted, human-confirmed, survives resync, rendered + retrievable |
| ~~Lexical retrieval ranking, graph expansion, enum-label boost (R.1–R.5, lexical half)~~ | ✅ shipped (Tier 2 retrieval pass): TF-IDF word + char n-gram scorer wired into the render's enrichment order and 1-hop join promotion; measured parity, not lift, on this catalog |
| ~~Embeddings (R.1–R.7, embedding half)~~ | ✅ shipped (eleventh re-scoring, embeddings-service branch): self-hosted ONNX embedding service, Backend B enabled by default (circuit-broken, lexical fallback), vectors persisted in `retrieval_embeddings` by `(text_hash, model)` — restart-stable |
| pgvector | 🔴 still absent — cosine similarity runs in-process over the cached vectors, exact and fast at the current catalog size; `retrieval_embeddings` is the seam it slots into without rework |
| ~~`join_paths`~~ | ✅ shipped: BFS over the confirmed whitelist + prompt route hints |
| `query_examples` memory | ✅ table + recall/remember shipped with Block A; recall now ranks by **similarity** (Tier 2 retrieval pass), not recency alone |

Block B's LEXICAL half is shipped in full — canonical-source flags (they flipped the
measured wrong answer once rendering was fixed), TF-IDF ranking, graph expansion, enum-label
boosting, and entities with grain (Tier 2 retrieval pass) all landed and were measured together
against the round-6 baseline: **parity** (strict 12/25 identical, value-verified 16/25 vs 17,
conditional 76% vs 77%) — read honestly as headroom-for-scale rather than accuracy-lift on this
82-object catalog, exactly as the pass's own spec predicted before it was built. The EMBEDDING
half is now also shipped (eleventh re-scoring): a live Arabic smoke run shows semantic ranking
beating lexical on the customers case, while the invoices case still ranks a
semantically-adjacent view first — the same small-catalog headroom this document has predicted
since the round-6 measurement, reported honestly rather than gated. What remains of Block B:
**pgvector itself** (infra-blocked no longer applies to embeddings — this is now a pure scale-up
item, not a live-endpoint blocker), plus two measured quality items: the answer-synthesis
grounding bug that recurred in new forms, and canonical-preference tuning where a golden set is
itself ambiguous about raw-vs-curated counts.

### Block C — engine hygiene the agent will inherit *(Layer 2, small and compounding)*

| Piece | Why it moves up once an agent exists |
|---|---|
| ~~`query_runs` telemetry~~ | ✅ shipped (with a live-caught pool-corruption fix worth reading in the spec appendix); now also carries `source_kind='refresh'` rows from the new refresh endpoint (UX+ETL+security pass) |
| ~~Drift → cache invalidation wire~~ | ✅ shipped: per-source cache epoch folded into result-cache keys |
| ~~`watermarks` unused~~ | ✅ shipped (UX+ETL+security pass, F3): full/incremental refresh actually drives the table now |
| ~~Rate limiting~~ | ✅ shipped (UX+ETL+security pass, S5): per-user + per-guest-link token buckets — still in-process, so the next line still matters |
| ~~Shared cache (Valkey)~~ | ✅ shipped, opt-in (Tier 4 offline/scale pass, O2): `cache_backend.py`'s `ValkeyCache`, byte-identical `InProcessCache` default when unset. The rate limiter and guest access log remain per-worker/in-process — this specific line's scope is closed, that broader caveat is not |
| sqlglot for `sql_expr.py` | sqlglot==30.17.0 is now pinned and in production use (ladder + policies) — consolidation is cheaper than ever |
| eval CI gate | `run_eval_gate.ps1` is now a REAL one-command live gate (restart → 25 asks → per-intent table → threshold exit code, ~20 min, live-proven); **now also runnable on a schedule** (`eval_schedule.py`, opt-in, nightly, default off — a documented CI stand-in per the Tier 1 foundations pass, not CI); actual CI still awaits any CI infra (no remote exists — the UX+ETL+security pass confirms this was ruled out of scope up front, not forgotten) |
| ~~Popup overlay renderer; drillthrough; tooltip triggers~~ | ✅ all shipped — every page type triggerable |

### Block D — analysis depth *(Layer 5, independent, optional)* — ✅ shipped (Tier 5 analysis pass)

`forecast` now defaults to StatsForecast `AutoETS` (the hand-rolled exponential smoothing kept as
tested fallback), `segment` is real standardized KMeans with silhouette auto-k, anomaly detection
gained an opt-in PyOD catalogue (`iforest`/`ecod`) alongside the byte-identical `iqr` default, and
a uniform `AnalysisResult` envelope (`analysis_contract.py`) now wraps every analysis service's
output without reshaping any existing wire response. A tool registry (`services/analysis/registry.py`)
exposes the catalogue to Layer 4's agent prompt. The sandbox (D5.2) stays out until Python nodes
do — by design, not deferral; see Layer 5's 🔴 Missing table above.

**What is deliberately *not* in any block:** the LLM-written-code sandbox (no Python nodes in
v1), data parallelism / a distributed engine (pushdown chosen instead), LangGraph (hand-rolled
executor chosen), and the import path's post-filtering RLS (real, pre-existing, flagged in the
Layer 4 spec as its own piece of work).

---

# Priority recommendations

## Tier 1 — Do these regardless of whether you ever build the AI layer

| # | Item | Why | Effort |
|---|---|---|---|
| 1 | **Rewrite README.md** from the actual code; delete README2.md | The README describes maybe 30% of what exists | 1 day |
| ~~2~~ | ~~**Adopt Alembic**~~ | ✅ **Done (Tier 1 foundations pass).** Baseline `0001_baseline.py` + revisions `0002`–`0005`, `create_all` retained as an adoption-safe fallback; found and fixed a real live-Postgres revision-id length failure the SQLite suite couldn't see. | — |
| 3 | **`query_runs` telemetry table** | Per-query executor / rows / bytes / duration / cache-hit. Free operational insight now, and it is the exact table Layer 4 would later need. | 1–2 days |
| ~~4~~ | ~~**OpenTelemetry**~~ | ✅ **Done, opt-in (Tier 3 tenancy pass).** `core/telemetry.py`, default off, FastAPI+SQLAlchemy+manual spans, sha256-only attributes, query strings scrubbed. | — |
| ~~5~~ | ~~**Shared cache (Valkey)**~~ | ✅ **Done, opt-in (Tier 4 offline/scale pass).** `services/cache_backend.py`'s `ValkeyCache` + a no-host-ports `valkey` compose service; `InProcessCache` stays the byte-identical default when `VALKEY_URL` is unset, so nothing changes for a deployment that doesn't opt in. | — |
| ~~6~~ | ~~**Rate limiting + quotas**~~ | ✅ **Both done.** Rate limiting closed UX+ETL+security pass; `quotas` closed Tier 3 tenancy pass (`Quota` + `services/quotas.py`, coherent across app/guest/embed access, charged to the data-owning org). | — |
| ~~7~~ | ~~**Persist `column_stats` (incl. `top_k`)**~~ | ✅ **Done in Layer 1.** `GET /datasets/{id}/columns/{name}/stats` returns `top_k`. The filter UI can now offer real enum dropdowns — still worth wiring into the frontend. | — |

## Tier 2 — If you want to close real architectural risk

| # | Item | Why |
|---|---|---|
| ~~7b~~ | ~~Pin share links to a revision (D7.2)~~ ✅ **Closed (all-layers pass);** Layer 7 section corrected to match (UX+ETL+security pass — it had drifted stale). `share_links.snapshot`+`pinned` — a pinned link keeps its layout after report edits (data stays live, labelled so). Bonus fix found en route: guest share views were serving hidden/tooltip/drillthrough pages to anonymous viewers — now filtered server-side. **S3 extension:** page role-visibility is now frozen inside the snapshot too. | A link you sent a customer silently shows whatever the report became. Small schema change, real correctness fix. **Arguably belongs in Tier 1.** |
| ~~8~~ | ~~**Embed support (D7.1)**~~ | ✅ **Closed (Tier 3 tenancy pass).** `embed_configs`, host-signed HS256 JWT, `allowed_origins`, filters injected server-side only from verified claims, creator-base RLS/column-security parity with guest links — the single biggest missing *product* feature is now built, after a High-severity RLS-bypass was caught and fixed in review. |
| 9 | **One renderer for exports** — Playwright server-side | Your PDF (reportlab/matplotlib) does not and will not match the screen (Recharts). This drift compounds with every new chart type. |
| 10 | **Evaluate sqlglot for `sql_expr.py`** | Not because yours is unsafe — it isn't — but for dialect coverage and normalized cache keys, which fixes the L2 cache-miss issue too. |
| ~~11~~ | ~~**Schema drift detection**~~ | ✅ **Done in Layer 1.** SHA-256 fingerprint, structured diff, and orphaned confirmed annotations flagged rather than deleted. |
| 12 | **Revisit authz before it collapses** (D8.1) | Four bolt-ons to a role enum already. Don't necessarily adopt OpenFGA — but consolidate the model. |

## Tier 3 — Only if you decide to become the architecture's product

This is a strategic choice, not a backlog item — but it is now a *started* one: the Layer 4
design spec is written and awaiting review, and the model endpoint's contract is verified. Layers
3+4 remain **6–8 weeks minimum** per the architecture's own Phase 1 estimate, and they require an
eval set and an accuracy gate you could fail (the GPU exists — the Qwen box scales to ~2.3 req/s
at concurrency 12, measured).

If you do it, the sequence the architecture prescribes is right, and your assets are:

- `measure_eval.py` → seeds `metrics` (formulas already validated)
- `relationships` + `hierarchy_nodes` → seeds `entities` and the join graph
- `core/rls.py` → is already the policy-injection layer V4 needs
- `data_views` → is already a saved semantic scope
- MCP server → is already the tool surface

**And the honest alternative:** your MCP server means an external agent (Claude, an internal
assistant) can already query your platform *with correct authorization*. For many buyers that
delivers most of Layer 4's value at ~2% of the cost. **Before building Layers 3–4, measure how far
the MCP path already gets you.**

---

# Summary table

| | Architecture | Your project |
|---|---|---|
| **Product category** | AI agent NL→SQL platform | Self-serve BI / report builder |
| **Primary surface** | Chat | Dashboards |
| **Primary user** | Business user asking questions | Analyst authoring reports |
| **Semantic model** | Auto-drafted, human-confirmed in <10 min | **Auto-drafted and human-confirmed** for relationships, semantic types and descriptions; hand-authored for measures and hierarchies |
| **Query origin** | LLM-generated, validated | User-configured widget + measures |
| **Chart choice** | Rules, model for ties | Rules + user choice |
| **Local engine** | DuckDB + Arrow | pandas |
| **SQL safety** | sqlglot AST | custom `ast` translator + bound params |
| **Authz** | OpenFGA | roles + capabilities |
| **Identity** | Keycloak | in-house OIDC + SAML |
| **Maturity** | Design document, Layer 1 build-ready | Shipping product, **2448 backend (4 skipped) + 897 frontend tests** |
| **Overall alignment** | — | **~86%** (eleventh re-scoring: the embeddings service — a self-hosted, air-gap-buildable ONNX embedding service, retrieval Backend B enabled by default in compose, restart-stable persistence) — Layer 3's retrieval half is now embedding-backed by default rather than lexical-only (~72% → ~78%), closing the EMBEDDINGS half of the architecture's last numbered Layer 3 gap; pgvector itself remains the named absent half — in-process cosine is exact and fast at current scale, and the table is the seam it slots into without rework; live Arabic smoke shows semantic ranking beating lexical on the customers case, expected small-catalog headroom (not gated) on the invoices case; Layers 1, 4, 5, 6, 7 remain substantially there, 8 further along; a single-layer, evidence-based move this size holds the rounded overall figure steady, consistent with how every prior pass in this document has weighted the recompute |

**The bottom line:** you have a competent, well-tested BI product that is stronger than the
architecture in visualization, governance, collaboration and test discipline — and it now also has
the architecture's metadata plane underneath it.

What changed with Layer 1 is not mainly the score. It is that the expensive, unglamorous
groundwork is done: a source can be sampled, profiled, masked, inferred over, drift-checked and
confirmed by a human, with provenance that a resync cannot trample. Layers 3 and 4 are still real
work — entities, enums, embeddings, retrieval, an agent, an eval harness — but they are no longer
waiting on raw material that did not exist.

Alignment was never the goal; **choosing knowingly is.** The choice in front of you is unchanged
and is now cheaper to act on in one direction: build Layer 3 on the catalog you have, or keep the
MCP path and let someone else's agent use it. Both are now viable. Before Layer 1, only one was.
