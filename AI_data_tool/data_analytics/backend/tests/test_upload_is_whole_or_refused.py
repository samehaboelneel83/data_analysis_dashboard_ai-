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
