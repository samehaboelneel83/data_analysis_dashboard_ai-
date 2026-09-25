"""A materialized dataset that keeps itself current.

This is the useful half of a "dataflow": a transformation that re-runs on a
schedule instead of waiting for somebody to press Rebuild. It reuses the recipe
already stored in `__derived_from__` and the scheduler already running for
source-backed datasets, so the whole feature is two seams -- letting a derived
dataset be considered due, and replaying its recipe when it is.

The property worth guarding is IDENTITY. A scheduled run has nobody at the
keyboard, and a refresh that read the base frame with no identity would be an
unfiltered read. The rebuild resolves row-level security as the dataset's
recorded builder, the same stance `ReportSchedule` takes with its creator.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.core.config import settings as app_settings
from app.models.models import Dataset, DatasetColumn, User
from app.services.prep import DERIVED_FROM_KEY
from app.services.refresh_scheduler import due_datasets, refresh_one


def _now():
    return datetime.utcnow()


def _derived(**over):
    """A Dataset shaped like one `materialize` produces."""
    base = dict(mode="import", filename="/tmp/x.csv", data_source_id=None,
                source_table=None, source_query=None,
                refresh_interval_minutes=60, last_refreshed_at=None,
                column_meta={DERIVED_FROM_KEY: {"source_dataset_id": 1, "steps": [],
                                                "built_by_user_id": 1}})
    base.update(over)
    return Dataset(name="Derived", org_id=1, **base)


def _source_backed(**over):
    base = dict(mode="import", filename="/tmp/y.csv", data_source_id=5,
                source_table="orders", refresh_interval_minutes=60,
                last_refreshed_at=None, column_meta={})
    base.update(over)
    return Dataset(name="Sourced", org_id=1, **base)


class TestWhatCountsAsDue:
    def test_a_derived_dataset_with_no_connection_is_now_eligible(self):
        """It has no data_source_id at all -- the check that used to exclude it
        is exactly what made a materialized dataset unable to refresh itself."""
        assert due_datasets([_derived()], _now())

    def test_a_source_backed_dataset_still_needs_its_connection(self):
        """The old rule has to keep applying to the old kind: without a
        connection a source refresh fails every tick."""
        assert not due_datasets([_source_backed(data_source_id=None)], _now())

    def test_a_source_backed_dataset_still_needs_a_table_or_query(self):
        assert not due_datasets(
            [_source_backed(source_table=None, source_query=None)], _now())

    def test_a_directquery_dataset_is_never_due(self):
        """Nothing is cached, so there is nothing to refresh."""
        assert not due_datasets([_derived(mode="directquery")], _now())

    def test_no_interval_means_no_schedule(self):
        assert not due_datasets([_derived(refresh_interval_minutes=None)], _now())
        assert not due_datasets([_derived(refresh_interval_minutes=0)], _now())

    def test_it_is_not_due_again_until_the_interval_passes(self):
        recent = _derived(last_refreshed_at=_now() - timedelta(minutes=5))
        assert not due_datasets([recent], _now())
        stale = _derived(last_refreshed_at=_now() - timedelta(minutes=90))
        assert due_datasets([stale], _now())


class TestTheRebuild:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    async def _pair(self, db, org, tmp_path, rows=3):
        """A base dataset, and a derived one whose recipe is 'copy it'."""
        src = tmp_path / "base.csv"
        pd.DataFrame({"k": [f"v{i}" for i in range(rows)],
                      "n": range(rows)}).to_csv(src, index=False)
        base = Dataset(name="Base", filename=str(src), org_id=org.id, mode="import")
        db.add(base)
        await db.flush()
        for c in ("k", "n"):
            db.add(DatasetColumn(dataset_id=base.id, name=c, dtype="categorical"))

        user = (await db.execute(
            __import__("sqlalchemy").select(User).where(User.org_id == org.id)
        )).scalars().first()

        out = tmp_path / "derived.csv"
        pd.DataFrame({"k": ["stale"], "n": [0]}).to_csv(out, index=False)
        derived = Dataset(
            name="Derived", filename=str(out), org_id=org.id, mode="import",
            row_count=1, refresh_interval_minutes=60,
            column_meta={DERIVED_FROM_KEY: {
                "source_dataset_id": base.id, "join_dataset_ids": [], "steps": [],
                "built_by_user_id": user.id, "recipe_version": 1}})
        db.add(derived)
        await db.flush()
        await db.commit()
        return base, derived, user

    @pytest.mark.asyncio
    async def test_it_replays_the_recipe_and_picks_up_new_rows(
            self, db_session, two_orgs, _uploads):
        base, derived, _ = await self._pair(db_session, two_orgs["a"]["org"], _uploads)

        ran = await refresh_one(db_session, derived)

        assert ran is True
        await db_session.refresh(derived)
        assert derived.row_count == 3, "the derived file did not pick up the base rows"

    @pytest.mark.asyncio
    async def test_a_later_change_to_the_source_is_picked_up(
            self, db_session, two_orgs, _uploads):
        base, derived, _ = await self._pair(db_session, two_orgs["a"]["org"], _uploads)
        await refresh_one(db_session, derived)

        pd.DataFrame({"k": list("abcde"), "n": range(5)}).to_csv(base.filename, index=False)
        await refresh_one(db_session, derived)

        await db_session.refresh(derived)
        assert derived.row_count == 5

    @pytest.mark.asyncio
    async def test_it_keeps_the_same_file_path(self, db_session, two_orgs, _uploads):
        """Written in place so every report pointing at this dataset picks the
        new rows up with no rewiring."""
        _, derived, _ = await self._pair(db_session, two_orgs["a"]["org"], _uploads)
        before = derived.filename

        await refresh_one(db_session, derived)

        await db_session.refresh(derived)
        assert derived.filename == before

    @pytest.mark.asyncio
    async def test_the_recipe_survives_the_refresh(self, db_session, two_orgs, _uploads):
        """Only the timestamps move -- a rebuild that lost the recipe could
        never run again."""
        _, derived, _ = await self._pair(db_session, two_orgs["a"]["org"], _uploads)

        await refresh_one(db_session, derived)

        await db_session.refresh(derived)
        prov = derived.column_meta[DERIVED_FROM_KEY]
        assert prov["source_dataset_id"] and prov["built_by_user_id"]
        assert prov["built_rows"] == 3

    @pytest.mark.asyncio
    async def test_the_timestamp_advances(self, db_session, two_orgs, _uploads):
        _, derived, _ = await self._pair(db_session, two_orgs["a"]["org"], _uploads)
        assert derived.last_refreshed_at is None
        await refresh_one(db_session, derived)
        await db_session.refresh(derived)
        assert derived.last_refreshed_at is not None


class TestItFailsQuietlyAndKeepsGoing:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    @pytest.mark.asyncio
    async def test_a_deleted_source_does_not_stop_the_loop(
            self, db_session, two_orgs, _uploads):
        """One broken recipe must not stop every other dataset refreshing, and
        the timestamp advances so it retries on schedule rather than every tick."""
        out = _uploads / "d.csv"
        pd.DataFrame({"k": ["x"]}).to_csv(out, index=False)
        derived = Dataset(
            name="Orphan", filename=str(out), org_id=two_orgs["a"]["org"].id,
            mode="import", refresh_interval_minutes=60,
            column_meta={DERIVED_FROM_KEY: {"source_dataset_id": 999_999,
                                            "steps": [], "built_by_user_id": 1}})
        db_session.add(derived)
        await db_session.commit()

        ran = await refresh_one(db_session, derived)

        assert ran is True, "a missing source should be handled, not crash the loop"
        await db_session.refresh(derived)
        assert derived.last_refreshed_at is not None

    @pytest.mark.asyncio
    async def test_a_departed_builder_stops_the_rebuild(
            self, db_session, two_orgs, _uploads):
        """The rebuild resolves RLS as the builder, so no builder means no
        identity and the data must not be rewritten.

        Note what this does and does not prove. Removing the explicit
        `builder is None` guard does NOT make this fail: `resolve_rls_expr`
        reads `user.role` and raises on None, which the never-die `except`
        catches, so the rebuild is skipped either way. The guard turns an
        incidental AttributeError into a named, logged skip. The test pins the
        OUTCOME -- data untouched without an identity -- which is the property
        that matters and which survives either implementation."""
        org = two_orgs["a"]["org"]
        # A REAL base, so the missing-source check cannot fire first and mask
        # what this test is actually about.
        src = _uploads / "base2.csv"
        pd.DataFrame({"k": list("abcde")}).to_csv(src, index=False)
        base = Dataset(name="Base2", filename=str(src), org_id=org.id, mode="import")
        db_session.add(base)
        await db_session.flush()

        out = _uploads / "d2.csv"
        pd.DataFrame({"k": ["x"]}).to_csv(out, index=False)
        derived = Dataset(
            name="NoBuilder", filename=str(out), org_id=org.id,
            mode="import", row_count=1, refresh_interval_minutes=60,
            column_meta={DERIVED_FROM_KEY: {"source_dataset_id": base.id, "steps": [],
                                            "built_by_user_id": 999_999}})
        db_session.add(derived)
        await db_session.commit()

        ran = await refresh_one(db_session, derived)

        assert ran is True
        await db_session.refresh(derived)
        assert derived.row_count == 1, (
            "it rebuilt with no identity -- the base has 5 rows, so a row_count "
            "of 5 means the RLS-resolving identity was skipped entirely")


# ── A dataflow's own schedule ─────────────────────────────────────────────────
# The distinction that makes a dataflow "independently scheduled": the interval
# lives on the DATAFLOW, not on the datasets it produces. The dataset query in
# the scheduler loop filters on Dataset.refresh_interval_minutes, so it cannot
# see these at all -- an output's own interval is normally None.

class TestDataflowsHaveTheirOwnClock:
    def test_a_dataflow_is_due_on_its_own_interval(self):
        from app.models.models import Dataflow
        from app.services.refresh_scheduler import due_dataflows

        stale = Dataflow(org_id=1, name="f", steps=[], join_dataset_ids=[],
                         refresh_interval_minutes=60,
                         last_run_at=_now() - timedelta(minutes=90))
        assert due_dataflows([stale], _now())

    def test_it_is_not_due_again_until_the_interval_passes(self):
        from app.models.models import Dataflow
        from app.services.refresh_scheduler import due_dataflows

        fresh = Dataflow(org_id=1, name="f", steps=[], join_dataset_ids=[],
                         refresh_interval_minutes=60,
                         last_run_at=_now() - timedelta(minutes=5))
        assert not due_dataflows([fresh], _now())

    def test_no_interval_means_no_schedule(self):
        from app.models.models import Dataflow
        from app.services.refresh_scheduler import due_dataflows

        for interval in (None, 0):
            f = Dataflow(org_id=1, name="f", steps=[], join_dataset_ids=[],
                         refresh_interval_minutes=interval, last_run_at=None)
            assert not due_dataflows([f], _now())


class TestTheDataflowRefreshItself:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    async def _flow_with_output(self, db, org, tmp_path, rows=4):
        """A source, a dataflow, and one output already produced from it."""
        import sqlalchemy

        from app.models.models import Dataflow
        from app.services.prep import DERIVED_FROM_KEY

        src_path = tmp_path / "src.csv"
        pd.DataFrame({"k": [f"v{i}" for i in range(rows)],
                      "n": range(rows)}).to_csv(src_path, index=False)
        src = Dataset(name="Src", filename=str(src_path), org_id=org.id, mode="import")
        db.add(src)
        await db.flush()
        for c in ("k", "n"):
            db.add(DatasetColumn(dataset_id=src.id, name=c, dtype="categorical"))

        user = (await db.execute(
            sqlalchemy.select(User).where(User.org_id == org.id))).scalars().first()
        flow = Dataflow(org_id=org.id, name="Nightly", source_dataset_id=src.id,
                        steps=[], join_dataset_ids=[], created_by=user.id,
                        refresh_interval_minutes=60)
        db.add(flow)
        await db.flush()

        out_path = tmp_path / "out.csv"
        pd.DataFrame({"k": ["stale"], "n": [0]}).to_csv(out_path, index=False)
        out = Dataset(name="Out", filename=str(out_path), org_id=org.id,
                      mode="import", row_count=1,
                      column_meta={DERIVED_FROM_KEY: {
                          "dataflow_id": flow.id, "source_dataset_id": src.id,
                          "steps": [], "built_by_user_id": user.id}})
        db.add(out)
        await db.flush()
        await db.commit()
        return src, flow, out

    @pytest.mark.asyncio
    async def test_it_refreshes_every_output_it_owns(
            self, db_session, two_orgs, _uploads):
        from app.services.refresh_scheduler import refresh_dataflow

        src, flow, out = await self._flow_with_output(
            db_session, two_orgs["a"]["org"], _uploads)

        assert await refresh_dataflow(db_session, flow) is True

        await db_session.refresh(out)
        assert out.row_count == 4, "the output did not pick up the source rows"

    @pytest.mark.asyncio
    async def test_a_run_records_success_on_the_dataflow(
            self, db_session, two_orgs, _uploads):
        """Recorded on the object, not only in a log, so a failing pipeline is
        visible in the UI rather than only to whoever reads the container."""
        from app.services.refresh_scheduler import refresh_dataflow

        _, flow, _ = await self._flow_with_output(
            db_session, two_orgs["a"]["org"], _uploads)

        await refresh_dataflow(db_session, flow)

        await db_session.refresh(flow)
        assert flow.last_run_status == "ok"
        assert flow.last_run_rows == 4
        assert flow.last_run_at is not None

    @pytest.mark.asyncio
    async def test_a_departed_creator_stops_the_run(
            self, db_session, two_orgs, _uploads):
        """A scheduled run resolves RLS as the dataflow's creator. With no
        creator there is no identity, and running anyway would be an unfiltered
        read -- so the data must not be rewritten.

        Same caveat as `test_a_departed_builder_stops_the_rebuild` above, and
        verified the same way: removing the explicit `builder is None` check does
        NOT make this fail, because `resolve_rls_expr` reads `user.role` and
        raises on None, which the never-die `except` catches and records as a
        failed run. The check turns an incidental AttributeError into a named
        failure. What this pins is the OUTCOME -- data untouched, run marked
        failed, loop still alive -- which is the property that matters and holds
        under either implementation."""
        from app.services.refresh_scheduler import refresh_dataflow

        _, flow, out = await self._flow_with_output(
            db_session, two_orgs["a"]["org"], _uploads)
        flow.created_by = None
        await db_session.commit()

        assert await refresh_dataflow(db_session, flow) is True

        await db_session.refresh(out)
        assert out.row_count == 1, "it rebuilt with no identity"
        await db_session.refresh(flow)
        assert flow.last_run_status == "failed"

    @pytest.mark.asyncio
    async def test_a_dataflow_with_no_outputs_is_skipped_quietly(
            self, db_session, two_orgs, _uploads):
        """Nothing to write into yet. The clock still advances so it stays quiet
        instead of retrying on every single tick."""
        from app.models.models import Dataflow
        from app.services.refresh_scheduler import refresh_dataflow

        flow = Dataflow(org_id=two_orgs["a"]["org"].id, name="Empty", steps=[],
                        join_dataset_ids=[], refresh_interval_minutes=60)
        db_session.add(flow)
        await db_session.commit()

        assert await refresh_dataflow(db_session, flow) is True

        await db_session.refresh(flow)
        assert flow.last_run_status == "skipped"
        assert flow.last_run_at is not None

    @pytest.mark.asyncio
    async def test_a_broken_recipe_never_stops_the_loop(
            self, db_session, two_orgs, _uploads):
        from app.services.refresh_scheduler import refresh_dataflow

        src, flow, out = await self._flow_with_output(
            db_session, two_orgs["a"]["org"], _uploads)
        await db_session.delete(src)
        await db_session.commit()

        assert await refresh_dataflow(db_session, flow) is True

        await db_session.refresh(flow)
        assert flow.last_run_status == "failed"
        assert flow.last_run_error
