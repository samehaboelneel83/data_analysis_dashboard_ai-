"""Process-local DataFrame memo: the same file parses once, not once per widget.

THE INVARIANT THAT MAKES THIS CACHE SAFE TO SHARE ACROSS ALL CALLERS:
it sits BELOW every security layer. The key is (path, mtime_ns, size) --
bytes-of-file identity, nothing else. RLS, column masks, prep and filters are
applied per-request to the copy this module hands out, exactly as they were
applied to a fresh parse. Never cache a frame that has had any of those
applied; a post-RLS frame under a bytes-of-file key would serve one user's
row-visibility to another.

Copy-on-hit is mandatory, not defensive paranoia: `detect_types`
(analytics.py) mutates its frame in place, and load_file has a dozen callers
beyond the widget path. One consumer mutating a shared cached frame would be
cross-request -- potentially cross-RLS-boundary -- data corruption. A deep
copy of a 1M-row frame is a block memcpy (~100-300ms) against a multi-second
CSV parse, and the equivalence gate (scripts/bench_equivalence.py) is the
referee for any future read-only fast path.

Locking mirrors the result cache in widget_data.py: the lock guards only the
dict get/put; parsing and copying happen outside it. Cold keys are
single-flighted: a 28-widget page arriving at once elects one parser, the
rest wait on its Event and read the stored frame -- measured, the
free-for-all alternative meant 28 simultaneous parses of the same file
fighting over the GIL. If the leader's parse doesn't get stored (error, or
the frame is over budget), waiters fall back to parsing themselves in
parallel, which is exactly today's behavior -- never a retry loop, which
would serialize the uncacheable case. Never "fix" any of this by holding
the lock across a parse.

O2 (services/cache_backend.py, the optional Valkey shared result cache) does
NOT extend to this module. This memo stays process-local by design: it holds
whole DataFrames, which don't serialize cheaply (a full CSV-shape roundtrip
through pandas' own to/from-parquet, per entry, per set/get, versus the
in-memory reuse this module exists to provide), and -- see the invariant
above -- it sits below RLS/masks/prep, so sharing it across processes would
mean sharing raw file bytes across a cache boundary those layers were never
designed to guard. The widget/DirectQuery RESULT caches (already
post-RLS/masks/prep, small JSON-shaped dicts) are what O2 wires up instead.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict

import pandas as pd

from ..core.config import settings
# ingest.py (layer 2) does not import this module, so this can be a normal
# top-level import. It used to be two function-local imports of
# `analytics.SUPPORTED`, working around the analytics <-> frame_cache cycle
# that splitting ingest.py out of analytics.py removed.
from .ingest import SUPPORTED

_CACHE: "OrderedDict[tuple[str, int, int], tuple[pd.DataFrame, int]]" = OrderedDict()
_LOCK = threading.Lock()
_TOTAL_BYTES = 0
_INFLIGHT: dict[tuple[str, int, int], threading.Event] = {}


def sidecar_path(csv_path: str) -> str:
    """The one place the "<csv>.parquet" naming convention is spelled out.
    O3's Materialization.path is written with this same function so the
    manifest row and the sidecar this module reads always name the same
    physical file -- see the Materialization docstring in models.py."""
    return str(csv_path) + ".parquet"


def _read_sidecar(pq_path: str) -> pd.DataFrame:
    """Read a parquet sidecar and normalize it to exactly what pd.read_csv
    would have produced. The one systematic difference is nulls in object
    columns: pyarrow yields None where read_csv yields float NaN, and
    astype(str) then renders "None" vs "nan" -- a real behavioral difference
    in string filters. Normalize every object-column null to NaN."""
    import numpy as np

    df = pd.read_parquet(pq_path)
    for c in df.columns:
        s = df[c]
        if s.dtype == object and s.hasnans:
            df[c] = s.where(s.notna(), np.nan)
    return df


def _parse(path: str) -> pd.DataFrame:
    """The uncached read: what load_file always did, except a CSV with a
    fresh parquet sidecar (written by write_parquet_sidecar at upload/refresh
    time, strictly newer than the CSV, verified at write time) loads from the
    sidecar instead -- same frame, a fraction of the parse cost. Any sidecar
    problem falls back to the CSV silently: the CSV is the source of truth,
    the sidecar only ever an accelerant."""
    from pathlib import Path

    p = Path(path)
    suffix = p.suffix.lower()
    reader = SUPPORTED.get(suffix)
    if not reader:
        raise ValueError(f"Unsupported file type: {p.suffix}")

    if suffix == ".csv" and ".parquet" in SUPPORTED:
        pq = sidecar_path(p)
        try:
            if os.stat(pq).st_mtime_ns >= os.stat(str(p)).st_mtime_ns:
                return _read_sidecar(pq)
        except Exception:  # noqa: BLE001 -- missing/corrupt sidecar: CSV wins
            pass
    return reader(p)


def write_parquet_sidecar(csv_path: str) -> bool:
    """Write and VERIFY a parquet sidecar next to a CSV. Returns True when a
    verified sidecar is in place. Best-effort by contract: every failure path
    deletes the sidecar and returns False -- a sidecar problem must never
    fail the upload/refresh that triggered it.

    The frame is RE-READ from disk, never taken from the caller's memory:
    callers hold frames that detect_types may have mutated (date strings
    converted to datetime64), and a sidecar preserving those dtypes would
    change filter/groupby semantics against what a CSV parse yields.

    Write order (CSV first, then sidecar) plus the strictly-not-older mtime
    check in _parse means a crash between the two leaves a stale sidecar
    that is simply never used.

    O3 note: every refresh caller (dataset_refresh.py) calls this, then
    separately writes/updates a Materialization manifest row pointing at
    this same sidecar_path() -- ONE parquet write per refresh either way,
    the manifest just adds row_count/columns/kind/watermark metadata on top
    of the file this function already produced."""
    import logging

    log = logging.getLogger(__name__)
    if ".parquet" not in SUPPORTED:
        return False
    if not str(csv_path).lower().endswith(".csv"):
        return False  # only files whose canonical reader is read_csv
    pq = sidecar_path(csv_path)
    try:
        original = pd.read_csv(csv_path)
        original.to_parquet(pq, index=False)
        os.utime(pq)  # ensure sidecar mtime >= csv mtime even on coarse clocks
        roundtrip = _read_sidecar(pq)

        # Strict verification: dtypes, values, and -- because assert_frame_equal
        # treats None and NaN as interchangeable -- an explicit type sweep over
        # the null positions of object columns.
        if list(original.columns) != list(roundtrip.columns):
            raise AssertionError("column mismatch")
        if list(original.dtypes) != list(roundtrip.dtypes):
            raise AssertionError("dtype mismatch")
        pd.testing.assert_frame_equal(original, roundtrip, check_exact=True)
        for c in original.columns:
            if original[c].dtype == object:
                mask = original[c].isna()
                if mask.any():
                    orig_nulls = original[c][mask]
                    rt_nulls = roundtrip[c][mask]
                    if [type(v) for v in orig_nulls] != [type(v) for v in rt_nulls]:
                        raise AssertionError(f"null representation drift in {c}")
        return True
    except Exception as e:  # noqa: BLE001 -- see docstring: never fail the caller
        try:
            os.remove(pq)
        except OSError:
            pass
        log.info("Parquet sidecar skipped for %s: %s", csv_path, e)
        return False


def remove_parquet_sidecar(csv_path: str) -> None:
    """Companion to dataset deletion: the sidecar dies with its CSV."""
    try:
        os.remove(sidecar_path(csv_path))
    except OSError:
        pass


#: Rows sampled to size a frame's object columns. Below this the frame is
#: simply walked; above it, the walk is what made a 1M-row cold render cost
#: 3.2s instead of 1s.
_SIZE_SAMPLE_ROWS = 10_000


def estimate_frame_bytes(df: pd.DataFrame) -> int:
    """How much memory a frame holds, without visiting every string in it.

    `memory_usage(deep=True)` is exact and linear in rows x object columns:
    measured 2026-09-12 at 2.21s on a 1M-row frame with 11 text columns --
    of a 3.2s cold render whose actual parquet read was 0.49s. The figure
    only feeds one decision, whether the frame fits the memo's byte bound,
    so it needs to be close, not exact.

    Numeric columns are exact either way (pandas knows their width). Object
    columns are sized from a fixed-size row sample and scaled, padded 5%
    because OVER-estimating is the safe direction: it evicts a little early,
    while under-estimating lets the cache exceed the bound it exists to keep.
    Frames at or below the sample size are walked in full -- nothing to
    extrapolate from.
    """
    n = len(df)
    if n == 0 and len(df.columns) == 0:
        return 0
    shallow = int(df.memory_usage(deep=False).sum())
    obj_cols = [c for c in df.columns if df[c].dtype == object]
    if not obj_cols:
        return shallow
    if n <= _SIZE_SAMPLE_ROWS:
        return int(df.memory_usage(deep=True).sum())
    sample = df[obj_cols].sample(n=_SIZE_SAMPLE_ROWS, random_state=0)
    deep_s = int(sample.memory_usage(deep=True, index=False).sum())
    shallow_s = int(sample.memory_usage(deep=False, index=False).sum())
    # Bytes the strings themselves add per row, beyond the pointer that the
    # shallow figure already counts.
    payload_per_row = (deep_s - shallow_s) / _SIZE_SAMPLE_ROWS
    return int(shallow + payload_per_row * n * 1.05)


def get_frame(path: str) -> pd.DataFrame:
    """Load a dataset file through the memo. Every return value is a private
    deep copy -- callers may mutate freely, as they always could."""
    if not settings.frame_cache_enabled:
        return _parse(path)

    abspath = os.path.abspath(path)
    try:
        st = os.stat(abspath)
    except OSError:
        return _parse(path)  # missing file: let the parse raise the real error
    key = (abspath, st.st_mtime_ns, st.st_size)

    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
        else:
            waiter = _INFLIGHT.get(key)
            if waiter is None:
                _INFLIGHT[key] = threading.Event()  # this thread is the leader
    if hit is not None:
        return hit[0].copy(deep=True)

    if waiter is not None:
        # Another thread is already parsing this exact file version. Wait for
        # it, then serve from the cache -- or, if nothing got stored, parse
        # independently (no retry loop: see module docstring).
        waiter.wait(timeout=600)
        with _LOCK:
            hit = _CACHE.get(key)
            if hit is not None:
                _CACHE.move_to_end(key)
        return hit[0].copy(deep=True) if hit is not None else _parse(path)

    try:
        df = _parse(path)
    except BaseException:
        with _LOCK:
            ev = _INFLIGHT.pop(key, None)
        if ev is not None:
            ev.set()
        raise

    try:
        size = estimate_frame_bytes(df)
    except Exception:
        size = None  # unsizeable exotic frame: serve it uncached

    # The stored copy is made before taking the lock -- a deep copy of a large
    # frame is tens to hundreds of ms, far too long to hold the lock for.
    store = None
    if size is not None and size <= settings.frame_cache_max_total_bytes:
        store = df.copy(deep=True)

    global _TOTAL_BYTES
    with _LOCK:
        if store is not None:
            if key not in _CACHE:
                _CACHE[key] = (store, size)
                _TOTAL_BYTES += size
            _CACHE.move_to_end(key)
            while (_TOTAL_BYTES > settings.frame_cache_max_total_bytes
                   or len(_CACHE) > settings.frame_cache_max_frames):
                _, (_, evicted_size) = _CACHE.popitem(last=False)
                _TOTAL_BYTES -= evicted_size
        ev = _INFLIGHT.pop(key, None)
    if ev is not None:
        ev.set()
    return df


def clear_frame_cache() -> None:
    global _TOTAL_BYTES
    with _LOCK:
        _CACHE.clear()
        _TOTAL_BYTES = 0
