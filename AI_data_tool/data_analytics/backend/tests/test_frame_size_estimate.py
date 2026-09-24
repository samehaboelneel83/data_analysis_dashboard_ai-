"""Sizing a frame for the memo without walking every string in it.

`get_frame` has to know how big a frame is to decide whether it fits
`frame_cache_max_total_bytes`. It asked pandas for `memory_usage(deep=True)`,
which visits every Python object in every object column. Measured 2026-09-12
on a 1M-row, 11-text-column frame: **2.21s of a 3.2s cold render** was that
one call. The read itself was 0.49s.

The number only has to be good enough to keep the cache inside its bound. So:
exact for numeric columns (pandas already knows), and for object columns a
sample of rows scaled up. Over-estimating is the safe direction -- it evicts a
little early -- so the estimate is padded, and the tests check it never lands
materially UNDER the true figure.
"""
import time

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.services.frame_cache import clear_frame_cache, estimate_frame_bytes, get_frame


@pytest.fixture(autouse=True)
def _fresh():
    clear_frame_cache()
    yield
    clear_frame_cache()


def _mixed(rows: int, seed: int = 7) -> pd.DataFrame:
    """Numeric columns plus text of varied length, the shape of a real upload."""
    rng = np.random.default_rng(seed)
    lengths = rng.integers(3, 40, size=rows)
    return pd.DataFrame({
        "n1": rng.normal(size=rows),
        "n2": rng.integers(0, 1000, size=rows),
        "short": rng.choice(["N", "S", "E", "W"], size=rows),
        "long": ["x" * int(k) for k in lengths],
        "nullable": [None if i % 5 == 0 else f"v{i}" for i in range(rows)],
    })


def test_numeric_only_frame_is_sized_exactly():
    df = pd.DataFrame({"a": np.arange(1000.0), "b": np.arange(1000)})
    assert estimate_frame_bytes(df) == int(df.memory_usage(deep=True).sum())


def test_empty_frame():
    assert estimate_frame_bytes(pd.DataFrame()) == 0


def test_estimate_is_close_to_the_deep_figure_and_never_much_under():
    df = _mixed(60_000)
    deep = int(df.memory_usage(deep=True).sum())
    est = estimate_frame_bytes(df)
    # Never more than 5% under: under-estimating lets the cache exceed its
    # bound, which is the one thing the number exists to prevent.
    assert est >= deep * 0.95, (est, deep)
    # And not wildly over, or nothing large would ever be cached.
    assert est <= deep * 1.30, (est, deep)


def test_a_small_frame_is_walked_in_full():
    """Below the sample size there is nothing to extrapolate; the figure
    should simply be the true one."""
    df = _mixed(500)
    assert estimate_frame_bytes(df) == int(df.memory_usage(deep=True).sum())


def test_sizing_does_not_scale_with_row_count():
    """The whole point. The deep walk is linear in rows × object columns;
    the estimate must not be.

    A timing assertion, so the bound is loose: the deep walk on this frame
    takes ~0.5s on the dev box, the estimate a few milliseconds. 0.25s is a
    10x margin over the estimate and still 2x under the walk it replaces."""
    df = _mixed(300_000)
    t0 = time.perf_counter()
    estimate_frame_bytes(df)
    took = time.perf_counter() - t0
    assert took < 0.25, f"sizing took {took:.2f}s -- is it still walking every string?"


def test_get_frame_still_refuses_to_cache_an_oversized_frame(tmp_path, monkeypatch):
    """The estimate feeds the same decision as before; the bound still holds."""
    monkeypatch.setattr(settings, "frame_cache_max_total_bytes", 10)
    p = tmp_path / "big.csv"
    pd.DataFrame([{"x": 1, "y": "hello"}]).to_csv(p, index=False)
    get_frame(str(p))
    from app.services import frame_cache
    assert len(frame_cache._CACHE) == 0


def test_get_frame_bookkeeping_uses_the_estimate(tmp_path):
    p = tmp_path / "m.csv"
    _mixed(2_000).to_csv(p, index=False)
    df = get_frame(str(p))
    from app.services import frame_cache
    (_, stored_size), = frame_cache._CACHE.values()
    assert stored_size == estimate_frame_bytes(df)
