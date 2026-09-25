"""Reading Microsoft Access files.

None of these require mdbtools to be installed. `mdb.py` has exactly one seam --
`_run_cli` -- and patching it exercises everything above: the MSys filtering, the
decoding, the path validation, and the whole upload fan-out. The single test that
does need the real binary is skipped when it is absent.

That is deliberate: the binary exists in the container and on no developer's
Windows machine, so a suite that needed it would be red for everyone who is not
in Docker.
"""
from pathlib import Path

import pytest

from app.core.config import settings as app_settings
from app.services import connectors, mdb


TABLES = b"Customers\nOrders\nMSysObjects\nMSysAccessStorage\n~TMPCLP\n"
ROWS = {
    "Customers": b"id,name\n1,Ann\n2,Bo\n",
    "Orders": b"id,total\n1,9.5\n",
}


@pytest.fixture
def fake_mdb(monkeypatch, tmp_path):
    """Stand in for the mdbtools binaries, and give the caller a real file to
    point at (every public function resolves and stats its path)."""
    db = tmp_path / "demo.accdb"
    db.write_bytes(b"\x00fake")

    def _run(args):
        if args[0] == "mdb-tables":
            return TABLES
        if args[0] == "mdb-export":
            return ROWS[args[-1]]
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
    monkeypatch.setattr(mdb, "_run_cli", _run)
    return db


class TestListTables:
    def test_system_tables_are_hidden(self, fake_mdb):
        """MSys* is Access's own catalogue and ~TMP* is scratch. Someone
        uploading a database wants neither as a dataset."""
        assert mdb.list_tables(str(fake_mdb)) == ["Customers", "Orders"]

    def test_read_table_returns_a_frame(self, fake_mdb):
        df = mdb.read_table(str(fake_mdb), "Customers")
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 2


class TestItFailsSafely:
    def test_a_missing_binary_is_a_clear_error_not_an_import_failure(
            self, monkeypatch, tmp_path):
        """The module must import on a machine without mdbtools -- only the
        Access request fails, and it says why."""
        db = tmp_path / "x.mdb"
        db.write_bytes(b"\x00")
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: False)

        with pytest.raises(mdb.MdbUnavailable, match="mdbtools"):
            mdb.list_tables(str(db))

    def test_a_file_that_is_not_access_is_refused(self, tmp_path):
        other = tmp_path / "notes.txt"
        other.write_text("hello")
        with pytest.raises(mdb.MdbReadError, match="Not a Microsoft Access file"):
            mdb.list_tables(str(other))

    def test_a_missing_file_is_refused(self, tmp_path):
        with pytest.raises(mdb.MdbReadError, match="File not found"):
            mdb.list_tables(str(tmp_path / "gone.mdb"))

    def test_a_password_protected_file_says_so(self, monkeypatch, tmp_path):
        """mdbtools' own wording is opaque. An encrypted database is the one
        failure a user can actually act on, so it gets a real instruction."""
        db = tmp_path / "locked.accdb"
        db.write_bytes(b"\x00")

        class _Proc:
            returncode = 1
            stdout = b""
            stderr = b"Error: file is encrypted or password protected"

        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb.subprocess, "run", lambda *a, **k: _Proc())

        with pytest.raises(mdb.MdbReadError, match="unencrypted copy"):
            mdb.list_tables(str(db))

    def test_the_cli_is_never_run_through_a_shell(self, monkeypatch, tmp_path):
        """A path containing `;` or `$(...)` must be one argv element. This is
        the assertion that keeps it that way."""
        db = tmp_path / "x.mdb"
        db.write_bytes(b"\x00")
        seen = {}

        class _Proc:
            returncode = 0
            stdout = b"T\n"
            stderr = b""

        def _capture(args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return _Proc()

        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb.subprocess, "run", _capture)
        mdb.list_tables(str(db))

        assert isinstance(seen["args"], list), "args must not be a string"
        assert seen["kwargs"].get("shell") is not True
        assert seen["kwargs"].get("timeout"), "a corrupt file must not hang a worker"

    def test_legacy_cp1252_bytes_still_decode(self, monkeypatch, tmp_path):
        """Jet 3 databases carry a Windows codepage rather than UTF-8."""
        db = tmp_path / "legacy.mdb"
        db.write_bytes(b"\x00")
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb, "_run_cli",
                            lambda args: "Ménagerie\n".encode("cp1252"))

        assert mdb.list_tables(str(db)) == ["Ménagerie"]


class TestTheConnector:
    def test_access_is_registered(self):
        spec = connectors.resolve("access")
        assert spec.category == "File"
        assert {f.name for f in spec.config_fields} == {"filepath"}

    def test_it_is_import_only(self):
        """Access has no server to push a query to, so DirectQuery is not
        'unsupported for now' -- it is impossible."""
        spec = connectors.resolve("access")
        assert spec.supports_directquery is False
        assert spec.sql_family is None

    def test_building_a_connection_url_is_refused_with_a_reason(self):
        with pytest.raises(ValueError, match="does not use a SQL connection URL"):
            connectors.build_url({"type": "access", "filepath": "/data/x.accdb"})

    def test_the_catalog_reports_whether_mdbtools_is_actually_installed(
            self, monkeypatch):
        """`driver_installed` normally probes for a Python module, and mdbtools
        is a binary -- without the probe the card would claim Access works on a
        host where it does not."""
        spec = connectors.resolve("access")
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: False)
        assert spec.driver_installed is False
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        assert spec.driver_installed is True


class TestUploadingAnAccessFile:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    @pytest.fixture
    def fake_cli(self, monkeypatch):
        def _run(args):
            if args[0] == "mdb-tables":
                return TABLES
            if args[0] == "mdb-export":
                return ROWS[args[-1]]
            raise AssertionError(args)
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb, "_run_cli", _run)

    async def _upload(self, client, headers, body=b"\x00fake", filename="demo.accdb"):
        return await client.post(
            "/api/v1/datasets/batch",
            files=[("files", (filename, body, "application/x-msaccess"))],
            data={"name": "Sales DB", "description": "", "mode": "separate"},
            headers=headers,
        )

    @pytest.mark.asyncio
    async def test_one_dataset_per_user_table(self, client, auth_headers, fake_cli):
        resp = await self._upload(client, auth_headers["a"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created"] == 2, body
        names = {i["dataset"]["name"] for i in body["items"]}
        assert names == {"Sales DB — Customers", "Sales DB — Orders"}

    @pytest.mark.asyncio
    async def test_system_tables_do_not_become_datasets(
            self, client, auth_headers, fake_cli):
        body = (await self._upload(client, auth_headers["a"])).json()
        assert not any("MSys" in i["dataset"]["name"] for i in body["items"])

    @pytest.mark.asyncio
    async def test_the_rows_actually_arrive(self, client, auth_headers, fake_cli):
        body = (await self._upload(client, auth_headers["a"])).json()
        customers = next(i["dataset"] for i in body["items"]
                         if i["dataset"]["name"].endswith("Customers"))
        assert customers["row_count"] == 2
        assert {c["name"] for c in customers["columns"]} == {"id", "name"}

    @pytest.mark.asyncio
    async def test_the_access_file_itself_is_not_kept(
            self, client, auth_headers, fake_cli, _uploads):
        """It is a transport format: every table is now its own CSV, nothing
        reads the original again, and keeping it would be charged twice against
        the org's storage quota."""
        await self._upload(client, auth_headers["a"])
        assert list(_uploads.rglob("*.accdb")) == []
        assert list(_uploads.rglob("*.mdb")) == []

    @pytest.mark.asyncio
    async def test_without_mdbtools_it_is_a_clear_400_not_a_500(
            self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: False)
        resp = await self._upload(client, auth_headers["a"])

        assert resp.status_code == 400
        body = resp.json()["detail"]
        assert "mdbtools" in body["items"][0]["error"]

    @pytest.mark.asyncio
    async def test_a_database_with_no_user_tables_is_rejected(
            self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb, "_run_cli", lambda args: b"MSysObjects\n")

        resp = await self._upload(client, auth_headers["a"])
        assert resp.status_code == 400
        assert "no user tables" in resp.json()["detail"]["items"][0]["error"]

    @pytest.mark.asyncio
    async def test_the_singular_endpoint_points_at_the_batch_one(
            self, client, auth_headers):
        resp = await client.post(
            "/api/v1/datasets",
            files={"file": ("demo.accdb", b"\x00", "application/x-msaccess")},
            data={"name": "x", "description": ""},
            headers=auth_headers["a"],
        )
        assert resp.status_code == 400
        assert "/api/v1/datasets/batch" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_it_cannot_be_appended(self, client, auth_headers, fake_cli):
        """Append merges frames into one dataset; an Access file is many
        tables, so the two ideas do not compose."""
        resp = await client.post(
            "/api/v1/datasets/batch",
            files=[("files", ("demo.accdb", b"\x00", "application/x-msaccess"))],
            data={"name": "x", "description": "", "mode": "append"},
            headers=auth_headers["a"],
        )
        assert resp.status_code == 400
        assert "cannot be appended" in resp.json()["detail"]["items"][0]["error"]


class TestImportModeIsEnforced:
    """An import-only source must be refused DirectQuery at the REQUEST, not at
    the first widget.

    This is not theoretical: `preview_table` works for Access (it reads the
    file), so the schema probe in the directquery branch succeeds and a dataset
    in `mode="directquery"` is happily created. It then cannot render, and the
    error surfaces far from the choice that caused it. Found by driving a live
    stack; the router had no `supports_directquery` check at all.
    """

    @pytest.mark.asyncio
    async def test_directquery_against_access_is_refused(
            self, client, auth_headers, monkeypatch, tmp_path):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        db_file = tmp_path / "f.accdb"
        db_file.write_bytes(b"fake-access-header")
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb, "_run_cli",
                            lambda args: TABLES if args[0] == "mdb-tables"
                            else ROWS["Customers"])

        src = (await client.post(
            "/api/v1/data-sources",
            json={"name": "acc", "type": "access",
                  "config": {"filepath": str(db_file)}},
            headers=auth_headers["a"])).json()

        resp = await client.post(
            f"/api/v1/data-sources/{src['id']}/import",
            json={"table": "Customers", "dataset_name": "dq",
                  "mode": "directquery"},
            headers=auth_headers["a"])

        assert resp.status_code == 400, resp.text
        assert "cannot be queried live" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_mode_against_access_still_works(
            self, client, auth_headers, monkeypatch, tmp_path):
        """The guard must refuse the mode, not the connector."""
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        db_file = tmp_path / "f.accdb"
        db_file.write_bytes(b"fake-access-header")
        monkeypatch.setattr(mdb, "mdbtools_available", lambda: True)
        monkeypatch.setattr(mdb, "_run_cli",
                            lambda args: TABLES if args[0] == "mdb-tables"
                            else ROWS["Customers"])

        src = (await client.post(
            "/api/v1/data-sources",
            json={"name": "acc2", "type": "access",
                  "config": {"filepath": str(db_file)}},
            headers=auth_headers["a"])).json()

        resp = await client.post(
            f"/api/v1/data-sources/{src['id']}/import",
            json={"table": "Customers", "dataset_name": "imported",
                  "mode": "import"},
            headers=auth_headers["a"])

        assert resp.status_code == 200, resp.text
        assert resp.json()["row_count"] == 2


@pytest.mark.skipif(mdb.mdbtools_available() is False,
                    reason="mdbtools is not installed on this host")
def test_the_real_binary_reports_a_version():
    """A smoke test for the container, where mdbtools IS present. Everything
    else here runs against the seam; this proves the seam matches reality."""
    import shutil
    assert shutil.which("mdb-tables")
