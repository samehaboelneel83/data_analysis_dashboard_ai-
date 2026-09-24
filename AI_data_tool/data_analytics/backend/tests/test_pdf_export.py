"""Server-rendered report PDF: the document builder and the download endpoint."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn, Report, ReportPage, ReportWidget
from app.services.pdf_export import build_report_pdf


def _sections():
    return [
        {"page_name": "Overview", "widgets": [
            {"title": "Revenue by region", "widget_type": "bar",
             "result": {"type": "series", "rows": [{"name": "N", "value": 10.0},
                                                   {"name": "S", "value": 20.0}], "total": 2}},
            {"title": "Total revenue", "widget_type": "kpi",
             "result": {"type": "scalar", "value": 30.0, "rows": [{"name": "revenue", "value": 30.0}]}},
        ]},
        {"page_name": "Detail", "widgets": [
            {"title": "Raw", "widget_type": "table",
             "result": {"type": "table", "columns": ["region", "revenue"],
                        "rows": [["N", 10.0], ["S", 20.0]], "total": 2}},
        ]},
    ]


def test_builds_a_real_pdf_with_cover_and_sections():
    pdf = build_report_pdf("Q3 Report", "Sales across regions", _sections())
    assert isinstance(pdf, bytes) and len(pdf) > 1500
    assert pdf[:5] == b"%PDF-"          # a genuine PDF signature
    assert pdf.rstrip()[-5:] == b"%%EOF"


def test_empty_report_still_produces_a_valid_pdf():
    pdf = build_report_pdf("Empty", None, [])
    assert pdf[:5] == b"%PDF-"


def test_chart_fallback_to_table_never_raises():
    # a widget type with no chart form must fall back, not crash
    pdf = build_report_pdf("X", None, [{"page_name": "P", "widgets": [
        {"title": "Odd", "widget_type": "sankey",
         "result": {"type": "table", "columns": ["a"], "rows": [["x"]], "total": 1}},
    ]}])
    assert pdf[:5] == b"%PDF-"


async def _seed(db, org_id, tmp_path):
    p = tmp_path / "p.csv"
    pd.DataFrame({"region": ["N", "N", "S"], "revenue": [10.0, 5.0, 20.0]}).to_csv(p, index=False)
    ds = Dataset(name="D", org_id=org_id, filename=str(p))
    db.add(ds)
    await db.flush()
    db.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"))
    db.add(DatasetColumn(dataset_id=ds.id, name="revenue", dtype="numeric"))
    report = Report(name="PDF Report", description="a test", org_id=org_id, dataset_id=ds.id)
    db.add(report)
    await db.flush()
    page = ReportPage(report_id=report.id, name="Page 1", position=0)
    db.add(page)
    await db.flush()
    db.add(ReportWidget(page_id=page.id, widget_type="bar", title="Rev by region",
                        config={"dimension": "region", "measure": "revenue", "aggregation": "sum"},
                        layout={"x": 0, "y": 0, "w": 6, "h": 4}))
    await db.commit()
    return report


@pytest.mark.asyncio
async def test_pdf_endpoint_returns_a_pdf(client, auth_headers, db_session, two_orgs, tmp_path):
    report = await _seed(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.get(f"/api/v1/reports/{report.id}/pdf", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_pdf_endpoint_is_org_scoped(client, auth_headers, db_session, two_orgs, tmp_path):
    report = await _seed(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.get(f"/api/v1/reports/{report.id}/pdf", headers=auth_headers["b"])
    assert r.status_code == 404



def _mediabox(pdf: bytes):
    import re
    m = re.search(rb"/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)", pdf)
    return float(m.group(1)), float(m.group(2))


def test_page_setup_options_change_the_page_size():
    sec = [{"page_name": "P", "widgets": []}]
    w, h = _mediabox(build_report_pdf("X", None, sec))
    assert w > h  # A4 landscape, the default
    w, h = _mediabox(build_report_pdf("X", None, sec, paper="Letter", orientation="portrait"))
    assert round(w) == 612 and round(h) == 792


@pytest.mark.asyncio
async def test_pdf_endpoint_takes_page_setup_and_rejects_nonsense(client, auth_headers, db_session, two_orgs, tmp_path):
    report = await _seed(db_session, two_orgs["a"]["org"].id, tmp_path)
    ok = await client.get(f"/api/v1/reports/{report.id}/pdf", params={"paper": "A3", "orientation": "portrait",
                                                                       "contents": "false"}, headers=auth_headers["a"])
    assert ok.status_code == 200 and ok.content[:5] == b"%PDF-"
    bad = await client.get(f"/api/v1/reports/{report.id}/pdf", params={"paper": "B5"}, headers=auth_headers["a"])
    assert bad.status_code == 400
