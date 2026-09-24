"""Multi-file upload: one dataset per file, or all of them appended into one.

The singular `POST /datasets` is left exactly as it was -- FastAPI cannot make
one parameter both `UploadFile` and `list[UploadFile]`, and the whole suite binds
that contract -- so this is a separate endpoint, and one test here pins that the
old one did not change shape.
"""
from pathlib import Path

import pytest

from app.core.config import settings as app_settings


def _csv(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode()


A = _csv("a,b", "1,2", "3,4")
B = _csv("a,b", "5,6")


async def _batch(client, headers, files, name="batch", mode="separate"):
    return await client.post(
        "/api/v1/datasets/batch",
        files=[("files", f) for f in files],
        data={"name": name, "description": "", "mode": mode},
        headers=headers,
    )


@pytest.fixture(autouse=True)
def _isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    return tmp_path


class TestSeparateMode:
    @pytest.mark.asyncio
    async def test_one_dataset_per_file(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"], [
            ("one.csv", A, "text/csv"),
            ("two.csv", B, "text/csv"),
            ("three.csv", A, "text/csv"),
        ])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 3 and body["failed"] == 0
        ids = {i["dataset"]["id"] for i in body["items"]}
        assert len(ids) == 3, "files shared a dataset"

    @pytest.mark.asyncio
    async def test_each_dataset_is_named_after_its_file(self, client, auth_headers):
        """Twenty datasets all called "Q3" would be indistinguishable in the
        list, so each file's stem is appended."""
        resp = await _batch(client, auth_headers["a"], [
            ("sales.csv", A, "text/csv"), ("costs.csv", B, "text/csv"),
        ], name="Q3")
        names = {i["dataset"]["name"] for i in resp.json()["items"]}
        assert names == {"Q3 — sales", "Q3 — costs"}

    @pytest.mark.asyncio
    async def test_a_stem_the_base_already_is_does_not_repeat(self, client, auth_headers):
        """The uploader seeds the base from what the files share, so the file
        the prefix came from would otherwise be named "qa_sample — qa_sample".
        The others still carry their own stem."""
        resp = await _batch(client, auth_headers["a"], [
            ("qa_sample.csv", A, "text/csv"), ("qa_sample2.csv", B, "text/csv"),
        ], name="qa_sample")
        names = {i["dataset"]["name"] for i in resp.json()["items"]}
        assert names == {"qa_sample", "qa_sample — qa_sample2"}

    @pytest.mark.asyncio
    async def test_a_single_file_keeps_the_name_the_user_typed(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"],
                            [("sales.csv", A, "text/csv")], name="Q3")
        assert resp.json()["items"][0]["dataset"]["name"] == "Q3"

    @pytest.mark.asyncio
    async def test_partial_failure_reports_per_file_and_keeps_the_good_ones(
            self, client, auth_headers):
        """The reason the response is a list rather than one verdict: one bad
        file in a folder of ten must not discard the nine that parsed."""
        resp = await _batch(client, auth_headers["a"], [
            ("good1.csv", A, "text/csv"),
            ("bad.txt", b"not a table", "text/plain"),
            ("good2.csv", B, "text/csv"),
        ])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 2 and body["failed"] == 1

        bad = next(i for i in body["items"] if i["status"] == "error")
        assert bad["source_filename"] == "bad.txt"
        assert "Unsupported file type" in bad["error"]
        assert bad["dataset"] is None

    @pytest.mark.asyncio
    async def test_when_every_file_fails_the_request_is_a_400(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"], [
            ("a.txt", b"x", "text/plain"), ("b.txt", b"y", "text/plain"),
        ])
        assert resp.status_code == 400
        body = resp.json()["detail"]
        assert body["created"] == 0 and body["failed"] == 2

    @pytest.mark.asyncio
    async def test_more_files_than_the_ceiling_is_rejected(
            self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(app_settings, "max_upload_files", 2)
        resp = await _batch(client, auth_headers["a"], [
            ("a.csv", A, "text/csv"), ("b.csv", A, "text/csv"),
            ("c.csv", A, "text/csv"),
        ])
        assert resp.status_code == 400
        assert "At most 2 files" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_an_unknown_mode_is_rejected(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"],
                            [("a.csv", A, "text/csv")], mode="sideways")
        assert resp.status_code == 400


class TestAppendMode:
    @pytest.mark.asyncio
    async def test_files_become_one_dataset(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"], [
            ("jan.csv", A, "text/csv"), ("feb.csv", B, "text/csv"),
        ], mode="append")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "append"
        ids = {i["dataset"]["id"] for i in body["items"] if i["dataset"]}
        assert len(ids) == 1, "append produced more than one dataset"
        assert body["items"][0]["dataset"]["row_count"] == 3   # 2 + 1

    @pytest.mark.asyncio
    async def test_columns_are_unioned_and_null_filled(self, client, auth_headers):
        """Not "identical headers required": monthly extracts routinely gain a
        trailing column, and refusing those would make append useless for the
        case it exists for."""
        resp = await _batch(client, auth_headers["a"], [
            ("jan.csv", _csv("a,b", "1,2"), "text/csv"),
            ("feb.csv", _csv("a,c", "3,4"), "text/csv"),
        ], mode="append")
        ds = resp.json()["items"][0]["dataset"]
        assert ds["col_count"] == 3
        assert {c["name"] for c in ds["columns"]} == {"a", "b", "c"}
        # b is present only in jan, so half the rows are missing it
        b = next(c for c in ds["columns"] if c["name"] == "b")
        assert b["missing_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_a_dtype_conflict_does_not_500(self, client, auth_headers):
        """int in one file, text in another. pandas coerces to object and
        detect_types reports it as text -- lossy but correct, and far better
        than guessing which file's type was meant."""
        resp = await _batch(client, auth_headers["a"], [
            ("a.csv", _csv("qty", "1", "2"), "text/csv"),
            ("b.csv", _csv("qty", "many"), "text/csv"),
        ], mode="append")
        assert resp.status_code == 200, resp.text
        ds = resp.json()["items"][0]["dataset"]
        qty = next(c for c in ds["columns"] if c["name"] == "qty")
        assert qty["dtype"] in ("text", "categorical")

    @pytest.mark.asyncio
    async def test_an_unreadable_file_is_skipped_not_fatal(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"], [
            ("good.csv", A, "text/csv"), ("bad.txt", b"x", "text/plain"),
        ], mode="append")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 1 and body["failed"] == 1

    @pytest.mark.asyncio
    async def test_zero_readable_files_is_a_400(self, client, auth_headers):
        resp = await _batch(client, auth_headers["a"], [
            ("a.txt", b"x", "text/plain"),
        ], mode="append")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_only_the_combined_file_is_kept_on_disk(
            self, client, auth_headers, _isolated_uploads):
        """The parts are parsed from temp paths and discarded, so the stored
        bytes match the dataset exactly and nothing is counted twice against
        the storage quota."""
        resp = await _batch(client, auth_headers["a"], [
            ("jan.csv", A, "text/csv"), ("feb.csv", B, "text/csv"),
        ], mode="append")
        stored = Path(resp.json()["items"][0]["dataset"]["filename"])
        csvs = list(_isolated_uploads.rglob("*.csv"))
        assert csvs == [stored], f"leftover part files: {csvs}"


class TestTheSingularEndpointIsUnchanged:
    @pytest.mark.asyncio
    async def test_it_still_returns_one_dataset_object(self, client, auth_headers):
        """A regression pin: the batch work extracted a shared helper out of
        this endpoint, and its response must be byte-identical in shape."""
        resp = await client.post(
            "/api/v1/datasets",
            files={"file": ("solo.csv", A, "text/csv")},
            data={"name": "solo", "description": "d"},
            headers=auth_headers["a"],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, dict) and "items" not in body
        assert body["name"] == "solo" and body["description"] == "d"
        assert body["row_count"] == 2 and body["col_count"] == 2
        assert {c["name"] for c in body["columns"]} == {"a", "b"}
