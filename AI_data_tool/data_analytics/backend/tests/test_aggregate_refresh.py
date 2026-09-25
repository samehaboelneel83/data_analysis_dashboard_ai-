"""A refresh re-checks the grain against the source's rules.

Rules can be added after the aggregate was built. One that reads a column the
grain lacks would be applied to an aggregate that cannot honour it -- reads
for that role already fail closed (test_aggregate_security.py); this makes
the refresh say WHY, the way every scheduler failure is said, instead of
silently rewriting the file every hour.
"""
import asyncio
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import (DataSource, Dataset, DatasetColumn, Role, RowSecurityRule,
                               ScheduleFailure)
from app.services import refresh_scheduler
from app.services.aggregates import compile_aggregate_sql


@pytest.fixture
async def pair(db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    ds_src = DataSource(name="W", type="postgresql", org_id=org.id,
                        config={"host": "h", "port": 5432, "database": "d", "username": "u", "password": "p"})
    db_session.add(ds_src)
    await db_session.flush()
    src = Dataset(name="orders", org_id=org.id, mode="directquery", source_table="orders", data_source_id=ds_src.id)
    db_session.add(src)
    await db_session.flush()
    for c in ("tenant", "region", "product", "amount"):
        db_session.add(DatasetColumn(dataset_id=src.id, name=c, dtype="categorical"))
    p = tmp_path / "agg.csv"
    pd.DataFrame([{"tenant": "acme", "region": "N", "amount_sum": 1.0, "row_count": 1}]).to_csv(p, index=False)
    spec = {"grain": ["tenant", "region"],
            "measures": [{"column": "amount", "agg": "sum", "name": "amount_sum"}]}
    # The stored source_query must be exactly what compile_aggregate_sql(src,
    # spec) produces today -- refresh_one recompiles and compares the two
    # (see the "query changed" test below), so a covered-grain refresh that
    # is not itself testing a source-query change must start from a match.
    agg = Dataset(name="agg", org_id=org.id, mode="import", filename=str(p), data_source_id=ds_src.id,
                  source_query=compile_aggregate_sql(src, spec), aggregate_of_dataset_id=src.id,
                  aggregate_spec=spec,
                  refresh_interval_minutes=60)
    db_session.add(agg)
    role = Role(org_id=org.id, name="Tenant", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=src.id, filter_expr="tenant == 'acme'"))
    await db_session.commit()
    return src, agg, role


@pytest.fixture
def rewrites(monkeypatch):
    calls = []

    def _rewrite(cfg, filename, source_table, source_query):
        calls.append(source_query)
        df = pd.DataFrame([{"tenant": "acme", "region": "N", "amount_sum": 2.0, "row_count": 1}])
        df.to_csv(filename, index=False)
        from app.services.ingest import detect_types
        return df, detect_types(df)
    from app.services import dataset_refresh
    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _rewrite)
    monkeypatch.setattr(refresh_scheduler, "rescan_insights", _noop_async)
    return calls


async def _noop_async(*a, **kw):
    return None


@pytest.mark.asyncio
async def test_a_covered_grain_refreshes_normally(db_session, pair, rewrites):
    src, agg, role = pair
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == [agg.source_query]


@pytest.mark.asyncio
async def test_a_rule_outside_the_grain_stops_the_refresh_and_says_why(db_session, pair, rewrites):
    src, agg, role = pair
    # A role holds at most one rule per dataset (uq_role_dataset_rule) -- widen
    # the existing rule rather than add a second row, per the brief's note.
    existing = (await db_session.execute(select(RowSecurityRule).where(
        RowSecurityRule.role_id == role.id, RowSecurityRule.dataset_id == src.id))).scalar_one()
    existing.filter_expr = "product == 'x'"
    await db_session.commit()
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == []                                   # the file was NOT rewritten
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    assert "product" in failure.last_error and "Tenant" in failure.last_error


@pytest.mark.asyncio
async def test_an_unknown_column_rule_says_it_cannot_be_checked_not_a_column_name(db_session, pair, rewrites):
    """`rls_columns_outside_grain` reports an untranslatable rule as the
    literal string `<untranslatable>` (fail closed, never guessed) -- that
    placeholder must never leak into the operator-facing message as though it
    were a column to add to the grain."""
    src, agg, role = pair
    existing = (await db_session.execute(select(RowSecurityRule).where(
        RowSecurityRule.role_id == role.id, RowSecurityRule.dataset_id == src.id))).scalar_one()
    existing.filter_expr = "nope == 1"          # not a column of the source
    await db_session.commit()
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == []
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    assert "cannot be checked" in failure.last_error
    assert "<untranslatable>" not in failure.last_error


@pytest.mark.asyncio
async def test_the_failure_clears_once_the_grain_covers_again(db_session, pair, rewrites):
    src, agg, role = pair
    await refresh_scheduler.record_failure(db_session, "dataset", agg.id, "old")
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_default_filter_added_to_the_source_stops_the_refresh(db_session, pair, rewrites, monkeypatch):
    src, agg, role = pair
    src.default_filter_expr = "region == 'N'"
    await db_session.commit()
    monkeypatch.setattr(refresh_scheduler, "rescan_insights", _noop_async)
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == []
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    # Exact wording, not just a substring: Rebuild must not be offered for
    # THIS failure (list_aggregates/AggregatesPanel match on "query changed"
    # only), so the message says to fix the source first, not to rebuild.
    assert failure.last_error == (
        "Not refreshed: the source has a report-level filter expression, which an "
        "aggregate would ignore. Remove the filter expression on the source, then "
        "rebuild this aggregate.")


@pytest.mark.asyncio
async def test_a_changed_source_query_stops_the_refresh_and_says_why(db_session, pair, rewrites):
    """The compiled SQL is frozen in ds.source_query at creation; the
    source's own base query is not. If the source is later re-pointed
    (routers/data_sources.py allows narrowing source_table/source_query),
    the aggregate must not keep silently summarising the OLD query forever
    -- it refuses the rewrite and says why, the same as an uncovered grain."""
    src, agg, role = pair
    src.source_table = "orders_v2"
    await db_session.commit()
    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    assert rewrites == []                                   # the file was NOT rewritten
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    assert "query changed" in failure.last_error


@pytest.mark.asyncio
async def test_a_failed_rewrite_does_not_erase_a_prior_failure(db_session, pair, monkeypatch):
    """The covered path used to clear a prior failure BEFORE attempting the
    rewrite. If the rewrite itself then fails, the pre-existing
    ScheduleFailure row must still be there afterwards -- clearing has to
    wait for a rewrite that actually succeeded."""
    src, agg, role = pair
    await refresh_scheduler.record_failure(db_session, "dataset", agg.id, "old failure")
    monkeypatch.setattr(refresh_scheduler, "rescan_insights", _noop_async)

    def _boom(cfg, filename, source_table, source_query):
        raise RuntimeError("the source is unreachable")
    from app.services import dataset_refresh
    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _boom)

    assert await refresh_scheduler.refresh_one(db_session, agg) is True
    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one_or_none()
    assert failure is not None, "a failed rewrite must not clear a pre-existing failure"
    # Not merely preserved: the swallowed error is SAID. Without a fresh
    # record_failure here the tick's guarded clear (see the tick test below)
    # would delete the row anyway, since nothing put the item into backoff.
    assert failure.attempts == 2
    assert "the source is unreachable" in failure.last_error


class _FactoryCtx:
    """Wraps one already-open test session as a `session_factory()` -- the
    same shape test_eval_schedule.py and test_refresh_schedule.py's
    `run_items` test use, since the module under test expects
    `session_factory()` to be an async context manager, not a plain session."""
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_the_scheduler_tick_does_not_erase_the_failure_it_just_recorded(db_session, pair, rewrites, monkeypatch):
    """Pins the interaction with `run_scheduler`'s own per-item loop, which
    used to call `clear_failure` right after `refresh_one` returns --
    unconditionally, before this task. `refresh_one` reports True for a
    grain violation (it DID run; it chose not to rewrite), so a blind clear
    right after it, inside the SAME tick, would erase the row that same call
    just wrote -- the Aggregates tab would never see it.

    Drives one REAL tick of `run_scheduler`, rather than reproducing its loop
    body inline, so a regression in the loop itself is actually caught (an
    inline copy stays green even if the real loop regresses). `asyncio.sleep`
    is monkeypatched to return once -- letting exactly one tick run -- and
    then raise `CancelledError`, which `run_scheduler`'s own handler re-raises
    cleanly out of the `while True`.
    """
    src, agg, role = pair
    existing = (await db_session.execute(select(RowSecurityRule).where(
        RowSecurityRule.role_id == role.id, RowSecurityRule.dataset_id == src.id))).scalar_one()
    existing.filter_expr = "product == 'x'"
    await db_session.commit()

    calls = {"n": 0}

    async def fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(refresh_scheduler.asyncio, "sleep", fake_sleep)

    def factory():
        return _FactoryCtx(db_session)

    with pytest.raises(asyncio.CancelledError):
        await refresh_scheduler.run_scheduler(factory)

    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one_or_none()
    assert failure is not None, "the tick's own clear_failure erased the row refresh_one just wrote"
    assert "product" in failure.last_error and "Tenant" in failure.last_error


@pytest.mark.asyncio
async def test_the_scheduler_tick_keeps_the_prior_failure_when_the_rewrite_fails(db_session, pair, monkeypatch):
    """End-to-end form of the unit test above. `run_scheduler`'s loop clears
    the item's failure after `refresh_one` unless the item is in backoff.
    A rewrite that raises is swallowed inside `refresh_one`; if that path
    recorded nothing, the prior row's `next_attempt_at` would still be in
    the past, `in_backoff` would be False, and the tick would erase the
    very row the unit-level fix preserved. So the swallowed error must be
    recorded, which both keeps the row and shows the real error in the
    Aggregates tab."""
    src, agg, role = pair
    await refresh_scheduler.record_failure(db_session, "dataset", agg.id, "old failure")
    row = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one()
    # The old failure is due for retry, otherwise the tick would skip the
    # item before refresh_one ever ran.
    row.next_attempt_at = datetime.utcnow() - timedelta(minutes=1)
    await db_session.commit()

    def _boom(cfg, filename, source_table, source_query):
        raise RuntimeError("the source is unreachable")
    from app.services import dataset_refresh
    monkeypatch.setattr(dataset_refresh, "rewrite_dataset_file", _boom)
    monkeypatch.setattr(refresh_scheduler, "rescan_insights", _noop_async)

    calls = {"n": 0}

    async def fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(refresh_scheduler.asyncio, "sleep", fake_sleep)

    def factory():
        return _FactoryCtx(db_session)

    with pytest.raises(asyncio.CancelledError):
        await refresh_scheduler.run_scheduler(factory)

    failure = (await db_session.execute(select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == agg.id))).scalar_one_or_none()
    assert failure is not None, "the tick's clear_failure erased the failure after a swallowed rewrite error"
    assert failure.attempts == 2
    assert "the source is unreachable" in failure.last_error
