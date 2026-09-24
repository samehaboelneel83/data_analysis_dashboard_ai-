"""Column-level security: denied columns cease to exist for the restricted role."""
import io

import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn, Role,
                               RowSecurityRule, User)


@pytest.fixture
def salary_ds(tmp_path):
    p = tmp_path / "hr.csv"
    pd.DataFrame({
        "dept": ["Eng", "Eng", "Ops"],
        "headcount": [5, 3, 4],
        "salary": [90000.0, 85000.0, 60000.0],
    }).to_csv(p, index=False)
    return str(p)


async def _setup(db, org, path):
    ds = Dataset(name="HR", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("dept", "categorical"), ("headcount", "numeric"), ("salary", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    role = Role(org_id=org.id, name="no-salary", is_org_admin=False)
    db.add(role)
    await db.flush()
    db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["salary"]))
    user = User(org_id=org.id, role_id=role.id, email="nosal@example.com",
                password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    return ds, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


@pytest.mark.asyncio
async def test_a_widget_on_a_denied_column_returns_nothing(client, db_session, two_orgs, salary_ds):
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "dept", "measure": "salary", "aggregation": "avg"}},
                          headers=headers)
    # The column ceased to exist before shaping: an empty result, never salary data.
    assert r.status_code == 200
    body = r.json()
    text = str(body)
    assert "90000" not in text and "85000" not in text


@pytest.mark.asyncio
async def test_allowed_columns_keep_working_for_the_same_role(client, db_session, two_orgs, salary_ds):
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "dept", "measure": "headcount", "aggregation": "sum"}},
                          headers=headers)
    assert {row["name"]: row["value"] for row in r.json()["rows"]} == {"Eng": 8, "Ops": 4}


@pytest.mark.asyncio
async def test_the_admin_still_sees_everything(client, auth_headers, db_session, two_orgs, salary_ds):
    ds, _ = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "dept", "measure": "salary", "aggregation": "avg"}},
                          headers=auth_headers["a"])
    assert len(r.json()["rows"]) == 2


@pytest.mark.asyncio
async def test_the_whole_table_export_drops_the_column(client, db_session, two_orgs, salary_ds):
    """The raw-rows path again: an export carrying a column the screen hides is the
    leak, not the display."""
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    r = await client.get(f"/api/v1/datasets/{ds.id}/export", headers=headers)
    exported = pd.read_csv(io.BytesIO(r.content))
    assert "salary" not in exported.columns
    assert list(exported.columns) == ["dept", "headcount"]


@pytest.mark.asyncio
async def test_two_roles_with_different_masks_never_share_a_cache_entry(client, db_session, two_orgs, salary_ds):
    """The cache-poisoning case: the admin's unmasked result must not be served to
    the masked role from cache, nor the reverse. Same argument as the RLS cache key."""
    from app.core.security import create_access_token
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    admin = two_orgs["a"]["user"]
    admin_headers = {"Authorization": f"Bearer {create_access_token(admin.id, admin.org_id)}"}
    body = {"widget_type": "table", "config": {"columns": ["dept", "headcount", "salary"]}}

    full = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=admin_headers)
    masked = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=headers)

    assert "salary" in str(full.json())
    assert "salary" not in str(masked.json().get("columns", []))


@pytest.mark.asyncio
async def test_a_row_rule_on_the_hidden_column_still_selects_rows(client, db_session, two_orgs, salary_ds):
    """A tenant id is exactly the column an admin hides as internal AND filters
    rows by. The row rule is the admin's predicate; the reader gets the rows
    it selects and never the column it reads. The widget path used to drop the
    column first, so this role saw an empty dashboard while DirectQuery and
    every analysis surface answered correctly."""
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
    from sqlalchemy import select
    role = (await db_session.execute(select(Role).where(Role.name == "no-salary"))).scalar_one()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="salary >= 85000"))
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "dept", "measure": "headcount", "aggregation": "sum"}},
                          headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert {row["name"]: row["value"] for row in body["rows"]} == {"Eng": 8}
    assert "90000" not in str(body) and "85000" not in str(body)


class TestTheAnalysisEndpointsHonourColumnRules:
    """The two endpoints that applied ROW security and skipped COLUMN security.

    Found by audit and confirmed against the running stack: a role denied
    `revenue` on the demo sales dataset received, from POST /analysis, that
    column's mean, min, max, sum, median, every percentile, its variance,
    skew, kurtosis and its correlations with every other column -- while the
    widget path for the same column correctly returned `{"type": "empty"}`.
    POST /segment likewise clustered on it and reported centroids in the
    column's original units.

    Both went unnoticed because every existing column-security test targeted
    the widget path, which was correct all along.
    """

    @pytest.mark.asyncio
    async def test_the_full_profile_omits_a_denied_column(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/analysis",
                              json={"analysis_type": "full"}, headers=headers)
        assert r.status_code == 200
        body = r.json()

        # Not merely absent from the stats block -- absent from the payload.
        # The type map alone would disclose that the column exists and is
        # numeric, and the profile leaked far more than that.
        assert "salary" not in (body.get("type_map") or {})
        assert "salary" not in (body.get("numeric", {}).get("columns") or {})
        assert "salary" not in str(body)
        # THE assertion: the actual values must not appear anywhere.
        assert "90000" not in str(body) and "85000" not in str(body)

    @pytest.mark.asyncio
    async def test_the_profile_still_carries_the_allowed_columns(
            self, client, db_session, two_orgs, salary_ds):
        """A fix that emptied the whole profile would pass the test above and
        be useless."""
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/analysis",
                              json={"analysis_type": "full"}, headers=headers)
        assert "headcount" in (r.json().get("numeric", {}).get("columns") or {})

    @pytest.mark.asyncio
    async def test_the_admin_still_gets_the_denied_column(
            self, client, auth_headers, db_session, two_orgs, salary_ds):
        ds, _ = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/analysis",
                              json={"analysis_type": "full"}, headers=auth_headers["a"])
        assert "salary" in (r.json().get("numeric", {}).get("columns") or {})

    @pytest.mark.asyncio
    async def test_segmentation_does_not_cluster_on_a_denied_column(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/segment", json={},
                              headers=headers)
        # 400 is acceptable here (one usable numeric column may be too few to
        # cluster); what must never happen is clustering that USES the column.
        assert "salary" not in str(r.json())

    @pytest.mark.asyncio
    async def test_asking_to_cluster_on_a_denied_column_is_refused_by_name(
            self, client, db_session, two_orgs, salary_ds):
        """Refused rather than silently dropped, matching the statistics
        endpoints: a clustering that quietly ignored one of its inputs would
        answer a different question than the one asked."""
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/segment",
                              json={"columns": ["salary", "headcount"]},
                              headers=headers)
        assert r.status_code == 400
        assert "salary" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_column_restricted_result_never_reaches_the_shared_cache(
            self, client, db_session, two_orgs, salary_ds):
        """The cache guarded on `rls_expr` only, so a role with a COLUMN rule
        and no row rule passed straight through it -- writing its restricted
        profile into the org-wide AnalysisResult row, and able to read back an
        unrestricted one containing the column its rule hides."""
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        await client.post(f"/api/v1/datasets/{ds.id}/analysis",
                          json={"analysis_type": "full"}, headers=headers)
        # Restricted callers must not READ the shared cache either.
        got = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=headers)
        assert got.status_code == 404


class TestThePreviewSurfacesHonourColumnRules:
    """The seven-endpoint sweep, round two.

    After the analysis endpoints were fixed, a structural audit of every
    apply_rls_filter call site found the same omission on the PREVIEW paths --
    and these leak more directly than a statistical profile ever did. Verified
    against the running stack before the fix:

      * data-preview returned the denied column's RAW ROW VALUES in the Data tab;
      * the measure preview computed SUM(<denied column>) exactly;
      * the filter preview answered "how many rows have <denied column> > X" --
        a predicate oracle over the hidden values.

    The structural pin (test_rls_base_frame_choke_point.py) now demands
    column-security code in every function that secures a base frame; these
    prove the VALUES are right, not merely that the code is present.
    """

    @pytest.mark.asyncio
    async def test_data_preview_omits_the_denied_column_and_its_values(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/data-preview",
                              json={"offset": 0, "limit": 10, "filters": [],
                                    "search": "", "calculated_columns": []},
                              headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert "salary" not in body["columns"]
        # THE assertion: the raw values must be gone, not merely the header.
        assert "90000" not in str(body) and "85000" not in str(body)
        # And the allowed columns still flow -- a fix that blanked the Data tab
        # would pass the assertions above and be useless.
        assert "headcount" in body["columns"]
        assert body["rows"]

    @pytest.mark.asyncio
    async def test_measure_preview_reports_the_denied_column_unknown(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                              json={"name": "m", "expression": "SUM(salary)"},
                              headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        # Unknown, not computed: the exact aggregate is what the rule hides.
        assert "235000" not in str(body)      # 90000+85000+60000

    @pytest.mark.asyncio
    async def test_filter_preview_cannot_be_used_as_a_predicate_oracle(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/filter-preview",
                              json={"expression": "salary > 70000"},
                              headers=headers)
        assert r.status_code == 200
        body = r.json()
        # "2 of 3 rows pass" would tell the caller two salaries exceed 70k.
        assert body.get("ok") is False or body.get("passing") is None

    @pytest.mark.asyncio
    async def test_the_admin_still_previews_everything(
            self, client, auth_headers, db_session, two_orgs, salary_ds):
        ds, _ = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.post(f"/api/v1/datasets/{ds.id}/data-preview",
                              json={"offset": 0, "limit": 10, "filters": [],
                                    "search": "", "calculated_columns": []},
                              headers=auth_headers["a"])
        assert "salary" in r.json()["columns"]
        m = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                              json={"name": "m", "expression": "SUM(salary)"},
                              headers=auth_headers["a"])
        assert m.json()["ok"] is True


class TestTheDatasetSchemaEndpointsHonourColumnRules:
    """The metadata path, found live rather than by grep: GET /datasets and
    GET /datasets/{id} build DatasetOut straight off the ORM `columns`
    relationship, which every other reader here (widget-data, export,
    analysis, the preview surfaces) does not touch. Values were always masked
    correctly; the schema listing quietly named the denied column anyway --
    a restricted role could not read `salary`'s numbers, but could always see
    that a column called `salary` existed on this dataset."""

    @pytest.mark.asyncio
    async def test_the_dataset_detail_omits_the_denied_columns_name(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()["columns"]]
        assert "salary" not in names
        assert names == ["dept", "headcount"]

    @pytest.mark.asyncio
    async def test_the_dataset_list_omits_the_denied_columns_name(
            self, client, db_session, two_orgs, salary_ds):
        ds, headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.get("/api/v1/datasets", headers=headers)
        assert r.status_code == 200
        entry = next(d for d in r.json() if d["id"] == ds.id)
        assert "salary" not in [c["name"] for c in entry["columns"]]

    @pytest.mark.asyncio
    async def test_the_admin_still_sees_the_columns_name_in_the_schema(
            self, client, auth_headers, db_session, two_orgs, salary_ds):
        ds, _ = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])
        assert "salary" in [c["name"] for c in r.json()["columns"]]


class TestTheRowSecurityPreflight:
    """S0 ticket 11: a row rule is evaluated over the full frame before column
    security drops the reader's denied columns, so a rule that reads a denied
    column still selects rows. This endpoint names, for a draft rule, the
    columns it reads and which of those the role cannot see -- informational,
    surfaced to the admin authoring the rule, never a block."""

    @pytest.mark.asyncio
    async def test_rule_preflight_names_the_columns_a_rule_reads_that_the_role_cannot_see(
            self, client, auth_headers, db_session, two_orgs, salary_ds):
        ds, _ = await _setup(db_session, two_orgs["a"]["org"], salary_ds)   # role 'no-salary' denied ['salary']
        from sqlalchemy import select
        role = (await db_session.execute(select(Role).where(Role.name == "no-salary"))).scalar_one()
        r = await client.get("/api/v1/admin/row-security-rules/preflight",
                             params={"role_id": role.id, "dataset_id": ds.id,
                                     "filter_expr": "salary >= 85000 and dept == 'Eng'"},
                             headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json() == {"columns": ["dept", "salary"], "denied": ["salary"]}

    @pytest.mark.asyncio
    async def test_rule_preflight_is_admin_only_and_org_scoped(
            self, client, db_session, two_orgs, salary_ds, auth_headers):
        ds, restricted_headers = await _setup(db_session, two_orgs["a"]["org"], salary_ds)
        r = await client.get("/api/v1/admin/row-security-rules/preflight",
                             params={"role_id": 1, "dataset_id": ds.id, "filter_expr": "dept == 'Eng'"},
                             headers=restricted_headers)
        # require_org_admin rejects a non-admin with 403, not 401 (the token itself
        # is valid -- it's the role that lacks admin privileges).
        assert r.status_code == 403
        r = await client.get("/api/v1/admin/row-security-rules/preflight",
                             params={"role_id": 1, "dataset_id": ds.id, "filter_expr": "dept == 'Eng'"},
                             headers=auth_headers["b"])
        assert r.status_code == 404

