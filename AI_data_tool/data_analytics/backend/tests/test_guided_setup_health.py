"""Guided setup 3a-3c: Check & discover -- plain lines, verified rules, fixes."""
import numpy as np
import pandas as pd
import pytest

from app.services.data_quality import quality_report
from app.services.guided_setup import health


class FakeClient:
    enabled = True
    last_error = None

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else None


def cars_frame(n=400):
    rng = np.random.default_rng(1)
    age = rng.integers(0, 15, n).astype(float)
    df = pd.DataFrame({
        "make": rng.choice(["Toyota", "Kia", "Fiat"], n),
        "price": rng.integers(200_000, 2_000_000, n).astype(float),
        "car_age": age,
        "mileage": age * 15_000 + 5_000,
        "imported": [None if i % 3 else "Yes" for i in range(n)],
    })
    df.loc[:9, "mileage"] = 180.0        # ten old cars with almost no km
    df.loc[:9, "car_age"] = 10.0
    df.loc[20:29, "car_age"] = -1.0      # a code for unknown
    df.loc[40:44, "price"] = -5.0        # entry mistakes
    return df


class TestPlainLines:
    def test_every_line_says_what_why_and_what_to_do(self):
        df = cars_frame()
        items = health.column_items(quality_report(df), df, "en")
        kinds = {(i["kind"], i["column"]) for i in items}
        assert ("empty", "imported") in kinds
        assert ("placeholder", "car_age") in kinds
        for i in items:
            assert i["what"] and i["why"] and i["todo"]
        empty = next(i for i in items if i["kind"] == "empty")
        assert empty["what"] == "67% of “imported” is empty."
        assert empty["action"]["kind"] == "fill"

    def test_a_number_column_with_blanks_is_not_offered_unknown(self):
        df = pd.DataFrame({"mileage": [1.0, None, None, 4.0, 5.0, 6.0, 7.0, 8.0]})
        item = next(i for i in health.column_items(quality_report(df), df, "en") if i["kind"] == "empty")
        assert item["action"] is None and "“No”" not in item["why"]

    def test_arabic(self):
        df = cars_frame()
        items = health.column_items(quality_report(df), df, "ar")
        assert any("فارغ" in i["what"] for i in items)

    def test_a_code_for_unknown_is_not_also_reported_as_negative(self):
        df = cars_frame()
        items = health.column_items(quality_report(df), df, "en")
        skip = {i["column"] for i in items if i["kind"] == "placeholder"}
        rules = health.generic_rules(df, "en", skip=skip)
        assert [r["column"] for r in rules if r["kind"] == "negative"] == ["price"]
        assert rules[0]["rows"] == 5


class TestModelRules:
    def test_implies_and_bare_names_are_normalised(self):
        expr = health.normalise_rule("car_age >= 5 implies mileage >= 10000", ["car_age", "mileage"])
        assert expr == "not (`car_age` >= 5) or (`mileage` >= 10000)"

    @pytest.mark.parametrize("expr", ["`price` > 0", "__import__('os')", "`price`.abs() > 1", "len(`make`) > 1"])
    def test_only_plain_comparisons_over_two_columns(self, expr):
        assert health.rule_columns(expr, ["price", "make"]) is None

    async def test_a_rule_is_kept_only_when_the_data_breaks_it_a_little(self):
        df = cars_frame()
        client = FakeClient({"rules": [
            {"columns": ["car_age", "mileage"], "relation": "old cars have been driven",
             "expression": "car_age >= 5 implies mileage >= 1000",
             "what": "Old cars with almost no km", "why": "Likely typos", "todo": "Leave them out"},
            {"columns": ["price", "car_age"], "relation": "never broken",
             "expression": "`price` > -100 or `car_age` > 100", "what": "x", "why": "x", "todo": "x"},
            {"columns": ["price", "mileage"], "relation": "nonsense", "expression": "`price` < `mileage`",
             "what": "x", "why": "x", "todo": "x"},
        ]})
        rules = await health.model_rules(df, None, "en", client)
        assert len(rules) == 1
        r = rules[0]
        assert r["rows"] == 10 and "(10 / 400)" in r["what"]
        # The fix keeps rows the rule cannot judge (an empty value it needs).
        assert "`mileage` != `mileage`" in r["action"]["expression"]
        from app.services.widget_data import apply_filter_expr
        assert len(apply_filter_expr(df, r["action"]["expression"], silent=False)) == 390


class TestInsights:
    async def test_the_model_only_rewords_and_keeps_order(self):
        findings = [{"kind": "standout", "score": .9, "title": "Coupes average 5.7M", "detail": "vs 2.1M", "columns": ["body"]},
                    {"kind": "data_quality", "score": 1, "title": "dq", "detail": "", "columns": []},
                    {"kind": "trend", "score": .5, "title": "Prices rose 18%", "detail": "", "columns": ["date"]}]
        client = FakeClient({"items": [{"index": 0, "what": "Coupes sell high: 5.7M", "why": "A premium segment",
                                        "todo": "Compare asking prices"}]})
        out = await health.plain_insights(findings, {"work": "dealer"}, "en", client)
        assert [i["what"] for i in out] == ["Coupes sell high: 5.7M", "Prices rose 18%"]
        assert "never call it the person's own" in client.calls[0][0]["content"]


class TestFixes:
    @pytest.mark.parametrize("action,step", [
        ({"kind": "fill", "column": "imported"}, {"kind": "fill_nulls", "column": "imported", "method": "value", "value": "Unknown"}),
        ({"kind": "drop_column", "column": "x"}, {"kind": "remove_columns", "columns": ["x"]}),
        ({"kind": "exclude", "expression": "`a` >= 0"}, {"kind": "filter_rows", "expression": "`a` >= 0"}),
        ({"kind": "dedupe"}, {"kind": "drop_duplicates"}),
    ])
    def test_each_fix_is_a_valid_prep_step(self, action, step):
        from app.services.prep import validate_prep_steps
        got = health.prep_step_for(action, "en")
        assert got == step
        validate_prep_steps([got], {"imported", "x", "a"}, {})


class TestRoutes:
    @pytest.fixture
    async def setup(self, client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
        from app.models.models import DataSource, Dataset
        from app.routers import guided_setup

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: FakeClient())
        df = cars_frame()

        async def frame(db, ds, user):
            return df
        monkeypatch.setattr("app.services.alerts.alert_frame", frame)

        async def no_insights(*a, **k):
            return {"findings": []}
        monkeypatch.setattr("app.routers.datasets.dataset_insights", no_insights)
        org = two_orgs["a"]["org"].id
        src = DataSource(name="Cars DB", type="postgresql", config={}, org_id=org, sync_status="ok")
        ds = Dataset(name="Cars", org_id=org, row_count=400, filename="x.parquet")
        db_session.add_all([src, ds])
        await db_session.commit()
        await client.get(f"/api/v1/setup/{src.id}", headers=auth_headers["a"])
        await client.patch(f"/api/v1/setup/{src.id}", headers=auth_headers["a"], json={"dataset_ids": [ds.id]})
        return src, ds

    async def test_each_dataset_is_checked_once_and_kept(self, client, auth_headers, setup):
        src, ds = setup
        first = (await client.get(f"/api/v1/setup/{src.id}/check", headers=auth_headers["a"])).json()
        f = first["datasets"][0]["findings"]
        assert f["checked"] and not f["pending"] and f["rows"] == 400
        assert any(i["kind"] == "placeholder" for i in f["health"])
        again = (await client.get(f"/api/v1/setup/{src.id}/check", headers=auth_headers["a"])).json()
        assert again["datasets"][0]["findings"]["health"] == f["health"]

    async def test_fix_adds_a_prep_step_and_is_remembered(self, client, auth_headers, setup, monkeypatch):
        src, ds = setup
        seen = {}

        async def fake_set(dataset_id, steps, db, user):
            seen["steps"] = steps
            return steps
        monkeypatch.setattr("app.routers.datasets.set_prep_steps", fake_set)
        f = (await client.get(f"/api/v1/setup/{src.id}/check", headers=auth_headers["a"])).json()["datasets"][0]["findings"]
        item = next(i for i in f["health"] if i["kind"] == "empty")
        r = (await client.post(f"/api/v1/setup/{src.id}/check/{ds.id}/fix", headers=auth_headers["a"],
                               json={"item_id": item["id"]})).json()
        assert seen["steps"][-1]["kind"] == "fill_nulls"
        assert f"{item['id']}|fix" in r["findings"]["fixed"]

    async def test_findings_are_offered_to_the_datasets_own_pages(self, client, auth_headers, setup):
        src, ds = setup
        await client.get(f"/api/v1/setup/{src.id}/check", headers=auth_headers["a"])
        got = (await client.get(f"/api/v1/setup/findings/{ds.id}", headers=auth_headers["a"])).json()
        assert got["source_id"] == src.id and got["findings"]["health"]

    async def test_a_dataset_outside_the_setup_cannot_be_fixed(self, client, auth_headers, setup):
        src, ds = setup
        r = await client.post(f"/api/v1/setup/{src.id}/check/999999/fix", headers=auth_headers["a"],
                              json={"item_id": "x"})
        assert r.status_code == 404


class TestAnyDataset:
    @pytest.fixture
    async def ds(self, db_session, two_orgs, monkeypatch):
        from app.models.models import Dataset
        df = cars_frame()

        async def frame(db, ds, user):
            return df
        monkeypatch.setattr("app.services.alerts.alert_frame", frame)
        d = Dataset(name="upload.csv", org_id=two_orgs["a"]["org"].id, row_count=400, filename="u.parquet")
        db_session.add(d)
        await db_session.commit()
        return d

    async def test_an_upload_gets_plain_health_without_a_model(self, client, auth_headers, ds, monkeypatch):
        def no_model(*a, **k):
            raise AssertionError("no model for the quick health")
        monkeypatch.setattr("app.services.llm.get_client", no_model)
        body = (await client.get(f"/api/v1/setup/datasets/{ds.id}/health?lang=ar", headers=auth_headers["a"])).json()
        assert body["rows"] == 400 and body["health"]
        assert any("فارغ" in i["what"] for i in body["health"])

    async def test_another_orgs_dataset_is_404(self, client, auth_headers, ds):
        assert (await client.get(f"/api/v1/setup/datasets/{ds.id}/health", headers=auth_headers["b"])).status_code == 404
        assert (await client.post(f"/api/v1/setup/datasets/{ds.id}/fix", headers=auth_headers["b"],
                                  json={"action": {"kind": "dedupe"}})).status_code == 404

    async def test_fix_goes_through_the_datasets_own_prep_route(self, client, auth_headers, ds, monkeypatch):
        seen = {}

        async def fake_set(dataset_id, steps, db, user):
            seen["steps"] = steps
            return steps
        monkeypatch.setattr("app.routers.datasets.set_prep_steps", fake_set)
        r = await client.post(f"/api/v1/setup/datasets/{ds.id}/fix", headers=auth_headers["a"],
                              json={"action": {"kind": "fill", "column": "imported"}})
        assert r.status_code == 200 and seen["steps"][-1]["kind"] == "fill_nulls"
        bad = await client.post(f"/api/v1/setup/datasets/{ds.id}/fix", headers=auth_headers["a"],
                                json={"action": {"kind": "rm -rf"}})
        assert bad.status_code == 400


class TestSensibleInsights:
    @pytest.mark.parametrize("finding,keep", [
        ({"kind": "trend", "columns": ["stock_close", "trade_date"], "figures": {"value": 1.4e6}}, False),
        ({"kind": "outlier_impact", "columns": ["stock_change"], "figures": {"share_pct": 113.2}}, False),
        ({"kind": "outlier_impact", "columns": ["amount"], "figures": {"share_pct": -33}}, False),
        ({"kind": "outlier_impact", "columns": ["revenue"], "figures": {"share_pct": 40}}, True),
        ({"kind": "trend", "columns": ["revenue", "month"], "figures": {}}, True),
        # A price the engine already averages (an intensive word) is fine.
        ({"kind": "trend", "columns": ["price_egp", "listed"], "figures": {}}, True),
        ({"kind": "standout", "columns": ["body_type", "price_egp"], "figures": {}}, True),
    ])
    def test_nonsense_is_dropped(self, finding, keep):
        assert health.sensible(finding) is keep

    def test_percentages_are_named_as_such_for_the_model(self):
        df = pd.DataFrame({"close": [1.0, 2.0], "change_pct": [0.5, -1.0]})
        prompt = health.build_rules_prompt(df, None, "en")
        assert "`change_pct`: percentage" in prompt[1]["content"]
        assert "`close`: number" in prompt[1]["content"]


def test_many_extreme_value_lines_read_as_one():
    rng = np.random.default_rng(3)
    df = pd.DataFrame({c: np.concatenate([rng.normal(10, 1, 300), [1e6] * 5]) for c in ("a", "b", "c", "d")})
    items = health.column_items(quality_report(df), df, "en")
    outl = [i for i in items if i["kind"] == "outliers"]
    assert len(outl) == 1 and outl[0]["what"].startswith("4 number columns")
