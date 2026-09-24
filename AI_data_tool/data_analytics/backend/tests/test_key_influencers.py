"""Key influencers: which factors move an outcome.

The analysis has to survive two very different failure modes. It must actually
find a driver that is there -- pinned here by planting one in synthetic data and
requiring it to come back on top -- and it must refuse to invent one when the
data cannot support it, because a confident "your top driver is X" that nobody
can check is worse than no answer at all.

The security tests matter as much as the statistical ones: this reports group
RATES, so a restricted viewer must get influencers computed over their own rows,
and a denied column must never surface as a named factor.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.config import settings as app_settings
from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn,
                               Role, RowSecurityRule, User)
from app.services.analysis.influencers import (InfluencerError, MIN_ROWS,
                                               key_influencers)


def churn_frame(n=800, seed=0):
    """Data with a KNOWN answer: Basic plan and many support tickets drive
    churn; long tenure protects against it."""
    rng = np.random.default_rng(seed)
    plan = rng.choice(["Basic", "Pro", "Enterprise"], n, p=[.5, .3, .2])
    support = rng.choice(["none", "some", "many"], n, p=[.5, .35, .15])
    tenure = rng.integers(1, 60, n)
    p = (0.06 + (plan == "Basic") * 0.30 + (support == "many") * 0.28
         - (tenure > 40) * 0.05)
    churn = rng.random(n) < np.clip(p, 0.01, 0.95)
    return pd.DataFrame({"plan": plan, "support": support, "tenure": tenure,
                         "churned": np.where(churn, "yes", "no")})


class TestItFindsWhatIsThere:
    def test_the_planted_drivers_come_back_on_top(self):
        r = key_influencers(churn_frame(), target="churned").to_dict()
        top_two = {(x["factor"], x["group"]) for x in r["rows"][:2]}
        assert top_two == {("support", "many"), ("plan", "Basic")}

    def test_it_reports_lift_against_the_baseline(self):
        r = key_influencers(churn_frame(), target="churned").to_dict()
        top = r["rows"][0]
        assert top["lift"] > 1.5, "the strongest driver should be well above baseline"
        assert top["rate"] == pytest.approx(top["lift"] * r["meta"]["baseline"], rel=1e-3)

    def test_a_protective_factor_ranks_too(self):
        """A factor that HALVES the outcome is exactly as informative as one
        that doubles it -- ranking on the raw rate would bury it."""
        rows = key_influencers(churn_frame(), target="churned").to_dict()["rows"]
        assert any(x["lift"] < 0.6 for x in rows), rows

    def test_it_defaults_to_the_rarer_outcome(self):
        """'What drives churn' is the question; 'what drives staying' is not."""
        r = key_influencers(churn_frame(), target="churned").to_dict()
        assert r["meta"]["target_value"] == "yes"
        assert r["meta"]["measure"] == "rate"

    def test_an_explicit_outcome_is_honoured(self):
        r = key_influencers(churn_frame(), target="churned",
                            target_value="no").to_dict()
        assert r["meta"]["target_value"] == "no"

    def test_a_numeric_target_compares_means(self):
        df = churn_frame()
        df["spend"] = np.where(df["plan"] == "Enterprise", 900.0, 100.0) \
            + np.random.default_rng(1).normal(0, 20, len(df))
        r = key_influencers(df, target="spend").to_dict()
        assert r["meta"]["measure"] == "mean"
        assert r["rows"][0]["factor"] == "plan"

    def test_numeric_factors_become_readable_ranges(self):
        """A group has to be a rule a person can read, not a threshold to four
        decimal places."""
        r = key_influencers(churn_frame(), target="churned",
                            factors=["tenure"]).to_dict()
        assert r["rows"], "tenure should yield groups"
        assert all(x["grouped_by"] == "quantile" for x in r["rows"])


class TestItRefusesToInvent:
    def test_too_few_rows_is_refused(self):
        df = churn_frame(n=MIN_ROWS - 5)
        with pytest.raises(InfluencerError, match="at least"):
            key_influencers(df, target="churned")

    def test_a_constant_target_is_refused(self):
        df = churn_frame()
        df["churned"] = "no"
        with pytest.raises(InfluencerError, match="only one value"):
            key_influencers(df, target="churned")

    def test_an_unknown_target_is_refused(self):
        with pytest.raises(InfluencerError, match="not in this dataset"):
            key_influencers(churn_frame(), target="nope")

    def test_an_unknown_target_value_is_refused(self):
        with pytest.raises(InfluencerError, match="not a value of"):
            key_influencers(churn_frame(), target="churned", target_value="maybe")

    def test_an_id_column_is_skipped_not_reported_as_the_driver(self):
        """A near-unique column splits the data perfectly and explains nothing.
        Left in, it would top every ranking on every dataset."""
        df = churn_frame()
        df["customer_id"] = [f"C{i}" for i in range(len(df))]
        r = key_influencers(df, target="churned").to_dict()
        assert all(x["factor"] != "customer_id" for x in r["rows"])
        assert any("customer_id" in w for w in r["warnings"])

    def test_tiny_groups_cannot_top_the_ranking(self):
        """A 3-row group with a 12x lift is an anecdote, not an influencer."""
        df = churn_frame()
        df.loc[df.index[:3], "plan"] = "Bespoke"
        df.loc[df.index[:3], "churned"] = "yes"
        r = key_influencers(df, target="churned").to_dict()
        assert all(x["group"] != "Bespoke" for x in r["rows"])

    def test_it_says_influence_is_not_causation(self):
        """Carried in the payload, not just the docs -- a UI rendering 'top
        driver' without it invites exactly the wrong reading."""
        r = key_influencers(churn_frame(), target="churned").to_dict()
        assert "not proof" in r["meta"]["caveat"]


class TestOverHttp:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    async def _dataset(self, db, org, tmp_path, frame=None):
        df = churn_frame() if frame is None else frame
        path = tmp_path / "churn.csv"
        df.to_csv(path, index=False)
        ds = Dataset(name="Churn", filename=str(path), org_id=org.id, mode="import")
        db.add(ds)
        await db.flush()
        for c in df.columns:
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db.commit()
        return ds

    @pytest.mark.asyncio
    async def test_it_answers_over_http(self, client, auth_headers, db_session,
                                        two_orgs, _uploads):
        ds = await self._dataset(db_session, two_orgs["a"]["org"], _uploads)
        resp = await client.post(f"/api/v1/datasets/{ds.id}/key-influencers",
                                 json={"target": "churned"},
                                 headers=auth_headers["a"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kind"] == "key_influencers"
        assert body["rows"], "no influencers returned"

    @pytest.mark.asyncio
    async def test_it_is_in_the_analysis_registry(self, client, auth_headers):
        """The registry is what the UI and the agent's prompt both read, so an
        analysis missing from it is invisible to both."""
        resp = await client.get("/api/v1/analysis/registry", headers=auth_headers["a"])
        names = {a["name"] for a in resp.json()["analyses"]}
        assert "key_influencers" in names

    @pytest.mark.asyncio
    async def test_a_bad_target_is_a_400_not_a_500(self, client, auth_headers,
                                                   db_session, two_orgs, _uploads):
        ds = await self._dataset(db_session, two_orgs["a"]["org"], _uploads)
        resp = await client.post(f"/api/v1/datasets/{ds.id}/key-influencers",
                                 json={"target": "nope"}, headers=auth_headers["a"])
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_another_orgs_dataset_is_not_reachable(self, client, auth_headers,
                                                         db_session, two_orgs, _uploads):
        ds = await self._dataset(db_session, two_orgs["a"]["org"], _uploads)
        resp = await client.post(f"/api/v1/datasets/{ds.id}/key-influencers",
                                 json={"target": "churned"}, headers=auth_headers["b"])
        assert resp.status_code == 404


class TestItRespectsSecurity:
    """Influencers are computed from group RATES, so the frame they run over has
    to be the viewer's own -- otherwise the platform answers 'what drives churn'
    using rows the asker may not see."""

    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    async def _restricted_user(self, db, org, dataset_id, *, rls=None, denied=None):
        role = Role(org_id=org.id, name="restricted", is_org_admin=False)
        db.add(role)
        await db.flush()
        if rls:
            db.add(RowSecurityRule(role_id=role.id, dataset_id=dataset_id,
                                   filter_expr=rls))
        if denied:
            db.add(ColumnSecurityRule(role_id=role.id, dataset_id=dataset_id,
                                      denied_columns=denied))
        user = User(org_id=org.id, role_id=role.id, email="r@example.com",
                    password_hash=hash_password("pw"))
        db.add(user)
        await db.flush()
        await db.commit()
        return {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

    async def _dataset(self, db, org, tmp_path):
        df = churn_frame()
        path = tmp_path / "churn.csv"
        df.to_csv(path, index=False)
        ds = Dataset(name="Churn", filename=str(path), org_id=org.id, mode="import")
        db.add(ds)
        await db.flush()
        for c in df.columns:
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db.commit()
        return ds

    @pytest.mark.asyncio
    async def test_rls_narrows_the_frame_it_analyses(self, client, db_session,
                                                     two_orgs, _uploads):
        org = two_orgs["a"]["org"]
        ds = await self._dataset(db_session, org, _uploads)
        headers = await self._restricted_user(db_session, org, ds.id,
                                              rls="`plan` == 'Basic'")

        resp = await client.post(f"/api/v1/datasets/{ds.id}/key-influencers",
                                 json={"target": "churned"}, headers=headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Every visible row is Basic, so plan cannot vary and cannot be a factor.
        assert all(x["factor"] != "plan" for x in body["rows"])
        assert body["meta"]["n_rows_used"] < 800

    @pytest.mark.asyncio
    async def test_a_denied_column_never_becomes_an_influencer(
            self, client, db_session, two_orgs, _uploads):
        """Naming a hidden column, with a rate attached, would leak exactly
        what the rule hides."""
        org = two_orgs["a"]["org"]
        ds = await self._dataset(db_session, org, _uploads)
        headers = await self._restricted_user(db_session, org, ds.id,
                                              denied=["plan"])

        resp = await client.post(f"/api/v1/datasets/{ds.id}/key-influencers",
                                 json={"target": "churned"}, headers=headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert all(x["factor"] != "plan" for x in body["rows"])
        assert all(c["name"] != "plan" for c in body["columns"])

    @pytest.mark.asyncio
    async def test_a_denied_column_cannot_be_the_target(
            self, client, db_session, two_orgs, _uploads):
        org = two_orgs["a"]["org"]
        ds = await self._dataset(db_session, org, _uploads)
        headers = await self._restricted_user(db_session, org, ds.id,
                                              denied=["churned"])

        resp = await client.post(f"/api/v1/datasets/{ds.id}/key-influencers",
                                 json={"target": "churned"}, headers=headers)

        assert resp.status_code == 400
        assert "not available to you" in resp.json()["detail"]
