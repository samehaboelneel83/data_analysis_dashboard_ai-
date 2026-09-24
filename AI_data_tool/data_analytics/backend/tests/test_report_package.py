"""Offline report package (MASTER_PLAN Phase 5 item 4): one HTML file, frozen
results resolved as the exporter, gated by export policy."""
import json
import re

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app.core.security import create_access_token, hash_password
from app.models.models import ColumnSecurityRule, ReportPage, ReportWidget, Role, User
from app.services.report_package import MAX_ROWS_PER_WIDGET, build_package_html
from tests.test_pdf_export import _seed


def _payload(html_text: str) -> dict:
    m = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html_text, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_the_package_is_one_self_contained_file():
    doc = build_package_html({"name": "Q3 </script> review", "pages": [
        {"name": "P", "widgets": [{"title": "T", "widget_type": "text", "content": "hello"}]}]},
        exporter="a@x.com")
    assert "<script src" not in doc and "http" not in doc.split("<script type")[0].split("<style>")[0]
    data = _payload(doc)
    assert data["name"] == "Q3 </script> review"
    assert data["exporter"] == "a@x.com"


def test_big_tables_are_capped_and_say_so():
    rows = [{"name": str(i), "value": i} for i in range(MAX_ROWS_PER_WIDGET + 10)]
    doc = build_package_html({"name": "R", "pages": [{"name": "P", "widgets": [
        {"title": "T", "widget_type": "table", "result": {"type": "table", "rows": rows}}]}]}, exporter="a")
    w = _payload(doc)["pages"][0]["widgets"][0]
    assert len(w["result"]["rows"]) == MAX_ROWS_PER_WIDGET
    assert w["result"]["package_cap"] == {"shown": MAX_ROWS_PER_WIDGET, "of": MAX_ROWS_PER_WIDGET + 10}


@pytest.mark.asyncio
async def test_the_endpoint_freezes_each_widget_as_the_exporter_sees_it(client, auth_headers, db_session, two_orgs, tmp_path):
    report = await _seed(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.get(f"/api/v1/reports/{report.id}/package", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert "attachment" in r.headers["content-disposition"]
    data = _payload(r.text)
    w = data["pages"][0]["widgets"][0]
    assert {row["name"]: row["value"] for row in w["result"]["rows"]} == {"N": 15.0, "S": 20.0}
    # Another org gets nothing.
    assert (await client.get(f"/api/v1/reports/{report.id}/package", headers=auth_headers["b"])).status_code == 404


@pytest.mark.asyncio
async def test_disabled_exports_are_withheld_by_name(client, auth_headers, db_session, two_orgs, tmp_path):
    from app.models.models import Dataset
    report = await _seed(db_session, two_orgs["a"]["org"].id, tmp_path)
    ds = await db_session.get(Dataset, report.dataset_id)
    from app.routers.datasets import EXPORT_DISABLED_KEY
    ds.column_meta = {**(ds.column_meta or {}), EXPORT_DISABLED_KEY: True}
    flag_modified(ds, "column_meta")
    await db_session.commit()
    r = await client.get(f"/api/v1/reports/{report.id}/package", headers=auth_headers["a"])
    w = _payload(r.text)["pages"][0]["widgets"][0]
    assert "result" not in w and "exports are disabled" in w["withheld"]


@pytest.mark.asyncio
async def test_a_denied_column_never_reaches_the_package(client, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    report = await _seed(db_session, org.id, tmp_path)
    role = Role(org_id=org.id, name="NoRevenue", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=report.dataset_id, denied_columns=["revenue"]))
    user = User(org_id=org.id, role_id=role.id, email="nr@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}
    r = await client.get(f"/api/v1/reports/{report.id}/package", headers=headers)
    assert r.status_code == 200, r.text
    w = _payload(r.text)["pages"][0]["widgets"][0]
    # The widget sums a column this role is denied: nothing of it is frozen in.
    assert "20.0" not in r.text and "15.0" not in r.text
    assert "result" not in w or not any(row.get("value") in (15.0, 20.0) for row in w["result"].get("rows", []))


@pytest.mark.asyncio
async def test_only_visible_pages_are_packaged(client, auth_headers, db_session, two_orgs, tmp_path):
    report = await _seed(db_session, two_orgs["a"]["org"].id, tmp_path)
    hidden = ReportPage(report_id=report.id, name="Notes", position=1, page_type="hidden")
    db_session.add(hidden)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=hidden.id, widget_type="text", title="secret", config={"content": "draft"},
                                layout={"x": 0, "y": 0, "w": 4, "h": 2}))
    await db_session.commit()
    r = await client.get(f"/api/v1/reports/{report.id}/package", headers=auth_headers["a"])
    assert [p["name"] for p in _payload(r.text)["pages"]] == ["Page 1"]
