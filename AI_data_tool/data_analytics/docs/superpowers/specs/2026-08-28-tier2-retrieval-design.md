# Tier 2 — Retrieval & Semantic Layer Design

**Goal:** close the gap the measurements proved is capping agent accuracy (77% conditional, residual errors are semantics/selection problems): question-aware retrieval over the catalog, entities with grain, and graph-expanded context — ARCHITECTURE.md Layer 3's R.1–R.5, sized to this codebase.

## Probed facts this design stands on

- The vLLM endpoint (qwen3.5, 10.125.18.189:8000/v1) serves `/v1/models` but **404s `/v1/embeddings`** — no embedding service exists today.
- Live Postgres is stock `postgres:16-alpine` — **no pgvector extension**; tests run SQLite. Switching the DB image is out of scope this pass (ledger-worthy deliberate cut; the retrieval interface below is built so pgvector can slot in later without rework).
- `agent/context.py` renders ALL objects two-pass: pass 1 guarantees every object NAME at any budget (H7 fix, measured 25%→75% recovery); pass 2 enriches in static priority order (canonical → tables → views). Glossary/joins blocks reserve budget first.

## Decisions

1. **Retrieval scorer, pluggable embedder.** New `services/retrieval.py`:
   - A *document* per retrievable thing: source objects (name + description + column names + enum label gloss), glossary terms, query examples. Built from the already-loaded `SchemaContext`/DB rows — no new sync stage required for v1; documents derive deterministically from catalog state.
   - **Backend A (default, works today): lexical TF-IDF** over word tokens + character 3–5-grams (char n-grams carry Arabic and code-ish names like `st_cd`), pure numpy (already a dep), corpus built per source and memoized keyed on a catalog fingerprint (max updated_at + counts). Cosine similarity.
   - **Backend B (opt-in): OpenAI-compatible embeddings endpoint** via `settings.embedding_base_url` / `embedding_model` / `embedding_dim` (all optional; unset = Backend A). Vectors cached in a new `retrieval_embeddings` table (kind, ref, text_hash, vector JSON, model). If the endpoint errors at query time, fall back to Backend A and log once — retrieval must never take the agent down.
   - One public function: `rank_objects(context, question, k) -> list[(name, score)]` plus `rank_documents(...)` for glossary/examples. Deterministic given equal state.
2. **Where retrieval plugs in (R.1–R.3): the render's priority order, not its breadth.** The H7 guarantee (every name present) survives untouched. `SchemaContext.render(question=...)` orders pass-2 enrichment by *relevance* when a question is given: retrieval-ranked objects first (canonical status breaks ties), then the rest in today's order. `_ordered_objects` gains an optional ranking argument; `render(question=None)` behaves byte-identically to today.
3. **Graph expansion (R.4):** after top-k ranking, any object one confirmed/declared join-hop from a top-3 object gets promoted into the enriched tier (right after the top-k, before unranked rest) — the "orders question pulls order_lines in" behavior the architecture names. Uses the existing `joins` whitelist only.
4. **Enum injection (R.5):** already rendered per-object; relevance ordering now makes retrieved objects' enum labels the ones that survive the budget. Additionally, when a question token (case-folded) matches an enum LABEL, that object gets a rank boost — labels are how humans ask ("cancelled orders" → `st_cd=3`).
5. **Entities with grain (E2).** New `entities` table: id, org_id, source_id, name (unique per source), business_name, grain (one row per …), description, primary_object (FK-ish by name to SourceObject), `source` provenance inferred|confirmed, timestamps. Drafted by the sync LLM pass (same complete_json pattern as enum labels; one prompt per sync listing objects → proposed entities), confirmed/edited in the existing metadata review UI surface (new tab/section). Rendered as a budget-reserved "Entities:" block in `SchemaContext.render` (same reservation rule as glossary: may never push an object name out of pass 1) and included as retrieval documents. Confirmed entities survive resync (same ladder discipline as enum labels).
6. **Query-example retrieval upgrade:** `agent/memory.py` `recall` currently matches how? (implementer verifies) — it gains retrieval ranking via the same scorer so few-shot examples are chosen by similarity, not recency alone.
7. **Measurement is the acceptance test (E5).** Before merge: run the eval gate (`run_eval_gate.ps1 -SourceId 2 -ValueVerified`) and compare to the round-6 baseline (completion 88%, conditional value-verified 77%, 17/25 end-to-end). Regression on either headline number blocks merge pending diagnosis. Improvement is hoped for, not promised — retrieval mostly buys headroom on larger catalogs; the honest claim goes in the gap doc.

## Non-goals (ledgered)

pgvector/DB image change; a separate embedding sync stage; NetworkX; entity-level RLS; UI beyond the review surface additions; Spider/BIRD.

## Error handling

Retrieval failures (scorer exception, endpoint down) degrade to today's static ordering — never a 500, never a blocked ask. Entity draft failures leave entities absent (sync stage marked failed like other stages, run continues).

## Testing

Unit: scorer ranks exact-name and Arabic-token matches top; fingerprint memo invalidates on catalog change; endpoint backend falls back on error. Render: question ordering respects ranking + H7 breadth guarantee intact (byte-identical when question=None); graph expansion promotes 1-hop neighbors; entities block reserved. Entities: draft→confirm ladder, resync survival. Memory: similarity recall beats recency in a pinned scenario. Live: E5 gate run.
