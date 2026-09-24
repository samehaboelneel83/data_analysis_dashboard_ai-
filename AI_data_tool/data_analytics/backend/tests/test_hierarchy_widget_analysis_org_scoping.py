from app.models.models import Dataset, HierarchyNode, AnalysisResult


async def _seed_dataset(db_session, org_id, name="Test Dataset"):
    ds = Dataset(name=name, org_id=org_id)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


# ── hierarchy.py ────────────────────────────────────────────────────────────

async def test_get_hierarchy_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}/hierarchy", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_create_hierarchy_node_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/hierarchy", json={"name": "Node 1", "node_type": "folder"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_hierarchy_endpoints_same_org_still_work(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}/hierarchy", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json() == []


# ── widget_data.py ────────────────────────────────────────────────────────────

async def test_query_widget_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data", json={"config": {}, "widget_type": "bar"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


# ── analysis.py ───────────────────────────────────────────────────────────────

async def test_run_analysis_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={"analysis_type": "full"}, headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_analysis_cross_org_returns_404_even_when_a_result_exists(client, db_session, two_orgs, auth_headers):
    """This is the specific case the task brief flags: get_analysis previously did
    zero ownership checking at all, so a pre-existing AnalysisResult for another
    org's dataset must now be unreachable, not just a dataset-not-found short-circuit."""
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)
    db_session.add(AnalysisResult(dataset_id=ds.id, analysis_type="full", result={"some": "data"}))
    await db_session.commit()

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_analysis_same_org_returns_the_result(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)
    db_session.add(AnalysisResult(dataset_id=ds.id, analysis_type="full", result={"some": "data"}))
    await db_session.commit()

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])

    assert resp.status_code == 200
    # A1: the response additively gains a `result` envelope key (uniform
    # AnalysisContract); every pre-existing key is still byte-preserved.
    body = resp.json()
    assert body["some"] == "data"
    assert "result" in body and body["result"]["kind"] == "full_profile"
