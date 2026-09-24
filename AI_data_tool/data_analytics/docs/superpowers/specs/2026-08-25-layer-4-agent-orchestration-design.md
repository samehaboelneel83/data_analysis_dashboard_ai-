# Layer 4 — AI Agent Orchestration

**Status:** design, awaiting review
**Date:** 2026-08-25
**Supersedes nothing.** Extends `ARCHITECTURE.md` § Layer 4 where noted.

---

## Purpose

Question in, correct answer out — with the loop, validation and repair that make
that reliable rather than lucky.

The request that started this was about **parallelism**, framed against SAS
Visual Analytics and CAS. That framing is useful, but only two of its three
levels apply here, and the reason matters:

| CAS level | Applies? | Why |
|---|---|---|
| Data parallel | **No** | CAS parallelises because it *owns* the data — it loads partitions into worker memory. This platform deliberately does the opposite: computation is pushed down to the source or into DuckDB. Adding it means adopting a distributed engine (Trino/Spark), which is out of scope by decision. |
| Task parallel | **Yes** | Independent operations overlapping under a bound. Already proven three times in this codebase. |
| Agent parallel | **Yes** | Concurrent agent runs, each owning its own DAG. |

So the DAG is where the parallelism lives, and it is genuinely the thing that
was missing — **there is no orchestration layer in the codebase at all today**:
no planner, no graph, no agent runner, no `sqlglot`, no sandbox.

---

## Decisions taken before this document

| # | Decision | Rationale |
|---|---|---|
| S1 | Data parallelism out of scope | Push down to the source; matches ARCHITECTURE.md's stated position and adds no service to operate |
| S2 | **SQL nodes only** in v1 | Python and ML nodes have no execution substrate — Layer 5 does not exist. The node interface is typed so they slot in later without reshaping the graph |
| S3 | **Row-policy AST injection is in v1** | ARCHITECTURE.md calls this "the security-critical flow of the whole platform". Retrofitting security onto a shipped agent means auditing every query path twice |
| S4 | Starter golden set generated, eval gate wired | Without a gate, no prompt or model change can be told from a regression |
| S5 | **Hand-rolled asyncio executor**, not LangGraph | Diverges from ARCHITECTURE.md deliberately — see below |
| S6 | Full loop in v1 | Clarify (D4.3) and bounded repair (D4.4) are what separate a demo from something trustworthy |

### S5 in detail — why not LangGraph

ARCHITECTURE.md names LangGraph (`packages/agent/graph.py`). This design does
not use it, for three reasons:

1. **Every concurrency path in this codebase is hand-rolled `gather` +
   `Semaphore`** — `widget_data.py`, `catalog_sync.stage_sample`,
   `catalog_sync.stage_describe`. A framework idiom foreign to the repo costs
   more in comprehension than it saves in code.
2. **LangGraph's strength is cyclic agent loops.** This graph is acyclic by
   construction; the one cycle (repair) is a bounded three-attempt retry inside
   a single node, not a graph edge.
3. The executor is ~300 lines. Owning it is cheaper than debugging through
   someone else's state machine.

What LangGraph would have given free — checkpointing, streaming — is not a v1
requirement. If it becomes one, that is a real reason to revisit.

---

## Architecture

```
question
   │
   ▼
classify ──ambiguous?──► clarify ──► (back to the user, run ends)
   │ no
   ▼
retrieve context   (Layer 3 interface; v1 reads the Layer 1 catalog)
   │
   ▼
plan  ──► typed step DAG
             │
   ┌─────────┼─────────┐        task parallel, ONE bounded gate
   ▼         ▼         ▼
 node A    node B    node C     each node, independently:
   │         │         │          generate SQL  (constrained decoding)
   │         │         │          validate      (V1–V5 ladder)
   │         │         │          repair        (≤3, error-specific)
   │         │         │          execute       (Layer 2)
   │         │         │          sanity        (empty · absurd · huge)
   └─────────┼─────────┘
             ▼
        synthesize ──► answer + provenance ──► query_examples
```

Nodes with dependencies run in later topological layers and receive their
parents' results. Independent nodes overlap. **Agent parallelism** is simply
several of these graphs running at once.

### Why the DAG does not contradict ARCHITECTURE.md

The doc's `plan.py` decomposes into "ordered steps". A dependency DAG
generalises an ordered list — a linear chain is the degenerate case. The
validation ladder is **per query**; the DAG is **per question**. They compose
without either changing.

---

## Findings from the existing system that shape this design

These were verified against the running system and the live endpoint, not
assumed.

### F1 — The provenance ladder is what makes V3 possible

Ladder rung V3 is "joins — path is confirmed". That maps exactly onto
`SourceRelationship.source in ('confirmed', 'declared')` — and **never
`inferred`**.

On the live `maps` source: **133 relationships, 28 declared, 105 inferred**. So
the majority of known join paths are *proposals*. The agent may surface an
inferred join as a suggestion for a human to confirm; it must not silently
execute on one. A wrong join produces a plausible number, which is the most
expensive kind of wrong answer.

This rule is only expressible because Layer 1 tracks provenance.

### F2 — Constrained decoding works, but not via the documented parameter

Measured against `http://10.125.18.189:8000/v1` (`qwen3.5`):

| method | result |
|---|---|
| `guided_json` (vLLM native, what XGrammar/Outlines integrations use) | **silently ignored** — returns unconstrained markdown prose |
| `extra_body.guided_json` | silently ignored |
| `response_format: {type: "json_object"}` | JSON, but not the schema — invented `table_name` for `table` |
| **`response_format: {type: "json_schema", json_schema: {...}}`** | **enforced at the grammar level** |

The enforced case was tested adversarially: the prompt *"Write me a friendly
paragraph about the weather. Do not use JSON."* against a schema with unnatural
key names and a strict enum still returned schema-valid JSON with the enum
respected.

The silent-ignore behaviour of `guided_json` is the dangerous one — it looks
like it works until something parses the output. **Every node contract in this
layer uses `response_format: json_schema`.**

**Caveat, and it is important:** enforcement is *structural, not semantic*. In
the same probe, "How did revenue trend by region last quarter?" was classified
`lookup` with confidence 0 — perfectly valid JSON, wrong answer. Constrained
decoding buys the contract and nothing else. Quality comes from few-shot
examples and the eval gate (S4), which is why that gate is not optional.

### F3 — Row-level security has no binding for agent SQL

`RowSecurityRule` is keyed **per dataset** (`resolve_rls_expr(db, user,
dataset_id)`). The agent queries the **catalog** — source objects, arbitrary
joins, tables nobody imported. No existing rule binds to that.

v1 therefore adds `object_row_policies`, keyed to `source_objects`, and injects
predicates into the parsed AST.

### F4 — The import path post-filters, and the agent must not copy it

Two RLS paths exist today, with different security properties:

- **DirectQuery** — `rls_where` / `rls_params` pushed into the SQL with bound
  parameters. Correct.
- **Import / pandas** — `apply_rls_filter(df, expr)` in `widget_data.py:2015`
  filters the DataFrame *after* the query has run.

ARCHITECTURE.md forbids the second explicitly: *"Post-filtering leaks row
counts, aggregates, and existence."* An aggregate computed before the filter is
already the wrong number, and it has already left the database.

The agent path follows the DirectQuery model. **The import path is a
pre-existing issue this design does not touch** — flagged here so the decision
to leave it is recorded rather than overlooked. It deserves its own piece of
work.

### F5 — One model endpoint serves everything

The sync's describe stage now runs 12 concurrent calls against the Qwen box
(measured: throughput 0.31 → 1.35 → 2.32 req/s at concurrency 1 → 6 → 12, with
per-call latency rising only 3.2s → 5.1s — continuous batching working).

Agent runs will hit the same box. Two independent semaphores against one
endpoint is a queue nobody manages: a sync during an agent run doubles the load
and the user's question waits behind 82 table descriptions.

**The gate moves into `services/llm.py` and becomes global.** Both callers
acquire from it.

Beyond that, a background sync should not be able to make a person wait, and
there are two ways to ensure it — they are materially different and the choice
is **open, to be settled during implementation**:

- **Reserved headroom.** The gate has N slots; background callers may take at
  most N−k, leaving k always available for an interactive run. Simple, and the
  guarantee is exact.
- **Priority queue.** Interactive requests jump the queue. Better utilisation
  when nothing interactive is waiting, but a busy period can starve the sync
  indefinitely unless ageing is added.

Reserved headroom is the likelier answer — it is a few lines and its worst case
is bounded — but this is a decision worth making with the code in front of us
rather than committing to here.

### F6 — Layer 3 does not exist, and Layer 4 depends on it

ARCHITECTURE.md has Layer 4 retrieve context from Layer 3 (entities, metrics,
join paths, glossary, synonyms). None of it is built.

What *is* built, from the Layer 1 work: table and column descriptions, semantic
types, relationships with provenance, column statistics with top-k enumerations.
That is a serviceable minimal semantic layer.

`context.py` is therefore defined as an **interface**, whose v1 implementation
reads the Layer 1 catalog directly. A real Layer 3 replaces the implementation
without touching the graph.

---

## Components

```
app/services/agent/
├── state.py       AgentRunState — typed, passed between nodes
├── plan.py        question + context → validated step DAG
├── dag.py         executor: topological layers, gather + one bounded gate
├── nodes/
│   ├── classify.py    intent + ambiguity           (json_schema)
│   ├── clarify.py     question generation          D4.3
│   ├── generate.py    SQL generation               (json_schema)
│   ├── validate.py    the V1–V5 ladder
│   ├── repair.py      error-specific, bounded to 3 D4.4
│   ├── sanity.py      empty · absurd · oversized
│   └── explain.py     answer + provenance
├── policy.py      sqlglot AST predicate injection  V4
├── context.py     Layer 3 interface; v1 reads the Layer 1 catalog
├── prompts/       versioned, one file each
└── memory.py      query_examples read and write

app/services/llm.py      MODIFIED — the concurrency gate moves here and
                        becomes global, shared with the sync (F5)
app/routers/agent.py     conversations, messages, run streaming
evals/
├── golden/        ~25 question→SQL pairs against maps, execution-verified
├── run_eval.py    execution accuracy, not string match
└── report.py      per-intent breakdown; CI gate
```

### The executor (`dag.py`)

```python
async def run_dag(dag, gate):
    """Nodes with no unmet dependency run together; the rest wait for theirs.

    One gate for the whole run, not one per layer: the bound is a promise about
    load on the customer's database, and a per-layer semaphore would let a wide
    layer exceed it.
    """
    results = {}
    for layer in dag.topological_layers():
        outcomes = await asyncio.gather(
            *(_run_node(n, results, gate) for n in layer),
            return_exceptions=True,
        )
        # A failed node fails its dependents, never its siblings.
        ...
```

Mirrors `stage_sample` exactly: plain data across the thread boundary, bounded
gate, `return_exceptions=True`, every outcome a value rather than a control-flow
exception.

### The validation ladder

Cheapest first, so most failures cost nothing (D4.1):

| Rung | Catches | Cost | Source of truth |
|---|---|---|---|
| V1 parse | syntax, wrong dialect | µs | `sqlglot` |
| V2 schema | **hallucinated tables/columns — the most common failure** | ms | `source_objects` / `source_columns` |
| V3 joins | invented or unconfirmed joins | ms | `SourceRelationship`, confirmed/declared only (F1) |
| V4 policy | missing row filters — **injected into the AST** | ms | `object_row_policies` (F3) |
| V5 dry run | type errors, ambiguous columns, permissions | one `EXPLAIN` | the source |

V2 costs nothing because Layer 1 already holds all 1,354 columns.

---

## Data model

Via the existing `_migrate` convention in `app/main.py` —
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, no Alembic.

```sql
conversations    (id, org_id, user_id, data_source_id, title, created_at)
messages         (id, conversation_id, role, content, agent_run_id, created_at)
agent_runs       (id, org_id, conversation_id, question, status, intent,
                  plan, answer, error, ms, created_at)
agent_steps      (id, agent_run_id, node, status, sql, rows_returned,
                  validation_failures, repair_attempts, ms)
query_examples   (id, org_id, data_source_id, question, sql, confirmed_by,
                  created_at)
object_row_policies (id, org_id, source_object_id, role_id, predicate,
                     created_at)
```

`agent_steps` is not optional bookkeeping: without a per-node record of what SQL
ran, what the ladder rejected and how many repairs it took, neither the eval
gate nor a support conversation has anything to work from.

---

## Testing

Follows the conventions this codebase already holds itself to.

**Correctness**
- Every ladder rung gets a test that a *bad* query is caught at that rung and no
  earlier — cheapest-first only matters if it holds.
- V3 must reject a join whose only support is an `inferred` relationship. This
  is the F1 rule and the single most important test in the layer.
- V4: a predicate reaching the AST, never the string. A test asserting the
  rendered SQL contains the predicate inside `WHERE` and that no code path
  concatenates it.
- Post-filtering must be impossible by construction: a test that the agent path
  never calls `apply_rls_filter`.

**Parallelism** — mirroring `tests/test_catalog_sync.py::TestSamplingIsBounded`
- Independent nodes overlap, asserted as *observed overlap*, not elapsed time.
- Concurrency never exceeds the bound.
- A failed node fails its dependents and **not** its siblings.
- The event loop keeps ticking throughout, per `test_sync_does_not_block.py`.

**Eval gate**
- ~25 golden question→SQL pairs against the real `maps` catalog, each verified
  by executing both the golden SQL and the generated SQL and comparing
  **results, not strings**.
- CI fails on a drop in execution accuracy. Reported per intent, because a model
  change that helps lookups and breaks trends is invisible in an average.

---

## Risks

| Risk | Bound |
|---|---|
| Agent executes on an inferred join and returns a plausible wrong number | V3 admits confirmed/declared only (F1). Inferred joins are surfaced as suggestions requiring confirmation |
| A generated query leaks rows across a policy boundary | V4 AST injection, tested for; agent path forbidden from the post-filter helper (F4) |
| Constrained decoding silently stops working after an endpoint upgrade | `guided_json` already fails this way (F2). A startup probe asserts enforcement and logs loudly if the contract is not honoured |
| Structurally valid, semantically wrong classification | Observed in the probe (F2). The eval gate is the only defence and ships with v1 |
| A sync starves interactive agent runs of model capacity | Global gate in `services/llm.py`; background work de-prioritised (F5) |
| An agent run hammers the customer's source | One bounded gate for the whole run, sized like `metadata_sample_concurrency` |
| Layer 3 arrives and invalidates the context node | `context.py` is an interface from day one (F6) |

---

## Not in scope

- **Data parallelism / distributed engine** (S1)
- **Python and ML nodes** (S2) — Layer 5
- **Fixing the import path's post-filtering RLS** (F4) — real, pre-existing,
  deserves its own work
- **The MCP server's per-call `httpx.Client`** — still unfixed, still a
  different service
- **Streaming and checkpointing** — the main things LangGraph would have given
  free (S5). Revisit if they become requirements

---

## v1 measured results (2026-08-26)

Live verification (Task 15) against the real `maps` DirectQuery source
(DataSource 2, Postgres, 82 objects) plus one multi-file (uploaded-CSV join)
scenario, run after the `classify.py` union-type fix (commit `e7fd340`)
that unblocked this task (see `task-15-report.md` for the blocking bug that
preceded this run). 25 golden `(question, sql, intent)` pairs live in
`backend/evals/golden/maps.jsonl`, 5 per intent, each golden SQL executed
and hand-verified against the live source before being trusted as ground
truth.

### Accuracy (`evals.run_eval.evaluate()`, execution-equality, order/alias-insensitive)

| Intent | Correct / Total | Accuracy |
|---|---|---|
| lookup | 3 / 5 | 60% |
| aggregate | 1 / 5 | 20% |
| trend | 0 / 5 | 0% |
| compare | 0 / 5 | 0% |
| explain | 0 / 5 | 0% |
| **Overall** | **4 / 25** | **16%** |

Worst intents: trend, compare, and explain, all at 0% — but the proximate
cause in every one of those cases is that the run never reached SQL
generation (clarification or repair-exhaustion), not that generated SQL
gave a wrong answer. Every run that *did* produce SQL and reach `status:
ok` (4/25) matched the golden answer exactly — 4/4, i.e. **conditional
accuracy on completed runs is 100%** in this sample. The 16% headline is
almost entirely a completion-rate problem, not a correctness-of-generated-SQL
problem.

### Operational metrics

| Metric | Value |
|---|---|
| Clarification stops | 18 / 25 (72%) |
| Repair-loop engagement (`repair_attempts > 0`) | 3 / 25 (12%) — all 3 exhausted repairs and still failed |
| Runs reaching `status: ok` | 4 / 25 (16%) |
| Runs `status: failed` (repair exhausted) | 3 / 25 (12%) |
| Median per-ask latency | 2,763 ms |
| Latency range | 1,810 ms – 7,197 ms |
| HTTP-level failures | 0 (one script-side UTF-8 body-encoding bug on question 17 was fixed and retried; not an agent failure) |

### Why the clarification rate is so high — and why that's the honest number

`maps` is a real, organically-grown production schema: 82 objects, many of
them near-duplicate variants of the same table
(`maps_state_student_solution_details`, `..._backup`, `..._old`,
`..._extra`, `..._predected`, `..._predected_add`,
`..._predected_top_symbols`, `..._15_2026`, plus half a dozen `v_...`
views layering corrections on corrections). Every clarification the model
asked was schema-grounded and specific — e.g. for "how many student
solutions are recorded in total?": *"Do you want the total count of unique
student solutions from the main metadata table
(`maps_state_student_solution`), or the sum of records across all related
detail and version-specific tables?"* — rather than a generic refusal. This
reads as the classify/clarify node (T6) working as designed (F ambiguity
handling: "a clarifying question costs a moment, a wrong confident answer
costs trust") against a genuinely ambiguous catalog, not as a defect. It
does mean the 16% headline is a property of this specific catalog's messiness
as much as of the agent — a cleaner schema would likely show a very
different number, which is exactly why this run used the real, unfiltered
`maps` source rather than a curated subset.

### Failure modes observed (the 3 `failed` / repair-exhausted runs)

- Two runs (`Which 5 map states received the most student submissions...`,
  `Which 5 students placed the most symbols...`) failed on V2 with `no such
  column: submission_count` / `no such column: symbol_count` — the model
  referenced a `SELECT`-list alias in a later clause in a way the target
  dialect/validator rejected, and 3 repair attempts did not converge on a
  fix.
- One run (`How many distinct students from each institute have submitted
  symbol placements?`) failed for the *right* reason: the join path
  (`cycle_students.institute_code = institute_codes.institute_code`) exists
  in the catalog only as an **inferred** relationship, not confirmed or
  declared, and the executor correctly refused to execute on it — "Inferred
  relationships are proposals awaiting human review and may not be executed
  on." This is F4/relationship-provenance policy working as intended, not a
  bug; the golden pair for this question stays in the set as a legitimate
  "correctly refused" case rather than being pulled for being unanswerable.

### Multi-file scenario (dataset mode, `dataset_ids`)

Two CSVs uploaded via `POST /api/v1/datasets` (`eval_cities`: city, country,
population, 5 rows; `eval_orders`: order_id, city, amount, 8 rows), a
CONFIRMED `Relationship` row inserted directly (`eval_orders.city ->
eval_cities.city`, `source="confirmed"`), then one dataset-mode conversation
(`dataset_ids: [14, 15]`).

- **Question:** "What is the total order amount for each city, including the
  city's country and population?"
- **Generated SQL** (DuckDB dialect, one step, no repairs, 1,048 ms):
  ```sql
  SELECT c.city, c.country, c.population, SUM(o.amount) AS total_order_amount
  FROM eval_orders o JOIN eval_cities c ON o.city = c.city
  GROUP BY c.city, c.country, c.population
  ```
- **Answer:** "The total order amounts are 450.0 for Giza, Egypt (population
  4,200,000), 780.6 for Cairo, Egypt (population 10,000,000), 165.25 for
  Alexandria, Egypt (population 5,200,000), and 60.0 for Luxor, Egypt
  (population 500,000)."
- **Verification:** hand-checked against the source CSVs — Cairo
  250.50+120.00+410.10 = 780.60, Alexandria 75.25+90.00 = 165.25, Giza
  300.00+150.00 = 450.00, Luxor 60.00 — all four exact, and Aswan (which has
  no orders) is correctly omitted by the inner join. First-try success, zero
  repairs, ~4.3s end to end. This is the one clean end-to-end confirmation
  that the "one SQL surface" design (DuckDB over registered, RLS-filtered
  frames) works for a confirmed cross-dataset join through the full
  classify → plan → generate → validate → execute path.

### Honest takeaway

The agent is not broken — the one full pipeline pass that got a clean
question against a well-specified schema (the multi-file join) succeeded
first try with correct arithmetic, and every DirectQuery run that reached
`status: ok` was also correct (4/4). The 16% headline overall accuracy on
`maps` is real and should not be rounded up, but it is dominated by a
72% clarification rate against a schema with heavy naming ambiguity, not by
the agent confidently returning wrong answers — on this sample it never did.
The two V2-repair failures (bad alias references surviving 3 repair
attempts) are the concrete place to invest next if raising completion rate
on messy catalogs matters more than the current bias toward asking first.

## Hardening pass results (2026-08-26)

Re-measured the same 25 golden `maps` questions against the agent-hardening
branch (H1–H5 landed, commit `d66ca69`), same DataSource 2 / org 1 / user 1
setup, same golden set, same `evals.run_eval.evaluate()` execution-equality
scoring. One conversation per question, sequential, HTTP against the live
container. This is a before/after of the v1 baseline above, not a fresh
study — read the two together.

### Headline: completion tripled, clarification collapsed, but conditional
### accuracy dropped — the rebalance traded some correctness for reach

| Metric | v1 baseline (2026-08-26 pre-hardening) | Hardening pass (this run) |
|---|---|---|
| Completion (`status: ok`) | 4/25 (16%) | **12/25 (48%)** |
| Clarification stops | 18/25 (72%) | **7/25 (28%)** |
| Failed (repair-exhausted / other) | 3/25 (12%) | 6/25 (24%) |
| Repair-loop engagement (`repair_attempts > 0`) | 3/25 (12%), all exhausted | 5/25 (20%), all exhausted |
| Conditional accuracy on completed runs — strict, same scoring as v1 | **4/4 (100%)** | **7/12 (58%)** |
| Conditional accuracy — value-verified (see note below) | n/a | 9/12 (75%) |
| Median per-ask latency | 2,763 ms | 3,608 ms |
| Latency range | 1,810 ms – 7,197 ms | 2,262 ms – 9,195 ms |

**Conditional accuracy is the number that must not drop, and it dropped —
this is the headline, not a footnote.** Under the exact v1 method (execute
the golden SQL and the SQL from the run's final step, compare rows), 7 of
the 12 completed runs matched; 5 did not. The controller should read this
as: H1–H5 pushed the agent to answer more (and ask less) on a genuinely
ambiguous, 82-object schema, and some of that extra reach is landing on
wrong or incomplete answers instead of a clarifying question. That is
exactly the trade the plan's own framing warned about ("a wrong confident
answer costs trust").

### Why there are two conditional-accuracy numbers

Post-hardening, several runs now decompose into multi-step DAG plans (2–5
steps) rather than one SQL statement — new behavior not present in the v1
data (all 4 v1 completions were single-step). The v1 scoring method takes
the *last* step's SQL as "the generated SQL." For two `compare` questions
that decompose into two independent scalar side-by-side queries (no single
combining step exists — see below), that method captures only one side and
scores the run wrong on a capture artifact, not a real error. Hand-verifying
those two against golden values (both step results together) shows they are
correct:

- *"Compare the number of map states registered under institute code 2
  versus institute code 6."* — steps: `SELECT COUNT(*) ... institute_code =
  2` (16) and `... = 6` (10). Golden: `(16, 10)`. NL answer: "16 ... and 10
  ..." — correct. Strict last-step score: wrong (only captures the "10"
  query). Value-verified: correct.
- *"Compare the number of defense-type map states ... to attack-type map
  states ..."* — steps: `state_type_code = 1` (14), `= 2` (18). Golden:
  `(14, 18)`. NL answer states both numbers correctly. Strict: wrong.
  Value-verified: correct.

Folding those two in gives 9/12 (75%) value-verified — still a real drop
from 100%, not a wash. No row-merging machinery was built for this (tuple
positional order makes generic merging fragile); this was a targeted
two-case hand-check per the specific shape these compares took.

### The two genuinely new wrong answers (not scoring artifacts)

These are actual regressions — wrong information reaching the user that
would previously have been a clarifying question or a refusal:

- **"What are the 5 most common symbols by usage count, and how often does
  each appear?"** (explain) — generated SQL aggregates `symbol_code` counts
  from `maps_state_student_solution_details` (values up to 544,676); golden
  reads from the precomputed `omda_symbol_count` table by `symbol_name`
  (values up to 3,116) — a different table entirely, off by two orders of
  magnitude. Wrong answer, not just a shape mismatch.
- **"Which map states have no ideal solution recorded yet?"** (explain) —
  the generated SQL is actually right (`maps_state_id` set matches golden's
  8 rows exactly, just missing the `maps_state_name` column golden also
  returns), but the model's synthesized natural-language answer told the
  user *"it is impossible to determine which states have no ideal solution
  recorded"* — a confidently wrong refusal delivered on top of correct
  underlying data. The SQL succeeded; the answer synthesis failed the user.

One more completed run is a lesser case, not counted as "wrong": **"Which 5
map states received the most student submissions, and how many did each
receive?"** — IDs and counts match golden exactly, just missing the
`maps_state_name` label column. Right numbers, less informative than golden
would be about which state is which.

### Which previously-clarified questions now complete

The v1 baseline report only recorded aggregate counts, not a per-question
log of which of the 18 clarified questions were which — so an exact "N of
18 now complete" cannot be reconstructed from what's on disk. What can be
said: completion went from 4/25 to 12/25 (net +8), so at least 8 questions
that did not reach `status: ok` in v1 do now, most plausibly former
clarification-stops given clarification fell from 18 to 7. The 7 that still
clarify look like the same class of schema-grounded ambiguity v1 described
— the model asking which near-duplicate table/column to use (e.g. "active
symbols" against `symbol_codes` vs `maps_states_ideal_solution`, or "average
student result" against which of several `..._predected...` variants) — so
the remaining 28% clarification rate reads as the same kind of schema
ambiguity working as designed on this catalog, not a defect.

### Failure modes among the 6 `failed` runs

5 of 6 are the same category the v1 baseline flagged as "failed for the
right reason": the join path needed exists only as an **inferred**
relationship, and the executor correctly refuses to execute on it after 3
repair attempts don't find a path through confirmed/declared relationships
instead. (v1 had 1 such case; this run has 5 — more multi-step decomposition
means more join paths get attempted, and more of them land on inferred-only
edges.) This is F4/relationship-provenance policy working as intended, not
a regression.

The 6th is new: *"Compare the average student result for the symbols
'اتجاه هجوم العدو' and '(دفاع على عجل) قواتنا'."* failed both on first try
and on a same-question retry with `error: "the model endpoint could not
classify the question"` — a real, reproducible failure at the classify
node on this specific Arabic-text question, not a transient blip. Worth a
follow-up look at the classify prompt/response handling for non-Latin
symbol-name text, though it is a single question in this sample and could
be idiosyncratic to these particular Arabic strings rather than a general
Arabic-input problem.

### Bottom line for the controller

H1–H5 did what they were built to do on the completion/clarification axes —
3x completion, clarification cut by more than half, repair-loop engagement
still fully exhausting when it fires (unchanged failure shape there). But
conditional accuracy fell from 100% to 58% (strict) / 75%
(value-verified), with two confirmed new wrong-answer cases (a
wrong-table aggregation, and a correct-SQL-wrong-answer synthesis failure).
On a 12-completion sample this is a small-N result and not proof the
rebalance is net negative, but it is proof the rebalance is not free — the
next move is either accepting this trade explicitly or tightening the
completion/correctness boundary (e.g. answer-synthesis grounding checks, or
narrowing which multi-step decompositions are allowed to reach `status:
ok` without an extra verification pass) rather than reporting the
completion/clarification wins alone.

## Hardening pass, second iteration (2026-08-26)

Three targeted fixes landed after the first hardening measurement above,
backend restarted with them, and the same 25-question `maps` golden set was
re-run with the same method (fresh conversation per question, DataSource 2,
`evals.run_eval.evaluate()` execution-equality against the live source):

1. `generate` now prefers base tables over near-duplicate derived views,
   using descriptions.
2. `explain` is forbidden from claiming "cannot determine" when figures
   exist.
3. `classify`'s `max_tokens` was 200 (too small at 82-object catalog scale —
   the model's `ambiguity_reason` field was getting truncated mid-JSON,
   which is what actually caused the "model endpoint could not classify the
   question" failure attributed to Arabic text in the first hardening pass,
   not an Arabic-input problem specifically); now 400.

### Three-way headline

| Metric | v1 baseline | Hardening, 1st pass | Hardening, 2nd pass |
|---|---|---|---|
| Completion (`status: ok`) | 4/25 (16%) | 12/25 (48%) | **12/25 (48%)** — unchanged |
| Clarification stops | 18/25 (72%) | 7/25 (28%) | **8/25 (32%)** |
| Failed | 3/25 (12%) | 6/25 (24%) | **5/25 (20%)** |
| Repair-loop engagement | 3/25 (12%), all exhausted | 5/25 (20%), all exhausted | **6/25 (24%)** — 5 exhausted, **1 now succeeds within budget** |
| Conditional accuracy — strict (v1 method) | 4/4 (100%) | 7/12 (58%) | **7/12 (58%)** — unchanged |
| Conditional accuracy — value-verified | n/a | 9/12 (75%) | **9/12 (75%)** — unchanged |
| Median latency | 2,763 ms | 3,608 ms | **2,828 ms** |
| Latency range | 1,810–7,197 ms | 2,262–9,195 ms | 1,598–10,012 ms |

Diffing per-question status between the two hardening passes: **24 of 25
questions have an identical status** (same `ok`/`needs_clarification`/
`failed`, same generated SQL where applicable). Exactly one changed: the
truncation-crash question (below). Completion and conditional accuracy are
therefore flat between passes — the three fixes did not move the aggregate
numbers, only the shape of one failure and the internals of two answers
discussed below.

### Did the truncation-failure question complete?

**No — it still does not reach `status: ok`, but the crash is fixed.**
*"Compare the average student result for the symbols 'اتجاه هجوم العدو' and
'(دفاع على عجل) قواتنا'."* went from `failed` (`error: "the model endpoint
could not classify the question"`, reproduced twice in the first pass) to
`needs_clarification` — the classify node now completes normally and asks a
legitimate schema-grounded clarifying question instead of erroring out. Fix
#3 worked as intended: the failure genuinely was `max_tokens` truncation at
this catalog scale, not something specific to Arabic symbol names. This is
the one status change across all 25 questions.

### Did the two previously-wrong answers come back right?

**No — neither is now correct, though one changed in character.**

- **"What are the 5 most common symbols by usage count, and how often does
  each appear?"** — **unchanged, still wrong.** Generated SQL is still
  `SELECT symbol_code, COUNT(*) ... FROM maps_state_student_solution_details
  GROUP BY symbol_code ORDER BY ... LIMIT 5` (values up to 544,676); golden
  needs the precomputed `omda_symbol_count` table by `symbol_name` (values
  up to 3,116). Fix #1 (prefer base tables over near-duplicate derived
  views) did not help here, and arguably explains *why* it didn't: this is
  a case where the *golden* answer actually depends on a precomputed/derived
  table (`omda_symbol_count`), so a preference for base tables pulls the
  model further from the right answer, not closer. This is the sharpest
  finding of this pass: table-preference heuristics that are correct for
  the near-duplicate-raw-table problem (`..._backup`, `..._old`, etc.) can
  be wrong for questions whose ground truth genuinely lives in a derived
  table.
- **"Which map states have no ideal solution recorded yet?"** — **still
  wrong, but the wrongness changed shape.** The generated SQL (final step)
  is unchanged and correct: `SELECT maps_state_id FROM maps_states WHERE
  maps_state_id NOT IN (SELECT maps_state_id FROM
  maps_states_ideal_solution)` returns the exact same 8 IDs as golden
  (`12, 3, 11, 402, 77, 500, 301, 303`). In the first pass, fix #2's absence
  meant the model saw that correct result and then told the user "it is
  impossible to determine" anyway — a false refusal on top of correct data.
  With fix #2 in place, the refusal is gone, but the model's answer-
  synthesis step now does its own (wrong) set arithmetic over the raw
  `step_1`/`step_2` intermediate dumps instead of reading `step_3`'s
  already-correct result: the NL answer lists IDs `4, 40, 306, 304, 43, 202,
  308, 15, 6, 302, 17` — none of which match the correct final list. **This
  is arguably worse for a user than the first pass's behavior**: a
  confidently wrong, specific list of IDs is more likely to be trusted and
  acted on than an explicit "cannot determine." Forbidding the refusal
  phrase removed the symptom without fixing the underlying bug, which is
  that answer synthesis doesn't reliably ground itself in the *last* (most
  complete/correct) step's result when earlier steps' raw rows are also in
  context.

### Any new wrong answers introduced by base-table preference?

**None found.** Every question that was strict-correct or value-verified-
correct in the first hardening pass is still correct in this pass, and no
previously-correct answer flipped to wrong — confirmed by the full
per-question status/SQL diff (24/25 identical, only the truncation question
changed, and it changed from `failed` to `needs_clarification`, not into or
out of a wrong answer). Fix #1's base-table preference is not visibly
harmful on this sample, but the "5 most common symbols" case above shows it
is not a strict improvement either — it's neutral-to-negative for questions
where the derived table *is* the ground truth, and this golden set doesn't
happen to contain a case where a near-duplicate raw table was previously
chosen wrongly instead of the correct base table, so fix #1's intended
upside isn't visible in this sample either. That absence of visible upside
or harm is itself worth noting for the controller: this fix's effect isn't
measurable on the current golden set in either direction.

### One incidental positive: repair now sometimes succeeds

*"What are the 10 most frequently used symbol codes in student
solutions?"* used 1 repair attempt this pass (0 in the first pass) and
still reached `status: ok` with a strict-correct answer — the first
observed case across both hardening passes of the repair loop firing and
*not* exhausting all 3 attempts before either succeeding or failing. Not
attributable to any of the three named fixes and not something to read much
into on n=1, but worth flagging as the first evidence the repair loop can
recover mid-budget rather than only ever succeeding on the first try or
exhausting.

### Bottom line for the second iteration

The three fixes did what they were narrowly built to do — the classify
truncation crash is gone, and the explicit "cannot determine" refusal
phrase is gone — but neither of the two wrong-answer cases flagged in the
first hardening pass is fixed, and completion/conditional accuracy are
unchanged in aggregate. The "no ideal solution" case is a genuine example
of a symptom-level fix (forbid the refusal phrase) uncovering the real bug
underneath (answer synthesis not grounding in the correct step's result),
which is now the concrete next thing to fix rather than declaring this
resolved. The "5 most common symbols" case suggests fix #1's table-
preference heuristic needs a "unless the derived table's description marks
it as the canonical precomputed source" exception, not just a blanket
prefer-base-tables rule.

## All-layers pass, round 4 (2026-08-26)

Task T13: seed the new Layer-3 semantics (`is_canonical`, `enum_labels`,
glossary — T1–T4 of this branch) onto the live `maps` source via APIs, then
re-run the same 25-question golden measurement a fourth time. **Seeding
succeeded and is durable. The first measurement attempt hit a live
connection-pool corruption bug in T5's query-run telemetry and was aborted
with 1/25 usable data points (incident narrative preserved below). Once
T5 was fixed (commit `8260b2f`) and the backend restarted clean, round 4
was re-run and completed 25/25 with no HTTP errors — those real results
follow the incident section.** Full detail:
`.superpowers/sdd/2026-08-26-all-layers-pass/task-T13-report.md`.

### Seeding manifest (confirmed durable via direct `psql`, independent of
### the later HTTP corruption)

- **Canonical flags**: `omda_symbol_count` (id 63, required — the
  precomputed table golden Q20's "5 most common symbols" needs) and
  `get_all_analysis_symbols` (id 66, judgment call — its description
  matches golden Q8/Q16's "average class result per symbol" shape;
  `avg_class_result` column existence verified before use). Surveyed all
  82 catalog objects; no other clearly-curated `omda_*`-style aggregate
  exists.
- **Metadata sync** (run 24): `status: ok`, ~8m18s, 320 `enum_labels`
  drafted across 1354 columns (spot-checked via `GET .../review` and via
  `psql SELECT count(*) FROM source_columns WHERE enum_labels IS NOT
  NULL` → 320).
- **Glossary** (3 terms): "symbol usage count" →
  `omda_symbol_count.count`; "average class result by symbol" →
  `get_all_analysis_symbols.avg_class_result`; and an Arabic term pairing
  the with-hamza spelling used in golden Q16's SQL literal
  (`إتجاه هجوم العدو`) with the without-hamza spelling used in golden
  Q16's question text (`اتجاه هجوم العدو`) — a real synonym gap found by
  reading the golden set, not a synthetic example.

### Why the four-way table (v1 → h1 → h2 → round 4) does not appear here

It cannot be honestly produced. Question 1 completed cleanly (`status:
ok`, correct-looking shape, 2978 ms) but from question 2 onward,
conversation and agent-run writes started silently failing to commit —
`POST /agent/conversations` returned `200 {"id": ...}` but the row was
**not durably persisted**, and by roughly question 21 even unrelated
writes (`POST .../glossary`) started returning bare `500`s. Diagnosis
(via `docker logs` + read-only `psql` against the app's own database, no
code changes, no restart):

- `backend/app/services/agent/executor.py` calls
  `log_query_run_sync(...)` (T5's telemetry, `backend/app/services/
  query_log.py`) fire-and-forget after every agent SQL execution, from a
  worker thread. That function calls `asyncio.run()`, creating a **new
  event loop per call**, which then uses the single shared, loop-bound
  `engine` from `core/database.py`.
- Logs show the exact defect signature on the *first* agent SQL execution
  of this run: `RuntimeError: ... got Future ... attached to a different
  loop` — an asyncpg connection touched from two event loops.
- `pg_stat_activity` confirmed the mechanism directly: poisoned
  connections sat `idle in transaction`, last statement `RELEASE
  SAVEPOINT` / `ROLLBACK TO SAVEPOINT __asyncpg_savepoint_...` — i.e. a
  later request's work gets nested as a savepoint inside a zombie's
  still-open outer transaction; `commit()` succeeds locally (`RELEASE
  SAVEPOINT`, 200 OK to the client) but the outer transaction never
  commits, so the row is invisible everywhere else. `conversations_id_seq`
  had reached 129 while `max(id)` in the table was 106 — 23 consumed
  sequence values from inserts that never landed.
- `idle_in_transaction_session_timeout` is `0` (confirmed via `SHOW`) —
  nothing reaps the zombies, so the corruption is permanent for the
  process's lifetime and compounds with every further agent SQL
  execution.
- **This is new in this branch.** T5 landed after the v1/h1/h2 baselines
  above were measured (commit range `8989089..7640a83`); round 4 is the
  first `maps`-live run to exercise T5's DirectQuery telemetry path at
  all, and it corrupted the pool on the very first real SQL execution.
  Not caused by this task's seeding, and not caused by the concurrent,
  read-only full-suite Docker run that was running alongside — the
  zombie connections are exclusively the app's own.
- A restart does not fix this: the corruption reproduces from the first
  agent SQL execution of any subsequent run. `pg_terminate_backend()` on
  the zombie sessions (a non-destructive, non-restart remediation) was
  attempted and refused by the harness's permission gate as a destructive
  action, and was not worked around. The real fix — giving
  `log_query_run_sync` its own non-shared connection, or bridging back
  onto the main loop instead of spinning a private one — is a code
  change, out of scope for a measurement-only task.

The coordinator fixed T5 (`log_query_run_sync` now uses a dedicated lazy
sync engine — psycopg2, NullPool, pre_ping, no asyncio anywhere in the
module — commit `8260b2f`, test-proven), restarted the backend clean, and
this task's second attempt is what follows.

### Real round-4 results (second attempt, clean run, 25/25 answered)

Same method as rounds 1–3 (fresh conversation per question, sequential
HTTP, `evals.run_eval.evaluate()` execution-equality against the live
source, plus hand value-verification on every multi-step completion, the
h1/h2 precedent). All scratch work was kept out of the repo (container
`/tmp` and host temp dir) while asks were in flight, per the coordinator's
instruction to avoid `--reload` churn.

#### Four-way headline

| Metric | v1 baseline | Hardening pass 1 | Hardening pass 2 | Round 4 (all-layers, real run) |
|---|---|---|---|---|
| Completion (status: ok) | 4/25 (16%) | 12/25 (48%) | 12/25 (48%) | 12/25 (48%) — unchanged |
| Clarification stops | 18/25 (72%) | 7/25 (28%) | 8/25 (32%) | 11/25 (44%) — up |
| Failed | 3/25 (12%) | 6/25 (24%) | 5/25 (20%) | 2/25 (8%) — down |
| Repair-loop engagement | 3/25 (12%), 0 succeeded | 5/25 (20%), 0 succeeded | 6/25 (24%), 1 succeeded | 4/25 (16%), 2 succeeded within budget |
| Conditional accuracy — strict | 4/4 (100%) | 7/12 (58%) | 7/12 (58%) | 3/12 (25%) — sharp drop |
| Conditional accuracy — value-verified | n/a | 9/12 (75%) | 9/12 (75%) | 3/12 (25%) — no capture-artifact cases found; strict = value-verified |
| Overall accuracy (correct/25) | 4/25 (16%) | 7/25 (28%) | 7/25 (28%) | 3/25 (12%) |
| Median per-ask latency | 2,763 ms | 3,608 ms | 2,828 ms | 2,886 ms |
| Latency range | 1,810–7,197 ms | 2,262–9,195 ms | 1,598–10,012 ms | 1,687–6,853 ms |

Value-verification detail: the two `compare` completions that decompose
into a 2-step DAG were hand-checked by executing both steps directly.
Both are genuinely wrong at the row level (not a last-step-capture
artifact like h1/h2's cases) — the institute-code compare's two steps
both return `23` (golden: `16` and `10`); the by-institute-name compare's
SQL for both steps uses a degenerate join (`ON i.institute_code = 6 WHERE
i.institute_code = 6`, ignoring the other institute entirely). The "no
ideal solution" completion (also 2 steps) was likewise hand-checked:
neither step queries `maps_states_ideal_solution` at all, so there is no
correct step being missed by strict scoring — it is wrong outright.

#### The headline finding: systemic table-selection drift, not a small-N blip

Diffing round 4's per-question status and generated SQL against round 3's
saved results shows 6 status changes (roughly a wash, matching flat
completion). But among questions that stayed `status: ok` in both rounds,
the generated SQL changed on **8 of 10**, and the new SQL is wrong on
nearly all of them — consistently substituting a different, incorrect
table for the correct one. Examples: "How many student solutions...total?"
went from `... FROM maps_state_student_solution` (correct) to `... FROM
cycle_students` (wrong — a roster/lookup table); "How many map
states...total?" went from `... FROM maps_states` (correct) to `SELECT
COUNT(*) FROM maps_state_sift_cache` (wrong — an internal cache table);
"10 most frequently used symbol codes" went from a correct
`GROUP BY symbol_code` aggregation to a nonsensical `UNION ALL` listing
of table and column *names* instead of any real data; "no ideal solution
recorded" went from the exactly-right `NOT IN (SELECT maps_state_id FROM
maps_states_ideal_solution)` to a query that never touches the
ideal-solution table at all. Only 2 of 10 stayed on the same, correct SQL.
This is the proximate cause of the strict/value-verified accuracy drop
from 58%/75% to 25%.

**This correlates in time with the Layer-3 seeding this task just applied
(2 new `is_canonical` flags, 320 new `enum_labels`, 3 new glossary terms,
all newly present in the agent's context for the first time this round)
but causation is not established** — the same underlying LLM call is also
subject to ordinary sampling variance across runs, and no controlled
ablation (same questions, seeding on vs. off, same day) was run to isolate
the effect. Reported as the honest, measured correlation it is, not a
proven causal claim.

#### Headline questions — answered

- **Did "5 most common symbols" flip to correct?** No. Generated SQL is
  `SELECT symbol_code, COUNT(*) as usage_count FROM
  maps_state_student_solution_details GROUP BY symbol_code ORDER BY
  usage_count DESC LIMIT 5` — still the raw-table aggregation (values up
  to 544,676), not a query against the now-canonical `omda_symbol_count`
  table the glossary term explicitly maps this exact phrasing to (golden:
  `symbol_name`/`count` from `omda_symbol_count`, max value 3,116). The
  canonical flag and glossary term are confirmed present in the catalog
  but the generate node did not pick them up for this question — a real
  negative result for the seeding's intended effect here.
- **Did overall completion/clarification move?** Completion is flat
  (48% → 48%). Clarification rose from 32% (round 3) to 44% (round 4) —
  3 more clarifying stops — while failures fell from 20% to 8% (3 fewer
  repair-exhaustion failures). Net: the same 12 questions complete, but
  more of the other 13 now end in a clarifying question rather than a
  failure — a modest positive shift in that balance, separate from the
  accuracy story above.
- **New wrong answers?** Yes, substantial — see the table-drift finding
  above. At least 6 previously-correct-or-reasonable questions now
  generate wrong SQL against a different table, one produces outright
  nonsensical SQL, and both completed `compare` questions are wrong
  (confirmed via value-verification). This is the sharpest accuracy
  regression across all rounds measured so far on this golden set.

Both remaining `failed` runs fail for the same reason as every prior
round: an inferred-only relationship (`cycle_students.institute_code =
institute_codes.institute_code`) that the executor correctly refuses to
execute on after 3 repair attempts — F4 working as intended, not a
regression. Two questions this round recovered mid-budget after 1–2
repairs and reached `status: ok` — the second and third observed cases of
the repair loop succeeding rather than only exhausting or succeeding
first-try.

#### Bottom line

Seeding is live and durable but did not visibly help on this sample, and
conditional accuracy regressed sharply (58%/75% → 25%) driven by a broad
table-selection drift affecting most previously-correct questions. Whether
this is caused by the new Layer-3 context or is sampling noise is not
established from a single run — recommend a repeat round-4 run (same
seeded catalog) to check reproducibility before treating the seeding as
net harmful, and if it reproduces, inspect whether the new
is_canonical/enum_labels/glossary context is crowding out the correct
base-table signal in the generate prompt. The T5 telemetry fix held up
cleanly through the full 25-question run — that incident is resolved.

## All-layers pass, round 5 (2026-08-26) — after the render fix

The controller fixed the table-selection drift round 4 surfaced:
`render()` is now two-pass (every catalog object name always present,
canonical objects prioritized ahead of tables ahead of views, labels
capped, budget 24,000 — commit `bc398e5`, backend restarted, smoke-tested).
This task re-ran the full 25-question golden set a fifth time, same
method as every prior round (fresh conversation per question, sequential
HTTP, `evals.run_eval.evaluate()` execution-equality plus hand
value-verification on every near-miss). Full detail:
`.superpowers/sdd/2026-08-26-all-layers-pass/task-T13-report.md`.

### Five-way headline

| Metric | v1 | Hardening 1 | Hardening 2 | Round 4 (real) | Round 5 (after render fix) |
|---|---|---|---|---|---|
| Completion (status: ok) | 4/25 (16%) | 12/25 (48%) | 12/25 (48%) | 12/25 (48%) | **22/25 (88%)** |
| Clarification stops | 18/25 (72%) | 7/25 (28%) | 8/25 (32%) | 11/25 (44%) | **0/25 (0%)** |
| Failed | 3/25 (12%) | 6/25 (24%) | 5/25 (20%) | 2/25 (8%) | **3/25 (12%)** |
| Repair-loop engagement | 3/25 (12%), 0 succeeded | 5/25 (20%), 0 succeeded | 6/25 (24%), 1 succeeded | 4/25 (16%), 2 succeeded | **5/25 (20%), 2 succeeded within budget** |
| Conditional accuracy — strict | 4/4 (100%) | 7/12 (58%) | 7/12 (58%) | 3/12 (25%) | **9/22 (41%)** |
| Conditional accuracy — value-verified | n/a | 9/12 (75%) | 9/12 (75%) | 3/12 (25%) | **15/22 (68%)** |
| Overall accuracy — strict / value-verified | 16% | 28% | 28% | 12% | **36% / 60%** |
| Median per-ask latency | 2,763 ms | 3,608 ms | 2,828 ms | 2,886 ms | **6,661 ms** |
| Latency range | 1,810–7,197 ms | 2,262–9,195 ms | 1,598–10,012 ms | 1,687–6,853 ms | **4,152–18,359 ms** |

Clarification dropped to zero for the first time across all 5 rounds —
every question now either completes or fails outright. Latency roughly
doubled (median 2,886 ms → 6,661 ms); plausible cost of the two-pass
render's larger context budget, not independently isolated.

Value-verification (6 hand-checked cases folded into the value-verified
count, same standard as h1/h2's multi-step capture-artifact method): 3
`compare` questions decompose into 2-step DAGs where each step is
individually correct and the NL answer states both numbers right (strict
scoring only captures the last step); 2 `aggregate` questions are correct
in substance but fail strict row-equality on rounding only (golden rounds
to 2 decimals, generated returns the unrounded float — same value); 1
`explain` question ("5 most common symbols") matches golden's columns'
values exactly plus one extra, harmless column. Every other near-miss was
checked and confirmed genuinely wrong, not a scoring artifact.

### Did conditional accuracy recover toward the 75% benchmark?

Substantially — from round 4's 25%/25% to round 5's 41% strict / 68%
value-verified — but it has not fully reached 75%. The remaining gap
is 3 completions confirmed genuinely wrong by hand (not artifacts): a
wrong-table answer, a NULL-value grounding bug, and a wrong-table
undercounting bug that is also a regression from round 4 (see below).

### Did "5 most common symbols" flip back to correct?

**Yes, in substance.** Generated SQL now reads `omda_symbol_count`
(the canonical table) with `symbol_name`/`count` values matching golden
exactly (3116, 2553, 2433, 2033, 1337), and the NL answer states the
correct names and counts. It scores "wrong" only because of one extra,
harmless `symbol_code` column breaking strict row-tuple equality — a
scoring technicality, not a wrong answer reaching the user. **This
corrects the controller's smoke-test note** that the symbols question
"still counts the raw details table" — that description matches a
*different* golden question ("10 most frequently used symbol codes"),
not this one.

That different question is where a new problem appeared: its golden SQL
deliberately reads *raw* `symbol_code` counts (max 544,676) from
`maps_state_student_solution_details`, but round 5's generated SQL now
pulls from `omda_symbol_count` instead — the render fix's stronger
canonical-table signal, over-generalized to a superficially similar
question it doesn't apply to. Same class of finding as round 4's
table-preference risk, now cutting in the opposite direction
(over-applying the canonical preference rather than under-applying it).

### Flips: round-4 wrong answers now correct

- "How many student solutions...total?" — `cycle_students` →
  `maps_state_student_solution`.
- "How many map states...total?" — `maps_state_sift_cache` →
  `maps_states`.
- "How many distinct students...?" — `cycle_students` →
  `maps_state_student_solution`.
- Both completed `compare` questions from round 4 (institute 2-vs-6
  states; institute 2-vs-6 by name) — value-verified correct.

Several more previously-`needs_clarification` questions (active symbols,
average-active-symbols, defense-vs-attack compare, and others) moved
straight to correct completions — new answers, not flips from wrong.

### New wrong answers / regressions

- **"10 most frequently used symbol codes"** — over-generalized
  canonical-table preference (above).
- **"5 map states, most submissions"** — completes now (was `failed` in
  round 4) but answers "each receiving None submissions": synthesis
  grounds in a step reading a NULL column instead of the correctly-computed
  earlier step (which has the exact right numbers). Same class of
  "wrong-step grounding" bug as h1/h2's "no ideal solution" case.
- **"No ideal solution recorded"** — still wrong, and the **false-refusal
  bug is back** with different wording ("impossible to identify" instead
  of the h2-forbidden "cannot determine") despite `step_1` correctly
  computing the needed join — suggesting the h2 fix was wording-specific,
  not structural.
- **"5 students, most symbols placed" — a genuine regression.** Correct
  in round 4; round 5's SQL switched from
  `maps_state_student_solution_details` to `maps_state_student_solution`
  (missing `_details`), undercounting by roughly two orders of magnitude.
- **Two new failures** (previously `needs_clarification`, i.e. the agent
  asked rather than attempted): an inferred-relationship refusal after
  repair exhaustion on "average student result by state level" (legitimate
  F4 policy, newly reached because more joins are attempted now), and a
  genuine SQL bug on the Arabic symbol-comparison question (repair
  attempts reference a nonexistent column).

### Bottom line

The render fix delivered a large, real win — clarification eliminated,
completion nearly doubled to 88%, and value-verified accuracy recovered
from 25% to 68%, closing most but not all of the gap to the 75%
benchmark. Two structural issues remain unresolved across multiple
rounds now: (1) the answer-synthesis grounding bug (doesn't reliably read
the correct/last step's result) recurred in a new question this round,
and (2) canonical-table preference can still misfire in either direction
depending on the specific question's phrasing. A genuine round-4→round-5
regression on one previously-correct question is a reminder that
sample-to-sample LLM variance persists even with the catalog and seeding
held fixed — round-over-round improvement should not be assumed
monotonic without re-checking previously-correct questions each time.

## Golden-set hygiene note (2026-08-26, post round 5)

Rounds 4-5 exposed an internal inconsistency in the golden set itself: the
question "10 most frequently used symbol codes" expected RAW placement counts
(`maps_state_student_solution_details`, max 544,676) while "5 most common
symbols by usage count" expected the CURATED `omda_symbol_count` (max 3,116).
No agent behaviour can satisfy both readings of the same phrase. Resolution:
the unqualified business phrase ("usage count", glossary-mapped) now belongs to
the curated table alone; the raw-count question was rephrased to say
explicitly that it counts raw placement records, and the per-student
placements question was likewise made explicit. Golden SQLs unchanged — only
the questions were disambiguated. Comparisons of per-question results across
rounds for these three questions should account for the rephrasing.


## All-layers pass, round 6 (2026-08-26) — after the targeted-fix series

Six targeted fixes landed on master since round 5 (backend restarted,
smoke-verified before this run): golden-set disambiguation (Q8/Q21/Q24
rephrased — see the hygiene note above), parent-facts truncation honesty
(never-enumerate rule), all-NULL column exclusion from render skeletons,
short descriptions added to skeleton lines, three relationships
human-confirmed via `POST /data-sources/2/review/confirm` (targeting the
Q11/Q25 inferred-relationship refusal edges), refused-join graceful
degradation, a ranking+measure one-query planner rule, and classify
running on the compact render (~20-30% latency reduction). This task
re-ran the full 25-question golden set a sixth time, same method as every
prior round, with the golden set reloaded fresh from
`/app/evals/golden/maps.jsonl` inside the container (not a cached copy)
since three questions were rephrased. Full detail:
`.superpowers/sdd/2026-08-26-all-layers-pass/task-T13-report.md`.

### Six-way headline

| Metric | v1 | H1 | H2 | R4 (real) | R5 | R6 (this run) |
|---|---|---|---|---|---|---|
| Completion (status: ok) | 4/25 (16%) | 12/25 (48%) | 12/25 (48%) | 12/25 (48%) | 22/25 (88%) | **22/25 (88%)** |
| Clarification stops | 18/25 (72%) | 7/25 (28%) | 8/25 (32%) | 11/25 (44%) | 0/25 (0%) | **2/25 (8%)** |
| Failed | 3/25 (12%) | 6/25 (24%) | 5/25 (20%) | 2/25 (8%) | 3/25 (12%) | **1/25 (4%)** |
| Repair-loop engagement | 3/25, 0 succeeded | 5/25, 0 succeeded | 6/25, 1 succeeded | 4/25, 2 succeeded | 5/25, 2 succeeded | **3/25 (12%), 2 reached ok / 1 exhausted** |
| Conditional accuracy — strict | 4/4 (100%) | 7/12 (58%) | 7/12 (58%) | 3/12 (25%) | 9/22 (41%) | **12/22 (55%)** |
| Conditional accuracy — value-verified | n/a | 9/12 (75%) | 9/12 (75%) | 3/12 (25%) | 15/22 (68%) | **17/22 (77%) — above the 75% benchmark** |
| Overall accuracy — strict / value-verified | 16% | 28% | 28% | 12% | 36% / 60% | **48% / 68%** |
| Median per-ask latency | 2,763 ms | 3,608 ms | 2,828 ms | 2,886 ms | 6,661 ms | **5,313 ms (~20% down from R5)** |
| Latency range | 1,810–7,197 ms | 2,262–9,195 ms | 1,598–10,012 ms | 1,687–6,853 ms | 4,152–18,359 ms | **2,130–15,535 ms** |

Value-verification folded in 5 hand-checked cases this round: 3 `compare`
questions (same multi-step capture-artifact pattern as every prior round
— each step individually correct, strict scoring only captures the last);
1 rounding-only mismatch ("average class result for each symbol"); and 1
label-column mismatch ("solutions per institute" — generated groups by
`institute_name` instead of golden's `institute_code`, but all 5
institute/count pairs match exactly when cross-referenced). Not folded
in: "5 map states, most submissions" — exact right numbers, missing
golden's `maps_state_name` column, the same "right-numbers-missing-label"
case kept out of the count in earlier rounds for consistency.

### Flips: did the expected round-5 failures come back?

The coordinator expected Q11, Q22, Q23, Q24, Q25 to flip. Checked
individually via direct step-by-step SQL verification:

- **Q23 "no ideal solution recorded" — full flip.** Textbook `LEFT JOIN
  ... WHERE ... IS NULL`, matches golden exactly. The false-refusal bug
  (present under different wording in h1's fix, round 4, and round 5) did
  not recur.
- **Q24 "5 students, most symbols placed" — full flip**, and the round-5
  regression (wrong table, missing `_details`) is fixed. The golden
  rephrase for this question and the fix landed together.
- **Q22 "5 map states, most submissions" — partial flip.** Round 5's
  NULL-value grounding bug is gone and the numbers are now exactly right;
  still missing the `maps_state_name` label, so not counted as fully
  correct, but a clear, confirmed improvement.
- **Q25 "distinct students per institute" — partial flip, not full
  recovery.** No longer refuses — the `cycle_students.institute_code ->
  institute_codes.institute_code` relationship is now one of the 3
  human-confirmed edges (verified via `psql` against
  `source_relationships`) — but the resulting counts are wrong (e.g.
  594 generated vs golden's 152 for one institute), an apparent
  over-count rather than a refusal.
- **Q11 "average student result by state level code" — did not flip,
  still fails.** Root cause confirmed via `psql`: the 3 human-confirmed
  edges are `cycle_students.institute_code -> institute_codes`,
  `maps_state_student_solution_details.maps_state_id -> maps_states`, and
  `v_student_solution_correction.maps_state_id -> maps_states` — the last
  is exactly the join round 5 needed for this question. But round 6's
  plan instead picked a *different*, still-unconfirmed table
  (`get_all_analysis.maps_state_id = maps_states.maps_state_id`). The
  confirmation didn't help here because the generate node's table choice
  changed underneath it, not because relationship coverage was
  insufficient.

### Regression

**"How many student solution detail records are confirmed?"** — correct
in rounds 4 and 5 (`WHERE confirmed = true`, 94 rows). Round 6 dropped the
filter entirely (`SELECT COUNT(*) FROM
maps_state_student_solution_details`, returning 904,266 — a ~9,600x
overcount). No apparent connection to any of the six named fixes;
ordinary sample-to-sample variance on a previously-simple, previously-
reliable question.

### Remaining failures/wrong answers, one line each

- **Q11** (failed) — inferred-relationship refusal on a different,
  still-unconfirmed join than the one that was fixed.
- **Q13, Q20** (needs_clarification; were completed-but-wrong in round 5)
  — legitimate schema-grounded ambiguity; asking now instead of
  confidently answering wrong reads as a net improvement.
- **Q17** (completed, wrong) — the Arabic hamza-spelling glossary term
  still isn't visibly applied (wrong spelling used in one step, wrong
  table in the other) — unchanged across rounds 4, 5, and 6 since the
  term was created.
- **Q10** (completed, wrong) — see regression above.
- **Q25** (completed, wrong) — see partial-flip note above.

### Bottom line

Value-verified conditional accuracy reached 77%, above the 75% h1/h2
benchmark, for the first time across all 6 rounds — a genuine recovery
driven by real fixes (Q23 and Q24 both fully resolved, Q22 substantially
improved). But the fix set was not a clean sweep: Q11 still fails because
the planner picked a different join than the one that was confirmed, Q25
stopped refusing but still overcounts, Q17's glossary term shows no
measurable effect after three full rounds, and one previously-reliable
question (Q10) regressed for reasons unconnected to any of the six
targeted fixes. The pattern holds from every prior round: aggregate
metrics can improve substantially while individual questions still move
in both directions underneath the average.
