"""Task E2: per-tenant quotas.

Value-pinned boundary tests seed QueryRun/AgentRun rows directly through
`db_session` (the same in-memory DB `client` is wired to via get_db) rather
than relying on the fire-and-forget `query_log` writer, which points at its
own separate sync engine and isn't guaranteed to land in this test's DB --
see test_query_runs.py's own docstring for why that writer is special-cased.
"""
from datetime import datetime, timedelta

import pytest

from app.models.models import AgentRun, Dataset, Quota
from app.services import quotas


@pytest.fixture(autouse=True)
def _clean_quota_state():
    """Module-level caches/counters in services/quotas.py must not leak
    between tests -- org ids repeat across tests (every fresh DB has org 1,
    2), and a stale cached None would mask a quota row seeded directly via
    db_session (bypassing the admin CRUD endpoint that normally invalidates
    the cache)."""
    quotas.invalidate_quota_cache()
    quotas.reset_concurrent_counts()
    yield
    quotas.invalidate_quota_cache()
    quotas.reset_concurrent_counts()


def _qr(org_id, when):
    from app.models.models import QueryRun
    return QueryRun(org_id=org_id, source_kind="import", duration_ms=1, executor="pandas", created_at=when)


def _ar(org_id, when):
    return AgentRun(org_id=org_id, question="q", status="ok", created_at=when)


async def _ensure_org(db_session, org_id: int):
    """Make sure an Organization row with this id exists.

    Quota.org_id is a real foreign key. Inserting a quota for an org that does
    not exist only worked while SQLite had foreign keys switched off; the test
    database now enforces them, matching the Postgres the product runs on.
    """
    from app.models.models import Organization

    existing = await db_session.get(Organization, org_id)
    if existing is None:
        db_session.add(Organization(id=org_id, name=f"Org {org_id}"))
        await db_session.flush()


async def _set_quota(db_session, org_id: int, **fields):
    await _ensure_org(db_session, org_id)
    row = Quota(org_id=org_id, **fields)
    db_session.add(row)
    await db_session.commit()
    quotas.invalidate_quota_cache(org_id)
    return row


# ── Null quota = unlimited (regression) ────────────────────────────────────

@pytest.mark.asyncio
async def test_null_quota_never_blocks_widget_data(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    now = datetime.utcnow()
    for _ in range(50):
        db_session.add(_qr(org_id, now))
    await db_session.commit()

    ds = Dataset(name="d", filename=None, org_id=org_id, mode="import", file_size=0)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                             json={"widget_type": "table", "config": {}},
                             headers=auth_headers["a"])
    # No quota row at all -- unlimited, so this must not be a 429 regardless
    # of how many query_runs already exist today.
    assert resp.status_code != 429


# ── Queries/day: value-pinned boundary ──────────────────────────────────────

@pytest.mark.asyncio
async def test_query_quota_boundary_n_minus_1_ok_n_blocked(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    await _set_quota(db_session, org_id, max_queries_per_day=3)

    ds = Dataset(name="d", filename=None, org_id=org_id, mode="import", file_size=0)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    now = datetime.utcnow()
    body = {"widget_type": "table", "config": {}}

    # 2 already run today (n-1 = 2 < max=3) -- the 3rd request must pass.
    for _ in range(2):
        db_session.add(_qr(org_id, now))
    await db_session.commit()
    ok = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert ok.status_code != 429, ok.text

    # That request itself doesn't get logged synchronously by query_log (it
    # writes through its own separate engine), so seed the 3rd run directly
    # to reach n=3 -- the 4th request (count=3 >= max=3) must now be blocked.
    db_session.add(_qr(org_id, now))
    await db_session.commit()
    blocked = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.asyncio
async def test_query_quota_only_counts_today(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    await _set_quota(db_session, org_id, max_queries_per_day=1)

    ds = Dataset(name="d", filename=None, org_id=org_id, mode="import", file_size=0)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    yesterday = datetime.utcnow() - timedelta(days=1)
    for _ in range(5):
        db_session.add(_qr(org_id, yesterday))
    await db_session.commit()

    resp = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                             json={"widget_type": "table", "config": {}},
                             headers=auth_headers["a"])
    assert resp.status_code != 429


# ── Per-org isolation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_org_isolation_a_exhausted_b_unaffected(client, db_session, two_orgs, auth_headers):
    org_a = two_orgs["a"]["org"].id
    org_b = two_orgs["b"]["org"].id
    await _set_quota(db_session, org_a, max_queries_per_day=1)

    ds_a = Dataset(name="a", filename=None, org_id=org_a, mode="import", file_size=0)
    ds_b = Dataset(name="b", filename=None, org_id=org_b, mode="import", file_size=0)
    db_session.add_all([ds_a, ds_b])
    await db_session.commit()
    await db_session.refresh(ds_a)
    await db_session.refresh(ds_b)

    now = datetime.utcnow()
    db_session.add(_qr(org_a, now))
    await db_session.commit()

    blocked = await client.post(f"/api/v1/datasets/{ds_a.id}/widget-data",
                                json={"widget_type": "table", "config": {}}, headers=auth_headers["a"])
    assert blocked.status_code == 429

    ok = await client.post(f"/api/v1/datasets/{ds_b.id}/widget-data",
                           json={"widget_type": "table", "config": {}}, headers=auth_headers["b"])
    assert ok.status_code != 429


# ── Agent asks/day ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_ask_quota_blocks_at_boundary(db_session):
    org_id = 1
    from app.models.models import Organization, Role, User
    org = Organization(id=org_id, name="Org")
    db_session.add(org)
    await db_session.commit()

    await _set_quota(db_session, org_id, max_agent_asks_per_day=2)
    now = datetime.utcnow()
    db_session.add(_ar(org_id, now))
    db_session.add(_ar(org_id, now))
    await db_session.commit()

    with pytest.raises(Exception) as exc_info:
        await quotas.enforce_agent_quota(db_session, org_id)
    assert isinstance(exc_info.value, quotas.QuotaExceeded)
    assert exc_info.value.status_code == 429


# ── Concurrent-asks counter ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_slot_releases_on_exception(db_session):
    org_id = 5
    await _set_quota(db_session, org_id, max_concurrent_asks=1)

    with pytest.raises(RuntimeError):
        async with quotas.concurrent_ask_slot(db_session, org_id):
            assert quotas._concurrent_counts.get(org_id) == 1
            raise RuntimeError("boom")

    # Released even though the body raised -- the slot is free again.
    assert quotas._concurrent_counts.get(org_id, 0) == 0
    async with quotas.concurrent_ask_slot(db_session, org_id):
        assert quotas._concurrent_counts.get(org_id) == 1


@pytest.mark.asyncio
async def test_concurrent_slot_blocks_at_the_limit(db_session):
    org_id = 6
    await _set_quota(db_session, org_id, max_concurrent_asks=1)

    async with quotas.concurrent_ask_slot(db_session, org_id):
        with pytest.raises(quotas.QuotaExceeded) as exc_info:
            async with quotas.concurrent_ask_slot(db_session, org_id):
                pass
        assert exc_info.value.status_code == 429
    # First slot released cleanly; a fresh acquire now succeeds.
    async with quotas.concurrent_ask_slot(db_session, org_id):
        assert quotas._concurrent_counts.get(org_id) == 1


# ── Storage: current datasets only, value-pinned boundary ──────────────────

@pytest.mark.asyncio
async def test_storage_quota_counts_live_datasets_not_deleted(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    org_id = two_orgs["a"]["org"].id
    # 1 MB quota. A dataset already using ~0.9MB exists, then gets deleted --
    # its bytes must stop counting toward the quota once it's gone.
    await _set_quota(db_session, org_id, max_storage_mb=1)
    big = Dataset(name="big", filename=None, org_id=org_id, mode="import", file_size=900_000)
    db_session.add(big)
    await db_session.commit()
    await db_session.refresh(big)

    small_body = b"a,b\n" + b"1,2\n" * 10
    # While the big dataset still exists, a modest upload should still fit
    # (900_000 + len(small_body) is under 1MB).
    ok = await client.post("/api/v1/datasets", files={"file": ("t.csv", small_body, "text/csv")},
                           data={"name": "small", "description": ""}, headers=auth_headers["a"])
    assert ok.status_code == 200, ok.text

    # Delete the big dataset (hard delete) -- it must no longer count.
    del_resp = await client.delete(f"/api/v1/datasets/{big.id}", headers=auth_headers["a"])
    assert del_resp.status_code == 204

    ok2 = await client.post("/api/v1/datasets", files={"file": ("t2.csv", small_body, "text/csv")},
                            data={"name": "small2", "description": ""}, headers=auth_headers["a"])
    assert ok2.status_code == 200, ok2.text


@pytest.mark.asyncio
async def test_upload_over_storage_quota_is_413(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    org_id = two_orgs["a"]["org"].id
    await _set_quota(db_session, org_id, max_storage_mb=0)  # 0 MB -- anything blocks

    body = b"a,b\n1,2\n"
    resp = await client.post("/api/v1/datasets", files={"file": ("t.csv", body, "text/csv")},
                             data={"name": "over", "description": ""}, headers=auth_headers["a"])
    assert resp.status_code == 413
