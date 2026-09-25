"""E07: a workbook with data on several sheets is never silently one sheet.

Every reader opened a workbook's FIRST sheet, so a file with Sales, Costs and
Staff became a dataset of Sales alone -- and looked complete."""
import io

import pandas as pd
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.models import Dataset

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _workbook(**sheets) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


SALES = pd.DataFrame({"region": ["N", "S"], "amount": [1, 2]})
COSTS = pd.DataFrame({"item": ["rent", "power", "water"], "cost": [5, 6, 7]})
EMPTY = pd.DataFrame({"notes": []})


@pytest.fixture
def uploads(monkeypatch, tmp_path):
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(root))
    return root


async def _upload(client, headers, body, sheet=None):
    data = {"name": "Book", "description": ""}
    if sheet is not None:
        data["sheet"] = sheet
    return await client.post("/api/v1/datasets", files={"file": ("book.xlsx", body, XLSX)},
                             data=data, headers=headers)


async def test_several_sheets_and_no_choice_is_refused_naming_them(
        client, db_session, two_orgs, auth_headers, uploads):
    before = (await db_session.execute(select(func.count()).select_from(Dataset))).scalar_one()
    r = await _upload(client, auth_headers["a"], _workbook(Sales=SALES, Costs=COSTS, Notes=EMPTY))
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["sheets"] == ["Sales", "Costs"]          # the empty sheet is not offered
    assert "2 sheets with data" in detail["message"]
    assert (await db_session.execute(select(func.count()).select_from(Dataset))).scalar_one() == before
    assert not [p for p in uploads.rglob("*") if p.is_file()]


async def test_the_chosen_sheet_is_the_dataset_and_stays_so(client, two_orgs, auth_headers, uploads):
    r = await _upload(client, auth_headers["a"], _workbook(Sales=SALES, Costs=COSTS), sheet="Costs")
    assert r.status_code == 200, r.text
    ds = r.json()
    assert ds["row_count"] == 3 and {c["name"] for c in ds["columns"]} == {"item", "cost"}
    # Every later reader opens the stored file; it must be the chosen sheet.
    stored = pd.read_csv(ds["filename"])
    assert stored["item"].tolist() == ["rent", "power", "water"]


async def test_an_unknown_sheet_is_refused(client, two_orgs, auth_headers, uploads):
    r = await _upload(client, auth_headers["a"], _workbook(Sales=SALES, Costs=COSTS), sheet="Staff")
    assert r.status_code == 400
    assert "no sheet named 'Staff'" in r.json()["detail"]["message"]


async def test_a_single_sheet_workbook_is_unchanged(client, two_orgs, auth_headers, uploads):
    r = await _upload(client, auth_headers["a"], _workbook(Sales=SALES, Notes=EMPTY))
    assert r.status_code == 200, r.text
    assert r.json()["filename"].endswith(".xlsx") and r.json()["row_count"] == 2


async def test_two_sheets_of_one_workbook_are_not_copies_of_each_other(client, two_orgs, auth_headers, uploads):
    book = _workbook(Sales=SALES, Costs=COSTS)
    a = await _upload(client, auth_headers["a"], book, sheet="Sales")
    b = await _upload(client, auth_headers["a"], book, sheet="Costs")
    c = await _upload(client, auth_headers["a"], book, sheet="Sales")
    assert b.json()["duplicate_of"] is None
    assert c.json()["duplicate_of"]["id"] == a.json()["id"]


async def test_a_batch_makes_one_dataset_per_sheet(client, two_orgs, auth_headers, uploads):
    r = await client.post("/api/v1/datasets/batch",
                          files=[("files", ("book.xlsx", _workbook(Sales=SALES, Costs=COSTS, Notes=EMPTY), XLSX))],
                          data={"name": "Q3", "description": "", "mode": "separate"}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["source_filename"] for i in items] == ["book.xlsx [Sales]", "book.xlsx [Costs]"]
    assert [i["dataset"]["name"] for i in items] == ["Q3 — Sales", "Q3 — Costs"]
    assert [i["dataset"]["row_count"] for i in items] == [2, 3]


async def test_append_refuses_a_workbook_of_several_sheets(client, two_orgs, auth_headers, uploads):
    r = await client.post("/api/v1/datasets/batch",
                          files=[("files", ("a.csv", b"region,amount\nE,3\n", "text/csv")),
                                 ("files", ("book.xlsx", _workbook(Sales=SALES, Costs=COSTS), XLSX))],
                          data={"name": "M", "description": "", "mode": "append"}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    by = {i["source_filename"]: i for i in r.json()["items"]}
    assert by["book.xlsx"]["status"] == "error" and "2 sheets with data" in by["book.xlsx"]["error"]
    assert by["a.csv"]["dataset"]["row_count"] == 1
