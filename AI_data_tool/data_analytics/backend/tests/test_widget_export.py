"""Exporting a widget's data as CSV or Excel.

The claim under test is not "a file downloads" but "the file is what the widget shows"
-- same aggregation, same filters, and above all the same row-level security. An export
that resolved data by its own route would be a second place for RLS to be applied, and
the second place is the one that gets forgotten.
"""
import io

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import Dataset, Role, RowSecurityRule, User
from app.core.security import create_access_token, hash_password

ROWS = [
    ("US", "Widget", 100.0),
    ("US", "Gadget", 50.0),
    ("CA", "Widget", 30.0),
    ("CA", "Gadget", 20.0),
]


@pytest.fixture
def sales_csv(tmp_path):
    path = tmp_path / "sales.csv"
    pd.DataFrame(ROWS, columns=["region", "product", "revenue"]).to_csv(path, index=False)
    return str(path)


async def _dataset(db, org_id, filename):
    ds = Dataset(name="Sales", filename=filename, org_id=org_id, mode="import")
    db.add(ds)
    await db.flush()
    from app.models.models import DatasetColumn
    for name, dtype in (("region", "categorical"), ("product", "categorical"), ("revenue", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
    await db.commit()
    return ds


def _body(**over):
    return {"widget_type": "bar",
            "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
            **over}


@pytest.mark.asyncio
async def test_export_requires_authentication(client, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export", json=_body())
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_csv_export_matches_what_the_widget_displays(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)

    shown = (await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                               json=_body(), headers=auth_headers["a"])).json()
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv",
                          json=_body(), headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")

    exported = pd.read_csv(io.BytesIO(r.content))
    # Compared against the DISPLAYED result, not against a hand-written expectation:
    # that is what makes this an equivalence test rather than a second opinion about
    # what the aggregation should produce.
    assert list(exported["name"]) == [row["name"] for row in shown["rows"]]
    assert list(exported["value"]) == [row["value"] for row in shown["rows"]]


@pytest.mark.asyncio
async def test_excel_export_is_a_real_workbook_with_the_same_rows(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=xlsx",
                          json=_body(), headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]

    exported = pd.read_excel(io.BytesIO(r.content))
    assert set(exported["name"]) == {"US", "CA"}
    assert exported.loc[exported["name"] == "US", "value"].iloc[0] == 150.0


@pytest.mark.asyncio
async def test_export_obeys_row_level_security(client, db_session, two_orgs, sales_csv):
    """The security-critical case. A user restricted to CA must not be able to download
    US rows -- if the export resolved data by its own path, this is what would leak."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org.id, sales_csv)

    role = Role(org_id=org.id, name="CA only", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'CA'"))
    restricted = User(org_id=org.id, role_id=role.id, email="ca@example.com",
                      password_hash=hash_password("pw"))
    db_session.add(restricted)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {create_access_token(restricted.id, org.id)}"}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv",
                          json=_body(), headers=headers)
    assert r.status_code == 200, r.text

    exported = pd.read_csv(io.BytesIO(r.content))
    assert set(exported["name"]) == {"CA"}, "row-level security did not reach the export"
    assert 150.0 not in list(exported["value"])


@pytest.mark.asyncio
async def test_another_orgs_dataset_cannot_be_exported(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export",
                          json=_body(), headers=auth_headers["b"])
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_an_unknown_format_is_rejected_rather_than_guessed(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=pdf",
                          json=_body(), headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_a_table_widget_exports_its_own_columns(client, auth_headers, db_session, two_orgs, sales_csv):
    """A table's shaped result carries columns/rows rather than {name, value}; the
    exporter must follow the widget's shape, not assume the series one."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv",
        json={"widget_type": "table", "config": {"columns": ["region", "revenue"]}},
        headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    exported = pd.read_csv(io.BytesIO(r.content))
    assert list(exported.columns) == ["region", "revenue"]
    assert len(exported) == len(ROWS)


@pytest.mark.asyncio
async def test_the_filename_cannot_carry_a_header_injection(client, auth_headers, db_session, two_orgs, sales_csv):
    """widget_type reaches Content-Disposition, and it is client input."""
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv",
        json=_body(widget_type='bar"; drop\r\nX-Injected: yes'),
        headers=auth_headers["a"])

    disposition = r.headers.get("content-disposition", "")
    # The property that matters is that the value cannot terminate the header or break
    # out of the quoted string -- not that the attacker's letters disappear. Stripping
    # CR, LF and the quote is what prevents response splitting; the harmless remainder
    # sitting inside the filename is fine, and asserting its absence would be testing
    # the wrong thing.
    assert "\r" not in disposition and "\n" not in disposition
    assert disposition.count('"') == 2, disposition
    assert "x-injected" not in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_tsv_export_uses_tabs(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=tsv",
                          json=_body(), headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert "tab-separated" in r.headers["content-type"]
    exported = pd.read_csv(io.BytesIO(r.content), sep="\t")
    assert set(exported["name"]) == {"US", "CA"}


@pytest.mark.asyncio
async def test_whole_dataset_export_returns_every_row(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    exported = pd.read_csv(io.BytesIO(r.content))
    assert len(exported) == len(ROWS)
    assert list(exported.columns) == ["region", "product", "revenue"]


@pytest.mark.asyncio
async def test_whole_dataset_export_obeys_row_level_security(client, db_session, two_orgs, sales_csv):
    """Same trap as the widget export: a second resolution path is where RLS gets
    forgotten. The whole-table export is the more dangerous one -- it is the raw rows."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org.id, sales_csv)
    role = Role(org_id=org.id, name="CA only 2", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'CA'"))
    restricted = User(org_id=org.id, role_id=role.id, email="ca2@example.com",
                      password_hash=hash_password("pw"))
    db_session.add(restricted)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {create_access_token(restricted.id, org.id)}"}
    r = await client.get(f"/api/v1/datasets/{ds.id}/export", headers=headers)
    exported = pd.read_csv(io.BytesIO(r.content))
    assert set(exported["region"]) == {"CA"}
    assert len(exported) == 2


@pytest.mark.asyncio
async def test_whole_dataset_export_is_org_scoped(client, auth_headers, db_session, two_orgs, sales_csv):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, sales_csv)
    r = await client.get(f"/api/v1/datasets/{ds.id}/export", headers=auth_headers["b"])
    assert r.status_code == 404
