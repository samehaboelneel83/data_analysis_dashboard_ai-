"""One endpoint that runs any catalogued analysis by name.

Eleven typed endpoints exist and stay: each gives a 422 naming the offending
field, which a dispatcher cannot. What they cannot do is grow -- a new analysis
needs a new route, a new request model and a new frontend caller, so eight
statistical tests sat with no UI at all and two analyses never reached the
catalogue.

This route closes that: `GET /analysis/registry` says what exists and what is
runnable, and this runs any of it from `{name, params}`. The generic panel
builds the form from `params_schema`; nothing per-analysis is written twice.

The whole risk of a dispatcher is that `params` is opaque -- the route cannot
know which strings are column names, so a column-security rule could be
defeated by naming the hidden column in a parameter the route does not
understand. It therefore refuses on EVERY string value in params, which is
broader than necessary (a method name gets checked too) and fails closed.
"""
import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, Dataset, Role,
                               RowSecurityRule, User)

# Twelve rows per region, because `compare_groups` refuses fewer than ten per
# group rather than report a p-value nobody should act on. Cost tops out at 130
# outside South, which is what the RLS test below reads back.
ROWS = ([{"region": "North", "sales": 100 + i, "cost": 40 + i, "salary": 10 + i}
         for i in range(12)]
        + [{"region": "South", "sales": 900 + i, "cost": 300 + i, "salary": 30 + i}
           for i in range(12)]
        + [{"region": "East", "sales": 300 + i, "cost": 119 + i, "salary": 50 + i}
           for i in range(12)])


async def _dataset(db_session, tmp_path, org_id, rows=ROWS, name="Runnable"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _user_denied(db_session, org_id, dataset_id, column, rls=None):
    role = Role(org_id=org_id, name=f"Limited{column}", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id,
                email=f"limited-{role.id}@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=dataset_id,
                                      denied_columns=[column]))
    if rls:
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=dataset_id,
                                       filter_expr=rls))
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


def _url(ds_id):
    return f"/api/v1/datasets/{ds_id}/analysis/run"


class TestItRunsWhatTheCatalogueAdvertises:
    async def test_a_statistical_test_runs_by_name(self, client, db_session,
                                                   two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "compare_groups",
            "params": {"value_col": "sales", "group_col": "region"}})
        assert r.status_code == 200, r.text
        assert r.json()["result"] is not None

    async def test_the_response_names_the_analysis_and_its_kind(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        """A generic renderer picks its view from `result_kind`; it must not
        have to infer it from the request it sent."""
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "correlation_test",
            "params": {"col_a": "sales", "col_b": "cost"}})
        body = r.json()
        assert body["analysis"] == "correlation_test"
        assert body["result_kind"] == "statistical_test"

    async def test_one_of_the_formerly_uncatalogued_analyses_runs(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "goal_seek",
            "params": {"x_column": "cost", "y_column": "sales",
                       "target_y": 500}})
        assert r.status_code == 200, r.text
        assert "required_x" in r.json()["result"]

    async def test_explain_runs_too(self, client, db_session, two_orgs,
                                    auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "explain_response", "params": {"response": "sales"}})
        assert r.status_code == 200, r.text
        assert r.json()["result"]["factors"]


class TestItRefusesClearly:
    async def test_an_unknown_name_is_a_404(self, client, db_session, two_orgs,
                                            auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"],
                              json={"name": "no_such_thing", "params": {}})
        assert r.status_code == 404

    async def test_a_catalogued_but_unrunnable_name_is_a_400(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        """Different from a typo: the analysis exists, the caller just cannot
        reach it this way yet."""
        from app.services.analysis import registry
        spec = registry.AnalysisSpec(name="_listed_only", description="x",
                                     params_schema={"type": "object"},
                                     result_kind="x")
        registry.register(spec)
        try:
            ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
            r = await client.post(_url(ds.id), headers=auth_headers["a"],
                                  json={"name": "_listed_only", "params": {}})
            assert r.status_code == 400
        finally:
            registry.unregister("_listed_only")

    async def test_a_bad_parameter_is_a_400_not_a_500(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "compare_groups",
            "params": {"value_col": "sales", "nonsense": "x"}})
        assert r.status_code == 400

    async def test_a_missing_column_is_a_400_not_a_500(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "goal_seek",
            "params": {"x_column": "absent", "y_column": "sales",
                       "target_y": 5}})
        assert r.status_code == 400

    async def test_another_orgs_dataset_is_a_404(self, client, db_session,
                                                 two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["b"], json={
            "name": "compare_groups",
            "params": {"value_col": "sales", "group_col": "region"}})
        assert r.status_code == 404


class TestSecurityIsNotDefeatedByAnOpaqueParameter:
    """The typed endpoints know which fields are column names. This one does
    not, so it checks every string it is given."""

    async def test_a_denied_column_named_in_params_is_refused(
            self, client, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        headers = await _user_denied(db_session, two_orgs["a"]["org"].id,
                                     ds.id, "salary")
        r = await client.post(_url(ds.id), headers=headers, json={
            "name": "correlation_test",
            "params": {"col_a": "salary", "col_b": "sales"}})
        assert r.status_code == 400
        assert "salary" in r.text

    async def test_a_denied_column_nested_in_a_list_is_refused(
            self, client, db_session, two_orgs, tmp_path):
        """`regression.predictors` is a list -- a check that only walked
        top-level strings would wave it straight through."""
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        headers = await _user_denied(db_session, two_orgs["a"]["org"].id,
                                     ds.id, "salary")
        r = await client.post(_url(ds.id), headers=headers, json={
            "name": "regression",
            "params": {"target": "sales", "predictors": ["cost", "salary"]}})
        assert r.status_code == 400
        assert "salary" in r.text

    async def test_an_allowed_column_still_runs_for_that_user(
            self, client, db_session, two_orgs, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        headers = await _user_denied(db_session, two_orgs["a"]["org"].id,
                                     ds.id, "salary")
        r = await client.post(_url(ds.id), headers=headers, json={
            "name": "correlation_test",
            "params": {"col_a": "cost", "col_b": "sales"}})
        assert r.status_code == 200, r.text

    async def test_the_analysis_sees_only_the_rows_rls_allows(
            self, client, db_session, two_orgs, tmp_path):
        """Proven by VALUE, not by reading the code: South's 900/950 must not
        reach the fit, so the answer differs from the unrestricted one."""
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        headers = await _user_denied(db_session, two_orgs["a"]["org"].id,
                                     ds.id, "salary", rls="region != 'South'")
        r = await client.post(_url(ds.id), headers=headers, json={
            "name": "goal_seek",
            "params": {"x_column": "cost", "y_column": "sales",
                       "target_y": 500}})
        assert r.status_code == 200, r.text
        # Only North and East remain: cost tops out at 130, so the observed
        # maximum reported back must be that -- not South's 320.
        assert r.json()["result"]["x_observed_max"] == 130


class TestTheDispatcherAndTheTypedRouteAgree:
    """The panel is about to stop calling the typed routes and call this one
    instead. That is only a swap if the answer is the same answer.

    It nearly was not. The inferential analyses return a `TestResult`
    DATACLASS; the typed routes call `.to_dict()` on it, which rounds the
    statistic, rounds the p-value to six places and adds `alpha`. The
    dispatcher returned the dataclass itself and let the serializer flatten it
    -- different numbers, a missing key, and `safe_clean`'s NaN guarantee
    silently not applying, because it walks dicts and lists and a dataclass is
    neither.
    """

    async def test_compare_groups_matches_field_for_field(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        params = {"value_col": "sales", "group_col": "region"}
        typed = await client.post(
            f"/api/v1/datasets/{ds.id}/statistics/compare-groups",
            headers=auth_headers["a"], json=params)
        generic = await client.post(_url(ds.id), headers=auth_headers["a"],
                                    json={"name": "compare_groups", "params": params})
        assert typed.status_code == 200, typed.text
        assert generic.status_code == 200, generic.text
        assert generic.json()["result"] == typed.json()

    async def test_correlation_matches_field_for_field(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        params = {"col_a": "sales", "col_b": "cost"}
        typed = await client.post(
            f"/api/v1/datasets/{ds.id}/statistics/correlation",
            headers=auth_headers["a"], json=params)
        generic = await client.post(_url(ds.id), headers=auth_headers["a"],
                                    json={"name": "correlation_test", "params": params})
        assert generic.json()["result"] == typed.json()

    async def test_the_alpha_the_typed_route_adds_is_present(
            self, client, db_session, two_orgs, auth_headers, tmp_path):
        """Named on its own because it is a whole key, not a rounding
        difference: a reader cannot judge `significant` without it."""
        ds = await _dataset(db_session, tmp_path, two_orgs["a"]["org"].id)
        r = await client.post(_url(ds.id), headers=auth_headers["a"], json={
            "name": "compare_groups",
            "params": {"value_col": "sales", "group_col": "region"}})
        assert "alpha" in r.json()["result"]
