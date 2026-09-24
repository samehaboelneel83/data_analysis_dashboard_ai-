"""Shared shaping and result-cache surface for the two widget query engines.

`widget_data.py` (import-mode, pandas) and `direct_query.py` (DirectQuery, SQL
push-down) both produce widget results, and both must agree on two things:

  * how a value is coerced to something JSON-native (`safe`)
  * how a result is keyed, read, and written in the result cache
    (`widget_cache_key` / `widget_cache_get` / `widget_cache_set`)

Before this module existed, `direct_query` imported `_safe`,
`_widget_data_cache_get` and `_widget_data_cache_set` -- three private,
underscore-prefixed names -- straight out of `widget_data`. The coupling was
real and load-bearing (see the RLS note on `widget_cache_key`), but it was
expressed by convention only: nothing stopped either side drifting, and the
guarantee was documented as a warning comment in two places rather than as one
contract in one place.

Everything here is deliberately downward-facing: this module imports
`cache_backend` (layer 3) and `config`, and nothing else from the app. It must
never import `widget_data`, `direct_query` or `prep` -- `prep` already carries a
lazy-import workaround for a cycle with `widget_data`, and this module exists
partly so that cycle has somewhere to unwind to.
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
from collections import OrderedDict

import numpy as np
import pandas as pd

from ..core.config import settings
from .cache_backend import InProcessCache, ValkeyCache


# ── value coercion ────────────────────────────────────────────────────────────

def safe(v):
    """Coerce a pandas/numpy scalar into a plain, JSON-native Python value.

    O2 (cache_backend.py): every widget-result field that reaches the cache
    is expected to already be JSON-native by the time it gets here -- the
    Valkey backend `json.dumps`s the whole result, the in-process backend
    stores it as-is. Any type this function lets through un-converted (the
    original gap: a non-NaT `pd.Timestamp`/`datetime.date` fell through to
    the bare `return v` below) is invisible on the in-process path but
    silently becomes a *different* type -- a string, via `default=str` --
    the moment it's written to Valkey. That's cache-backend-dependent type
    drift for the exact same cache key, which is worse than either behavior
    alone. Converting date/datetime/Timestamp to an ISO string HERE, at the
    single choke point every result field already funnels through, keeps
    both backends storing (and returning) the identical value -- no
    Valkey-specific special-casing needed in cache_backend.py itself.
    """
    if isinstance(v, np.bool_):                    return bool(v)
    if isinstance(v, np.integer):                  return int(v)
    if isinstance(v, np.floating):                 return None if np.isnan(v) else float(v)
    if isinstance(v, np.str_):                     return str(v)
    if isinstance(v, np.ndarray):                  return [safe(x) for x in v.tolist()]
    if isinstance(v, float) and v != v:            return None   # NaN
    if isinstance(v, (list, tuple)):               return [safe(x) for x in v]
    if v is pd.NaT:                                 return None   # NaT reads as both a
    # datetime.date and datetime.datetime instance (pandas compat shim), so it MUST be
    # caught before the generic datetime/date branch below or it stringifies to "NaT".
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        ts = pd.Timestamp(v)
        return None if pd.isna(ts) else ts.isoformat()
    if isinstance(v, (_dt.datetime, _dt.date)):     return v.isoformat()
    try:
        if pd.isna(v): return None
    except Exception:
        pass
    return v


# ── cache state ───────────────────────────────────────────────────────────────
# The store, the backends, and the accessors below are ONE unit and must stay
# together: `widget_cache_get`/`set` branch on `backend is _inprocess_backend`,
# an identity check. Split the functions from the singletons across two modules
# and that comparison silently starts comparing objects from different modules,
# the in-process fast path stops firing, and every in-process read begins
# round-tripping through JSON.

WIDGET_DATA_CACHE: "OrderedDict[str, dict]" = OrderedDict()
WIDGET_DATA_CACHE_LOCK = threading.Lock()

# O2: `_inprocess_backend` wraps `WIDGET_DATA_CACHE` itself (same OrderedDict
# object, `store=`) rather than owning a copy -- so the default path
# (`settings.valkey_url` is None) is the pre-O2 OrderedDict LRU exactly,
# byte-identical, and every test that introspects `_WIDGET_DATA_CACHE`
# directly keeps working untouched. `maxsize` is a callable so a test (or a
# runtime settings change) that mutates `settings.widget_data_cache_maxsize`
# after import is still honored on the next `set()`, matching the pre-O2
# function's behavior of reading the setting fresh every call.
_inprocess_backend = InProcessCache(
    maxsize=lambda: settings.widget_data_cache_maxsize, store=WIDGET_DATA_CACHE)

def _code_epoch() -> str:
    """A fingerprint of the code that SHAPES results.

    The shared Valkey tier outlives the process: without this, a deploy that
    fixes a shaper keeps serving the old shaper's cached output until each
    entry happens to expire. Hashing the services sources scopes every entry
    to the code that produced it (the in-process tier needs nothing -- a new
    process starts empty)."""
    import hashlib
    from pathlib import Path
    h = hashlib.sha1()
    root = Path(__file__).resolve().parent
    try:
        for f in sorted(root.rglob("*.py")):
            h.update(f.read_bytes())
    except OSError:
        return "0"
    return h.hexdigest()[:10]


CODE_EPOCH = _code_epoch()

_valkey_backend: "ValkeyCache | None" = None
_valkey_backend_lock = threading.Lock()


def get_cache_backend():
    """The in-process backend when `settings.valkey_url` is unset (default,
    byte-identical to pre-O2); otherwise a lazily-built, process-wide
    `ValkeyCache` singleton -- built once so its circuit-breaker state
    (`_circuit_opened_at`, the once-per-process error log) persists across
    calls the way retrieval.py's Backend-B breaker does.

    One tier, not two: a deployment with Valkey configured does not ALSO
    keep an in-process front-cache in front of it (beyond ValkeyCache's own
    cooldown-fallback instance, which only serves while the circuit is
    open). That trades away a per-render network hop for cross-replica
    coherence -- every worker/replica sees the same entry, so cache_epoch/
    TTL invalidation behaves identically everywhere, with no local copy that
    could go stale relative to Valkey after an eviction or a manual clear.
    """
    global _valkey_backend
    if not settings.valkey_url:
        return _inprocess_backend
    with _valkey_backend_lock:
        if _valkey_backend is None:
            _valkey_backend = ValkeyCache(
                valkey_url=settings.valkey_url, key_prefix=f"wdc:{CODE_EPOCH}:",
                fallback=InProcessCache(maxsize=lambda: settings.widget_data_cache_maxsize))
        return _valkey_backend


def reset_cache_backend() -> None:
    """Test hook: drop the memoized ValkeyCache singleton so a test that
    monkeypatches `settings.valkey_url` after import builds a fresh one on
    next use, instead of reusing one wired to a stale URL/client."""
    global _valkey_backend
    _valkey_backend = None


# ── cache key and accessors ───────────────────────────────────────────────────

def widget_cache_key(
    file_path: str, file_stat: tuple | None, config: dict, widget_type: str,
    calculated_columns: list[dict] | None, filter_expr: str | None, rls_filter_expr: str | None,
    measures: list[dict] | None = None,
) -> str:
    """Canonical, hashable (string) cache key. rls_filter_expr is included
    VERBATIM and un-normalized -- this is load-bearing for RLS isolation: two
    roles with different filter expression strings for the same
    dataset+config always land in different cache entries, so a role with
    tighter RLS can never be served a cached result computed for a role with
    looser (or no) RLS, and a fail-closed empty result for a malformed
    expression is never served to a different role whose expression is valid.

    DirectQuery builds its own key rather than calling this one (its inputs
    differ -- there is no file_stat, and a TTL bucket participates), but it
    must preserve this same property. `tests/test_direct_query_cache.py`
    asserts that independently; if this docstring's guarantee ever changes,
    that test is the other half that has to change with it.
    """
    payload = {
        "file_path": file_path,
        "file_stat": file_stat,          # (mtime, size) or None -- invalidates on re-upload
        "config": config,
        "widget_type": widget_type,
        "calculated_columns": calculated_columns or [],
        "filter_expr": filter_expr,
        "rls_filter_expr": rls_filter_expr,
        # Verbatim, so editing a measure's expression invalidates its cached results
        # instead of serving a stale value under the unchanged measure name.
        "measures": measures or [],
    }
    return json.dumps(payload, sort_keys=True, default=str)


def widget_cache_get(key: str):
    """Reads through `get_cache_backend()`. On the default (in-process)
    backend this returns the stored dict exactly as before -- no
    serialization round-trip. On the Valkey backend, values were JSON-encoded
    at `set()` time, so they're decoded back here."""
    backend = get_cache_backend()
    if backend is _inprocess_backend:
        return backend.get(key)
    raw = backend.get(key)
    return None if raw is None else json.loads(raw)


def widget_cache_set(key: str, value: dict, ttl_s: int | None = None) -> None:
    """`ttl_s` only matters on the Valkey backend (the in-process backend
    ignores it, matching InProcessCache's own contract). Defaults to
    `settings.valkey_cache_ttl_s`; DirectQuery passes its own per-call
    `cache_ttl_seconds` instead, since that TTL is already meaningful there
    (it's the bucket width baked into the cache key) and reusing it avoids a
    second, disconnected TTL governing the same entry."""
    backend = get_cache_backend()
    if backend is _inprocess_backend:
        backend.set(key, value)
        return
    payload = json.dumps(value, default=str).encode("utf-8")
    backend.set(key, payload, ttl_s=ttl_s if ttl_s is not None else settings.valkey_cache_ttl_s)


def clear_widget_data_cache() -> None:
    """Manual full-cache clear. Not wired into any endpoint (mtime-based
    invalidation already covers the re-upload path) -- exposed as a small
    escape hatch for tests and any future 'refresh' action. Clears both the
    in-process store and (if configured) this process's Valkey namespace."""
    _inprocess_backend.delete_prefix("")
    if _valkey_backend is not None:
        _valkey_backend.delete_prefix("")
