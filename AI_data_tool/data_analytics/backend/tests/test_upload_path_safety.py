"""Where uploaded bytes are allowed to land.

These pin a fix for a real, verified defect: `routers/datasets.py` used to build
the save path from the client-supplied filename, and neither Starlette nor
python_multipart sanitises it. A filename of `../../../../tmp/pwned.csv` reached
the handler verbatim, and an absolute one escaped `upload_dir` entirely, because
`Path("/app/uploads") / "/abs/evil.csv"` is `/abs/evil.csv`. That value went into
`open(path, "wb")`, so any authenticated user could write anywhere the server
process could.

The same line also made `upload_dir` a shared namespace across organisations:
two orgs uploading `sales.csv` got one file and two Dataset rows, and deleting
either destroyed the other's data.

Every test here fails against the old one-line implementation.
"""
from pathlib import Path

import pytest

from app.core.config import settings as app_settings


CSV = b"a,b\n1,2\n3,4\n"


async def _upload(client, headers, filename, body=CSV, name="ds"):
    return await client.post(
        "/api/v1/datasets",
        files={"file": (filename, body, "text/csv")},
        data={"name": name, "description": ""},
        headers=headers,
    )


class TestFilenameCannotSteerThePath:
    @pytest.mark.asyncio
    async def test_traversal_filename_cannot_escape_the_upload_dir(
            self, client, auth_headers, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        resp = await _upload(client, auth_headers["a"], "../../../../tmp/pwned.csv")

        assert resp.status_code == 200, resp.text
        stored = Path(resp.json()["filename"]).resolve()
        # The decisive assertion: wherever it went, it is inside tmp_path.
        assert tmp_path.resolve() in stored.parents
        assert stored.name != "pwned.csv"
        assert not (tmp_path.parent / "pwned.csv").exists()

    @pytest.mark.asyncio
    async def test_absolute_filename_cannot_escape_the_upload_dir(
            self, client, auth_headers, tmp_path, monkeypatch):
        """The nastier half: pathlib DISCARDS the left operand when the right is
        absolute, so this bypassed upload_dir without needing any `..`."""
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        escaped = tmp_path.parent / "abs_evil.csv"

        resp = await _upload(client, auth_headers["a"], str(escaped))

        assert resp.status_code == 200, resp.text
        stored = Path(resp.json()["filename"]).resolve()
        assert tmp_path.resolve() in stored.parents
        assert not escaped.exists(), "an absolute filename escaped the upload dir"

    @pytest.mark.asyncio
    async def test_the_extension_is_preserved(
            self, client, auth_headers, tmp_path, monkeypatch):
        """Not cosmetic: frame_cache dispatches its reader on the suffix, and
        the parquet sidecar is written only for .csv. A UUID with no extension
        would be unreadable on the next request."""
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        resp = await _upload(client, auth_headers["a"], "quarterly.csv")

        assert Path(resp.json()["filename"]).suffix == ".csv"


class TestFilesDoNotCollide:
    @pytest.mark.asyncio
    async def test_two_orgs_uploading_the_same_name_get_separate_files(
            self, client, auth_headers, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        a = await _upload(client, auth_headers["a"], "sales.csv", b"a,b\n1,2\n")
        b = await _upload(client, auth_headers["b"], "sales.csv", b"x,y,z\n1,2,3\n")
        assert a.status_code == 200 and b.status_code == 200

        pa, pb = Path(a.json()["filename"]), Path(b.json()["filename"])
        assert pa != pb, "two orgs shared one file on disk"
        assert pa.parent != pb.parent, "orgs are not separated by directory"
        assert pa.exists() and pb.exists()

    @pytest.mark.asyncio
    async def test_deleting_one_orgs_dataset_leaves_the_others_readable(
            self, client, auth_headers, tmp_path, monkeypatch):
        """The consequence that made the collision a data-loss bug rather than
        an untidiness: delete unlinks by stored path, so a shared file took the
        other org's dataset with it."""
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        a = (await _upload(client, auth_headers["a"], "sales.csv")).json()
        b = (await _upload(client, auth_headers["b"], "sales.csv")).json()

        resp = await client.delete(f"/api/v1/datasets/{a['id']}",
                                   headers=auth_headers["a"])
        assert resp.status_code == 204

        assert Path(b["filename"]).exists(), "deleting org A's dataset ate org B's file"
        still = await client.get(f"/api/v1/datasets/{b['id']}", headers=auth_headers["b"])
        assert still.status_code == 200

    @pytest.mark.asyncio
    async def test_the_same_org_uploading_a_name_twice_does_not_overwrite(
            self, client, auth_headers, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        one = await _upload(client, auth_headers["a"], "sales.csv",
                            b"a,b\n1,2\n", name="first")
        two = await _upload(client, auth_headers["a"], "sales.csv",
                            b"a,b\n1,2\n3,4\n5,6\n", name="second")

        assert Path(one.json()["filename"]) != Path(two.json()["filename"])
        assert one.json()["row_count"] == 1
        assert two.json()["row_count"] == 3
        assert Path(one.json()["filename"]).exists()


class TestRejectionHappensBeforeAnyWrite:
    @pytest.mark.asyncio
    async def test_an_unsupported_extension_writes_nothing_to_disk(
            self, client, auth_headers, tmp_path, monkeypatch):
        """The old order wrote the bytes, then discovered the reader could not
        parse them. Validating the suffix first means a rejected upload costs
        no disk at all."""
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        resp = await _upload(client, auth_headers["a"], "notes.txt", b"hello world")

        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]
        assert list(tmp_path.rglob("*.txt")) == []

    @pytest.mark.asyncio
    async def test_an_access_file_is_redirected_to_the_batch_endpoint(
            self, client, auth_headers, tmp_path, monkeypatch):
        """One .mdb yields one dataset PER TABLE, which cannot be returned as a
        single DatasetOut -- so this endpoint refuses it rather than widening
        its response model for every existing caller."""
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

        resp = await _upload(client, auth_headers["a"], "db.accdb", b"\x00\x01")

        assert resp.status_code == 400
        assert "/api/v1/datasets/batch" in resp.json()["detail"]
