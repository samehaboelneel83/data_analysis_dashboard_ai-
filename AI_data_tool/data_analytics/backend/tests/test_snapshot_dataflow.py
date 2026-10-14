"""4.6: a month-by-month headcount trend from a live source, without SQL."""
import sqlite3
from datetime import date

import pandas as pd
import pytest

from app.models.models import DataSource, Dataset, DatasetColumn
from app.services.snapshot_flow import PERIOD_COL, merge, snapshot_rows, validate_spec


@pytest.fixture(autouse=True)
def _uploads(tmp_path, monkeypatch):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    return tmp_path


EMP = pd.DataFrame({
    "emp_no": [1, 2, 3, 4],
    "dept": ["Dev", "Dev", "Sales", "Sales"],
    "from_date": ["2026-01-10", "2026-02-01", "2026-01-01", "2026-03-15"],
    "to_date": ["9999-01-01", "2026-03-20", "9999-01-01", "9999-01-01"],
})


def test_one_run_is_one_period_per_group():
    spec = validate_spec({"every": "month", "group_by": ["dept"], "as": "headcount"}, set(EMP.columns))
    rows = snapshot_rows(EMP, spec, today=date(2026, 9, 17))
    assert list(rows.columns) == [PERIOD_COL, "dept", "headcount"]
    assert rows.to_dict("records") == [
        {PERIOD_COL: "2026-09-01", "dept": "Dev", "headcount": 2},
        {PERIOD_COL: "2026-09-01", "dept": "Sales", "headcount": 2}]


def test_rerun_in_the_same_month_replaces_it_and_a_new_month_appends():
    spec = validate_spec({"every": "month", "as": "headcount"}, set(EMP.columns))
    sep = snapshot_rows(EMP, spec, today=date(2026, 9, 1))
    again = snapshot_rows(EMP.iloc[:3], spec, today=date(2026, 9, 30))
    hist = merge(merge(None, sep), again)
    assert hist.to_dict("records") == [{PERIOD_COL: "2026-09-01", "headcount": 3}]
    octo = snapshot_rows(EMP, spec, today=date(2026, 10, 2))
    hist = merge(hist, octo)
    assert hist[PERIOD_COL].tolist() == ["2026-09-01", "2026-10-01"]


def test_backfill_reconstructs_each_month_from_start_and_end_dates():
    spec = validate_spec({"every": "month", "as": "headcount",
                          "backfill": {"from_column": "from_date", "to_column": "to_date", "start": "2026-01-01"}},
                         set(EMP.columns))
    rows = snapshot_rows(EMP, spec, today=date(2026, 4, 5))
    # Jan: 1,3   Feb: 1,2,3   Mar: 1,3,4 (2 left on 20 Mar)   Apr: 1,3,4
    assert rows["headcount"].tolist() == [2, 3, 3, 3]
    assert rows[PERIOD_COL].tolist() == ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]


def test_bad_specs_are_refused():
    with pytest.raises(ValueError):
        validate_spec({"every": "year"}, set(EMP.columns))
    with pytest.raises(ValueError):
        validate_spec({"group_by": ["nope"]}, set(EMP.columns))
    with pytest.raises(ValueError):
        validate_spec({"agg": "sum"}, set(EMP.columns))


@pytest.mark.asyncio
async def test_a_live_dataset_feeds_a_snapshot_dataflow(client, db_session, two_orgs, auth_headers, tmp_path):
    path = tmp_path / "hr.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE emp (emp_no INTEGER, dept TEXT);"
                      "INSERT INTO emp VALUES (1,'Dev'),(2,'Dev'),(3,'Sales');")
    con.commit(); con.close()
    org = two_orgs["a"]["org"]
    src = DataSource(name="HR", type="sqlite", config={"filepath": str(path)}, org_id=org.id)
    db_session.add(src)
    await db_session.flush()
    live = Dataset(name="Current workforce", org_id=org.id, mode="directquery", data_source_id=src.id,
                   source_query="SELECT * FROM emp", row_count=0, column_meta={})
    db_session.add(live)
    await db_session.flush()
    for c in ("emp_no", "dept"):
        db_session.add(DatasetColumn(dataset_id=live.id, name=c, dtype="categorical"))
    await db_session.commit()

    made = await client.post("/api/v1/dataflows", json={
        "name": "Monthly headcount", "source_dataset_id": live.id, "steps": [],
        "snapshot": {"every": "month", "group_by": ["dept"], "as": "headcount"}}, headers=auth_headers["a"])
    assert made.status_code == 201, made.text
    assert made.json()["snapshot"]["as"] == "headcount"
    run = await client.post(f"/api/v1/dataflows/{made.json()['id']}/run",
                            json={"output_name": "Headcount history"}, headers=auth_headers["a"])
    assert run.status_code == 200, run.text
    out = await db_session.get(Dataset, run.json()["outputs"][0]["id"])
    frame = pd.read_csv(out.filename)
    assert frame.columns.tolist() == [PERIOD_COL, "dept", "headcount"]
    assert frame["headcount"].tolist() == [2, 1]
    # a second run in the same month replaces, it does not duplicate
    con = sqlite3.connect(path); con.execute("INSERT INTO emp VALUES (4,'Sales')"); con.commit(); con.close()
    again = await client.post(f"/api/v1/dataflows/{made.json()['id']}/run", json={}, headers=auth_headers["a"])
    assert again.status_code == 200, again.text
    frame = pd.read_csv(out.filename)
    assert frame["headcount"].tolist() == [2, 2]
