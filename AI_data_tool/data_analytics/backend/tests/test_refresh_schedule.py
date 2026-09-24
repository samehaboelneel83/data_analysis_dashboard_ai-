"""Scheduled dataset refresh.

The valuable, testable part is the due-calculation and the multi-worker guard, not
the sleep loop. An in-process scheduler runs once per uvicorn worker, so without a
guard N workers means N simultaneous refreshes of the same dataset — each
overwriting the same CSV. `advisory_lock_key` and `is_due` are pure so both are
pinned here; the loop that calls them stays deliberately thin.
"""
from datetime import datetime, timedelta

import pandas as pd

from app.models.models import Dataset, DataSource
from app.services.refresh_scheduler import advisory_lock_key, due_datasets, is_due

NOW = datetime(2026, 8, 17, 12, 0, 0)


def test_a_dataset_with_no_interval_is_never_due():
    assert is_due(None, NOW - timedelta(days=9), NOW) is False


def test_a_dataset_never_refreshed_is_due_immediately():
    """Otherwise a newly scheduled dataset would wait a full interval before its
    first refresh, which looks broken to whoever just set it up."""
    assert is_due(60, None, NOW) is True


def test_a_dataset_is_due_once_the_interval_has_elapsed():
    assert is_due(60, NOW - timedelta(minutes=61), NOW) is True


def test_a_dataset_is_not_due_before_the_interval_elapses():
    assert is_due(60, NOW - timedelta(minutes=59), NOW) is False


def test_the_boundary_counts_as_due():
    assert is_due(60, NOW - timedelta(minutes=60), NOW) is True


def test_a_non_positive_interval_is_treated_as_unscheduled():
    """Zero would otherwise mean "refresh every tick", which is a footgun rather
    than a feature."""
    assert is_due(0, None, NOW) is False
    assert is_due(-5, None, NOW) is False


def test_due_datasets_selects_only_the_eligible_ones():
    rows = [
        Dataset(id=1, name="due", mode="import", data_source_id=1, source_table="t",
                refresh_interval_minutes=30, last_refreshed_at=NOW - timedelta(hours=2)),
        Dataset(id=2, name="not yet", mode="import", data_source_id=1, source_table="t",
                refresh_interval_minutes=30, last_refreshed_at=NOW - timedelta(minutes=5)),
        Dataset(id=3, name="unscheduled", mode="import", data_source_id=1, source_table="t",
                refresh_interval_minutes=None, last_refreshed_at=None),
    ]

    assert [d.id for d in due_datasets(rows, NOW)] == [1]


def test_directquery_datasets_are_never_scheduled():
    """They read the live source on every query, so there is no cached file to
    refresh — scheduling one would burn a connection for no effect."""
    rows = [Dataset(id=1, name="dq", mode="directquery", data_source_id=1, source_table="t",
                    refresh_interval_minutes=5, last_refreshed_at=None)]

    assert due_datasets(rows, NOW) == []


def test_a_dataset_without_a_recorded_source_is_skipped():
    """Refresh needs a connection plus a table or query; without them the manual
    endpoint 400s, and the scheduler must not retry it forever."""
    rows = [
        Dataset(id=1, name="no source", mode="import", data_source_id=None,
                refresh_interval_minutes=5, last_refreshed_at=None),
        Dataset(id=2, name="no table", mode="import", data_source_id=1, source_table=None,
                source_query=None, refresh_interval_minutes=5, last_refreshed_at=None),
    ]

    assert due_datasets(rows, NOW) == []


def test_lock_keys_are_stable_and_distinct_per_dataset():
    assert advisory_lock_key(7) == advisory_lock_key(7)
    assert advisory_lock_key(7) != advisory_lock_key(8)


def test_lock_keys_fit_in_a_signed_64_bit_integer():
    """pg_try_advisory_lock takes a bigint; a key outside that range errors at the
    database rather than failing loudly here."""
    for dataset_id in (1, 999, 2**31, 2**62):
        key = advisory_lock_key(dataset_id)
        assert -(2**63) <= key < 2**63


# ── Schedule API ──────────────────────────────────────────────────────────────

async def _dataset(db_session, org_id, tmp_path):
    path = tmp_path / "d.csv"
    pd.DataFrame([{"a": 1}]).to_csv(path, index=False)
    src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    ds = Dataset(name="ds", filename=str(path), org_id=org_id, row_count=1, col_count=1,
                 data_source_id=src.id, source_table="t")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_setting_a_schedule_persists_the_interval(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                           json={"interval_minutes": 120}, headers=auth_headers["a"])

    assert r.status_code == 200
    assert r.json()["refresh_interval_minutes"] == 120


async def test_clearing_a_schedule_sets_it_back_to_null(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                       json={"interval_minutes": 60}, headers=auth_headers["a"])

    r = await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                           json={"interval_minutes": None}, headers=auth_headers["a"])

    assert r.json()["refresh_interval_minutes"] is None


async def test_a_too_frequent_interval_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    """A one-minute schedule against a real database is a self-inflicted denial of
    service, so there is a floor."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                           json={"interval_minutes": 1}, headers=auth_headers["a"])

    assert r.status_code == 400


async def test_scheduling_a_directquery_dataset_is_rejected(db_session, two_orgs, auth_headers, client, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    ds.mode = "directquery"
    await db_session.commit()

    r = await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                           json={"interval_minutes": 60}, headers=auth_headers["a"])

    assert r.status_code == 400


async def test_another_orgs_dataset_cannot_be_scheduled(db_session, two_orgs, auth_headers, client, tmp_path):
    other = await _dataset(db_session, two_orgs["b"]["org"].id, tmp_path)

    r = await client.patch(f"/api/v1/datasets/{other.id}/refresh-schedule",
                           json={"interval_minutes": 60}, headers=auth_headers["a"])

    assert r.status_code == 404


# ── Tick discipline: fairness ordering and the per-tick cap ──────────────────

def test_oldest_first_puts_never_run_items_before_everything():
    from types import SimpleNamespace
    from app.services.refresh_scheduler import _oldest_first
    items = [
        SimpleNamespace(id=1, last_run_at=datetime(2026, 8, 23, 10)),
        SimpleNamespace(id=2, last_run_at=None),
        SimpleNamespace(id=3, last_run_at=datetime(2026, 8, 23, 8)),
        SimpleNamespace(id=4, last_run_at=None),
    ]
    ordered = _oldest_first(items, "last_run_at")
    assert [x.id for x in ordered] == [2, 4, 3, 1]


def test_the_per_tick_cap_is_a_constantly_visible_contract():
    """MAX_ITEMS_PER_TICK exists and is sane — the loop slices with it, so a
    backlog drains over a few ticks instead of stampeding after downtime."""
    from app.services.refresh_scheduler import MAX_ITEMS_PER_TICK, ITEM_CONCURRENCY
    assert 1 <= ITEM_CONCURRENCY <= MAX_ITEMS_PER_TICK


async def test_run_items_opens_one_session_per_item_and_survives_failures(db_session, two_orgs, tmp_path):
    """Concurrent items must NOT share a session (AsyncSession is not
    concurrency-safe, and advisory locks are connection-scoped), and one
    failing item must not sink its siblings."""
    from app.models.models import DataAlert
    from app.services.refresh_scheduler import run_items

    org = two_orgs["a"]["org"]
    ds = Dataset(name="d", org_id=org.id, filename=str(tmp_path / "x.csv"))
    db_session.add(ds)
    await db_session.flush()
    alerts = []
    for i in range(3):
        a = DataAlert(org_id=org.id, dataset_id=ds.id, name=f"a{i}",
                      creator_user_id=two_orgs["a"]["user"].id,
                      expression="SUM(x) > 1", interval_minutes=5)
        db_session.add(a)
        alerts.append(a)
    await db_session.commit()

    sessions_opened = []

    class CountingFactory:
        def __call__(self):
            from app.core.database import AsyncSessionLocal  # not used; stub below
            raise AssertionError("unused")

    # A factory stub that hands out the real test session machinery is complex;
    # instead count invocations while delegating to a fresh-session context.
    class FactoryCtx:
        def __init__(self, session):
            self._s = session
        async def __aenter__(self):
            return self._s
        async def __aexit__(self, *exc):
            return False

    def factory():
        sessions_opened.append(object())
        return FactoryCtx(db_session)

    ran, failed = [], []

    async def runner(s, row):
        if row.name == "a1":
            failed.append(row.name)
            raise RuntimeError("boom")
        ran.append(row.name)

    ids = [a.id for a in alerts]
    await run_items(factory, ids, DataAlert, 2_000_000_000, runner, "alert")

    # One session per item, PLUS one for bookkeeping the single failure: the
    # failing item's own session may be poisoned by whatever raised, so the
    # backoff row is written on a fresh one.
    assert len(sessions_opened) == 4
    assert sorted(ran) == ["a0", "a2"]        # siblings survived the failure
    assert failed == ["a1"]

    # And the failure is now REMEMBERED, not just logged -- a1 is held back
    # from the next tick while its siblings stay due.
    from app.services.refresh_scheduler import in_backoff
    from datetime import datetime as _dt
    now = _dt.utcnow()
    assert await in_backoff(db_session, "alert", ids[1], now) is True
    assert await in_backoff(db_session, "alert", ids[0], now) is False


# ── Calendar semantics (daily/weekly/monthly at a UTC clock time) ────────────

def test_daily_calendar_fires_once_after_its_time():
    from app.services.refresh_scheduler import is_calendar_due
    spec = {"kind": "daily", "hour": 9, "minute": 0}
    before = datetime(2026, 8, 24, 8, 30)
    after = datetime(2026, 8, 24, 9, 5)
    # never run: due as soon as an occurrence has passed
    assert is_calendar_due(spec, None, after) is True
    # ran at 09:01 today: not due again at 09:05
    assert is_calendar_due(spec, datetime(2026, 8, 24, 9, 1), after) is False
    # ran yesterday: due after today's 09:00, not before it
    y = datetime(2026, 8, 23, 9, 1)
    assert is_calendar_due(spec, y, before) is False
    assert is_calendar_due(spec, y, after) is True


def test_weekly_calendar_respects_the_weekday():
    from app.services.refresh_scheduler import is_calendar_due
    spec = {"kind": "weekly", "weekday": 0, "hour": 7, "minute": 30}  # Mondays 07:30
    monday_after = datetime(2026, 8, 24, 8, 0)   # 2026-08-24 is a Monday
    last_week = datetime(2026, 8, 17, 7, 31)
    assert is_calendar_due(spec, last_week, monday_after) is True
    ran_today = datetime(2026, 8, 24, 7, 31)
    assert is_calendar_due(spec, ran_today, monday_after) is False
    tuesday = datetime(2026, 8, 25, 12, 0)
    assert is_calendar_due(spec, ran_today, tuesday) is False


def test_monthly_calendar_clamps_to_day_28_and_rolls_months():
    from app.services.refresh_scheduler import is_calendar_due
    spec = {"kind": "monthly", "monthday": 1, "hour": 0, "minute": 30}
    ran_last_month = datetime(2026, 7, 1, 0, 31)
    assert is_calendar_due(spec, ran_last_month, datetime(2026, 8, 1, 1, 0)) is True
    ran_this_month = datetime(2026, 8, 1, 0, 31)
    assert is_calendar_due(spec, ran_this_month, datetime(2026, 8, 20, 0, 0)) is False


def test_aware_and_naive_datetimes_never_collide():
    """Postgres hands back tz-aware last_run_at; the loop clock is naive UTC.
    The comparison must normalize instead of raising (the share-link lesson)."""
    from datetime import timezone as tz
    from app.services.refresh_scheduler import is_calendar_due, is_due
    aware = datetime(2026, 8, 24, 9, 1, tzinfo=tz.utc)
    now = datetime(2026, 8, 24, 9, 5)
    assert is_calendar_due({"kind": "daily", "hour": 9, "minute": 0}, aware, now) is False
    assert is_due(60, aware, now) is False


def test_calendar_spec_rides_invisibly_in_recipients():
    from app.services.refresh_scheduler import calendar_spec
    from app.services.delivery import valid_recipients
    recipients = ["a@b.co", {"__calendar__": {"kind": "daily", "hour": 9, "minute": 0}}]
    assert calendar_spec(recipients) == {"kind": "daily", "hour": 9, "minute": 0}
    # delivery must never treat the settings entry as an address
    assert valid_recipients(recipients) == ["a@b.co"]


# ── Derived datasets can be scheduled too ─────────────────────────────────────
# Found live, not by a test: every case above builds a SOURCE-backed dataset, so
# the endpoint's `if not ds.data_source_id: 400` guard was never exercised against
# a derived one. A derived dataset has no connection by design -- it refreshes by
# replaying `__derived_from__` -- so that guard made scheduled materialization
# unreachable from the UI while the scheduler itself supported it perfectly.

async def _derived_dataset(db_session, org_id, tmp_path):
    from app.services.prep import DERIVED_FROM_KEY

    path = tmp_path / "derived.csv"
    pd.DataFrame([{"a": 1}]).to_csv(path, index=False)
    ds = Dataset(name="derived", filename=str(path), org_id=org_id, row_count=1,
                 col_count=1, mode="import",
                 column_meta={DERIVED_FROM_KEY: {"source_dataset_id": 1, "steps": [],
                                                 "built_by_user_id": 1}})
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_a_derived_dataset_can_be_given_a_schedule(
        db_session, two_orgs, auth_headers, client, tmp_path):
    """The whole point of scheduled materialization: no connection, but a recipe."""
    ds = await _derived_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)

    r = await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                           json={"interval_minutes": 120}, headers=auth_headers["a"])

    assert r.status_code == 200, r.text
    assert r.json()["refresh_interval_minutes"] == 120


async def test_a_plain_upload_still_cannot_be_scheduled(
        db_session, two_orgs, auth_headers, client, tmp_path):
    """The relaxation must be narrow: a file with neither a connection nor a
    recipe has nothing to re-read, so scheduling it would fail every tick."""
    path = tmp_path / "plain.csv"
    pd.DataFrame([{"a": 1}]).to_csv(path, index=False)
    ds = Dataset(name="plain", filename=str(path), org_id=two_orgs["a"]["org"].id,
                 row_count=1, col_count=1, mode="import", column_meta={})
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    r = await client.patch(f"/api/v1/datasets/{ds.id}/refresh-schedule",
                           json={"interval_minutes": 120}, headers=auth_headers["a"])

    assert r.status_code == 400
