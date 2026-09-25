"""E07: a CSV in another dialect becomes the canonical one at upload, instead
of one garbage column or a UnicodeDecodeError naming a byte."""
import pandas as pd
import pytest

from app.core.config import settings
from app.services.csv_dialect import canonicalize_csv


def _write(tmp_path, data: bytes, name="f.csv"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


class TestCanonicalize:
    def test_a_canonical_file_is_left_byte_for_byte(self, tmp_path):
        body = 'city,amount\n"Cairo, Egypt",1.5\nGiza,2\n'.encode()
        p = _write(tmp_path, body)
        assert canonicalize_csv(p) is None
        assert p.read_bytes() == body

    def test_semicolons_and_decimal_commas(self, tmp_path):
        p = _write(tmp_path, "region;amount;code\nNorth;1,5;007\nSouth;2,25;010\n".encode())
        found = canonicalize_csv(p)
        assert found["separator"] == ";" and found["decimal_comma"] == ["amount"]
        df = pd.read_csv(p)
        assert list(df.columns) == ["region", "amount", "code"]
        assert df["amount"].tolist() == [1.5, 2.25]

    def test_a_windows_1256_arabic_export(self, tmp_path):
        p = _write(tmp_path, "المنطقة,القيمة\nالقاهرة,10\nالجيزة,20\n".encode("cp1256"))
        assert canonicalize_csv(p)["encoding"] == "cp1256"
        df = pd.read_csv(p)                  # plain UTF-8 read, as every reader does
        assert list(df.columns) == ["المنطقة", "القيمة"]
        assert df["المنطقة"].tolist() == ["القاهرة", "الجيزة"]

    def test_a_western_legacy_file_is_not_read_as_arabic(self, tmp_path):
        p = _write(tmp_path, "name,v\nCafé,1\nNaïve,2\n".encode("cp1252"))
        assert canonicalize_csv(p)["encoding"] == "cp1252"
        assert pd.read_csv(p)["name"].tolist() == ["Café", "Naïve"]

    def test_tabs_and_a_bom(self, tmp_path):
        p = _write(tmp_path, b"\xef\xbb\xbfa\tb\n1\t2\n")
        assert canonicalize_csv(p)["separator"] == "\t"
        assert list(pd.read_csv(p).columns) == ["a", "b"]    # no "﻿a"

    def test_a_late_legacy_byte_is_still_found(self, tmp_path):
        """Sampling the head would miss it; every later read would then fail."""
        rows = "".join(f"r{i},{i}\n" for i in range(20000))
        p = _write(tmp_path, ("k,v\n" + rows + "القاهرة,1\n").encode("cp1256"))
        assert canonicalize_csv(p)["encoding"] == "cp1256"
        assert pd.read_csv(p)["k"].iloc[-1] == "القاهرة"

    def test_a_comma_file_with_one_semicolon_text_column_stays_comma(self, tmp_path):
        body = b"a,note\n1,x;y\n2,z\n"
        p = _write(tmp_path, body)
        assert canonicalize_csv(p) is None and p.read_bytes() == body


@pytest.fixture
def uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def test_the_upload_endpoint_reads_a_semicolon_file_as_columns(client, two_orgs, auth_headers, uploads):
    r = await client.post("/api/v1/datasets",
                          files={"file": ("eu.csv", "region;amount\nNorth;1,5\nSouth;2,5\n".encode("cp1252"), "text/csv")},
                          data={"name": "EU", "description": ""}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    cols = {c["name"]: c["dtype"] for c in r.json()["columns"]}
    assert set(cols) == {"region", "amount"} and cols["amount"] == "numeric"


async def test_batch_append_canonicalizes_each_part(client, two_orgs, auth_headers, uploads):
    r = await client.post("/api/v1/datasets/batch",
                          files=[("files", ("x.csv", b"a;b\n1;2\n", "text/csv")),
                                 ("files", ("y.csv", b"a,b\n3,4\n", "text/csv"))],
                          data={"name": "M", "description": "", "mode": "append"}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ds = r.json()["items"][0]["dataset"]
    assert ds["row_count"] == 2 and {c["name"] for c in ds["columns"]} == {"a", "b"}
