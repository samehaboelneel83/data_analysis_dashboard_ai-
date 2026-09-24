# Embeddings Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Stand up a self-hosted embeddings service inside the compose network (air-gap compliant — weights baked into the image at build time), wire retrieval Backend B to it by default, and wake the dormant `retrieval_embeddings` persistence seam so vectors survive restarts.

**Spec decisions (settled here, not implementer guesses):**
- **Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** — prefix-free (no E5 "query:/passage:" asymmetry that the OpenAI-compatible contract can't express), 384-dim, genuine Arabic coverage (the golden set and UI are partly Arabic). Use the community ONNX export (`Xenova/paraphrase-multilingual-MiniLM-L12-v2` on HF carries `onnx/model.onnx` + tokenizer files) or convert at build — whichever the implementer verifies actually loads; the quantized int8 variant is acceptable IF a quick cosine-sanity check against fp32 shows rank-order stability on a 10-pair fixture (else fp32).
- **Runtime: ONNX Runtime + `tokenizers` — NO torch, NO sentence-transformers** anywhere in the image (a torch layer is ~2GB of dead weight). Mean-pooling + L2-normalize implemented in numpy per the model card.
- **Compose default: ENABLED.** `EMBEDDING_BASE_URL` points at the service in compose; the circuit breaker + lexical fallback (R1) already make a dead endpoint harmless, so shipping it on is safe and is the point of building it. `embedding_dim: 384` in settings/compose.
- **Host-disk discipline (binding):** C: is nearly full; Docker's vhdx has ~28GB internal headroom. ALL model downloads happen inside the Dockerfile (`RUN` layer) — NEVER to host HuggingFace caches, host temp, or the scratchpad. Build context lives on D:.

## Global Constraints

- BOM utf-8-sig on models.py/main.py/config.py — preserve. No schema changes expected (retrieval_embeddings exists since 0004); if any appear: alembic revision chained on 0008, id ≤32.
- `_request_embeddings` in `services/retrieval.py` is the CLIENT CONTRACT — read it first and build the server to match what it actually sends/expects (request/response field names), not the OpenAI docs.
- Docker pytest from PowerShell ONLY; foreground runs; rebuild test image only if backend requirements change (E2 shouldn't need new deps — the redis/requests stack already covers HTTP? No: Backend B uses httpx, already present).
- TDD; deterministic; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- **Pre-committed honesty:** this closes the Layer-3 infra gap; expected retrieval parity on the small live catalog, headroom for larger ones. No eval-gate run; acceptance = the targeted smokes in E2.

### Task M1: The embedding service container

**Files:** new `embedding_server/` (Dockerfile, `server.py`, `requirements.txt` — its OWN requirements: fastapi, uvicorn, onnxruntime, tokenizers, numpy, huggingface-hub for the build-time download only), `docker-compose.yml` (+`embeddings` service: build context `./embedding_server`, compose-network only — NO host ports, healthcheck hitting a `/health` route, mem_limit sane ~1g), `scripts/build_offline_bundle.ps1` picks the image up automatically (verify its regex catches a `build:`-only service the way it does for backend/frontend — extend if needed).

- Dockerfile: `RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('Xenova/paraphrase-multilingual-MiniLM-L12-v2', allow_patterns=[...])"` into a fixed in-image path (download at BUILD; runtime never touches the network); pin every dep.
- `server.py`: POST `/v1/embeddings` accepting the exact shape `_request_embeddings` sends (batch input list), returning the shape it parses; tokenize (max_length 256, truncation), ONNX session (intra-op threads capped), mean-pool over attention mask, L2-normalize, 384 floats each. `/health` returns model name + dim. Reject >256 inputs per call with 413 (client batches — check what batch size retrieval sends and support it).
- Tests: a container-level smoke script (run in the built image: embed ["hello", Arabic string, "hello"] → dims 384, first==third vector, Arabic ≠ english, all L2-norm ≈1); the int8-vs-fp32 rank-stability check if int8 chosen (document the choice + result in the Dockerfile comment); server unit tests runnable in the image (pytest in its requirements-dev or a plain script — keep it simple, this container is 200 lines).

### Task M2: Wire Backend B + persistence + smokes

**Files:** `docker-compose.yml` backend env (`EMBEDDING_BASE_URL: http://embeddings:8000/v1`, `EMBEDDING_MODEL`, `EMBEDDING_DIM: 384` — match the actual settings names in config.py; grep), `backend/app/services/retrieval.py` (wake the seam: read-through persistence of vectors in `retrieval_embeddings` keyed by text_hash+model — on rank, batch-load cached rows, embed only misses via Backend B, write misses back fire-and-forget; in-process LRU stays in front; lexical fallback unchanged), tests.

- The persistence needs a DB session where `rank_objects`/`rank_documents` have none (pinned no-db signatures) — solve WITHOUT breaking the signatures: a module-level sync engine helper like `query_log._get_engine` (the established fire-and-forget pattern) for both read and write, wrapped so any DB failure degrades to embed-everything (never blocks ranking). Document the pattern choice.
- Tests (fakeredis-style, using a fake embeddings HTTP server or monkeypatched `_request_embeddings` + real SQLite for the persistence): restart simulation — first rank embeds+persists, new process (cleared in-process cache) ranks again → ZERO embed calls (all hashes hit); model-tag mismatch re-embeds; DB failure degrades gracefully; dim-mismatch guard (server says 384, settings disagree → log + lexical fallback, never garbage cosine).
- **Live smokes (controller-verifiable, print results):** with the stack up — (a) Arabic query discrimination: two Arabic-described objects, Backend B ON ranks the right one first (and print the lexical-only ranking beside it); (b) kill the embeddings container → ranking still serves (lexical, circuit opens) within one request; (c) restart backend → retrieval_embeddings row count stable, no re-embed burst (log evidence). Ship these as a script `backend/scripts/smoke_embeddings.py` runnable via docker exec.

**Batching:** B1: M1 · B2: M2 · final review + live deploy (compose up with the new service) + doc re-score.
