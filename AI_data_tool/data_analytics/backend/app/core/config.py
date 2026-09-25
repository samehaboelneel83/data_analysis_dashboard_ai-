from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://datalytics:datalytics_secret@localhost:5433/datalytics"
    secret_key: str = "change_me_in_production"
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"
    env: str = "development"
    upload_dir: str = "/app/uploads"
    #: Starter boundary packs (backend/boundary_packs). Empty = the folder
    #: next to the app; a missing folder lists no packs (lean offline builds).
    boundary_packs_dir: str = ""
    #: Hosts an org's basemap tile URL may point at, comma-separated
    #: ("tiles.corp.local,gis.intra"). Empty = any host. Air-gapped deployments
    #: set it so no map can be pointed at a public tile service.
    map_tile_hosts: str = ""
    max_upload_mb: int = 100
    #: Ceilings for a multi-file upload. `max_upload_mb` still applies to each
    #: file; these bound the REQUEST. Ingestion runs inline, and append mode
    #: holds every frame in memory at once (pandas expands several-fold over
    #: file size), so the batch ceiling is deliberately well under
    #: max_upload_mb * max_upload_files.
    max_upload_files: int = 20
    max_batch_upload_mb: int = 200
    widget_data_cache_maxsize: int = Field(default=500, ge=0)
    widget_data_cache_max_entry_bytes: int = Field(default=2_000_000, ge=0)  # 2MB

    # Process-local DataFrame memo (services/frame_cache.py): parsed files are
    # kept in memory keyed by (path, mtime_ns, size) so an N-widget page pays
    # one parse, not N. Kill switch + budget are env-overridable; frames larger
    # than the total budget are served uncached rather than evicting everything.
    frame_cache_enabled: bool = True
    frame_cache_max_frames: int = Field(default=8, ge=0)
    frame_cache_max_total_bytes: int = Field(default=1_500_000_000, ge=0)  # 1.5GB

    # How many widget-data pipelines may run on worker threads at once. The
    # GIL serializes pandas work anyway, so more parallelism than this only
    # adds contention that starves the event loop (measured: a 28-wide burst
    # kept wall time flat while trivial-request latency went from ~80ms to
    # seconds). Bounded, the queue drains at the same total rate and the loop
    # stays responsive.
    widget_work_max_concurrency: int = Field(default=4, ge=1)

    # DirectQuery pools one SQLAlchemy engine per distinct connection (services/
    # direct_query.py). The registry is an LRU capped here: beyond the cap the
    # least-recently-used engine is disposed, so credential churn or many sources
    # cannot leak connection pools without bound. Engines that share a connection
    # string share one entry, so this counts distinct connections, not data sources.
    directquery_engine_pool_maxsize: int = Field(default=32, ge=1)

    # Platform super-admins: a comma-separated email allowlist. A user whose email is
    # listed can manage organizations across the whole platform (create orgs, list all,
    # arrange the org hierarchy) — a tier above any single org's admin. Config-driven so
    # there is no chicken-and-egg grant problem; empty means no super-admin exists.
    super_admin_emails: str = ""

    # At-rest encryption of connection secrets in DataSource.config (services/
    # secrets.py). A Fernet key (urlsafe base64, 44 chars); empty derives a stable
    # key from secret_key, so encryption is always on without extra config. Rotating
    # secret_key (or setting a new key here) makes previously-encrypted secrets
    # undecryptable, so pin this in production before storing real credentials.
    connector_secret_key: str = ""

    # SSRF guard for data-source connections (services/net_guard.py). Cloud
    # instance-metadata endpoints are always blocked; private/loopback/reserved
    # hosts are blocked only when this is False. Default True preserves local/
    # sandbox/dev DB and sqlite-demo connectivity; set False in production.
    connector_allow_private_hosts: bool = True

    # Outbound email for scheduled deliveries and alerts. Unset host = delivery is
    # recorded as undeliverable rather than raising -- a deployment without SMTP
    # still schedules, and the status column says why nothing arrived.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "datalytics@localhost"
    smtp_starttls: bool = True
    # Base URL used in email links back to the app.
    public_base_url: str = "http://localhost:3000"

    # ── Layer 1 — Connectors & Ingestion ────────────────────────────────────
    # Self-hosted model endpoint (vLLM, OpenAI-compatible). Used by Layer 1 only
    # for column/table descriptions, which are an improvement and never a
    # requirement -- services/llm.py returns None rather than raising when the
    # box is unreachable, so a sync still completes with the GPU host down.
    # Set llm_enabled=False to keep the platform entirely offline.
    llm_base_url: str = "http://10.125.18.189:8000/v1"
    llm_model: str = "qwen3.5"
    llm_timeout_s: float = Field(default=180.0, gt=0)
    llm_enabled: bool = True

    # Total in-flight requests to the model endpoint, ACROSS features -- the
    # sync's describe stage and agent runs share one box. Measured on the Qwen
    # endpoint: throughput 0.31 / 1.35 / 2.32 req/s at concurrency 1 / 6 / 12,
    # per-call latency rising only 3.2s -> 5.1s (continuous batching working).
    llm_max_concurrency: int = Field(default=12, ge=1)
    # Slots background work may never occupy, so a person's question does not
    # queue behind 82 table descriptions. Reserved headroom, not priority:
    # exact by construction, worst case bounded.
    llm_reserved_interactive: int = Field(default=2, ge=0)

    # Metadata sample cache (services/metadata/cache.py). ~1000 rows per dataset
    # in a DuckDB file, so foreign-key inference joins samples locally instead of
    # querying a customer's production database once per candidate pair. Lives on
    # the existing uploads volume -- no new mount. Budgeted and LRU-evicted.
    duckdb_cache_path: str = "/app/uploads/metadata_cache.duckdb"
    metadata_cache_max_mb: int = Field(default=512, ge=1)
    metadata_sample_rows: int = Field(default=1000, ge=10)

    # How long the metadata plane may spend on ONE object before giving up.
    # ARCHITECTURE.md lists statement_timeout among the security requirements,
    # and a real source proved why: an expensive view took nearly two minutes to
    # return its first 1000 rows, because the cost lives in the view definition
    # rather than in how it is queried. Everything this layer produces is an
    # improvement and none of it is a requirement, so a deadline is the correct
    # trade -- one slow object must not hold a whole catalog hostage.
    metadata_statement_timeout_s: int = Field(default=20, ge=1)

    # How many objects are sampled from the source at once (services/metadata/
    # catalog_sync.py, stage_sample). Measured on a live 82-table Postgres
    # source: a strictly serial loop took 495s, of which ~160s was eight
    # expensive views each burning the full metadata_statement_timeout_s one
    # after another. Four in flight overlaps those deadlines without turning a
    # background sync into a load test -- and sampling gets its OWN engine pool
    # of exactly this size (direct_query.get_metadata_engine), so interactive
    # DirectQuery traffic never queues behind a sync.
    metadata_sample_concurrency: int = Field(default=4, ge=1)

    # Per-table description calls in flight. Was a hardcoded constant in
    # catalog_sync.py; the right value depends entirely on the model endpoint's
    # capacity, which is a deployment fact rather than a code one.
    #
    # 12 rather than 6, measured against the Qwen box this deployment uses:
    #
    #     concurrency  1   0.31 req/s   3.2s per call
    #     concurrency  6   1.35 req/s   4.3s per call
    #     concurrency 12   2.32 req/s   5.1s per call
    #
    # Throughput nearly doubles from 6 to 12 while per-call latency rises by
    # under a second -- that is continuous batching doing its job, and at 6 the
    # describe stage was leaving about half the endpoint's capacity idle.
    #
    # Raise this further only against a measurement on YOUR endpoint. The curve
    # above is a property of that box and its model, not of this code. And note
    # that a shared endpoint means concurrent syncs multiply this number; if
    # agent runs ever share the box, they need a gate that spans both.
    #
    # DEPRECATED: no longer read by stage_describe, which now relies on the
    # client-level gate (llm_max_concurrency / llm_reserved_interactive in
    # services/llm.py) so the sync and agent runs share one bound against the
    # same endpoint. Kept here, additive, because a deployment's .env may
    # still set it -- removing a setting out from under someone is not a safe
    # change even when nothing reads it anymore.
    metadata_describe_concurrency: int = Field(default=12, ge=1)

    # Foreign-key inference thresholds (services/metadata/infer_keys.py), as
    # value-overlap ratios. At or above _high: proposed with high confidence and
    # pre-selected in review. Between the two: proposed, needs a human. Below
    # _review: discarded, never written -- a wrong join silently corrupts every
    # number downstream, so the floor is deliberately unforgiving.
    fk_overlap_high: float = Field(default=0.95, ge=0.0, le=1.0)
    fk_overlap_review: float = Field(default=0.70, ge=0.0, le=1.0)

    # The agent's per-query bounds. A generated query is a guess wrapped in a
    # ladder; these are the two promises execution keeps regardless: no query
    # holds the source longer than this, and no result is unbounded.
    agent_statement_timeout_s: int = Field(default=30, ge=1)
    agent_row_cap: int = Field(default=5000, ge=1)

    # Import-mode's source-frame ceiling. DirectQuery has always been bounded
    # (direct_query.DEFAULT_ROW_CAP); the pandas path was not, so a single
    # widget could materialise an entire dataset to answer a five-row question.
    # Measured 2026-08-28: a 406 MB / 2M-row / 30-column CSV costs ~1.8 GB of
    # RSS on that path, and each concurrent render holds its own frame.
    #
    # 0 disables the cap. When a frame exceeds it, the request FAILS with a
    # clear message rather than silently aggregating a truncated frame -- a
    # wrong number returned confidently is worse than an error, and this path
    # has no way to say "these totals are partial".
    #
    # Defaulted to 2M rows (was 0) on 2026-08-29. Uncapped, a single oversized
    # upload can exhaust the container for EVERY tenant on it, and the failure
    # arrives as an OOM kill with no attribution. A 413 naming the dataset size
    # and the limit is a better answer than a dead worker, and 2M is roughly
    # where the measured 1.8 GB-per-render cost stops being survivable on a
    # shared box. An operator with the memory to spare can still set 0.
    import_row_cap: int = Field(default=2_000_000, ge=0)
    #: How many rows an ANALYSIS pulls from a live source. Between the two
    #: caps either side of it: the widget cap (10,000) sizes a scatter plot,
    #: the import cap sizes a file on disk. Statistics over 10,000 rows of a
    #: 112,650-row table would be a needless estimate; pulling millions across
    #: the wire to compute a mean is a download, not an analysis.
    analysis_row_cap: int = Field(default=250_000, ge=1)

    # The automation chain's per-run frame ceiling, in megabytes of parquet.
    #
    # Step 1 persists the creator's SECURED frame so steps 3-5 read it instead
    # of re-reading the dataset and re-applying RLS, denied columns and prep in
    # the right order three more times. That trade buys correctness with disk,
    # so the disk has to be bounded: a run per dataset per night, each holding
    # one person's slice, fills a volume quietly and takes the scheduler with
    # it.
    #
    # Refuses rather than truncates, the same call `import_row_cap` makes: half
    # a frame behind a committed output_ref is truncated customer data reaching
    # a model, which is worse than a step that says why it stopped. 0 disables
    # the check, for an operator who has the disk.
    automation_frame_max_mb: float = Field(default=256.0, ge=0)

    # DuckDB pre-aggregation for the import path (services/duck_agg.py).
    #
    # ON by default since 2026-08-29. It was opt-in while the parity contract
    # was being established; that contract is now pinned by 59 tests, and the
    # design is fail-safe in the one direction that matters -- an ineligible
    # config or ANY DuckDB error falls back to pandas, so the worst case is the
    # path that ran before. Leaving it off cost every deployment up to 25.6x
    # more memory per render for no safety it did not already have.
    #
    # When on, an ELIGIBLE widget query (plain dimension + measure + grain-safe
    # aggregation, basic filters) is aggregated by DuckDB against the parquet
    # sidecar and the small result handed to the same shaper; anything else, and
    # any DuckDB failure, falls back to pandas. The fallback is the pre-existing
    # path, so the worst case of enabling this is "no faster", never "wrong".
    #
    # Measured 2026-08-28 end to end on a 422 MB / 2M-row / 30-column CSV:
    # 977 MB -> 116 MB of peak RSS (8.4x) and 7.44s -> 3.30s. The speedup is
    # larger once a parquet sidecar exists (uploads and refreshes write one);
    # that run re-parsed the CSV because the fixture never went through upload.
    #
    # Aggregated VALUES may differ from the pandas path in the last bits of a
    # float: two engines summing the same column in different orders cannot
    # agree bit-for-bit, and the measured relative difference is ~2e-16 --
    # machine epsilon. Group names, ordering, row counts and totals match
    # exactly. This is the same property DirectQuery has always had against
    # Postgres/MySQL; tests/test_duck_agg.py pins the contract at rel=1e-9.
    widget_duckdb_pushdown: bool = True
    # Bounded so one render cannot take every core on a shared worker.
    widget_duckdb_threads: int = Field(default=2, ge=1)

    # S5: in-process rate limiting (core/rate_limit.py). No Valkey/Redis in this
    # stack -- each worker enforces its own token bucket, so the effective
    # ceiling scales with worker count. `*_requests_per_window` tokens refill
    # evenly across `rate_limit_window_seconds`; guest/share routes get their
    # own, stricter bucket per share link rather than sharing the general one.
    # Generous defaults so normal frontend traffic and the test suite (which
    # bypasses this entirely -- see rate_limit.is_test_mode) never trip it.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    rate_limit_requests_per_window: int = Field(default=300, ge=1)
    rate_limit_guest_requests_per_window: int = Field(default=60, ge=1)
    # Bucket keys are attacker-influenced (guest tokens, source IPs), so the
    # in-memory store is capped rather than growing unbounded on a long-lived
    # worker fielding many distinct bogus keys -- least-recently-used buckets
    # are evicted once this many distinct keys are live.
    rate_limit_bucket_cap: int = Field(default=10_000, ge=1)

    # T4: scheduled eval gate (services/eval_schedule.py) -- an opt-in,
    # in-process stand-in for a real CI gate, NOT CI itself. Off by default:
    # a real run costs ~20 minutes of LLM calls against a live source, so it
    # must be an explicit choice per deployment, never a surprise on boot.
    eval_gate_enabled: bool = False
    eval_gate_source_id: int = 0
    eval_gate_min_accuracy: float = Field(default=0.5, ge=0.0, le=1.0)

    # Tier 2 retrieval (services/retrieval.py, spec §1). Backend A (lexical
    # TF-IDF, pure numpy) always works and is the default -- these three are
    # all optional/None, meaning "Backend B (OpenAI-compatible embeddings
    # endpoint) is off." Setting all three opts in; the endpoint is called
    # POST {embedding_base_url}/embeddings, OpenAI shape. Any query-time
    # failure (unreachable, wrong shape, timeout) falls back to Backend A --
    # retrieval degrading is never allowed to take the agent down.
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = None

    # E3: OpenTelemetry, opt-in. Off by default -- otel packages are never
    # even imported unless this is True (core/telemetry.py), so a broken or
    # absent otel install can never brick startup or import time.
    otel_enabled: bool = False
    otel_endpoint: str | None = None
    otel_service_name: str = "datalytics-backend"

    # Metrics ride the same switch: they only exist when otel_enabled is on, and
    # this second flag lets a deployment take traces without metrics (or drop
    # metrics if its collector cannot take them) without losing both.
    otel_metrics_enabled: bool = True
    # OTLP/HTTP uses DIFFERENT paths for the two signals -- /v1/traces and
    # /v1/metrics -- so the metrics exporter cannot reuse otel_endpoint
    # verbatim. Left overridable for a collector that routes them elsewhere.
    otel_metrics_endpoint: str | None = None
    # 60s: metrics are for trends and alerting, not per-request debugging (spans
    # already cover that), so a slower cadence costs nothing and keeps the
    # export volume low on a small deployment.
    otel_metric_interval_ms: int = Field(default=60_000, ge=1_000)

    # O2: optional shared result-cache backend (services/cache_backend.py).
    # None (default) keeps every deployment on the pre-O2 in-process LRU
    # cache, byte-identical -- redis is never even imported. Set to a
    # redis://-scheme URL (Valkey is wire-compatible) to share widget/
    # DirectQuery cache entries across worker processes/replicas; any
    # connection failure at runtime falls back to the in-process cache for a
    # cooldown, so a dead/unset Valkey never takes rendering down.
    valkey_url: str | None = None
    # Per-key TTL for entries written to Valkey (bounds memory alongside the
    # compose service's own --maxmemory + allkeys-lru). The import-mode cache
    # key has no TTL bucket of its own (freshness comes from the file's
    # mtime), so this is what caps its Valkey footprint; DirectQuery already
    # has its own `cache_ttl_seconds` per call and uses that instead.
    valkey_cache_ttl_s: int = Field(default=300, ge=1)

    #: How long a login token lives. 168h (7 days) is the historical value, kept
    #: as the default so no session changes length on upgrade; a deployment
    #: that wants shorter sessions sets ACCESS_TOKEN_EXPIRE_HOURS. A password
    #: reset ends a user's existing sessions regardless (User.tokens_valid_after).
    access_token_expire_hours: int = Field(default=168, ge=1)

    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    def is_production(self) -> bool:
        """Anything that is not explicitly a development or test environment.
        The same rule sso.py's secure-cookie choice has always used."""
        return (self.env or "").lower() not in ("development", "dev", "test")

    @model_validator(mode="after")
    def _refuse_a_known_secret_in_production(self) -> "Settings":
        # The JWT signing key. Its default is printed in this file and in
        # docker-compose.yml, so a production install left on it lets anyone
        # mint an admin login token. Refusing to START is the only safe answer:
        # a warning in a log nobody reads leaves the door open.
        if self.is_production() and (self.secret_key in _KNOWN_DEV_SECRETS
                                     or len(self.secret_key) < 32):
            raise ValueError(
                "SECRET_KEY is a development default or shorter than 32 characters, "
                "and ENV is not development/test. Set a long random SECRET_KEY "
                "(e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`) "
                "before starting in production.")
        return self

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


#: Signing keys that ship in this repository, so are public by definition.
_KNOWN_DEV_SECRETS = frozenset({"change_me_in_production", "changeme", "secret", ""})


settings = Settings()
