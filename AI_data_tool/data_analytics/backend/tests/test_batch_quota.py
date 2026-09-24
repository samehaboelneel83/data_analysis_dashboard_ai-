"""Storage limits across a multi-file upload.

`quotas.enforce_storage_quota` sums `Dataset.file_size` over COMMITTED rows. That
is fine for one upload and quietly wrong for a batch: process N files in a loop
without committing and every one of them sees the same pre-batch total, so an org
can exceed its cap by (N-1) files.

The fix is committing per file inside the loop, which makes file k+1 see files
1..k. `test_the_quota_stops_the_batch_instead_of_being_overshot` fails against a
loop that commits once at the end -- that is the whole point of it.
"""
import pytest
from sqlalchemy import func, select

from app.core.config import settings as app_settings
from app.models.models import Dataset, Organization, Quota
from app.services import quotas


async def _ensure_org(db_session, org_id: int):
    if (await db_session.get(Organization, org_id)) is None:
        db_session.add(Organization(id=org_id, name=f"org{org_id}"))
        await db_session.flush()


async def _set_quota(db_session, org_id: int, **fields):
    await _ensure_org(db_session, org_id)
    db_session.add(Quota(org_id=org_id, **fields))
    await db_session.commit()
    quotas.invalidate_quota_cache(org_id)


async def _used_bytes(db_session, org_id: int) -> int:
    return (await db_session.execute(
        select(func.coalesce(func.sum(Dataset.file_size), 0))
        .where(Dataset.org_id == org_id))).scalar_one()


async def _batch(client, headers, files, mode="separate", name="batch"):
    return await client.post(
        "/api/v1/datasets/batch",
        files=[("files", f) for f in files],
        data={"name": name, "description": "", "mode": mode},
        headers=headers,
    )


@pytest.fixture(autouse=True)
def _isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    # `get_quota` memoises the Quota ORM ROW for 30s, and that row belongs to
    # the session that loaded it. A row cached by an earlier test outlives its
    # session, so the next test to read it gets DetachedInstanceError rather
    # than the quota it set. Clearing per test keeps each one self-contained.
    quotas.invalidate_quota_cache()
    yield tmp_path
    quotas.invalidate_quota_cache()


#: ~300 KB each, so four of them are ~1.2 MB against a 1 MB cap.
CHUNK = b"col\n" + b"0123456789\n" * 27_000


@pytest.mark.asyncio
async def test_the_quota_stops_the_batch_instead_of_being_overshot(
        client, db_session, two_orgs, auth_headers):
    """The regression this file exists for.

    Four ~300 KB files against a 1 MB cap: three fit, the fourth must not. The
    decisive assertion is not the count but the total -- an implementation that
    checked the quota per file without committing would store all four and end
    up over the limit.
    """
    org_id = two_orgs["a"]["org"].id
    await _set_quota(db_session, org_id, max_storage_mb=1)

    resp = await _batch(client, auth_headers["a"],
                        [(f"f{i}.csv", CHUNK, "text/csv") for i in range(4)])

    # 200 with partial success, or 413 if not even the first file fit -- either
    # is a correct refusal; what must never happen is all four being stored.
    assert resp.status_code in (200, 413), resp.text
    body = resp.json() if resp.status_code == 200 else resp.json()["detail"]
    assert body["failed"] >= 1, "the quota did not stop anything"
    assert body["created"] < 4, "every file was stored despite the cap"

    used = await _used_bytes(db_session, org_id)
    assert used <= 1 * 1024 * 1024, (
        f"the batch overshot the 1 MB quota: stored {used} bytes across "
        f"{body['created']} datasets")


@pytest.mark.asyncio
async def test_a_rejected_file_leaves_no_bytes_behind(
        client, db_session, two_orgs, auth_headers, _isolated_uploads):
    """A file blocked by the quota is written to disk before the check (its size
    is not known until then), so it has to be unlinked on the way out."""
    org_id = two_orgs["a"]["org"].id
    await _set_quota(db_session, org_id, max_storage_mb=1)

    resp = await _batch(client, auth_headers["a"],
                        [(f"f{i}.csv", CHUNK, "text/csv") for i in range(4)])

    body = resp.json() if resp.status_code == 200 else resp.json()["detail"]
    stored = {i["dataset"]["filename"] for i in body["items"]
              if i["status"] == "created"}
    on_disk = {str(p) for p in _isolated_uploads.rglob("*.csv")}
    assert on_disk == stored, "a rejected upload left orphaned bytes on disk"


@pytest.mark.asyncio
async def test_the_batch_size_ceiling_returns_413(
        client, db_session, two_orgs, auth_headers, monkeypatch):
    """A ceiling on the REQUEST, distinct from the per-file one: twenty files
    each under max_upload_mb can still be far more than one process should
    ingest inline."""
    monkeypatch.setattr(app_settings, "max_batch_upload_mb", 1)

    resp = await _batch(client, auth_headers["a"],
                        [(f"f{i}.csv", CHUNK, "text/csv") for i in range(6)])

    body = resp.json() if resp.status_code == 200 else resp.json()["detail"]
    errors = [i["error"] for i in body["items"] if i["status"] == "error"]
    assert any("1 MB limit for a single batch" in e for e in errors), errors


@pytest.mark.asyncio
async def test_the_ceiling_stops_the_batch_rather_than_failing_each_file(
        client, db_session, two_orgs, auth_headers, monkeypatch):
    """Once the request is over budget nothing after it can fit either, so the
    loop stops instead of reporting the same error N more times."""
    monkeypatch.setattr(app_settings, "max_batch_upload_mb", 1)

    resp = await _batch(client, auth_headers["a"],
                        [(f"f{i}.csv", CHUNK, "text/csv") for i in range(8)])

    body = resp.json() if resp.status_code == 200 else resp.json()["detail"]
    assert len(body["items"]) < 8, "every file was attempted after the budget blew"


@pytest.mark.asyncio
async def test_append_mode_counts_the_combined_size(
        client, db_session, two_orgs, auth_headers):
    """Append writes one file, so the quota must be charged for what actually
    landed -- not for the sum of the inputs, which is only an estimate."""
    org_id = two_orgs["a"]["org"].id
    await _set_quota(db_session, org_id, max_storage_mb=1)

    resp = await _batch(client, auth_headers["a"],
                        [(f"f{i}.csv", CHUNK, "text/csv") for i in range(2)],
                        mode="append")

    if resp.status_code == 200:
        stored = resp.json()["items"][0]["dataset"]["file_size"]
        assert stored == await _used_bytes(db_session, org_id), (
            "the recorded size is not what the quota counts")
        assert await _used_bytes(db_session, org_id) <= 1 * 1024 * 1024
    else:
        assert resp.status_code == 413
        assert await _used_bytes(db_session, org_id) == 0
