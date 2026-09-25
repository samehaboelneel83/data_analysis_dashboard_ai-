"""The decomposition tree: a number broken down one level at a time.

The property everything else depends on is that **children reconcile to their
parent**. A drill-down whose parts do not sum to the whole is worse than no
drill-down, because the reader cannot tell what is missing and will trust the
parts anyway. That is why a capped level folds its tail into "Other" rather than
dropping it, and why several tests here assert the sum rather than the shape.

The second concern is the "explain" split. The server may choose the next field,
but it must never be able to pass that choice off as the reader's -- hence the
`auto` flag, and a test that an explicit choice always wins.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.config import settings as app_settings
from app.models.models import Dataset, DatasetColumn, Role, RowSecurityRule, User
from app.core.security import create_access_token, hash_password
from app.services.widget_data import (DECOMP_MAX_DEPTH, shape_decomposition)


def sales(n=600, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "region": rng.choice(["EMEA", "APAC", "AMER"], n),
        "product": rng.choice(["Alpha", "Beta", "Gamma"], n),
        "channel": rng.choice(["Direct", "Partner"], n),
        "revenue": rng.integers(100, 1000, n).astype(float),
    })


def cfg(**over):
    base = {"roles": {"measure": "revenue"}, "aggregation": "sum"}
    base.update(over)
    return base


class TestItReconciles:
    def test_children_sum_to_the_parent(self):
        """The whole point. If this fails the visual is actively misleading."""
        r = shape_decomposition(sales(), cfg(split_by="region"))
        assert sum(c["value"] for c in r["children"]) == pytest.approx(r["total"])

    def test_drilling_narrows_to_that_branch(self):
        df = sales()
        root = shape_decomposition(df, cfg(split_by="region"))
        emea_total = next(c["value"] for c in root["children"] if c["name"] == "EMEA")

        node = shape_decomposition(df, cfg(path=[{"field": "region", "value": "EMEA"}],
                                           split_by="product"))

        assert node["total"] == pytest.approx(emea_total)
        assert sum(c["value"] for c in node["children"]) == pytest.approx(node["total"])

    def test_a_capped_level_folds_the_tail_into_other(self):
        """Dropping the tail would silently break reconciliation; naming it
        keeps the arithmetic honest AND tells the reader how much is hidden."""
        df = pd.DataFrame({"k": [f"v{i}" for i in range(40)] * 5,
                           "revenue": [10.0] * 200})
        r = shape_decomposition(df, cfg(split_by="k", limit=5))

        other = r["children"][-1]
        assert other["name"] == "Other"
        assert other["collapsed"] == 35
        assert sum(c["value"] for c in r["children"]) == pytest.approx(r["total"])

    def test_other_withholds_a_value_it_cannot_honestly_compute(self):
        """For avg/min/max an "Other" total is not the sum of anything, so the
        bucket is named and its value left null rather than invented."""
        df = pd.DataFrame({"k": [f"v{i}" for i in range(40)] * 5,
                           "revenue": [10.0] * 200})
        r = shape_decomposition(df, cfg(split_by="k", limit=5, aggregation="avg"))
        assert r["children"][-1]["value"] is None

    def test_counting_rows_when_no_measure_is_set(self):
        r = shape_decomposition(sales(), {"roles": {}, "split_by": "region"})
        assert r["total"] == 600
        assert sum(c["value"] for c in r["children"]) == 600


class TestTheExplainSplit:
    def test_it_finds_the_field_that_actually_separates(self):
        rng = np.random.default_rng(1)
        n = 600
        tier = rng.choice(["Free", "Paid"], n, p=[.7, .3])
        df = pd.DataFrame({
            "region": rng.choice(["EMEA", "APAC", "AMER"], n),
            "channel": rng.choice(["Direct", "Partner"], n),
            "tier": tier,
            "revenue": np.where(tier == "Paid", 5000, 200) + rng.integers(0, 100, n),
        })

        r = shape_decomposition(df, cfg(auto_split=True))

        assert r["split_by"] == "tier", "picked a noise column over the real driver"
        assert r["auto"] is True

    def test_an_explicit_choice_always_wins(self):
        """A suggestion must never override the reader."""
        r = shape_decomposition(sales(), cfg(auto_split=True, split_by="region"))
        assert r["split_by"] == "region"
        assert r["auto"] is False

    def test_the_reader_is_told_when_the_server_chose(self):
        auto = shape_decomposition(sales(), cfg(auto_split=True))
        manual = shape_decomposition(sales(), cfg(split_by="region"))
        assert auto["auto"] is True and manual["auto"] is False

    def test_no_split_is_offered_when_nothing_separates(self):
        df = pd.DataFrame({"only": ["same"] * 50, "revenue": [1.0] * 50})
        r = shape_decomposition(df, cfg(auto_split=True))
        assert r["split_by"] is None
        assert r["children"] == []


class TestItStaysBounded:
    def test_a_used_field_is_not_offered_again(self):
        """Splitting by region twice yields one child and no information."""
        r = shape_decomposition(sales(), cfg(path=[{"field": "region", "value": "EMEA"}],
                                             split_by="product"))
        assert "region" not in r["available"]
        assert "product" in r["available"] or "channel" in r["available"]

    def test_the_measure_is_never_a_split_candidate(self):
        r = shape_decomposition(sales(), cfg(split_by="region"))
        assert "revenue" not in r["available"]

    def test_depth_is_capped(self):
        deep = [{"field": "region", "value": "EMEA"}] * (DECOMP_MAX_DEPTH + 3)
        r = shape_decomposition(sales(), cfg(path=deep))
        assert len(r["path"]) == DECOMP_MAX_DEPTH
        assert r["at_max_depth"] is True

    def test_a_branch_whose_value_vanished_degrades_to_empty(self):
        """A saved widget outlives the data it was built on. An unknown value
        must give an empty branch the reader can climb out of, not a 500."""
        r = shape_decomposition(sales(), cfg(path=[{"field": "region", "value": "ATLANTIS"}],
                                             split_by="product"))
        assert r["total"] == 0
        assert r["children"] == []

    def test_an_unknown_split_field_is_not_an_error(self):
        r = shape_decomposition(sales(), cfg(split_by="nope"))
        assert r["children"] == []


class TestOverHttp:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    async def _dataset(self, db, org, tmp_path):
        df = sales()
        path = tmp_path / "sales.csv"
        df.to_csv(path, index=False)
        ds = Dataset(name="Sales", filename=str(path), org_id=org.id, mode="import")
        db.add(ds)
        await db.flush()
        for c in df.columns:
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db.commit()
        return ds

    @pytest.mark.asyncio
    async def test_it_renders_through_the_widget_endpoint(
            self, client, auth_headers, db_session, two_orgs, _uploads):
        ds = await self._dataset(db_session, two_orgs["a"]["org"], _uploads)

        resp = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "decomposition",
                  "config": {"roles": {"measure": "revenue"}, "aggregation": "sum",
                             "split_by": "region"}},
            headers=auth_headers["a"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["type"] == "decomposition"
        assert len(body["children"]) == 3
        assert sum(c["value"] for c in body["children"]) == pytest.approx(body["total"])

    @pytest.mark.asyncio
    async def test_rls_narrows_every_level(self, client, db_session, two_orgs, _uploads):
        """A restricted reader must drill their own slice. Without this the tree
        becomes a way to read totals the RLS rule exists to hide."""
        org = two_orgs["a"]["org"]
        ds = await self._dataset(db_session, org, _uploads)
        role = Role(org_id=org.id, name="emea-only", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                                       filter_expr="`region` == 'EMEA'"))
        user = User(org_id=org.id, role_id=role.id, email="e@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

        resp = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "decomposition",
                  "config": {"roles": {"measure": "revenue"}, "aggregation": "sum",
                             "split_by": "region"}},
            headers=headers)

        body = resp.json()
        assert [c["name"] for c in body["children"]] == ["EMEA"]


class TestItRefusesIdColumns:
    """A field with one row per value has maximal variation and zero
    explanatory power. Because the auto-split ranks ON variation, such a column
    wins every time it is offered -- found live, where splitting demo revenue
    suggested `date` (633 distinct values) over `region`."""

    def test_a_high_cardinality_column_is_not_offered(self):
        df = sales()
        df["order_id"] = [f"O{i}" for i in range(len(df))]
        r = shape_decomposition(df, cfg(split_by="region"))
        assert "order_id" not in r["available"]

    def test_the_auto_split_picks_a_real_level_over_an_id(self):
        rng = np.random.default_rng(3)
        n = 400
        df = pd.DataFrame({
            "tier": rng.choice(["Free", "Paid"], n),
            "order_id": [f"O{i}" for i in range(n)],
            "revenue": rng.integers(10, 100, n).astype(float),
        })
        r = shape_decomposition(df, cfg(auto_split=True))
        assert r["split_by"] == "tier", f"picked {r['split_by']}"

    def test_a_column_at_the_boundary_is_still_usable(self):
        """The ceiling excludes ids, not merely wide dimensions."""
        from app.services.widget_data import DECOMP_MAX_LEVELS
        n = DECOMP_MAX_LEVELS * 4
        df = pd.DataFrame({
            "sku": [f"S{i % DECOMP_MAX_LEVELS}" for i in range(n)],
            "revenue": [10.0] * n,
        })
        # Offered as a candidate before it is used...
        probe = shape_decomposition(df, cfg())
        assert "sku" in probe["available"], "a 50-level dimension is a level, not an id"
        # ...and it splits.
        r = shape_decomposition(df, cfg(split_by="sku", limit=5))
        assert r["children"]
