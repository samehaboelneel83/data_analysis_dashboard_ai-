# Agent Hardening & Accuracy Pass

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Close the deferred findings from the Layer 4 final review and raise the agent's end-to-end completion rate, measured before/after on the existing 25-question maps golden set.

**Baseline (measured 2026-08-26):** 16% end-to-end (4/25), 100% conditional accuracy, **72% clarification stops (18/25)**, 3 repair exhaustions (2 were the since-fixed V2 alias bug), median 2.8s.

**Spec:** `docs/superpowers/specs/2026-08-25-layer-4-agent-orchestration-design.md` — D4.3 (ask, don't guess) stays binding: the fix for over-clarification is better discrimination, never guessing.

## Global Constraints

Same as the Layer 4 plan: Docker tests via PowerShell (`docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <args> -q --no-header -p no:warnings`); focused tests per task, full suite at the end; BOM files (`models.py`, `main.py`, `config.py`) = utf-8-sig; additive; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. Baseline suites: **1902 backend + 715 frontend green**.

---

### Task H1: V2 CTE scoping — close the parked blind spot

**File:** `backend/app/services/agent/validate.py` + `tests/test_agent_validate.py`
The current fix treats CTE presence as a GLOBAL pass for unqualified columns: `WITH t2 AS (SELECT city FROM customers) SELECT bogus_col FROM orders, t2` passes V2. Fix: permit an unqualified column via the CTE pass-through ONLY when a CTE is actually referenced in the same SELECT's FROM as the column, and the column is not resolvable against the real tables present. Tests: the exact bypass above now fails V2 naming `bogus_col`; the legitimate CTE cases from the previous round still pass; alias/HAVING cases still pass.

### Task H2: Dataset-executor watchdog

**File:** `backend/app/services/agent/executor.py` + `tests/test_agent_executor.py`
`_run_datasets` has no deadline (DuckDB has no timeout pragma). Add one: a `threading.Timer(settings.agent_statement_timeout_s, conn.interrupt)` armed before execute, cancelled in `finally`. An interrupted query returns the normal `(None, error)` tuple. Test: a deliberately slow query (large cross join of two registered frames) with the timeout monkeypatched to ~1s returns an error tuple within a bounded time, never hangs.

### Task H3: `object_row_policies` management API

**Files:** extend `backend/app/routers/agent.py` (or a small `policies.py` router) + `tests/test_agent_api.py`
The security-critical flow is currently configurable only by SQL. Admin-gated (`require_org_admin`, matching `routers/metadata.py`), org-scoped 404s: `GET /agent/row-policies?source_id=` (list, joined with object+role names), `POST /agent/row-policies` `{source_object_id, role_id, predicate}` (validate: predicate parses as a sqlglot Condition, else 422 — reuse policy.py's parse), `DELETE /agent/row-policies/{id}`. Tests: CRUD round-trip; non-admin 403 (per require_org_admin's real behaviour); cross-org 404; unparseable predicate 422.

### Task H4: Dead code + conversation resume

**Files:** `backend/app/services/llm.py` (delete `llm_gate_state` — unused, untested), `frontend/src/services/api.ts` (fix `listConversations` types: `data_source_id: number | null`, add `dataset_ids: number[] | null` — match the backend), `frontend/src/components/chat/ChatPane.tsx` (+test): on mount, list conversations and resume the most recent one matching this pane's target instead of always creating anew; if none, keep lazy-create. Frontend tests local (`npx vitest run`), full frontend suite green.
NOTE: the backend list endpoint must return `dataset_ids` — add it to the router's response if absent.

### Task H5: Clarification discrimination (the accuracy lever)

**Files:** `backend/app/services/agent/nodes/classify.py` (+`tests/test_agent_classify.py`)
72% of real questions stopped for clarification; the golden questions were authored to be answerable, so most stops are FALSE ambiguity. D4.3 stays: never guess — but discriminate better:
- The system prompt currently biases "when in doubt, prefer ambiguous=true". Rebalance: ambiguous=true ONLY when two materially different queries both fit AND the schema context (descriptions, semantic types, join graph) cannot break the tie; explicitly instruct that near-duplicate table names alone are not ambiguity when descriptions distinguish them, and that the most specific matching table wins.
- Pass MORE context: raise classify's render budget (4000 chars is starving an 82-object catalog — use the full render like generate does) and include table descriptions (already in render()).
- Add few-shot examples of NON-ambiguous questions over near-duplicate schemas (the maps failure mode).
Tests: existing contract tests unchanged; add prompt-content tests (the rebalanced instruction present; render not truncated below the generate budget).

### Task H6: Re-measure (controller-style, like Task 15)

Restart backend, run all 25 golden questions end-to-end again, `evaluate()`, and append "## Hardening pass results (2026-08-26)" to the spec appendix with before/after: completion, conditional accuracy, clarification rate, repair engagement, latency. Honest numbers whatever they are. Commit. Also run the FULL backend suite once (final gate).

## Self-Review
H1 closes the parked final-review residual; H2/H3/H4 close the accepted-deferred list except eval-CI (no CI infra exists — still out) and load_file caching (defer until it measurably hurts); H5+H6 target the measured bottleneck with the measurement to prove it. Nothing speculative added.
