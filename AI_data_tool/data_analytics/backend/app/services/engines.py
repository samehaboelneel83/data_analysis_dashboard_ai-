"""Pooled SQLAlchemy engines, keyed by connection identity.

Layer 1. This is connection ACQUISITION -- reaching an external system --
which is layer 1 work. It lived inside `direct_query.py` (layer 4) until the
conformance test made the consequence visible: `metadata/sync.py` and
`metadata/catalog_sync.py` (layer 2) had to import a layer 4 module just to
open a connection, recorded as two allowlisted upward imports.

Nothing here builds or runs a query. The registry is a bounded LRU: beyond
`settings.directquery_engine_pool_maxsize` the least-recently-used engine is
evicted and disposed, so many sources or credential churn cannot leak
connection pools without limit.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from ..core.config import settings
from . import connectors
from .connections import _build_url


# LRU (move_to_end on use, evict from the front) so the registry stays bounded.
_ENGINE_REGISTRY: "OrderedDict[str, Engine]" = OrderedDict()
_ENGINE_REGISTRY_LOCK = threading.Lock()


def _engine_key(cfg: dict) -> str:
    """Normalized connection identity. Two data sources with the SAME connection
    string share one pooled engine even when their configs differ in cosmetic fields
    (a label, a `type` spelled `postgres` vs `postgresql`), because the key is the
    built URL — the thing that actually determines the connection — not the raw config.

    Keyed on `_build_url` specifically (not `connectors.build_url`) so the test seam
    that redirects the URL stays consistent with the engine that gets created.

    In-memory sources are the exception: every `:memory:` database is distinct, so
    sharing one engine would merge their data. Those fall back to a per-config key and
    never share. A URL that cannot be built (api/unknown) also falls back."""
    try:
        url = _build_url(cfg)
    except Exception:
        url = None
    # The schema rides along, because it is part of what a connection RESOLVES
    # even though it is not part of the URL. Two sources on the same database
    # with different schemas build a byte-identical url; without this they
    # share one pooled engine and whichever connected first sets the search
    # path for both. (The cfg: fallback below already hashes the whole config.)
    if url and ":memory:" not in url:
        schema = (cfg.get("schema") or "").strip()
        ident = url + (f"|schema={schema}" if schema else "")
        return "url:" + hashlib.sha256(ident.encode()).hexdigest()
    return "cfg:" + hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()


def get_metadata_engine(cfg: dict) -> Engine:
    """A SEPARATE pool for background metadata sampling.

    `get_engine` below is shared with live widget renders. Sampling a whole
    catalogue several objects at a time, each holding a connection for up to
    `metadata_statement_timeout_s`, would take most of that pool's five slots
    and make a background task visible as a stall on somebody's report.

    `max_overflow=0` is deliberate: this pool's size IS the promise made to the
    source database. The sync's connection footprint is exactly
    `metadata_sample_concurrency` and cannot exceed it, so the load a sync adds
    is a number someone chose rather than a number that emerged.

    Shares the registry and its LRU bound with `get_engine`, under a distinct
    key prefix so a metadata engine and an interactive one for the same source
    never collide or evict each other's identity.
    """
    key = "meta:" + _engine_key(cfg)
    with _ENGINE_REGISTRY_LOCK:
        engine = _ENGINE_REGISTRY.get(key)
        if engine is not None:
            _ENGINE_REGISTRY.move_to_end(key)
            return engine

        url = _build_url(cfg)
        kwargs = {"pool_pre_ping": True,
                  "connect_args": connectors.connect_args(cfg)}
        # pool_size/max_overflow are QueuePool arguments. SQLite uses
        # SingletonThreadPool (and StaticPool for :memory:), which reject them —
        # and the test suite runs on SQLite, so this is not a hypothetical.
        if not url.startswith("sqlite"):
            kwargs.update(pool_size=settings.metadata_sample_concurrency,
                          max_overflow=0, pool_timeout=30)

        engine = create_engine(url, **kwargs)
        _ENGINE_REGISTRY[key] = engine
        while len(_ENGINE_REGISTRY) > settings.directquery_engine_pool_maxsize:
            _, victim = _ENGINE_REGISTRY.popitem(last=False)
            victim.dispose()
        return engine


def get_engine(cfg: dict) -> Engine:
    """Engine registry keyed by connection identity, so DirectQuery reuses pooled
    connections across widget renders (and across data sources that share a
    connection string) instead of paying create_engine/dispose on every request.

    Bounded LRU: beyond `directquery_engine_pool_maxsize` the least-recently-used
    engine is evicted and disposed, so many sources or credential churn cannot leak
    connection pools without limit."""
    key = _engine_key(cfg)
    with _ENGINE_REGISTRY_LOCK:
        engine = _ENGINE_REGISTRY.get(key)
        if engine is not None:
            _ENGINE_REGISTRY.move_to_end(key)   # most-recently-used
            return engine
        engine = create_engine(_build_url(cfg), pool_pre_ping=True,
                               connect_args=connectors.connect_args(cfg))
        _ENGINE_REGISTRY[key] = engine
        while len(_ENGINE_REGISTRY) > settings.directquery_engine_pool_maxsize:
            _, victim = _ENGINE_REGISTRY.popitem(last=False)   # least-recently-used
            victim.dispose()
        return engine


def dispose_engine(cfg: dict) -> None:
    """Drop this connection config's pooled engine, closing its connections.

    The registry above deliberately keeps connections open between renders, which is
    right for a live database and wrong for a source whose STORAGE is about to be
    replaced -- a file-backed SQLite source being re-seeded, above all. A pool holding
    that file makes the unlink fail outright on Windows, and on POSIX it keeps serving
    the deleted inode, so every later query answers from a file nobody can see.
    Whoever replaces a source's storage calls this first; a config with no engine
    registered is a no-op."""
    key = _engine_key(cfg)
    with _ENGINE_REGISTRY_LOCK:
        engine = _ENGINE_REGISTRY.pop(key, None)
    if engine is not None:
        engine.dispose()
