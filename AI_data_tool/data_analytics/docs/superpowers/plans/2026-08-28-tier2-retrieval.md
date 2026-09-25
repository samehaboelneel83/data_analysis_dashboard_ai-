# Tier 2 Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Question-aware retrieval (R.1–R.5) + entities table, per the spec.

**Spec:** `docs/superpowers/specs/2026-08-28-tier2-retrieval-design.md` — the binding authority; read it in full before any task.

## Global Constraints

- models.py / main.py / config.py are BOM utf-8-sig — preserve.
- New schema: alembic revision (chained on current head, **revision id ≤ 32 chars** — VARCHAR(32) pin test enforces) AND `_migrate`/create_all belt-and-braces.
- Startup/ask-path failures degrade, never brick (spec's Error handling section).
- Docker pytest from PowerShell ONLY: `docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <paths> -q --no-header -p no:warnings`
- TDD; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- `render(question=None)` must stay byte-identical to today (existing snapshot-ish tests must not change).
- The H7 breadth guarantee (every object NAME present at any sane budget) is inviolable.
- No new heavy deps: numpy only for the scorer. No sentence-transformers, no pgvector this pass.

### Task R1: Retrieval scorer + pluggable embedder (spec §1)

**Files:** Create `backend/app/services/retrieval.py`, `backend/tests/test_retrieval.py`. Modify `backend/app/core/config.py` (embedding_base_url/model/dim, all optional-None), models.py (+`retrieval_embeddings` per spec §1B) + alembic revision + `_migrate`.
Build documents from SchemaContext-shaped inputs (pure function of ObjectInfo/glossary/query-example rows). TF-IDF word + char 3–5-gram vectors, cosine, per-source memo keyed on catalog fingerprint. Backend B: POST `{base}/embeddings` OpenAI shape, cache rows by text_hash, query-time fallback to A on any error (log once per process). Public API exactly: `rank_objects(context, question, k)`, `rank_documents(docs, question, k)`.
**Tests:** exact-name match ranks first; Arabic question token ranks the Arabic-described object first (use real Arabic strings); enum-label token match boosts (spec §4 boost lives here as a scorer feature over documents that include label text); fingerprint memo invalidates when catalog changes; Backend B fallback on connection error; deterministic ordering.

### Task R2: Wire retrieval into the agent context (spec §2–§4)

**Files:** Modify `backend/app/services/agent/context.py` (`_ordered_objects` gains optional ranking; `render(question=...)` uses it; 1-hop join promotion after top-3), `backend/app/services/agent/memory.py` (recall ranked by `rank_documents` over stored examples — verify current recall mechanics first and keep its write side untouched), graph call sites if the question isn't already passed (grep `render(` in agent/graph.py). Tests: extend `backend/tests/test_agent_context.py` + `test_agent_memory*` (grep exact name).
**Tests:** with a question, top-ranked object is enriched first and unranked objects keep old relative order; `render(question=None)` byte-identical (assert equality against pre-change output captured in the test); H7 breadth holds under tiny budget with ranking active; 1-hop neighbor of a top-3 object enriched before unranked rest; memory recall similarity-beats-recency pinned scenario.

### Task R3: Entities table + sync draft + review + render (spec §5)

**Files:** models.py (+`Entity` per spec field list) + alembic revision + `_migrate`; `backend/app/services/metadata/catalog_sync.py` (new draft stage mirroring the enum-labels LLM pattern — same complete_json, same failure isolation, confirmed rows survive resync); router: extend the existing metadata review/admin router (grep where enum labels / descriptions are confirmed) with entity list/confirm/edit endpoints (org-scoped); `agent/context.py`: budget-reserved "Entities:" block (reservation rule identical to glossary block) + entities as retrieval documents (feed into R1's documents); frontend: entities section on the existing source review surface (list, edit business_name/grain/description, confirm) — follow the enum-labels review UI pattern.
**Tests:** draft→rows with source='inferred'; confirm flips provenance; confirmed survives resync; render reserves entities block without evicting object names; org scoping 404; frontend section renders + confirm calls API (vitest).

### Task R4: Measurement + docs (spec §7)

Controller-run (not a subagent): full suites, then `.\run_eval_gate.ps1 -SourceId 2 -ValueVerified` live gate; compare vs baseline (88% completion / 77% conditional / 17/25). Regression blocks merge pending diagnosis. Then update the four stale Tier-1 gap-doc rows + Layer 3 retrieval rows honestly (what shipped: lexical retrieval + entities; what remains: real embeddings endpoint, pgvector) and rebuild the HTML.

**Batching:** B1: R1 · B2: R2 · B3: R3 · B4: R4 (controller) · final review + merge.
