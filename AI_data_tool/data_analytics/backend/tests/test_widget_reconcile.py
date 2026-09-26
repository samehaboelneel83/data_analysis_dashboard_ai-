"""E17: reconcile a widget with the report it replaces.

The owner of a migrated report has its old export -- the same table as a CSV
or Excel file. The widget is compared with it row by row, as the reader sees
the widget (their row and column rules apply), and every run is audited.
"""
import io

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import AuditLogEntry, Dataset, DatasetColumn
from app.services.reconcile import default_mapping, parse_number, reconcile

from .test_prediction_models_api import _restricted_user


class TestNumbers:
    @pytest.mark.parametrize("text,value,decimals", [
        ("1,234.57", 1234.57, 2), ("(12.5)", -12.5, 1), ("12.5%", 0.125, 3), ("SAR 1,200", 1200.0, 0),
        ("$ 3.10", 3.1, 2), ("١٢٣٫٥", 123.5, 1), ("-7", -7.0, 0), ("", None, None), ("n/a", None, None),
    ])
    def test_what_an_export_writes_is_read_as_the_number_it_is(self, text, value, decimals):
        assert parse_number(text) == (value, decimals)

    def test_a_number_from_excel_has_no_display_precision(self):
        assert parse_number(12.345) == (12.345, None)


class TestPairing:
    def test_by_name_ignoring_case_and_spacing(self):
        assert default_mapping(["region", "total_sales"], ["Region", "Total Sales"]) == {
            "keys": [["region", "Region"]], "values": [["total_sales", "Total Sales"]]}

    def test_two_columns_each_side_pair_by_position(self):
        assert default_mapping(["name", "value"], ["Governorate", "Revenue"]) == {
            "keys": [["name", "Governorate"]], "values": [["value", "Revenue"]]}


class TestComparing:
    actual = pd.DataFrame({"region": ["Europe", "Asia", "Africa"], "revenue": [1234.5678, 99.0, 5.0]})

    def test_rows_that_agree_differ_or_are_missing(self):
        file = pd.DataFrame({"Region": ["europe ", "Asia", "Americas"], "Revenue": ["1,234.57", "98.9", "7"]})
        r = reconcile(self.actual, file)
        assert r["counts"] == {"match": 1, "mismatch": 1, "missing_in_widget": 1, "missing_in_file": 1}
        assert [x["status"] for x in r["rows"]] == ["mismatch", "missing_in_widget", "missing_in_file", "match"]
        asia = r["rows"][0]["values"][0]
        assert asia["expected"] == "98.9" and asia["actual"] == 99.0 and asia["difference"] == pytest.approx(0.1)
        assert r["reconciled"] is False
        # Totals are each side's whole column.
        assert r["totals"][0]["expected"] == pytest.approx(1340.47) and r["totals"][0]["actual"] == pytest.approx(1338.5678)

    def test_agreement_is_to_the_decimals_the_file_shows(self):
        ok = reconcile(self.actual.iloc[:1], pd.DataFrame({"Region": ["Europe"], "Revenue": ["1234.6"]}))
        off = reconcile(self.actual.iloc[:1], pd.DataFrame({"Region": ["Europe"], "Revenue": ["1234.58"]}))
        assert ok["reconciled"] and not off["reconciled"]

    def test_excel_numbers_must_agree_closely(self):
        near = reconcile(self.actual.iloc[:1], pd.DataFrame({"Region": ["Europe"], "Revenue": [1234.5678001]}))
        far = reconcile(self.actual.iloc[:1], pd.DataFrame({"Region": ["Europe"], "Revenue": [1234.57]}))
        assert near["reconciled"] and not far["reconciled"]

    def test_whole_number_and_date_keys_pair_however_written(self):
        a = pd.DataFrame({"year": [2024, 2025], "n": [1, 2]})
        e = pd.DataFrame({"Year": ["2024.0", "2025"], "N": ["1", "2"]})
        assert reconcile(a, e)["reconciled"]

    def test_a_mapping_naming_no_column_is_refused(self):
        with pytest.raises(ValueError, match="Not a column"):
            reconcile(self.actual, pd.DataFrame({"x": [1]}), {"keys": [["region", "nope"]], "values": [["revenue", "x"]]})

    def test_duplicate_keys_are_counted_not_hidden(self):
        e = pd.DataFrame({"Region": ["Europe", "Europe"], "Revenue": ["1234.57", "1"]})
        assert reconcile(self.actual.iloc[:1], e)["duplicate_keys"] == {"widget": 0, "file": 1}


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["North", "North", "South", "East"], "sales": [100.25, 50.0, 300.0, 7.5]}).to_csv(p, index=False)
    return str(p)


async def _ds(db, org, path):
    ds = Dataset(name="Sales", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("sales", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


WIDGET = '{"widget_type": "bar", "config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}}'


async def _reconcile(client, headers, ds_id, name, content, widget=WIDGET, mapping=None):
    data = {"widget": widget}
    if mapping:
        data["mapping"] = mapping
    return await client.post(f"/api/v1/datasets/{ds_id}/widget-data/reconcile", headers=headers,
                             data=data, files={"file": (name, content)})


class TestTheEndpoint:
    async def test_a_matching_export_reconciles_and_is_audited(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        # The old report's export: its own headers, a thousands separator, rounded.
        csv = "Region,Total Sales\nNorth,150.3\nSouth,300.0\nEast,7.5\n".encode()
        r = await _reconcile(client, auth_headers["a"], ds.id, "sas_export.csv", csv, mapping=(
            '{"keys": [["name", "Region"]], "values": [["value", "Total Sales"]]}'))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reconciled"] is True and body["counts"]["match"] == 3 and body["file"] == "sas_export.csv"
        entry = (await db_session.execute(select(AuditLogEntry).where(
            AuditLogEntry.action == "widget.reconcile"))).scalar_one()
        assert "3 match, 0 differ" in entry.detail

    async def test_a_semicolon_windows_arabic_file(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        csv = "المنطقة;المبيعات\nNorth;150,25\nSouth;300\nEast;7,5\n".encode("cp1256")
        r = await _reconcile(client, auth_headers["a"], ds.id, "export.csv", csv)
        assert r.status_code == 200, r.text
        assert r.json()["reconciled"] is True, r.json()["rows"]

    async def test_an_excel_export(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        buf = io.BytesIO()
        pd.DataFrame({"Region": ["North", "South", "East"], "Sales": [150.25, 299.0, 7.5]}).to_excel(buf, index=False)
        r = await _reconcile(client, auth_headers["a"], ds.id, "export.xlsx", buf.getvalue())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["counts"] == {"match": 2, "mismatch": 1, "missing_in_widget": 0, "missing_in_file": 0}
        assert body["rows"][0]["key"] == {"Region": "South"} and body["rows"][0]["values"][0]["difference"] == 1

    async def test_a_restricted_reader_reconciles_what_they_see(self, client, db_session, two_orgs, salesfile):
        """Their row rule applies: rows they cannot see are "only in the file",
        never their numbers."""
        org = two_orgs["a"]["org"]
        ds = await _ds(db_session, org, salesfile)
        headers = await _restricted_user(db_session, org, ds, rls="`region` == 'North'", email="north-rec@example.com")
        csv = b"Region,Sales\nNorth,150.25\nSouth,300\n"
        body = (await _reconcile(client, headers, ds.id, "e.csv", csv)).json()
        assert body["counts"] == {"match": 1, "mismatch": 0, "missing_in_widget": 1, "missing_in_file": 0}
        assert "300" not in str([r["values"] for r in body["rows"]])

    async def test_a_denied_column_gives_nothing_to_compare(self, client, db_session, two_orgs, salesfile):
        """The widget path drops the column, as it does when the widget draws:
        there is no table, and none of its values come back."""
        org = two_orgs["a"]["org"]
        ds = await _ds(db_session, org, salesfile)
        headers = await _restricted_user(db_session, org, ds, denied=["sales"], email="nosales-rec@example.com")
        r = await _reconcile(client, headers, ds.id, "e.csv", b"Region,Sales\nNorth,150.25\n")
        assert r.status_code in (400, 403), r.text
        assert "150.25" not in r.text and "300" not in r.text

    async def test_another_org_s_dataset_is_not_found(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        r = await _reconcile(client, auth_headers["b"], ds.id, "e.csv", b"Region,Sales\nNorth,1\n")
        assert r.status_code == 404

    async def test_a_file_that_is_not_a_table(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        r = await _reconcile(client, auth_headers["a"], ds.id, "report.pdf", b"%PDF-1.4")
        assert r.status_code == 400 and "CSV or Excel" in r.json()["detail"]
