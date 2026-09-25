"""E07: one timezone policy for every stored instant.

Offset-carrying timestamps are stored as wall-clock time in ONE reference zone
(settings.data_timezone). Before: a column with two offsets (a timestamptz
across Egypt's DST change, a CSV from two regions) was typed "datetime" but
held objects, and every date chart on it failed."""
import pandas as pd
import pytest

from app.core.config import settings
from app.services.ingest import detect_types
from app.services.timezones import normalize_instants


class TestNormalize:
    def test_two_offsets_become_one_usable_datetime_column(self):
        df = pd.DataFrame({"at": ["2026-03-01T10:00:00+02:00", "2026-07-01T10:00:00+03:00",
                                  "2026-07-01T07:00:00Z", None]})
        assert normalize_instants(df, "UTC") == ["at"]
        assert str(df["at"].dtype) == "datetime64[ns]"
        assert df["at"].dt.hour.dropna().tolist() == [8, 7, 7]
        assert detect_types(df)["at"] == "datetime"

    def test_the_reference_zone_decides_the_wall_clock(self):
        df = pd.DataFrame({"at": ["2026-03-01T23:30:00+00:00"]})
        normalize_instants(df, "Africa/Cairo")
        assert df["at"].iloc[0] == pd.Timestamp("2026-03-02 01:30")     # the next day in Cairo

    def test_a_tz_aware_frame_from_a_driver(self):
        at = pd.to_datetime(["2026-03-01 10:00", "2026-08-01 10:00"]).tz_localize("Africa/Cairo")
        df = pd.DataFrame({"at": at})
        normalize_instants(df, "UTC")
        assert df["at"].tolist() == [pd.Timestamp("2026-03-01 08:00"), pd.Timestamp("2026-08-01 07:00")]

    def test_timestamps_without_an_offset_are_never_touched(self):
        df = pd.DataFrame({"at": ["2026-03-01 10:00:00", "2026-03-02 11:00:00"], "n": ["a-01", "b-02"]})
        before = df.copy()
        assert normalize_instants(df, "Africa/Cairo") == []
        pd.testing.assert_frame_equal(df, before)

    def test_stored_plain_rows_beside_new_aware_rows_are_merged_correctly(self):
        """An incremental refresh: the file holds plain reference-zone times,
        the source returns aware ones."""
        df = pd.DataFrame({"at": ["2026-03-01 08:00:00", pd.Timestamp("2026-03-02 12:00", tz="Africa/Cairo")]})
        normalize_instants(df, "UTC")
        assert df["at"].tolist() == [pd.Timestamp("2026-03-01 08:00"), pd.Timestamp("2026-03-02 10:00")]

    def test_text_that_only_looks_like_an_offset_is_left_alone(self):
        df = pd.DataFrame({"code": ["10:00 Z-shift", "not a date +02:00"]})
        normalize_instants(df, "UTC")
        assert df["code"].tolist() == ["10:00 Z-shift", "not a date +02:00"]


@pytest.fixture
def uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def test_an_upload_with_mixed_offsets_is_stored_in_the_reference_zone(
        client, two_orgs, auth_headers, uploads, monkeypatch):
    monkeypatch.setattr(settings, "data_timezone", "Africa/Cairo")
    body = b"at,v\n2026-03-01T22:30:00Z,1\n2026-07-01T10:00:00+03:00,2\n"
    r = await client.post("/api/v1/datasets", files={"file": ("t.csv", body, "text/csv")},
                          data={"name": "T", "description": ""}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert {c["name"]: c["dtype"] for c in r.json()["columns"]}["at"] == "datetime"
    stored = pd.read_csv(r.json()["filename"])["at"].tolist()
    assert stored == ["2026-03-02 00:30:00", "2026-07-01 10:00:00"]   # no offsets on disk


async def test_a_json_upload_with_offsets_is_stored_as_normalised_csv(client, two_orgs, auth_headers, uploads):
    body = b'[{"at": "2026-03-01T10:00:00+02:00", "v": 1}, {"at": "2026-07-01T10:00:00+03:00", "v": 2}]'
    r = await client.post("/api/v1/datasets", files={"file": ("t.json", body, "application/json")},
                          data={"name": "J", "description": ""}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["filename"].endswith(".csv")
    assert pd.read_csv(r.json()["filename"])["at"].tolist() == ["2026-03-01 08:00:00", "2026-07-01 07:00:00"]


class TestIncrementalCursor:
    def test_the_watermark_keeps_its_instant(self, tmp_path, monkeypatch):
        """The stored column is plain time in the reference zone; the cursor
        goes back to the SOURCE and must name the same instant."""
        import sqlite3
        from app.services import dataset_refresh as R
        monkeypatch.setattr(settings, "data_timezone", "Africa/Cairo")
        db = tmp_path / "s.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (id INTEGER, at TEXT)")
        conn.executemany("INSERT INTO t VALUES (?, ?)",
                         [(1, "2026-03-01T08:00:00+00:00"), (2, "2026-03-01T09:00:00+00:00")])
        conn.commit()
        conn.close()
        cfg = {"type": "sqlite", "filepath": str(db)}
        out = R.refresh_dataset(cfg, str(tmp_path / "d.csv"), "t", None, "full", "at", None)
        assert out["cursor_value"] == "2026-03-01T11:00:00+02:00"      # 09:00Z, as Cairo time
        assert pd.read_csv(tmp_path / "d.csv")["at"].tolist() == ["2026-03-01 10:00:00", "2026-03-01 11:00:00"]
