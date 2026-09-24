"""Small multiples: the same chart, once per value of a facet field.

Two properties decide whether this visual tells the truth.

**One shared scale.** Comparing the panels to each other is the entire point, so
`max_value` is computed across all of them and returned once. Per-panel axes
would draw a small category identically to a large one -- the single way small
multiples lie, and the reason the scale is a server-side fact rather than a
renderer's local decision.

**Panels are the ordinary chart.** Each one is produced by the SAME shaper the
inner widget type would use on its own, over a filtered frame. That is what
keeps aggregation, measures, quick calcs and formatting identical to the
un-faceted chart, instead of a second shaping path that drifts.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.config import settings as app_settings
from app.models.models import Dataset, DatasetColumn
from app.services.widget_data import (FACET_MAX_PANELS, shape_series,
                                      shape_small_multiples)


def sales(n=600, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "region": rng.choice(["EMEA", "APAC", "AMER"], n),
        "month": rng.choice(["Jan", "Feb", "Mar"], n),
        "revenue": rng.integers(100, 900, n).astype(float),
    })


def cfg(**over):
    base = {"facet_by": "region", "inner_widget_type": "bar",
            "dimension": "month", "measure": "revenue", "aggregation": "sum"}
    base.update(over)
    return base


class TestPanelsAreTheOrdinaryChart:
    def test_one_panel_per_facet_value(self):
        r = shape_small_multiples(sales(), cfg())
        assert {p["name"] for p in r["panels"]} == {"EMEA", "APAC", "AMER"}

    def test_a_panel_matches_the_same_chart_built_alone(self):
        """The guarantee that keeps faceting from becoming a second, drifting
        shaping path: a panel IS the chart, over a filtered frame."""
        df = sales()
        faceted = shape_small_multiples(df, cfg())
        emea_panel = next(p for p in faceted["panels"] if p["name"] == "EMEA")

        alone = shape_series(df[df["region"] == "EMEA"],
                             {"dimension": "month", "measure": "revenue",
                              "aggregation": "sum"})

        assert emea_panel["result"]["rows"] == alone["rows"]

    def test_the_facet_config_does_not_leak_into_the_panel(self):
        """`facet_by` is not a chart option; passing it through would make the
        inner shaper see a key it does not understand."""
        r = shape_small_multiples(sales(), cfg())
        rows = r["panels"][0]["result"]["rows"]
        assert rows and all("value" in row for row in rows)

    def test_it_facets_a_different_inner_chart_too(self):
        r = shape_small_multiples(sales(), cfg(inner_widget_type="line"))
        assert r["inner"] == "line"
        assert all(p["result"]["rows"] for p in r["panels"])


class TestOneSharedScale:
    def test_the_scale_spans_every_panel(self):
        """Per-panel axes would make a small category look like a large one."""
        r = shape_small_multiples(sales(), cfg())
        every_value = [row["value"] for p in r["panels"]
                       for row in p["result"]["rows"]]
        assert r["max_value"] == pytest.approx(max(every_value))

    def test_a_dominant_facet_sets_the_scale_for_all(self):
        df = sales()
        df.loc[df["region"] == "EMEA", "revenue"] *= 10
        r = shape_small_multiples(df, cfg())
        emea_max = max(row["value"] for p in r["panels"] if p["name"] == "EMEA"
                       for row in p["result"]["rows"])
        assert r["max_value"] == pytest.approx(emea_max)

    def test_no_numeric_rows_yields_no_scale_rather_than_zero(self):
        """A zero max would make the renderer divide by nothing; None tells it
        to fall back honestly."""
        empty = pd.DataFrame({"region": [], "month": [], "revenue": []})
        r = shape_small_multiples(empty, cfg())
        assert r["max_value"] is None


class TestItStaysReadable:
    def test_panels_are_capped_and_the_tail_is_reported(self):
        """A reader comparing panels cannot see which categories never made it
        onto the page -- so the count of those is part of the answer."""
        rng = np.random.default_rng(1)
        n = 900
        df = pd.DataFrame({"sku": rng.choice([f"S{i}" for i in range(30)], n),
                           "month": rng.choice(["Jan", "Feb"], n),
                           "revenue": rng.integers(10, 100, n).astype(float)})

        r = shape_small_multiples(df, cfg(facet_by="sku"))

        assert len(r["panels"]) == FACET_MAX_PANELS
        assert r["omitted"] == 30 - FACET_MAX_PANELS

    def test_the_biggest_facets_are_the_ones_kept(self):
        df = sales(n=400)
        # Make AMER overwhelmingly the largest by row count.
        df = pd.concat([df, sales(n=600).assign(region="AMER")], ignore_index=True)
        r = shape_small_multiples(df, cfg(facet_limit=1))
        assert [p["name"] for p in r["panels"]] == ["AMER"]

    def test_nothing_is_omitted_when_everything_fits(self):
        assert shape_small_multiples(sales(), cfg())["omitted"] == 0


class TestItDegradesRatherThanBreaking:
    def test_a_vanished_facet_column_still_draws_the_chart(self):
        """A saved widget outlives its data. Losing the facet field should cost
        the panels, not the visual."""
        r = shape_small_multiples(sales(), cfg(facet_by="gone"))
        assert len(r["panels"]) == 1
        assert r["panels"][0]["name"] is None
        assert r["panels"][0]["result"]["rows"], "the single chart lost its data too"

    def test_no_facet_configured_behaves_the_same(self):
        r = shape_small_multiples(sales(), cfg(facet_by=None))
        assert len(r["panels"]) == 1

    def test_it_cannot_facet_itself(self):
        """Recursion here would be an infinite request, not a clever feature."""
        r = shape_small_multiples(sales(), cfg(inner_widget_type="small_multiples"))
        assert r["inner"] == "bar"

    def test_an_empty_frame_is_not_an_error(self):
        empty = pd.DataFrame({"region": [], "month": [], "revenue": []})
        r = shape_small_multiples(empty, cfg())
        assert r["type"] == "small_multiples"


class TestOverHttp:
    @pytest.fixture(autouse=True)
    def _uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
        return tmp_path

    @pytest.mark.asyncio
    async def test_it_renders_through_the_widget_endpoint(
            self, client, auth_headers, db_session, two_orgs, _uploads):
        df = sales()
        path = _uploads / "sales.csv"
        df.to_csv(path, index=False)
        ds = Dataset(name="Sales", filename=str(path),
                     org_id=two_orgs["a"]["org"].id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        for c in df.columns:
            db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "small_multiples", "config": cfg()},
            headers=auth_headers["a"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["type"] == "small_multiples"
        assert len(body["panels"]) == 3
        assert body["max_value"] > 0
