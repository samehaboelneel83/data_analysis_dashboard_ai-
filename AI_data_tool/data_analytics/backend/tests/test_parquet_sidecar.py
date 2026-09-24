"""The parquet sidecar: a verified derived cache next to each CSV. The CSV
stays the source of truth; every test here guards one way the sidecar could
silently change what a CSV parse would have produced."""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.analytics import load_file
from app.services.frame_cache import (
    clear_frame_cache, remove_parquet_sidecar, write_parquet_sidecar,
)
from app.services.widget_data import clear_widget_data_cache, get_widget_data


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_frame_cache()
    clear_widget_data_cache()
    yield
    clear_frame_cache()
    clear_widget_data_cache()


TRICKY = pd.DataFrame({
    "d": ["2024-01-01", "2024-02-01", None, "2024-04-01"],
    "s": ["a", None, "c", "d"],
    "i": [1, 2, 3, 4],
    "f": [1.5, np.nan, 3.5, 4.5],
    "mixed_missing": ["x", "", None, "y"],
})


def _write_csv(path, df=TRICKY):
    df.to_csv(path, index=False)
    return str(path)


def test_sidecar_roundtrip_is_byte_identical_to_csv_parse(tmp_path):
    p = _write_csv(tmp_path / "t.csv")
    assert write_parquet_sidecar(p) is True
    via_csv = pd.read_csv(p)
    clear_frame_cache()
    via_sidecar = load_file(p)
    pd.testing.assert_frame_equal(via_csv, via_sidecar)
    assert list(via_csv.dtypes) == list(via_sidecar.dtypes)
    # the null-representation trap: object-column nulls must be float NaN,
    # never None, or astype(str) filters change meaning
    for c in via_sidecar.columns:
        if via_sidecar[c].dtype == object:
            for v in via_sidecar[c][via_sidecar[c].isna()]:
                assert isinstance(v, float)


def test_stale_sidecar_is_rejected(tmp_path):
    p = _write_csv(tmp_path / "t.csv")
    assert write_parquet_sidecar(p)
    time.sleep(0.02)
    _write_csv(tmp_path / "t.csv", pd.DataFrame({"only": [1, 2]}))  # CSV newer now
    clear_frame_cache()
    df = load_file(p)
    assert list(df.columns) == ["only"]


def test_fresh_sidecar_is_actually_used(tmp_path, monkeypatch):
    p = _write_csv(tmp_path / "t.csv")
    assert write_parquet_sidecar(p)
    clear_frame_cache()

    def boom(*a, **k):
        raise AssertionError("CSV was parsed despite a fresh sidecar")

    from app.services import analytics
    monkeypatch.setitem(analytics.SUPPORTED, ".csv", boom)
    df = load_file(p)
    assert list(df.columns) == list(TRICKY.columns)


def test_corrupt_sidecar_falls_back_to_csv(tmp_path):
    p = _write_csv(tmp_path / "t.csv")
    assert write_parquet_sidecar(p)
    with open(p + ".parquet", "wb") as f:
        f.write(b"this is not parquet")
    os.utime(p + ".parquet")  # still "fresh" -- freshness alone must not be trusted
    clear_frame_cache()
    df = load_file(p)
    pd.testing.assert_frame_equal(df, pd.read_csv(p))


def test_widget_battery_equal_with_and_without_sidecar(tmp_path):
    rows = pd.DataFrame({
        "region": ["N", "S", "N", "E"] * 25,
        "d": (["2024-01-05", "2024-02-05", None, "2024-03-05"] * 25),
        "rev": [10.0, np.nan, 30.0, 40.0] * 25,
    })
    p = _write_csv(tmp_path / "w.csv", rows)
    configs = [
        ("bar", {"dimension": "region", "measure": "rev", "aggregation": "sum"}),
        ("table", {"columns": ["region", "d", "rev"], "limit": 100}),
        ("bar", {"dimension": "region", "measure": "rev", "aggregation": "sum",
                 "filters": [{"column": "d", "op": "like", "value": "2024-01"}]}),
    ]
    baseline = [get_widget_data(p, c, widget_type=t, use_cache=False) for t, c in configs]
    assert write_parquet_sidecar(p)
    clear_frame_cache()
    with_sidecar = [get_widget_data(p, c, widget_type=t, use_cache=False) for t, c in configs]
    assert baseline == with_sidecar


def test_non_csv_gets_no_sidecar(tmp_path):
    p = tmp_path / "t.json"
    pd.DataFrame({"x": [1]}).to_json(p, orient="records")
    assert write_parquet_sidecar(str(p)) is False
    assert not os.path.exists(str(p) + ".parquet")


def test_remove_parquet_sidecar(tmp_path):
    p = _write_csv(tmp_path / "t.csv")
    assert write_parquet_sidecar(p)
    assert os.path.exists(p + ".parquet")
    remove_parquet_sidecar(p)
    assert not os.path.exists(p + ".parquet")
    remove_parquet_sidecar(p)  # idempotent


async def test_upload_creates_sidecar_and_delete_removes_it(
        client, auth_headers, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    csv_bytes = TRICKY.to_csv(index=False).encode()

    resp = await client.post(
        "/api/v1/datasets",
        files={"file": ("sidecar_e2e.csv", csv_bytes, "text/csv")},
        data={"name": "sidecar e2e"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200, resp.text
    ds = resp.json()
    # Derived from the response, not from the name we sent: the stored file is
    # UUID-named under a per-org directory so a client-supplied filename cannot
    # steer where bytes land. See services/upload_store.py.
    csv_path = Path(ds["filename"])
    assert csv_path.exists() and csv_path.suffix == ".csv"
    assert csv_path.parent.parent == tmp_path
    sidecar = Path(str(csv_path) + ".parquet")
    assert sidecar.exists()

    resp = await client.delete(f"/api/v1/datasets/{ds['id']}", headers=auth_headers["a"])
    assert resp.status_code == 204
    assert not csv_path.exists()
    assert not sidecar.exists()
