"""Tier 2 retrieval scorer (spec §1, Task R1).

`rank_objects`/`rank_documents` are pure functions of already-loaded
SchemaContext-shaped state -- no db session, no network required for Backend
A (the lexical default). These tests exercise Backend A directly, plus
Backend B's fallback-on-error path (never a real network call).
"""
import numpy as np
import pytest

from app.services.agent.context import ObjectInfo, SchemaContext
from app.services import retrieval
from app.services.retrieval import Document, rank_documents, rank_objects


@pytest.fixture(autouse=True)
def _reset_retrieval_process_state():
    """Backend B's fallback-log latch and embedding cache are process
    globals (spec: "log once per process"). Reset them around every test
    through the module's own helper so tests don't order-couple on which
    test happened to run first and flip `_EMBED_ERROR_LOGGED`."""
    retrieval._reset_embedding_process_state()
    yield
    retrieval._reset_embedding_process_state()


def _ctx(source_id: int = 1) -> SchemaContext:
    ctx = SchemaContext(source_id=source_id, family="postgresql")
    ctx.objects["orders"] = ObjectInfo(
        name="orders", kind="table",
        description="Customer purchase orders",
        columns={"id": "integer", "st_cd": "integer", "total": "numeric"},
        enum_labels={"st_cd": {"1": "new", "2": "paid", "3": "cancelled"}},
    )
    ctx.objects["customers"] = ObjectInfo(
        name="customers", kind="table",
        description="فروع العملاء وبياناتهم الأساسية",
        columns={"id": "integer", "city": "text"},
    )
    ctx.objects["invoices"] = ObjectInfo(
        name="invoices", kind="table",
        description="فواتير المبيعات الشهرية لكل فرع",
        columns={"id": "integer", "amount": "numeric"},
    )
    ctx.objects["v_sales"] = ObjectInfo(
        name="v_sales", kind="view",
        description="Sales rollup by month",
        columns={"month": "text", "amount": "numeric"},
    )
    return ctx


class TestRankObjectsExactName:
    def test_exact_name_match_ranks_first(self):
        ctx = _ctx()
        ranked = rank_objects(ctx, "show me the orders table", k=3)
        assert ranked[0][0] == "orders"


class TestRankObjectsArabic:
    def test_arabic_token_ranks_matching_arabic_object_first(self):
        """Two Arabic-described objects in the catalog (customers, invoices)
        -- a question must pick the one its tokens actually describe, not
        merely "the only Arabic object" (which a single-Arabic-doc fixture
        can't distinguish from a real match)."""
        ctx = _ctx()
        ranked_customers = rank_objects(ctx, "بيانات العملاء الأساسية", k=4)
        assert ranked_customers[0][0] == "customers"

        ranked_invoices = rank_objects(ctx, "فواتير المبيعات الشهرية", k=4)
        assert ranked_invoices[0][0] == "invoices"


class TestRankObjectsEnumBoost:
    def test_enum_label_token_boosts_matching_object(self):
        ctx = _ctx()
        # "cancelled" appears nowhere except as an enum label on orders.st_cd.
        ranked = rank_objects(ctx, "how many cancelled were there", k=3)
        assert ranked[0][0] == "orders"

    def test_boost_isolated_from_plain_lexical_match(self, monkeypatch):
        """The test above can pass on cosine similarity alone -- the label
        text is folded into the object's main TF-IDF bag too, so it would
        win even with ENUM_LABEL_BOOST=0. This isolates the boost itself:
        two documents with IDENTICAL main text (so their cosine similarity
        to the query is exactly tied at 0.0 -- "cancelled" appears in
        neither main bag) where only one carries the query token as its
        label_text. With the boost, that document scores 0.25 and is
        returned; without it (`ENUM_LABEL_BOOST=0.0`), BOTH documents tie
        at exactly 0.0 -- which the zero-score filter now drops entirely,
        so the unboosted call returns nothing at all. That contrast (one
        result vs. none) is what proves the boost, not term weighting, did
        the work; before zero-score filtering existed this was instead
        proven by an alphabetical id tie-break, which no longer applies
        since a 0.0 never reaches `_top_k`'s output."""
        docs = [
            Document(id="alpha_no_label", text="orders table purchase history"),
            Document(id="zulu_with_label", text="orders table purchase history",
                     label_text="cancelled"),
        ]
        boosted = rank_documents(docs, "cancelled", k=2)
        assert boosted[0][0] == "zulu_with_label"
        assert len(boosted) == 1  # alpha_no_label's 0.0 was filtered out

        monkeypatch.setattr(retrieval, "ENUM_LABEL_BOOST", 0.0)
        unboosted = rank_documents(docs, "cancelled", k=2)
        assert unboosted == []  # both tied at 0.0 -> filtered to nothing


class TestFingerprintMemo:
    def test_memo_invalidates_when_catalog_changes(self):
        ctx = _ctx()
        first = rank_objects(ctx, "orders", k=3)
        assert first[0][0] == "orders"

        # Mutate the catalog: rename the object so the old name no longer
        # scores at all -- if the memo were stale, this would still return
        # the old "orders" entry from a cached corpus/matrix.
        ctx.objects["orders_renamed"] = ctx.objects.pop("orders")
        ctx.objects["orders_renamed"].name = "orders_renamed"

        second = rank_objects(ctx, "orders_renamed", k=3)
        assert second[0][0] == "orders_renamed"

    def test_memo_reused_when_catalog_unchanged(self, monkeypatch):
        ctx = _ctx()
        rank_objects(ctx, "orders", k=3)
        calls = {"n": 0}
        real_build = retrieval._build_corpus

        def counting_build(*a, **kw):
            calls["n"] += 1
            return real_build(*a, **kw)

        monkeypatch.setattr(retrieval, "_build_corpus", counting_build)
        rank_objects(ctx, "orders", k=3)
        rank_objects(ctx, "customers", k=3)
        assert calls["n"] == 0  # same context object -> memo hit both times


class TestBackendBFallback:
    def test_connection_error_falls_back_to_lexical(self, monkeypatch):
        monkeypatch.setattr(retrieval.settings, "embedding_base_url",
                            "http://nonexistent.invalid:9")
        monkeypatch.setattr(retrieval.settings, "embedding_model", "test-embed")
        monkeypatch.setattr(retrieval.settings, "embedding_dim", 8)

        ctx = _ctx()
        # Must not raise, and must still return a sane lexical ranking.
        ranked = rank_objects(ctx, "show me the orders table", k=3)
        assert ranked[0][0] == "orders"


class TestEmbedCacheBounded:
    def test_cache_evicts_least_recently_used_beyond_cap(self, monkeypatch):
        monkeypatch.setattr(retrieval, "_EMBED_CACHE_MAX", 2)
        calls = {"n": 0}

        def fake_request(texts):
            calls["n"] += 1
            return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(retrieval, "_request_embeddings", fake_request)
        retrieval._embed_many(["one"])
        retrieval._embed_many(["two"])
        assert len(retrieval._EMBED_CACHE) == 2
        retrieval._embed_many(["three"])  # evicts "one" (least recently used)
        assert len(retrieval._EMBED_CACHE) == 2

        retrieval._embed_many(["one"])  # was evicted -> re-requested
        assert calls["n"] == 4  # one, two, three, one-again


class TestBackendBCircuitBreaker:
    """A dead Backend B must be dialed at most once per cooldown window, not
    once per question -- `_request_embeddings` is a blocking `httpx.post`
    reached from render's sync call stack, so every extra attempt is an
    extra `_EMBED_REQUEST_TIMEOUT_SECONDS`-second block on the event loop
    for a box that is, by definition of "we just failed", still down."""

    def _configure(self, monkeypatch):
        monkeypatch.setattr(retrieval.settings, "embedding_base_url",
                            "http://fake.invalid")
        monkeypatch.setattr(retrieval.settings, "embedding_model", "test-embed")
        monkeypatch.setattr(retrieval.settings, "embedding_dim", 8)

    def test_after_a_failure_the_endpoint_is_not_touched_again_within_cooldown(
            self, monkeypatch):
        self._configure(monkeypatch)
        calls = {"n": 0}

        def always_fails(texts):
            calls["n"] += 1
            raise ConnectionError("down")

        monkeypatch.setattr(retrieval, "_request_embeddings", always_fails)
        ctx = _ctx()

        rank_objects(ctx, "show me the orders table", k=3)
        assert calls["n"] == 1  # first attempt pays the real cost

        for _ in range(5):
            rank_objects(ctx, "show me the orders table", k=3)
        assert calls["n"] == 1  # circuit open -- no further attempts

    def test_after_cooldown_expiry_one_retry_happens(self, monkeypatch):
        self._configure(monkeypatch)
        calls = {"n": 0}

        def always_fails(texts):
            calls["n"] += 1
            raise ConnectionError("down")

        monkeypatch.setattr(retrieval, "_request_embeddings", always_fails)
        ctx = _ctx()

        rank_objects(ctx, "show me the orders table", k=3)
        assert calls["n"] == 1

        # Simulate cooldown elapsing without sleeping the test.
        retrieval._EMBED_CIRCUIT_OPENED_AT -= (
            retrieval._EMBED_CIRCUIT_COOLDOWN_SECONDS + 1)

        rank_objects(ctx, "show me the orders table", k=3)
        assert calls["n"] == 2  # cooldown expired -- one retry allowed


class TestZeroScoreFiltering:
    """spec-motivated fix: a 0.0 (or negative) score means no relevance
    signal at all -- keeping it in the ranked results is worse than the
    static fallback order, since `_ordered_objects` (agent/context.py)
    would treat "found nothing" as "found something", demoting every
    unranked canonical object below noise ordered by nothing but id."""

    #: Digits share no word tokens AND no char 3-5-grams with any fixture
    #: object's text (none of them contain a digit character) -- unlike a
    #: nonsense word, which can still accidentally share a short char
    #: n-gram with real text (e.g. "zzqxw plonk" contributes the 3-gram
    #: "w p", which collides with "new paid" in the `orders` fixture doc).
    #: This is a genuinely zero-overlap "off-topic question" for Backend A.
    OFF_TOPIC_QUESTION = "0102030405 0607080900 1112131415"

    def test_off_topic_question_returns_no_ranked_objects(self):
        ctx = _ctx()
        ranked = rank_objects(ctx, self.OFF_TOPIC_QUESTION, k=4)
        assert ranked == []

    def test_rank_documents_drops_zero_score_entries(self):
        docs = [
            Document(id="a", text="orders table with customer purchases"),
            Document(id="b", text="customers table with city and name"),
        ]
        ranked = rank_documents(docs, self.OFF_TOPIC_QUESTION, k=2)
        assert ranked == []

    def test_top_k_never_returns_a_zero_or_negative_score(self):
        assert retrieval._top_k({"a": 0.0, "b": -0.1, "c": 0.4}, k=3) == [("c", 0.4)]

    def test_positive_scores_still_come_through(self):
        # Regression guard: the filter must not eat real matches.
        ctx = _ctx()
        ranked = rank_objects(ctx, "show me the orders table", k=3)
        assert ranked
        assert all(score > 0 for _, score in ranked)


class TestRankDocuments:
    def test_deterministic_ordering(self):
        docs = [
            Document(id="a", text="orders table with customer purchases"),
            Document(id="b", text="customers table with city and name"),
            Document(id="c", text="v_sales monthly rollup view"),
        ]
        first = rank_documents(docs, "customer purchases", k=3)
        for _ in range(5):
            again = rank_documents(docs, "customer purchases", k=3)
            assert again == first
        assert first[0][0] == "a"

    def test_never_raises_on_bad_input(self):
        # Empty corpus, empty question -- degrade to [] rather than raise.
        assert rank_documents([], "anything", k=5) == []
        assert rank_objects(SchemaContext(source_id=1, family="postgresql"),
                            "anything", k=5) == []


# ---------------------------------------------------------------------------
# Task M2: chunking, persistence (read-through/write-back), dim guard.
# ---------------------------------------------------------------------------

@pytest.fixture
def persist_db(monkeypatch, tmp_path):
    """A real, FILE-backed (not `:memory:`) sqlite db for persistence tests.
    Unlike `:memory:`, a file db survives across separate engine instances --
    the property the restart-simulation test needs: a brand-new
    `_get_persist_engine()` (after `_reset_persist_engine()`, standing in for
    a new worker process) opened against the SAME file sees rows an earlier
    engine wrote."""
    from sqlalchemy import create_engine

    from app.core.database import Base
    import app.models.models  # noqa: F401  (registers all tables on Base)

    db_path = tmp_path / "retrieval_persist_test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setattr(retrieval.settings, "database_url", url)
    retrieval._reset_persist_engine()
    yield db_path
    retrieval._reset_persist_engine()


def _configure_backend_b(monkeypatch, dim=8):
    monkeypatch.setattr(retrieval.settings, "embedding_base_url", "http://fake.invalid/v1")
    monkeypatch.setattr(retrieval.settings, "embedding_model", "test-embed")
    monkeypatch.setattr(retrieval.settings, "embedding_dim", dim)


class TestEmbedChunking:
    def test_600_docs_batched_at_256_per_post(self, monkeypatch, persist_db):
        _configure_backend_b(monkeypatch)
        calls = []

        def fake_request(texts):
            calls.append(len(texts))
            return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(retrieval, "_request_embeddings", fake_request)
        texts = [f"doc {i}" for i in range(600)]
        vectors = retrieval._embed_many(texts, kind="document",
                                        refs=[str(i) for i in range(600)])
        assert len(vectors) == 600
        assert calls == [256, 256, 88]  # ceil(600/256) == 3 POSTs

    def test_chunk_failure_never_returns_partial_vectors(self, monkeypatch, persist_db):
        """A failure partway through chunked embedding must propagate (so
        the whole rank falls back to lexical) rather than silently handing
        back a mix of real and missing vectors."""
        _configure_backend_b(monkeypatch)
        calls = {"n": 0}

        def flaky_request(texts):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ConnectionError("down mid-batch")
            return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(retrieval, "_request_embeddings", flaky_request)
        texts = [f"doc {i}" for i in range(600)]
        with pytest.raises(ConnectionError):
            retrieval._embed_many(texts, kind="document",
                                  refs=[str(i) for i in range(600)])


class TestPersistence:
    def test_restart_simulation_zero_embed_calls_on_reload(self, monkeypatch, persist_db):
        """First rank embeds+persists; a simulated new process (cleared
        in-process cache AND a fresh persist engine) ranks the SAME question
        again and must make zero embed calls -- every hash, document and
        query alike, hits the persisted table."""
        _configure_backend_b(monkeypatch)
        calls = {"n": 0}

        def fake_request(texts):
            calls["n"] += 1
            return [[1.0, 0.0, 0.0] for _ in texts]

        monkeypatch.setattr(retrieval, "_request_embeddings", fake_request)
        # The dim guard's /health preflight is a real httpx.get -- stub it so
        # this unit test never touches the network (dim=8 here matches
        # _configure_backend_b's default, so the guard passes through).
        class _FakeHealthResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"dim": 8, "model": "test-embed", "status": "ok"}

        import httpx
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeHealthResp())
        ctx = _ctx()

        first = rank_objects(ctx, "show me the orders table", k=3)
        assert first
        assert calls["n"] >= 1

        # Simulate a fresh worker process: clear the in-process LRU/latches
        # and drop the cached persistence engine, but keep the same db file.
        retrieval._reset_embedding_process_state()
        retrieval._reset_persist_engine()
        calls["n"] = 0

        second = rank_objects(ctx, "show me the orders table", k=3)
        assert second == first
        assert calls["n"] == 0  # everything -- documents and query -- hit the DB

    def test_model_tag_mismatch_re_embeds(self, monkeypatch, persist_db):
        _configure_backend_b(monkeypatch)
        calls = {"n": 0}

        def fake_request(texts):
            calls["n"] += 1
            return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(retrieval, "_request_embeddings", fake_request)
        retrieval._embed_many(["hello"], kind="document", refs=["x"])
        assert calls["n"] == 1

        retrieval._reset_embedding_process_state()
        retrieval._reset_persist_engine()
        monkeypatch.setattr(retrieval.settings, "embedding_model", "a-different-model")
        retrieval._embed_many(["hello"], kind="document", refs=["x"])
        assert calls["n"] == 2  # different model tag -- the old row doesn't match

    def test_db_failure_degrades_to_embed_everything(self, monkeypatch, persist_db):
        _configure_backend_b(monkeypatch)
        calls = {"n": 0}

        def fake_request(texts):
            calls["n"] += 1
            return [[1.0, 0.0] for _ in texts]

        monkeypatch.setattr(retrieval, "_request_embeddings", fake_request)

        # Point persistence at a broken engine (bad DB URL) -- read AND
        # write must both fail silently, never raise or block the embed.
        monkeypatch.setattr(retrieval.settings, "database_url",
                            "sqlite:////nonexistent-dir/does-not-exist.db")
        retrieval._reset_persist_engine()

        vectors = retrieval._embed_many(["hello"], kind="document", refs=["x"])
        assert vectors == [[1.0, 0.0]]  # ranking proceeds despite DB failure
        assert calls["n"] == 1

    def test_persisted_rows_survive_across_engine_instances(self, monkeypatch, persist_db):
        """Direct check of the read/write helpers (not through rank_objects)
        that a row written by one engine instance is visible to another."""
        _configure_backend_b(monkeypatch)
        retrieval._persist_vectors([
            {"kind": "document", "ref": "obj-a", "text_hash": "h" * 64,
             "vector": [1.0, 2.0, 3.0], "model": "test-embed"},
        ])
        retrieval._reset_persist_engine()
        hits = retrieval._load_persisted_vectors(["h" * 64], "test-embed")
        assert hits == {"h" * 64: [1.0, 2.0, 3.0]}


class TestDimGuard:
    def test_dim_mismatch_blocks_backend_and_falls_back_to_lexical(self, monkeypatch):
        _configure_backend_b(monkeypatch, dim=999)  # server (below) says 384

        class _FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"dim": 384, "model": "x", "status": "ok"}

        import httpx
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResp())

        def fail_if_called(texts):
            raise AssertionError("Backend B must not be reached on dim mismatch")

        monkeypatch.setattr(retrieval, "_request_embeddings", fail_if_called)

        ctx = _ctx()
        ranked = rank_objects(ctx, "show me the orders table", k=3)
        assert ranked[0][0] == "orders"  # lexical fallback still works
        assert retrieval._EMBED_DIM_MISMATCH is True

    def test_dim_match_allows_backend(self, monkeypatch):
        _configure_backend_b(monkeypatch, dim=384)

        class _FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"dim": 384, "model": "x", "status": "ok"}

        import httpx
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResp())
        monkeypatch.setattr(retrieval, "_request_embeddings",
                            lambda texts: [[1.0, 0.0] for _ in texts])

        assert retrieval._verify_embedding_dim_or_block() is False
        assert retrieval._EMBED_DIM_VERIFIED is True

    def test_health_check_failure_is_not_treated_as_mismatch(self, monkeypatch):
        _configure_backend_b(monkeypatch, dim=384)

        import httpx

        def broken_get(*a, **kw):
            raise ConnectionError("health endpoint unreachable")

        monkeypatch.setattr(httpx, "get", broken_get)
        # Not blocked by the dim guard itself -- the real embed call (mocked
        # here to fail too) is what should trigger the ordinary fallback.
        assert retrieval._verify_embedding_dim_or_block() is False
