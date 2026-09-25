"""Tier 2 retrieval scorer (spec §1, Task R1).

Ranks the catalog's retrievable things (source objects today; glossary terms
and query examples via `rank_documents` once R2/R3 supply them) against a
question, so `SchemaContext.render` can put the most relevant objects where
the H7 two-pass render's enrichment budget actually reaches them (Task R2).

Two interchangeable backends behind one scorer:

  Backend A (default, always available) -- lexical TF-IDF over word tokens
  PLUS character 3-5-grams, pure numpy. Char n-grams are what make this work
  on Arabic text and code-ish identifiers (`st_cd`) that word-tokenization
  alone handles poorly. Cosine similarity against an L2-normalized TF-IDF
  matrix, built once per catalog state and memoized (see `_CATALOG_MEMO`).

  Backend B (opt-in) -- an OpenAI-compatible embeddings endpoint
  (`settings.embedding_base_url`/`embedding_model`/`embedding_dim`). Any
  failure at query time (unreachable box, bad response shape, timeout) falls
  back to Backend A and logs once per process -- retrieval degrading must
  never take the agent's ask-path down (spec's Error handling section).

Public API is exactly `rank_objects(context, question, k)` and
`rank_documents(docs, question, k)` -- Task R2 wires these into
`SchemaContext.render` verbatim, and Task R3 pushes entity documents through
`rank_documents`. BOTH are designed to never raise: any internal failure
(scorer bug, corrupt state, backend timeout) is caught, logged, and degrades
to a static/empty result rather than propagating to the render path.

NOTE on `RetrievalEmbedding` (models.py, Task M2): the public API still
takes no `db` argument -- R2 calls `rank_objects` from the currently-sync
`SchemaContext.render`, and the signatures are pinned. Persistence is wired
without one: a module-level sync engine (`_get_persist_engine`, mirroring
`services.query_log._get_engine`'s established fire-and-forget pattern --
its own `create_engine`/`NullPool`, never the app's shared async engine)
read-through-caches vectors by (text_hash, model) and writes misses back,
fire-and-forget, after every embed. ANY failure on that engine (down db,
missing table, bad url) is caught and degrades to "embed everything as if
the cache were empty" -- persistence is an optimization on top of the
in-process LRU (`_EMBED_CACHE`, still checked first and always populated),
never something ranking can be blocked by.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ..core.config import settings
from .query_log import _sync_database_url

if TYPE_CHECKING:
    from .agent.context import SchemaContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    """One retrievable thing: an id the caller can map back to whatever it
    represents (an object name, a glossary term, an entity id, ...), and the
    text it is scored against. `label_text` is optional extra text that
    earns the enum-label boost (spec §4: a question token matching an enum
    LABEL boosts that document) without being diluted into the main TF-IDF
    bag at the same weight as everything else."""
    id: str
    text: str
    label_text: str = ""


#: spec §4: "cancelled orders" -> st_cd=3. A question token that casefold-
#: matches a whole word of an object's enum label gloss gets this added to
#: its cosine score. Kept well under 1.0 (the max possible cosine) so it can
#: tip a close race without letting one label word alone outrank an object
#: that is a much better lexical match on everything else.
ENUM_LABEL_BOOST = 0.25

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_CHAR_NGRAM_SIZES = (3, 4, 5)


def _word_tokens(text: str) -> list[str]:
    return [t.casefold() for t in _WORD_RE.findall(text or "")]


def _char_ngrams(text: str) -> list[str]:
    norm = re.sub(r"\s+", " ", (text or "").strip().casefold())
    if not norm:
        return []
    grams: list[str] = []
    for n in _CHAR_NGRAM_SIZES:
        if len(norm) < n:
            continue
        grams.extend(norm[i:i + n] for i in range(len(norm) - n + 1))
    return grams


def _features(text: str) -> Counter:
    counts: Counter = Counter()
    for tok in _word_tokens(text):
        counts[("w", tok)] += 1
    for gram in _char_ngrams(text):
        counts[("c", gram)] += 1
    return counts


@dataclass
class _Corpus:
    vocab: dict[tuple[str, str], int]
    idf: np.ndarray
    matrix: np.ndarray          # (n_docs, n_features), L2-normalized rows
    ids: list[str]
    label_words: list[set[str]]  # per-doc set of casefolded label words


def _build_corpus(documents: list[Document]) -> _Corpus:
    doc_features = [_features(d.text) for d in documents]
    df: Counter = Counter()
    for feats in doc_features:
        for key in feats:
            df[key] += 1
    vocab = {key: i for i, key in enumerate(df)}
    n_docs = len(documents)
    n_feats = len(vocab)

    idf = np.zeros(n_feats, dtype=np.float64)
    for key, i in vocab.items():
        idf[i] = math.log((1 + n_docs) / (1 + df[key])) + 1.0

    matrix = np.zeros((n_docs, n_feats), dtype=np.float64)
    for row, feats in enumerate(doc_features):
        for key, cnt in feats.items():
            idx = vocab.get(key)
            if idx is not None:
                matrix[row, idx] = cnt * idf[idx]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    label_words = [set(_word_tokens(d.label_text)) for d in documents]
    return _Corpus(vocab=vocab, idf=idf, matrix=matrix,
                   ids=[d.id for d in documents], label_words=label_words)


def _vectorize_query(query: str, corpus: _Corpus) -> np.ndarray:
    feats = _features(query)
    vec = np.zeros(len(corpus.vocab), dtype=np.float64)
    for key, cnt in feats.items():
        idx = corpus.vocab.get(key)
        if idx is not None:
            vec[idx] = cnt * corpus.idf[idx]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def _lexical_scores(documents: list[Document], question: str) -> dict[str, float]:
    return _lexical_scores_from_corpus(_build_corpus(documents), question)


def _lexical_scores_from_corpus(corpus: "_Corpus", question: str) -> dict[str, float]:
    if not corpus.ids:
        return {}
    query_vec = _vectorize_query(question, corpus)
    if corpus.matrix.shape[1] == 0 or not np.any(query_vec):
        cosine = np.zeros(len(corpus.ids))
    else:
        cosine = corpus.matrix @ query_vec

    q_tokens = set(_word_tokens(question))
    scores: dict[str, float] = {}
    for i, doc_id in enumerate(corpus.ids):
        score = float(cosine[i])
        if q_tokens & corpus.label_words[i]:
            score += ENUM_LABEL_BOOST
        scores[doc_id] = score
    return scores


# ---------------------------------------------------------------------------
# Backend B: OpenAI-compatible embeddings endpoint, opt-in, query-time
# fallback to Backend A on any error.
# ---------------------------------------------------------------------------

#: Logged once per process (not once per call) so a down endpoint does not
#: spam the log on every single question -- the failure mode is durable
#: (the box stays down) so one log line establishes it.
_EMBED_ERROR_LOGGED = False

#: In-process cache for embedded text: (text_hash, model) -> vector. See the
#: module docstring's note on `RetrievalEmbedding` for why this is memory-
#: only in this pass rather than backed by that table. An OrderedDict so it
#: can be LRU-bounded below -- same "attacker/scale-influenced key set needs
#: a cap" shape as config.py's rate_limit_bucket_cap.
_EMBED_CACHE: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()

#: Distinct (text_hash, model) entries kept before the least-recently-used
#: one is evicted. A long-lived worker process re-embedding many distinct
#: questions/documents over its lifetime must not grow this dict without
#: bound -- bounded, it just means an old text gets re-embedded on next use
#: rather than the process leaking memory.
_EMBED_CACHE_MAX = 5000


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


#: Circuit breaker for Backend B (spec's "retrieval degrading must never
#: take the agent's ask-path down", sharpened for the sync-call-in-an-async-
#: handler case: `_request_embeddings` is a blocking `httpx.post` reached
#: from render/rank paths that may be running inside the event loop, so a
#: dead endpoint must not get re-dialed -- and re-blocked-on -- for every
#: question). `None` means "no failure recorded yet, attempt freely."
#: monotonic (not wall-clock) so a system clock step never fools the
#: cooldown into expiring early or never.
_EMBED_CIRCUIT_OPENED_AT: float | None = None

#: How long Backend B is skipped after a failure before one retry is
#: allowed. 5 minutes: long enough that a durably-dead box (the common
#: case -- see `_EMBED_ERROR_LOGGED`'s docstring) isn't re-dialed on every
#: ask, short enough that a box that comes back is noticed within a
#: session rather than requiring a process restart.
_EMBED_CIRCUIT_COOLDOWN_SECONDS = 300.0

#: Timeout for the one blocking HTTP call this module makes. Kept low
#: (versus a more generous default) because the circuit breaker above means
#: at most one ask per cooldown window ever pays this -- every other ask
#: within the window is a cache/dict lookup, never a socket. The tradeoff:
#: that one first-ask-after-cooldown can still block the event loop for up
#: to this long (the call is synchronous `httpx.post`, made from render's
#: sync call stack -- see the module docstring's note on why it isn't
#: farmed out to a thread).
_EMBED_REQUEST_TIMEOUT_SECONDS = 3.0


#: Verified-once-per-process latches for the server-vs-settings dim guard
#: (spec: "server /health dim vs settings dim mismatch -> log once + lexical
#: fallback, never garbage cosine"). `_EMBED_DIM_VERIFIED` means "checked and
#: matched, stop checking"; `_EMBED_DIM_MISMATCH` means "checked and did NOT
#: match, permanently refuse Backend B this process" -- same durable-failure
#: shape as `_EMBED_ERROR_LOGGED` above (a dim mismatch is a config error,
#: not a transient blip, so there is no cooldown/retry for it).
_EMBED_DIM_VERIFIED = False
_EMBED_DIM_MISMATCH = False


def _reset_embedding_process_state() -> None:
    """Test/helper hook: clears the once-per-process error-log latch, the
    circuit breaker, the dim-guard latches, and the in-process embedding
    cache. Exists so tests reset this module's process-global state through
    one named call rather than reaching into private globals directly --
    keeps tests from order-coupling on whichever test happened to run
    first."""
    global _EMBED_ERROR_LOGGED, _EMBED_CIRCUIT_OPENED_AT
    global _EMBED_DIM_VERIFIED, _EMBED_DIM_MISMATCH
    _EMBED_ERROR_LOGGED = False
    _EMBED_CIRCUIT_OPENED_AT = None
    _EMBED_DIM_VERIFIED = False
    _EMBED_DIM_MISMATCH = False
    _EMBED_CACHE.clear()


# ---------------------------------------------------------------------------
# Persistence (Task M2): read-through/write-back cache for `retrieval_
# embeddings`, fronted by the in-process LRU above. `rank_objects`/
# `rank_documents` are pinned to take no `db` argument, so this owns its own
# module-level sync engine -- exactly the pattern `services.query_log.
# _get_engine` established for "a fire-and-forget DB write reachable from a
# sync call stack that may already be inside an event loop": a dedicated
# `create_engine` (never the app's shared async engine/`AsyncSessionLocal`),
# `NullPool` so no connection is held or reused across calls, and every
# public function here catches its own failures rather than raising --
# ranking must degrade to "embed everything" on ANY db problem, never block
# or crash on one.
# ---------------------------------------------------------------------------

_PERSIST_ENGINE = None
_persist_engine_lock = threading.Lock()


def _get_persist_engine():
    global _PERSIST_ENGINE
    if _PERSIST_ENGINE is None:
        with _persist_engine_lock:
            if _PERSIST_ENGINE is None:
                from sqlalchemy import create_engine
                from sqlalchemy.pool import NullPool

                url = _sync_database_url(settings.database_url)
                _PERSIST_ENGINE = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
    return _PERSIST_ENGINE


def _reset_persist_engine() -> None:
    """Test/helper hook: dispose and drop the cached engine so a
    monkeypatched `settings.database_url` takes effect on the next call, and
    so a test can simulate "new worker process" for restart-persistence
    scenarios without actually spawning one."""
    global _PERSIST_ENGINE
    if _PERSIST_ENGINE is not None:
        _PERSIST_ENGINE.dispose()
    _PERSIST_ENGINE = None


def _load_persisted_vectors(hashes: list[str], model: str) -> dict[str, list[float]]:
    """Batch read-through: `{text_hash: vector}` for whichever of `hashes`
    already have a row for `model`. ANY failure (down db, missing table,
    bad url, ...) returns `{}` -- an empty read-through result means every
    caller falls through to "embed it," which is exactly correct behavior
    when the cache can't be consulted."""
    if not hashes:
        return {}
    try:
        from ..models.models import RetrievalEmbedding

        table = RetrievalEmbedding.__table__
        engine = _get_persist_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                table.select()
                .with_only_columns(table.c.text_hash, table.c.vector)
                .where(table.c.model == model, table.c.text_hash.in_(hashes))
            ).fetchall()
        return {row.text_hash: row.vector for row in rows}
    except Exception:
        logger.warning(
            "retrieval: embedding cache read failed, embedding as if the "
            "cache were empty", exc_info=True)
        return {}


def _persist_vectors(rows: list[dict]) -> None:
    """Write-back, fire-and-forget: each row is its own connect/insert/
    commit/close (mirrors `query_log`'s per-call NullPool discipline) so one
    bad row (e.g. a race against another worker that persisted the same
    (text_hash, model) first -- the table's unique constraint) can't abort
    the rest of the batch, and any failure here never propagates to the
    ranking call that triggered it."""
    if not rows:
        return
    try:
        from ..models.models import RetrievalEmbedding

        table = RetrievalEmbedding.__table__
        engine = _get_persist_engine()
        with engine.connect() as conn:
            for row in rows:
                try:
                    with conn.begin():
                        conn.execute(table.insert().values(**row))
                except Exception:
                    # Most likely a unique-constraint race against a
                    # concurrent request that persisted this exact
                    # (text_hash, model) first -- not a problem, just a
                    # wasted embed we already paid for; keep going.
                    continue
    except Exception:
        logger.warning("retrieval: embedding cache write failed", exc_info=True)


def _verify_embedding_dim_or_block() -> bool:
    """True if Backend B must NOT be used because its `/health` dim doesn't
    match `settings.embedding_dim` -- checked once per process (latched in
    `_EMBED_DIM_VERIFIED`/`_EMBED_DIM_MISMATCH`) since a mismatch is a
    static config error, not a transient one. A health-check request that
    itself fails (network, bad JSON, ...) is NOT treated as a mismatch --
    that's a different failure mode already owned by `_request_embeddings`
    and the circuit breaker, so this returns "not blocked" and lets the
    real embed call surface it."""
    global _EMBED_DIM_VERIFIED, _EMBED_DIM_MISMATCH
    if _EMBED_DIM_MISMATCH:
        return True
    if _EMBED_DIM_VERIFIED or not settings.embedding_dim:
        return False
    try:
        import httpx

        base = settings.embedding_base_url.rstrip("/")
        # `embedding_base_url` is the `/v1` embeddings prefix (compose:
        # `http://embeddings:8000/v1`); `/health` lives one level up at the
        # service root, per embedding_server/server.py.
        health_base = base[:-len("/v1")] if base.endswith("/v1") else base
        resp = httpx.get(f"{health_base}/health", timeout=_EMBED_REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        server_dim = resp.json().get("dim")
    except Exception:
        return False
    if server_dim != settings.embedding_dim:
        logger.error(
            "retrieval: embeddings server reports dim=%r but "
            "settings.embedding_dim=%r -- disabling Backend B for this "
            "process (falling back to lexical scoring) rather than "
            "scoring cosine similarity on mismatched vectors",
            server_dim, settings.embedding_dim)
        _EMBED_DIM_MISMATCH = True
        return True
    _EMBED_DIM_VERIFIED = True
    return False


def _embed_backend_configured() -> bool:
    return bool(settings.embedding_base_url and settings.embedding_model)


def _circuit_open() -> bool:
    """True while Backend B is being skipped after a recent failure."""
    if _EMBED_CIRCUIT_OPENED_AT is None:
        return False
    return (time.monotonic() - _EMBED_CIRCUIT_OPENED_AT) < _EMBED_CIRCUIT_COOLDOWN_SECONDS


def _open_circuit() -> None:
    global _EMBED_CIRCUIT_OPENED_AT
    _EMBED_CIRCUIT_OPENED_AT = time.monotonic()


def _request_embeddings(texts: list[str]) -> list[list[float]]:
    """One batched POST to `{embedding_base_url}/embeddings`, OpenAI shape.
    Raises on any failure -- callers are responsible for catching and
    falling back; this function never degrades on its own.

    Blocking (`httpx.post`, not an async client): the callers that reach
    this are sync functions deep in the render call stack, too deep to
    hand an event loop off to `asyncio.to_thread` without a broader
    refactor. `_try_embedding_backend`'s circuit breaker is what keeps this
    tolerable -- see its docstring and `_EMBED_REQUEST_TIMEOUT_SECONDS`."""
    import httpx

    base = settings.embedding_base_url.rstrip("/")
    resp = httpx.post(
        f"{base}/embeddings",
        json={"model": settings.embedding_model, "input": texts},
        timeout=_EMBED_REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = sorted(payload["data"], key=lambda row: row["index"])
    vectors = [row["embedding"] for row in data]
    if len(vectors) != len(texts):
        raise ValueError(
            f"embeddings endpoint returned {len(vectors)} vectors for "
            f"{len(texts)} inputs")
    return vectors


#: The server's per-call cap (embedding_server/server.py `MAX_BATCH_SIZE`,
#: itself the plan's "reject >256 inputs per call with 413"). `_embed_many`
#: chunks at this size so a large catalog never trips that 413 -- a chunk
#: failure raises out of `_request_embeddings_chunked` same as any other
#: `_request_embeddings` failure, which `_try_embedding_backend` catches and
#: turns into a whole-rank fallback to lexical scoring; there is no path
#: where some chunks succeed and the caller gets a partially-embedded
#: (mixed embedding/zero-vector) ranking.
_EMBED_MAX_BATCH = 256


def _request_embeddings_chunked(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_MAX_BATCH):
        vectors.extend(_request_embeddings(texts[start:start + _EMBED_MAX_BATCH]))
    return vectors


def _embed_many(texts: list[str], *, kind: str = "text",
                refs: list[str] | None = None) -> list[list[float]]:
    """Vectors for `texts`, in order. Three tiers, cheapest first: the
    in-process LRU (`_EMBED_CACHE`), then a batch read-through of
    `retrieval_embeddings` for whatever the LRU didn't have, then Backend B
    (chunked at `_EMBED_MAX_BATCH`) for whatever neither had -- and every
    freshly-embedded text is written back to both. `kind`/`refs` are
    persistence metadata only (the `retrieval_embeddings.kind`/`ref`
    columns); `refs` defaults to a hash-derived placeholder for callers with
    no natural id (the query text itself has none)."""
    model = settings.embedding_model
    hashes = [_text_hash(t) for t in texts]
    refs = refs if refs is not None else [h[:16] for h in hashes]

    missing_after_lru = [i for i, h in enumerate(hashes)
                         if (h, model) not in _EMBED_CACHE]
    if missing_after_lru:
        db_hits = _load_persisted_vectors(
            [hashes[i] for i in missing_after_lru], model)
        still_missing = []
        for i in missing_after_lru:
            h = hashes[i]
            if h in db_hits:
                _EMBED_CACHE[(h, model)] = db_hits[h]
            else:
                still_missing.append(i)
        if still_missing:
            fresh = _request_embeddings_chunked([texts[i] for i in still_missing])
            for i, vec in zip(still_missing, fresh):
                _EMBED_CACHE[(hashes[i], model)] = vec
            _persist_vectors([
                {"kind": kind, "ref": refs[i], "text_hash": hashes[i],
                 "vector": vec, "model": model}
                for i, vec in zip(still_missing, fresh)
            ])
    results = []
    for h in hashes:
        key = (h, model)
        _EMBED_CACHE.move_to_end(key)  # mark recently used
        results.append(_EMBED_CACHE[key])
    while len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
        _EMBED_CACHE.popitem(last=False)  # evict least-recently-used
    return results


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def _embedding_scores(documents: list[Document], question: str) -> dict[str, float]:
    """Backend B. Raises on any failure -- see `_score_documents`, which is
    the only caller and the one place the fallback-to-A decision is made."""
    texts = [d.text for d in documents]
    doc_vectors = _embed_many(texts, kind="document", refs=[d.id for d in documents])
    # The query text has no natural `ref` -- `_embed_many` falls back to a
    # hash-derived one. Persisting it too (not just documents) is what lets
    # the restart-simulation smoke ("same question, new process -> zero
    # embed calls") actually hit zero rather than one (the query itself).
    [query_vector] = _embed_many([question], kind="query")

    q_tokens = set(_word_tokens(question))
    scores: dict[str, float] = {}
    for doc, vec in zip(documents, doc_vectors):
        score = _cosine(vec, query_vector)
        if q_tokens & set(_word_tokens(doc.label_text)):
            score += ENUM_LABEL_BOOST
        scores[doc.id] = score
    return scores


def _try_embedding_backend(documents: list[Document],
                           question: str) -> dict[str, float] | None:
    """Backend B if configured and it succeeds; None (never raises) to tell
    the caller to fall back to Backend A otherwise. The single place the
    once-per-process failure log fires, and the single place the circuit
    breaker is consulted/opened: while the circuit is open (a failure
    happened within the last `_EMBED_CIRCUIT_COOLDOWN_SECONDS`) this skips
    the attempt entirely -- no socket touched, no timeout paid -- so a dead
    endpoint costs the ask-path at most one blocking `_EMBED_REQUEST_TIMEOUT_
    SECONDS`-second call per cooldown window, not one per question."""
    global _EMBED_ERROR_LOGGED
    if not _embed_backend_configured():
        return None
    if _circuit_open():
        return None
    if _verify_embedding_dim_or_block():
        return None
    try:
        return _embedding_scores(documents, question)
    except Exception:
        _open_circuit()
        if not _EMBED_ERROR_LOGGED:
            logger.exception(
                "retrieval: embeddings backend failed, falling back to "
                "lexical scoring for the rest of this process")
            _EMBED_ERROR_LOGGED = True
        return None


def _score_documents(documents: list[Document], question: str) -> dict[str, float]:
    """The one place Backend A/B is chosen for a caller-supplied (non-
    memoized) document list -- used by `rank_documents`."""
    scores = _try_embedding_backend(documents, question)
    if scores is not None:
        return scores
    return _lexical_scores(documents, question)


def _top_k(scores: dict[str, float], k: int) -> list[tuple[str, float]]:
    # Zero (and negative) scores mean "no relevance signal at all" -- an
    # off-topic question against Backend A's cosine similarity, or a
    # document with no token overlap. Keeping them in the ranked tier would
    # let `_ordered_objects` (agent/context.py) treat "we found nothing"
    # the same as "we found a real match", demoting every unranked
    # canonical object below a list ordered by nothing more than dict/name
    # tie-break -- worse than the static priority order it would otherwise
    # fall back to. Filtering here, upstream of every caller, is what makes
    # that fallback (`ranking` empty -> `_ordered_objects` uses
    # `default_order`) actually trigger for a truly off-topic question.
    scored = [(doc_id, score) for doc_id, score in scores.items() if score > 0]
    # Deterministic: ties broken by id so equal-score results are stable
    # regardless of dict/insertion order.
    ordered = sorted(scored, key=lambda kv: (-kv[1], kv[0]))
    return ordered[:k]


def _rank(documents: list[Document], question: str, k: int) -> list[tuple[str, float]]:
    if not documents or not question or k <= 0:
        return []
    return _top_k(_score_documents(documents, question), k)


# ---------------------------------------------------------------------------
# Per-source memo for rank_objects: rebuilding the TF-IDF corpus is O(catalog
# size) and this is called once per render, so a catalog that hasn't changed
# should not pay that cost on every question.
# ---------------------------------------------------------------------------

#: source_id -> (fingerprint, documents, built _Corpus). Both the documents
#: (Backend B needs the raw text) and the built TF-IDF corpus (Backend A's
#: whole point of memoizing -- building it is the O(catalog size) cost) are
#: cached together, keyed on the same fingerprint, so an unchanged catalog
#: pays neither cost more than once regardless of how many questions are
#: asked against it in this process.
_CATALOG_MEMO: dict[int, tuple[str, list[Document], "_Corpus"]] = {}


def _object_document(info) -> Document:
    parts = [info.name]
    if info.description:
        parts.append(info.description)
    parts.extend(info.columns.keys())
    label_texts: list[str] = []
    for labels in info.enum_labels.values():
        label_texts.extend(labels.values())
    parts.extend(label_texts)
    return Document(id=info.name, text=" ".join(parts),
                    label_text=" ".join(label_texts))


def entity_document(entity) -> Document:
    """Task R3 (spec section 5): an entity as a retrieval `Document`, for
    `rank_documents` -- same shape as `_object_document` above, minus enum
    labels (entities have none). Takes anything with `.name`/`.business_name`
    /`.grain`/`.description` rather than importing `EntityInfo` directly:
    `agent.context` already imports FROM this module, and importing
    `EntityInfo` back would be a cycle."""
    parts = [entity.name]
    for attr in ("business_name", "grain", "description"):
        value = getattr(entity, attr, None)
        if value:
            parts.append(value)
    return Document(id=entity.name, text=" ".join(parts))


def _catalog_fingerprint(context: "SchemaContext") -> str:
    """A content hash of the objects that feed `rank_objects`'s documents --
    stands in for "max updated_at + counts" (the spec's phrasing) because
    ObjectInfo/SchemaContext are already-loaded in-memory state with no
    updated_at of their own; hashing the derived documents changes exactly
    when the documents would change, which is the property the memo needs.

    Note: `load_dataset_context` gives every dataset-mode context
    source_id=0, so alternating dataset combinations under that shared key
    will look like catalog churn and rebuild every time -- correct (the
    fingerprint differs), just not free; dataset mode has no larger catalog
    to make that cost matter today.
    """
    parts = []
    for name in sorted(context.objects):
        info = context.objects[name]
        parts.append(name)
        parts.append(info.description or "")
        parts.append(",".join(f"{c}:{t}" for c, t in sorted(info.columns.items())))
        for col in sorted(info.enum_labels):
            labels = info.enum_labels[col]
            parts.append(col + ":" + ",".join(
                f"{v}={l}" for v, l in sorted(labels.items())))
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()


def _catalog_state(context: "SchemaContext") -> tuple[list[Document], _Corpus]:
    fingerprint = _catalog_fingerprint(context)
    cached = _CATALOG_MEMO.get(context.source_id)
    if cached is not None and cached[0] == fingerprint:
        return cached[1], cached[2]
    documents = [_object_document(info) for info in context.objects.values()]
    corpus = _build_corpus(documents)
    _CATALOG_MEMO[context.source_id] = (fingerprint, documents, corpus)
    return documents, corpus


def rank_objects(context: "SchemaContext", question: str,
                 k: int) -> list[tuple[str, float]]:
    """Rank `context.objects` by relevance to `question`, most relevant
    first. Returns `[(object_name, score), ...]`, at most `k` entries.

    Never raises: any internal failure is caught, logged, and an empty list
    is returned -- callers (Task R2's `SchemaContext.render`) treat an empty
    result as "no ranking available" and fall back to today's static order,
    never a broken render.
    """
    try:
        if not question or k <= 0:
            return []
        documents, corpus = _catalog_state(context)
        if not documents:
            return []
        scores = _try_embedding_backend(documents, question)
        if scores is None:
            scores = _lexical_scores_from_corpus(corpus, question)
        return _top_k(scores, k)
    except Exception:
        logger.exception("rank_objects failed; degrading to no ranking")
        return []


def rank_documents(docs: list[Document], question: str,
                   k: int) -> list[tuple[str, float]]:
    """Rank an arbitrary caller-supplied document list (glossary terms,
    query examples, entities, ...) by relevance to `question`. Returns
    `[(document_id, score), ...]`, at most `k` entries. Same never-raise
    contract as `rank_objects`.
    """
    try:
        return _rank(list(docs), question, k)
    except Exception:
        logger.exception("rank_documents failed; degrading to no ranking")
        return []
