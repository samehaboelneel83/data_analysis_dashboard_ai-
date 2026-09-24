"""Novelty: what changed since the last scan.

Insights were recomputed per request and forgotten, so the engine could never
answer the question a returning reader actually has -- "what is DIFFERENT since
yesterday?" A finding seen daily and a finding that appeared this morning
rendered identically.

The scan now persists (AnalysisResult, analysis_type="insights_scan") and each
run is annotated against the previous one. Two design points carry the value:

* **The first run gets no annotations.** Marking everything "new" on run one
  is noise dressed as signal -- a page of NEW badges teaches the reader to
  ignore NEW badges.

* **Restricted callers are excluded from BOTH sides.** Their scan must not be
  written to the shared org-wide row (the AnalysisResult poisoning rule from
  routers/analysis.py), and comparing their restricted scan against an
  unrestricted baseline would flag "changes" that are really the rows their
  rules hide -- an inference channel dressed as a badge.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.insights import (NOVELTY_CHANGED_DELTA, apply_novelty)


def _f(kind="trend", cols=("revenue", "date"), score=0.5, **kw):
    return {"kind": kind, "columns": list(cols), "score": score,
            "title": "t", "detail": "d", **kw}


class TestTheAnnotationRules:
    def test_no_previous_scan_means_no_annotations(self):
        out = apply_novelty([_f()], None)
        assert "novelty" not in out[0]

    def test_a_finding_absent_from_the_previous_scan_is_new(self):
        out = apply_novelty([_f()], [])
        assert out[0]["novelty"] == "new"

    def test_a_persistent_finding_with_a_steady_score_is_unchanged(self):
        out = apply_novelty([_f(score=0.5)], [_f(score=0.52)])
        assert out[0]["novelty"] == "unchanged"
        assert out[0]["score"] == 0.5          # no boost

    def test_a_material_score_move_is_changed(self):
        out = apply_novelty([_f(score=0.5)],
                            [_f(score=0.5 - NOVELTY_CHANGED_DELTA)])
        assert out[0]["novelty"] == "changed"

    def test_identity_ignores_the_title(self):
        """The title carries the computed numbers, so it changes whenever the
        data does. A trend on (revenue, date) is the same finding next week
        even though its sentence states a different percentage."""
        cur = _f(title="revenue ran 18% above average")
        prev = _f(title="revenue ran 9% above average")
        assert apply_novelty([cur], [prev])[0]["novelty"] == "unchanged"

    def test_identity_ignores_column_order(self):
        cur = _f(kind="correlation", cols=("a", "b"))
        prev = _f(kind="correlation", cols=("b", "a"))
        assert apply_novelty([cur], [prev])[0]["novelty"] == "unchanged"


class TestNoveltyMovesTheRanking:
    def test_a_new_finding_outranks_an_equal_persistent_one(self):
        # The whole point of the boost: the reader has already seen the
        # persistent finding.
        cur = [_f(kind="standout", cols=("region", "revenue"), score=0.6),
               _f(kind="trend", cols=("units", "date"), score=0.6)]
        prev = [_f(kind="standout", cols=("region", "revenue"), score=0.6)]
        out = apply_novelty(cur, prev)
        assert out[0]["kind"] == "trend"
        assert out[0]["novelty"] == "new"

    def test_the_boost_cannot_bury_a_strong_standing_finding(self):
        cur = [_f(kind="standout", cols=("region", "revenue"), score=0.9),
               _f(kind="trend", cols=("units", "date"), score=0.3)]
        prev = [_f(kind="standout", cols=("region", "revenue"), score=0.9)]
        out = apply_novelty(cur, prev)
        assert out[0]["kind"] == "standout"

    def test_the_score_is_capped_at_one(self):
        out = apply_novelty([_f(score=0.95)], [])
        assert out[0]["score"] <= 1.0

    def test_the_input_is_not_mutated(self):
        """The caller persists the RAW scan for the next comparison; a mutated
        input would store boosted scores, compounding the boost every run."""
        cur = [_f(score=0.5)]
        apply_novelty(cur, [])
        assert cur[0]["score"] == 0.5
        assert "novelty" not in cur[0]


@pytest.fixture
def scan_ds(tmp_path):
    """Data with PLANTED findings -- a standout and a correlation.

    The first version of this fixture was two random columns, which yields ZERO
    findings: no date for a trend, no measure pair for a correlation, and even
    shares. Every endpoint test then passed vacuously over an empty list --
    `all("novelty" not in f for f in [])` is True no matter what the code does.
    The fixture-derives-nothing trap, again; the guard is the explicit
    findings-exist assertion each endpoint test now carries.
    """
    rng = np.random.default_rng(0)
    n = 200
    region = rng.choice(["N", "S"], n)
    # N carries an outsized share of revenue -> standout finding. The detector
    # gate is top_frac > uniform * 1.6, i.e. > 0.8 with two levels -- a x4
    # concentration sat exactly AT the boundary and fired nothing, so the
    # plant is x10.
    revenue = (rng.normal(100, 10, n) + (region == "N") * 900).round(2)
    # cost tracks revenue -> correlation finding.
    cost = (revenue * 0.9 + rng.normal(0, 5, n)).round(2)
    p = tmp_path / "scan.csv"
    pd.DataFrame({"region": region, "revenue": revenue,
                  "cost": cost}).to_csv(p, index=False)
    return str(p)


async def _make_ds(db, org, path):
    from app.models.models import Dataset, DatasetColumn
    ds = Dataset(name="Scan", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("revenue", "numeric"),
                 ("cost", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


class TestThePersistedScan:
    @pytest.mark.asyncio
    async def test_first_run_stores_and_annotates_nothing(
            self, client, auth_headers, db_session, two_orgs, scan_ds):
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/insights",
                              headers=auth_headers["a"])
        assert r.status_code == 200
        assert r.json()["findings"], "fixture produced no findings; every assertion below is vacuous"
        assert all("novelty" not in f for f in r.json()["findings"])

    @pytest.mark.asyncio
    async def test_second_run_over_the_same_data_is_all_unchanged(
            self, client, auth_headers, db_session, two_orgs, scan_ds):
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        await client.post(f"/api/v1/datasets/{ds.id}/insights",
                          headers=auth_headers["a"])
        r = await client.post(f"/api/v1/datasets/{ds.id}/insights",
                              headers=auth_headers["a"])
        assert r.json()["findings"], "fixture produced no findings"
        marks = {f.get("novelty") for f in r.json()["findings"]}
        assert marks == {"unchanged"}

    @pytest.mark.asyncio
    async def test_the_stored_scan_keeps_raw_unannotated_scores(
            self, client, auth_headers, db_session, two_orgs, scan_ds):
        """Boost compounding: if run N stored its boosted scores, run N+1 would
        measure its honest score against an inflated baseline and flag phantom
        changes forever."""
        from sqlalchemy import select
        from app.models.models import AnalysisResult
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        # Seed an EMPTY previous scan so this run flags everything new (boosted).
        db_session.add(AnalysisResult(dataset_id=ds.id,
                                      analysis_type="insights_scan",
                                      result={"findings": []}))
        await db_session.commit()
        r = await client.post(f"/api/v1/datasets/{ds.id}/insights",
                              headers=auth_headers["a"])
        assert {f.get("novelty") for f in r.json()["findings"]} == {"new"}

        row = (await db_session.execute(select(AnalysisResult).where(
            AnalysisResult.dataset_id == ds.id,
            AnalysisResult.analysis_type == "insights_scan"))).scalar_one()
        # Stored raw: no annotations, and no boosted score.
        assert "novelty" not in str(row.result["findings"])
        stored = {f["title"]: f["score"] for f in row.result["findings"]}
        boosted = {f["title"]: f["score"] for f in r.json()["findings"]}
        assert any(boosted[t] > stored[t] for t in stored if t in boosted)

    @pytest.mark.asyncio
    async def test_a_restricted_caller_neither_reads_nor_writes_the_scan(
            self, client, auth_headers, db_session, two_orgs, scan_ds):
        from sqlalchemy import func, select
        from app.core.security import create_access_token, hash_password
        from app.models.models import (AnalysisResult, ColumnSecurityRule,
                                       Role, User)
        org = two_orgs["a"]["org"]
        ds = await _make_ds(db_session, org, scan_ds)
        role = Role(org_id=org.id, name="no-cost", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id,
                                          denied_columns=["cost"]))
        user = User(org_id=org.id, role_id=role.id, email="nu@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

        r = await client.post(f"/api/v1/datasets/{ds.id}/insights", headers=headers)
        assert r.status_code == 200
        assert r.json()["findings"], "fixture produced no findings"
        # No annotations for a restricted caller...
        assert all("novelty" not in f for f in r.json()["findings"])
        # ...and no shared row written: the next unrestricted scan must not be
        # measured against a restricted baseline.
        count = (await db_session.execute(select(func.count()).select_from(
            AnalysisResult).where(
                AnalysisResult.dataset_id == ds.id,
                AnalysisResult.analysis_type == "insights_scan"))).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_the_scan_does_not_shadow_the_profile_on_get(
            self, client, auth_headers, db_session, two_orgs, scan_ds):
        """GET /analysis returns the latest AnalysisResult row with no type
        filter of its own. Without the exclusion, a fresh insight scan would be
        served where the Overview tab expects column statistics."""
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        await client.post(f"/api/v1/datasets/{ds.id}/analysis",
                          json={"analysis_type": "full"},
                          headers=auth_headers["a"])
        await client.post(f"/api/v1/datasets/{ds.id}/insights",
                          headers=auth_headers["a"])   # stored AFTER the profile
        got = await client.get(f"/api/v1/datasets/{ds.id}/analysis",
                               headers=auth_headers["a"])
        assert got.status_code == 200
        assert "type_map" in got.json()      # a profile, not a findings list


class TestTheScheduledRescan:
    """After a refresh, the stored baseline describes the OLD data -- rescanning
    there is what makes NEW/CHANGED badges describe the refresh rather than
    whichever click happened to come first."""

    @pytest.mark.asyncio
    async def test_a_rescan_writes_the_shared_baseline(
            self, db_session, two_orgs, scan_ds):
        from sqlalchemy import select
        from app.models.models import AnalysisResult
        from app.services.refresh_scheduler import rescan_insights
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        assert await rescan_insights(db_session, ds) is True
        row = (await db_session.execute(select(AnalysisResult).where(
            AnalysisResult.dataset_id == ds.id,
            AnalysisResult.analysis_type == "insights_scan"))).scalar_one()
        assert row.result["findings"], "the scan stored no findings"
        # Raw, unannotated -- the same rule the click path follows.
        assert "novelty" not in str(row.result["findings"])

    @pytest.mark.asyncio
    async def test_a_second_rescan_updates_in_place(
            self, db_session, two_orgs, scan_ds):
        from sqlalchemy import func, select
        from app.models.models import AnalysisResult
        from app.services.refresh_scheduler import rescan_insights
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        await rescan_insights(db_session, ds)
        await rescan_insights(db_session, ds)
        count = (await db_session.execute(select(func.count()).select_from(
            AnalysisResult).where(
                AnalysisResult.dataset_id == ds.id,
                AnalysisResult.analysis_type == "insights_scan"))).scalar()
        assert count == 1

    @pytest.mark.asyncio
    async def test_a_join_pipeline_is_skipped_not_scanned(
            self, db_session, two_orgs, scan_ds):
        """THE security property. Joined frames are secured per identity, and
        the scheduler has none whose rules are guaranteed empty -- a baseline
        quietly shaped by one person's row visibility would poison every
        reader's badges. Skipping is the only write that cannot lie."""
        from sqlalchemy import func, select
        from app.models.models import AnalysisResult
        from app.services.refresh_scheduler import rescan_insights
        ds = await _make_ds(db_session, two_orgs["a"]["org"], scan_ds)
        # Steps live in column_meta under the prep key, and a join step is
        # kind="join" -- the first version of this fixture used a `prep_steps`
        # attribute and `type`, neither of which exists, so the "skip" it
        # observed was really "no steps found". Route through the real reader.
        from app.services.prep import PREP_STEPS_KEY, collect_join_dataset_ids, prep_steps_of
        ds.column_meta = {PREP_STEPS_KEY: [
            {"kind": "join", "dataset_id": 999,
             "left_on": "region", "right_on": "region"}]}
        await db_session.commit()
        assert collect_join_dataset_ids(prep_steps_of(ds)) == [999], (
            "fixture does not register as a join pipeline; the skip assertion "
            "below would pass vacuously")
        assert await rescan_insights(db_session, ds) is False
        count = (await db_session.execute(select(func.count()).select_from(
            AnalysisResult).where(
                AnalysisResult.dataset_id == ds.id))).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_a_broken_file_is_swallowed_never_raised(
            self, db_session, two_orgs):
        # Fail-soft like everything in the scheduler loop: a scan failure must
        # never mark the REFRESH failed.
        from app.services.refresh_scheduler import rescan_insights
        from app.models.models import Dataset
        org = two_orgs["a"]["org"]
        ds = Dataset(name="gone", filename="/nowhere/gone.csv",
                     org_id=org.id, mode="import")
        db_session.add(ds)
        await db_session.commit()
        assert await rescan_insights(db_session, ds) is False

    def test_refresh_one_actually_calls_it(self):
        """The wiring pin. A helper nothing calls is the unreachable-feature
        trap this codebase has hit seven times; this fails until refresh_one
        invokes the rescan after its commit."""
        import inspect
        from app.services import refresh_scheduler as rs
        src = inspect.getsource(rs.refresh_one)
        assert "rescan_insights(" in src

