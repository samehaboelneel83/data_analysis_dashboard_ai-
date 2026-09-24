"""Phase 6.1: cross-source mapping -- a match check before saving, and the
mappings published with shared links so cross-dataset clicks survive publication."""
import pandas as pd
import pytest

from app.models.models import (Dataset, DatasetColumn, Relationship, Report, ReportPage,
                               ReportWidget)
from app.services.prep import mapping_match_report


def test_value_level_match_with_near_misses_and_type_note():
    src = pd.Series(["Egypt", "Egypt", "Saudi Arabia", "UAE", "Oman"], name="country")
    tgt = pd.Series(["Egypt", "saudi arabia", "UAE", "Qatar"], name="cust_country")
    r = mapping_match_report(src, tgt)
    assert r["source_values"] == 4 and r["matched_values"] == 2 and r["pct_values"] == 50
    assert {u["value"] for u in r["unmatched"]} == {"Saudi Arabia", "Oman"}
    assert r["near_matches"] == [{"source": "Saudi Arabia", "target": "saudi arabia"}]
    assert r["pct_target_covered"] == 50 and r["type_mismatch"] is None
    assert mapping_match_report(pd.Series([1, 2], name="a"), pd.Series(["1", "2"], name="b"))["type_mismatch"]


@pytest.fixture
def files(tmp_path):
    s = tmp_path / "sales.csv"
    pd.DataFrame({"country": ["EG", "SA", "AE"], "amount": [1.0, 2.0, 3.0]}).to_csv(s, index=False)
    h = tmp_path / "ship.csv"
    pd.DataFrame({"cust_country": ["EG", "SA", "KW"], "days": [3.0, 4.0, 5.0]}).to_csv(h, index=False)
    return str(s), str(h)


async def _setup(db, org, files):
    sales = Dataset(name="Sales", filename=files[0], org_id=org.id, mode="import")
    ship = Dataset(name="Shipments", filename=files[1], org_id=org.id, mode="import")
    db.add_all([sales, ship])
    await db.flush()
    for ds, cols in ((sales, ["country", "amount"]), (ship, ["cust_country", "days"])):
        for c in cols:
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db.commit()
    return sales, ship


@pytest.mark.asyncio
async def test_check_endpoint_reads_both_sides_as_the_caller(client, auth_headers, db_session, two_orgs, files):
    sales, ship = await _setup(db_session, two_orgs["a"]["org"], files)
    body = {"from_dataset_id": sales.id, "from_column": "country", "to_dataset_id": ship.id, "to_column": "cust_country"}
    r = await client.post("/api/v1/relationships/check", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["pct_values"] == 66 and r.json()["unmatched"] == [{"value": "AE", "rows": 1}]
    # another org cannot probe these datasets
    r = await client.post("/api/v1/relationships/check", json=body, headers=auth_headers["b"])
    assert r.status_code == 404
    r = await client.post("/api/v1/relationships/check", json={**body, "to_column": "nope"}, headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_shared_link_publishes_only_the_mappings_it_needs(client, auth_headers, db_session, two_orgs, files):
    org = two_orgs["a"]["org"]
    sales, ship = await _setup(db_session, org, files)
    db_session.add(Relationship(org_id=org.id, from_dataset_id=sales.id, from_column="country",
                                to_dataset_id=ship.id, to_column="cust_country"))
    rep = Report(name="Two sources", dataset_id=sales.id, org_id=org.id)
    db_session.add(rep)
    await db_session.flush()
    page = ReportPage(report_id=rep.id, name="P1", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add_all([
        ReportWidget(page_id=page.id, widget_type="bar", config={"dimension": "country", "measure": "amount"}),
        ReportWidget(page_id=page.id, widget_type="bar",
                     config={"dataset_id": ship.id, "dimension": "cust_country", "measure": "days"}),
    ])
    await db_session.commit()
    token = (await client.post(f"/api/v1/reports/{rep.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    got = (await client.get(f"/api/v1/shared/{token}")).json()
    assert got["relationships"] == [{"from_dataset_id": sales.id, "from_column": "country",
                                     "to_dataset_id": ship.id, "to_column": "cust_country"}]
    # only the relationship columns are named, never the rest of the schema
    assert got["datasets"][str(sales.id)]["columns"] == [{"name": "country"}]
    assert got["datasets"][str(ship.id)]["columns"] == [{"name": "cust_country"}]


@pytest.mark.asyncio
async def test_single_source_report_publishes_nothing(client, auth_headers, db_session, two_orgs, files):
    org = two_orgs["a"]["org"]
    sales, _ = await _setup(db_session, org, files)
    rep = Report(name="One source", dataset_id=sales.id, org_id=org.id)
    db_session.add(rep)
    await db_session.flush()
    db_session.add(ReportPage(report_id=rep.id, name="P1", position=0))
    await db_session.commit()
    token = (await client.post(f"/api/v1/reports/{rep.id}/share-links", json={},
                               headers=auth_headers["a"])).json()["token"]
    got = (await client.get(f"/api/v1/shared/{token}")).json()
    assert got["relationships"] == [] and got["datasets"] == {}
