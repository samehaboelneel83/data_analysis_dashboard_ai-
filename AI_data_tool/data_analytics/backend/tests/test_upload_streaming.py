"""A CSV upload too large to parse in memory becomes the dataset's parquet
file a chunk at a time (services/upload_stream.py)."""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import connections, upload_stream
from app.services import memory_guard as mg

N = 2300


@pytest.fixture(autouse=True)
def small(monkeypatch):
    monkeypatch.setattr(connections, "CHUNK_ROWS", 500)
    monkeypatch.setattr(mg, "free_bytes", lambda: 10 ** 12)


def frame():
    return pd.DataFrame({"id": range(N), "grp": [f"g{i % 7}" for i in range(N)],
                         "amount": [i * 1.5 if i % 50 else None for i in range(N)],
                         # whole numbers for two thousand rows, then text
                         "code": [str(i) if i < 2000 else f"x{i}" for i in range(N)],
                         "day": [f"2024-01-{1 + i % 28:02d}" for i in range(N)]})


def test_every_row_arrives_and_a_column_that_turns_to_text_keeps_every_value(tmp_path):
    src = tmp_path / "up.csv"
    frame().to_csv(src, index=False)
    out = tmp_path / "s"
    out.mkdir()
    got = upload_stream.csv_to_parquet(src, str(out))
    back = pd.read_parquet(got.path)
    assert got.rows == N == len(back) and back["id"].tolist() == list(range(N))
    assert got.missing["amount"] == round(100.0 * 46 / N, 2)
    assert back["code"].isna().sum() == 0 and back["code"].iloc[-1] == f"x{N - 1}"
    assert str(back["day"].dtype).startswith("datetime")              # dates typed as a small upload's are
    assert [p.name for p in out.iterdir()] == ["import.parquet"]


def test_semicolons_decimal_commas_and_an_old_encoding_are_read_as_they_are_for_a_small_file(tmp_path):
    src = tmp_path / "up.csv"
    df = pd.DataFrame({"name": ["é" + str(i) for i in range(N)], "amount": [f"{i},5" for i in range(N)]})
    df.to_csv(src, index=False, sep=";", encoding="cp1252")
    out = tmp_path / "s"
    out.mkdir()
    back = pd.read_parquet(upload_stream.csv_to_parquet(src, str(out)).path)
    assert back["name"].iloc[3] == "é3" and back["amount"].iloc[3] == 3.5 and back["amount"].iloc[-1] == N - 1 + 0.5


def test_only_a_large_csv_is_streamed_and_the_setting_switches_it_off(tmp_path, monkeypatch):
    src = tmp_path / "up.csv"
    frame().to_csv(src, index=False)
    monkeypatch.setattr(settings, "upload_stream_mb", 300, raising=False)
    assert not upload_stream.wanted(src, src.stat().st_size)
    assert upload_stream.wanted(src, 300 * 1024 * 1024)
    assert not upload_stream.wanted(tmp_path / "up.xlsx", 10 ** 10)
    # A file that would not fit parsed whole is streamed whatever its size...
    monkeypatch.setattr(mg, "check", lambda p: (_ for _ in ()).throw(mg.TooLargeToLoad(10, 1)))
    assert upload_stream.wanted(src, 10)
    # ...unless streaming is switched off.
    monkeypatch.setattr(settings, "upload_stream_mb", 0, raising=False)
    assert not upload_stream.wanted(src, 10 ** 12)


async def test_a_large_csv_uploaded_through_the_product_is_a_parquet_dataset_that_draws_charts(
        client, two_orgs, auth_headers, tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(upload_stream, "wanted", lambda path, size: str(path).endswith(".csv"))
    body = frame().to_csv(index=False).encode()
    r = await client.post("/api/v1/datasets/batch", files=[("files", ("big.csv", body, "text/csv"))],
                          data={"name": "big", "description": "", "mode": "separate"}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ds = r.json()["items"][0]["dataset"]
    assert ds["row_count"] == N and ds["col_count"] == 5
    kinds = {c["name"]: c["dtype"] for c in ds["columns"]}
    assert kinds["amount"] == "numeric" and kinds["day"] == "datetime"
    assert next(c for c in ds["columns"] if c["name"] == "amount")["missing_pct"] == 2.0
    # One file is kept: the parquet. The uploaded CSV and the working folder are gone.
    left = [f for _, _, fs in os.walk(tmp_path) for f in fs]
    assert len(left) == 1 and left[0].endswith(".parquet")
    w = await client.post(f"/api/v1/datasets/{ds['id']}/widget-data", headers=auth_headers["a"], json={
        "widget_type": "bar", "config": {"dimension": "grp", "measure": "amount", "aggregation": "sum"},
        "calculated_columns": [], "parameters": {}})
    assert w.status_code == 200 and len(w.json()["rows"]) == 7
    assert abs(sum(x["value"] for x in w.json()["rows"]) - frame()["amount"].sum()) < 1e-6
