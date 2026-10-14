"""HR evaluation 2026-10-01, item 3.2: the dashboard as an Excel workbook."""
import io

import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn, Report, ReportPage, ReportWidget


async def _hr_dashboard(db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"].id
    path = tmp_path / "hr.csv"
    pd.DataFrame({"dept": ["Sales", "HR", "Sales"], "salary": [100, 80, 120]}).to_csv(path, index=False)
    ds = Dataset(name="hr", org_id=org, filename=str(path), row_count=3, col_count=2, file_size=1,
                 created_by=two_orgs["a"]["user"].id)
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("dept", "categorical"), ("salary", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t, stats={}))
    r = Report(name="HR dashboard", org_id=org, dataset_id=ds.id, created_by=two_orgs["a"]["user"].id)
    db_session.add(r)
    await db_session.flush()
    p = ReportPage(report_id=r.id, name="Page 1", position=0)
    db_session.add(p)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=p.id, widget_type="bar", title="Pay by dept",
                                config={"dimension": "dept", "measure": "salary", "aggregation": "avg"},
                                layout={"x": 0, "y": 0, "w": 6, "h": 4}))
    await db_session.commit()
    return ds, r


@pytest.mark.asyncio
async def test_dashboard_downloads_as_xlsx(client, db_session, two_orgs, auth_headers, tmp_path, monkeypatch):
    ds, r = await _hr_dashboard(db_session, two_orgs, tmp_path)
    resp = await client.get(f"/api/v1/reports/{r.id}/xlsx", headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    book = pd.read_excel(io.BytesIO(resp.content), sheet_name=None)
    assert "Pay by dept" in book
    assert resp.headers["x-sheet-count"] == "1"


@pytest.mark.asyncio
async def test_a_dashboard_whose_data_may_not_be_exported_says_so(
        client, db_session, two_orgs, auth_headers, tmp_path):
    """HR re-test 2026-10-01: with exports switched off the reader still got a
    workbook whose one line was "No widget produced tabular data"."""
    ds, r = await _hr_dashboard(db_session, two_orgs, tmp_path)
    off = await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true",
                            headers=auth_headers["a"])
    assert off.status_code == 200, off.text
    resp = await client.get(f"/api/v1/reports/{r.id}/xlsx", headers=auth_headers["a"])
    assert resp.status_code == 403
    assert "switched off" in resp.json()["detail"]
