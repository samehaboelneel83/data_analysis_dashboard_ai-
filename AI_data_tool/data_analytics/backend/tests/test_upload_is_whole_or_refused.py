"""E07: an uploaded file becomes a dataset that can be used, or is refused and
leaves nothing behind -- no row, no bytes on disk."""
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.models import Dataset


@pytest.fixture
def uploads(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(root))
    return root


def _files_under(root):
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


async def _count(db_session):
    return (await db_session.execute(select(func.count()).select_from(Dataset))).scalar_one()


async def _upload(client, headers, body: bytes, name="f.csv"):
    return await client.post("/api/v1/datasets", files={"file": (name, body, "text/csv")},
                             data={"name": "Upload", "description": ""}, headers=headers)


async def test_a_file_over_the_row_cap_is_refused_at_the_door(
        client, db_session, two_orgs, auth_headers, uploads, monkeypatch):
    """It was accepted, and then every widget reading it refused: a dataset
    that looked ready and could never be used."""
    monkeypatch.setattr(settings, "import_row_cap", 5)
    before = await _count(db_session)
    body = b"id,v\n" + b"".join(b"%d,%d\n" % (i, i) for i in range(6))
    r = await _upload(client, auth_headers["a"], body)
    assert r.status_code == 400, r.text
    assert "more than the import limit of 5" in r.json()["detail"]
    assert await _count(db_session) == before
    assert _files_under(uploads) == []


async def test_at_the_cap_it_is_accepted(client, two_orgs, auth_headers, uploads, monkeypatch):
    monkeypatch.setattr(settings, "import_row_cap", 5)
    body = b"id,v\n" + b"".join(b"%d,%d\n" % (i, i) for i in range(5))
    r = await _upload(client, auth_headers["a"], body)
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 5


async def test_two_columns_differing_only_in_case_are_named_and_refused(
        client, db_session, two_orgs, auth_headers, uploads):
    before = await _count(db_session)
    r = await _upload(client, auth_headers["a"], b"Unit,unit,v\nkg,ward,1\n")
    assert r.status_code == 400, r.text
    assert "'Unit'" in r.json()["detail"] or "'unit'" in r.json()["detail"]
    assert await _count(db_session) == before
    assert _files_under(uploads) == []


async def test_an_oversized_file_stops_being_written_at_the_limit(
        client, two_orgs, auth_headers, uploads, monkeypatch):
    """The whole stream used to be written first and measured afterwards."""
    import builtins
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    real_open, peak = builtins.open, []

    class Watch:
        def __init__(self, f): self.f, self.n = f, 0
        def write(self, b):
            self.n += len(b)
            peak.append(self.n)
            return self.f.write(b)
        def __enter__(self): return self
        def __exit__(self, *a): return self.f.__exit__(*a)

    def spy(path, mode="r", *a, **k):
        f = real_open(path, mode, *a, **k)
        return Watch(f) if "w" in mode and "b" in mode and str(uploads) in str(path) else f

    monkeypatch.setattr(builtins, "open", spy)
    body = b"id,v\n" + b"1,2\n" * (3 * 1024 * 1024 // 4)   # ~3 MB
    r = await _upload(client, auth_headers["a"], body)
    monkeypatch.setattr(builtins, "open", real_open)
    assert r.status_code == 400 and "MB limit" in r.json()["detail"]
    assert max(peak) <= 1024 * 1024
    assert _files_under(uploads) == []


# ── batch uploads: every file gets its own true outcome ─────────────────────

async def _batch(client, headers, files, mode):
    return await client.post("/api/v1/datasets/batch", files=[("files", f) for f in files],
                             data={"name": "B", "description": "", "mode": mode}, headers=headers)


GOOD = ("good.csv", b"a,b\n1,2\n", "text/csv")
EMPTY = ("empty.csv", b"a,b\n", "text/csv")


async def test_append_mode_checks_each_file_like_a_single_upload(
        client, db_session, two_orgs, auth_headers, uploads):
    """A header-only file joined the merge; it is now that file's error."""
    r = await _batch(client, auth_headers["a"], [GOOD, EMPTY], "append")
    assert r.status_code == 200, r.text
    by = {i["source_filename"]: i for i in r.json()["items"]}
    assert by["good.csv"]["status"] == "created" and by["good.csv"]["dataset"]
    assert by["empty.csv"]["status"] == "error" and "no data rows" in by["empty.csv"]["error"]


async def test_append_mode_an_unreadable_file_is_its_own_error_not_a_500(
        client, two_orgs, auth_headers, uploads):
    bad = ("bad.xlsx", b"this is not a workbook", "application/octet-stream")
    r = await _batch(client, auth_headers["a"], [GOOD, bad], "append")
    assert r.status_code == 200, r.text
    by = {i["source_filename"]: i for i in r.json()["items"]}
    assert by["bad.xlsx"]["status"] == "error" and "Could not read" in by["bad.xlsx"]["error"]
    assert by["good.csv"]["status"] == "created"


async def test_append_mode_says_no_file_was_created_when_the_merge_is_refused(
        client, db_session, two_orgs, auth_headers, uploads, monkeypatch):
    """Each file passed alone; together they pass the row cap. Every file said
    "created" before the merge had run -- and no dataset existed."""
    monkeypatch.setattr(settings, "import_row_cap", 3)
    before = await _count(db_session)
    two = b"a\n1\n2\n"
    r = await _batch(client, auth_headers["a"], [("x.csv", two, "text/csv"), ("y.csv", two, "text/csv")], "append")
    assert r.status_code == 400, r.text
    items = r.json()["detail"]["items"]
    assert [i["status"] for i in items] == ["error", "error"]
    assert all("combined data has 4 rows" in i["error"] for i in items)
    assert await _count(db_session) == before


async def test_append_mode_unions_unit_and_Unit_only_by_refusing(
        client, two_orgs, auth_headers, uploads):
    r = await _batch(client, auth_headers["a"], [("x.csv", b"Unit\nkg\n", "text/csv"),
                                                 ("y.csv", b"unit\nward\n", "text/csv")], "append")
    assert r.status_code == 400, r.text
    assert all("more than one column named" in i["error"] for i in r.json()["detail"]["items"])


async def test_separate_mode_an_unexpected_failure_is_one_files_outcome(
        client, two_orgs, auth_headers, uploads, monkeypatch):
    """It escaped as a 500: the files already committed went unreported and
    the ones after it were never tried."""
    import app.routers.datasets as ds_router
    real = ds_router.detect_types

    def boom(df):
        if "boom" in df.columns:
            raise RuntimeError("type detection broke")
        return real(df)

    monkeypatch.setattr(ds_router, "detect_types", boom)
    r = await _batch(client, auth_headers["a"], [GOOD, ("b.csv", b"boom\n1\n", "text/csv"),
                                                 ("c.csv", b"z\n3\n", "text/csv")], "separate")
    assert r.status_code == 200, r.text
    assert [i["status"] for i in r.json()["items"]] == ["created", "error", "created"]
    assert "type detection broke" in r.json()["items"][1]["error"]
    assert not [p for p in _files_under(uploads) if "boom" in p.read_text(errors="ignore")]
