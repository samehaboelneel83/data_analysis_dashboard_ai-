"""E17: the migration inventory -- the old estate, mapped, checked, signed off.

An admin imports the estate's inventory (a CSV) and its SAS programs (each
scanned for what it uses, mapped to Datalytics features). The owner of an
item links the report that replaces it, reconciles its widgets against the
old exports (each result kept on the item) and signs off. Status is derived
from that evidence, so it cannot claim more than was shown.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import AuditLogEntry, Dataset, DatasetColumn, MigrationItem, Report, Role, User
from app.services.migration import sign_off_basis, status_of
from app.services.sas_inventory import read_inventory, scan_sas

PROGRAM = """
/* Monthly sales pack -- proc means data=old; is only a comment */
libname dw oracle path=prod schema=sales;
libname dw clear;
%let month = 2025-06;
* proc gchart data=x; this whole statement is a comment;
data work.sales (keep=region amount);
  set dw.orders(where=(month="&month"));
run;
proc sort data=work.sales nodupkey; by region; run;
proc sql; create table totals as select region, sum(amount) as total from work.sales group by region; quit;
proc tabulate data=totals; class region; var total; table region, total*sum; run;
ods pdf file="/reports/pack.pdf";
proc sgplot data=totals; vbar region / response=total; run;
ods pdf close;
proc arima data=work.sales; identify var=amount; run;
proc shewhart data=work.sales; run;
x 'rm /tmp/stage/*';
"""


class TestScanning:
    def test_a_program_s_features_are_found_and_mapped(self):
        scan = scan_sas(PROGRAM)
        keys = {f["key"]: f for f in scan["features"]}
        for k in ("data_step", "proc_sort", "proc_sql", "proc_tabulate", "graphs", "forecast",
                  "macro", "ods", "libname", "os_command"):
            assert k in keys, k
        assert keys["proc_tabulate"]["fit"] == "native" and "Pivot" in keys["proc_tabulate"]["target"]
        assert keys["os_command"]["fit"] == "manual"
        assert scan["libnames"] == ["DW"]
        assert keys["ods"]["count"] == 1                     # `ods pdf close` is not a destination opened

    def test_comments_are_not_uses(self):
        keys = {f["key"] for f in scan_sas(PROGRAM)["features"]}
        assert "proc_means" not in keys                      # inside /* */
        assert "graphs" in keys                              # SGPLOT, not the commented GCHART
        assert scan_sas("* proc gchart data=x;\n/* proc sql; */")["features"] == []

    def test_an_unknown_proc_is_listed_as_manual_not_dropped(self):
        scan = scan_sas(PROGRAM)
        assert scan["unknown_procs"] == ["shewhart"]
        row = next(f for f in scan["features"] if f["key"] == "proc:shewhart")
        assert row["fit"] == "manual" and row["label"] == "PROC SHEWHART"

    def test_data_options_are_not_data_steps(self):
        keys = {f["key"]: f["count"] for f in scan_sas("proc print data=a; run;\ndata b; set a; run;")["features"]}
        assert keys == {"proc_print": 1, "data_step": 1}


class TestTheInventoryFile:
    def test_the_estate_s_own_headings_are_read(self):
        rows = read_inventory("﻿Report Name;Type;Business Owner;Folder;Comments\n"
                              "Sales pack;STP;a@x.com;/Shared/Sales;monthly\n;;;;\nChurn;program;;;\n")
        assert rows == [
            {"name": "Sales pack", "kind": "stored_process", "source_path": "/Shared/Sales", "owner": "a@x.com",
             "report": None, "notes": "monthly", "source_system": "SAS"},
            {"name": "Churn", "kind": "program", "source_path": None, "owner": None, "report": None,
             "notes": None, "source_system": "SAS"}]

    def test_a_file_with_no_name_column_is_refused(self):
        with pytest.raises(ValueError, match="Name"):
            read_inventory("a,b\n1,2\n")


class _Item:
    def __init__(self, **kw):
        self.decision, self.kind, self.report_id = "migrate", "report", None
        self.reconciles, self.sign_off = None, None
        self.__dict__.update(kw)


CLEAN = {"match": 3, "mismatch": 0, "missing_in_widget": 0, "missing_in_file": 0}
OFF = {"match": 2, "mismatch": 1, "missing_in_widget": 0, "missing_in_file": 0}


class TestStatus:
    def test_status_follows_the_evidence(self):
        assert status_of(_Item()) == "to_map"
        assert status_of(_Item(report_id=5)) == "mapped"
        assert status_of(_Item(report_id=5, reconciles={"w1": {"report_id": 5, "counts": CLEAN}})) == "reconciled"
        assert status_of(_Item(report_id=5, reconciles={"w1": {"report_id": 5, "counts": CLEAN},
                                                         "w2": {"report_id": 5, "counts": OFF}})) == "differences"
        assert status_of(_Item(decision="retire", report_id=5)) == "retired"

    def test_a_comparison_against_another_report_does_not_count(self):
        item = _Item(report_id=6, reconciles={"w1": {"report_id": 5, "counts": CLEAN}})
        assert status_of(item) == "mapped"
        with pytest.raises(ValueError, match="Reconcile"):
            sign_off_basis(item, None, False)

    def test_a_sign_off_for_another_report_does_not_stand(self):
        item = _Item(report_id=6, sign_off={"report_id": 5, "basis": "reconciled"})
        assert status_of(item) == "mapped"

    def test_differences_need_accepting_with_a_reason(self):
        item = _Item(report_id=5, reconciles={"w1": {"report_id": 5, "counts": OFF}})
        with pytest.raises(ValueError, match="differences"):
            sign_off_basis(item, "fine", False)
        with pytest.raises(ValueError, match="why"):
            sign_off_basis(item, "  ", True)
        assert sign_off_basis(item, "rounding in the old report", True) == "accepted"

    def test_a_job_with_nothing_to_compare_needs_a_reason(self):
        item = _Item(kind="job")
        with pytest.raises(ValueError, match="no comparison"):
            sign_off_basis(item, "", False)
        assert sign_off_basis(item, "replaced by the nightly dataflow", False) == "no_comparison"


# ── the API ─────────────────────────────────────────────────────────────────

@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["North", "North", "South", "East"], "sales": [100.25, 50.0, 300.0, 7.5]}).to_csv(p, index=False)
    return str(p)


async def _member(db, org, email):
    role = Role(org_id=org.id, name=f"role-{email}", is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org.id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def _report(db, org, path, *, published=True, author=None):
    ds = Dataset(name="Sales", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("region", "categorical"), ("sales", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    # An unowned report is everyone's (demo content); a draft has an author.
    rep = Report(name="Sales pack", org_id=org.id, dataset_id=ds.id, published=published,
                 created_by=author.id if author else None)
    db.add(rep)
    await db.commit()
    return ds, rep


WIDGET = ('{"widget_type": "bar", "report_id": %d, '
          '"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}}')
GOOD = b"Region,Sales\nNorth,150.25\nSouth,300\nEast,7.5\n"
BAD = b"Region,Sales\nNorth,150.25\nSouth,301\nEast,7.5\n"


async def _reconcile(client, headers, ds, rep, content, item_id, key="w1"):
    return await client.post(f"/api/v1/datasets/{ds.id}/widget-data/reconcile", headers=headers,
                             data={"widget": WIDGET % rep.id, "migration_item": str(item_id),
                                   "widget_key": key, "widget_title": "Sales by region"},
                             files={"file": ("sas_export.csv", content)})


class TestTheApi:
    async def test_the_whole_journey(self, client, auth_headers, db_session, two_orgs, salesfile):
        org = two_orgs["a"]["org"]
        owner, oh = await _member(db_session, org, "owner-mig@example.com")
        ds, rep = await _report(db_session, org, salesfile)
        admin = auth_headers["a"]

        inv = (b"Name,Type,Owner,Notes\nSales pack,report,owner-mig@example.com,monthly\n"
               b"Old extract,job,nobody@example.com,\n")
        r = await client.post("/api/v1/migration/items/import", headers=admin, files=[
            ("files", ("inventory.csv", inv)), ("files", ("sales_pack.sas", PROGRAM.encode())),
            ("files", ("notes.docx", b"x"))])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 3
        assert any("nobody@example.com" in w for w in body["warnings"])
        assert any("notes.docx" in w for w in body["warnings"])

        listing = (await client.get("/api/v1/migration/items", headers=oh)).json()
        assert listing["can_manage"] is False and listing["summary"]["to_map"] == 3
        item = next(i for i in listing["items"] if i["name"] == "Sales pack")
        assert item["owner"]["email"] == "owner-mig@example.com" and item["can_sign_off"] is True
        program = next(i for i in listing["items"] if i["name"] == "sales_pack")
        assert program["kind"] == "program" and program["fit"] == "manual"

        # The owner links the replacement and compares a widget: a difference.
        r = await client.patch(f"/api/v1/migration/items/{item['id']}", headers=oh, json={"report_id": rep.id})
        assert r.status_code == 200 and r.json()["status"] == "mapped"
        r = await _reconcile(client, oh, ds, rep, BAD, item["id"])
        assert r.status_code == 200, r.text
        assert r.json()["recorded_on"] == item["id"]
        got = (await client.get("/api/v1/migration/items", headers=oh)).json()["items"]
        now = next(i for i in got if i["id"] == item["id"])
        assert now["status"] == "differences" and now["reconciles"][0]["title"] == "Sales by region"

        r = await client.post(f"/api/v1/migration/items/{item['id']}/sign-off", headers=oh, json={})
        assert r.status_code == 400 and "differences" in r.json()["detail"]

        # Reconciled again after the fix: the latest per widget counts.
        await _reconcile(client, oh, ds, rep, GOOD, item["id"])
        r = await client.post(f"/api/v1/migration/items/{item['id']}/sign-off", headers=oh, json={})
        assert r.status_code == 200, r.text
        signed = r.json()
        assert signed["status"] == "signed_off" and signed["sign_off"]["basis"] == "reconciled"
        assert signed["report_changed_since_sign_off"] is False

        # A later comparison that agrees leaves the sign-off; one that differs takes it away.
        await _reconcile(client, oh, ds, rep, GOOD, item["id"], key="w2")
        got = (await client.get("/api/v1/migration/items", headers=oh)).json()["items"]
        assert next(i for i in got if i["id"] == item["id"])["status"] == "signed_off"
        await _reconcile(client, oh, ds, rep, BAD, item["id"], key="w2")
        got = (await client.get("/api/v1/migration/items", headers=oh)).json()["items"]
        now = next(i for i in got if i["id"] == item["id"])
        assert now["status"] == "differences" and now["sign_off"] is None
        await _reconcile(client, oh, ds, rep, GOOD, item["id"], key="w2")
        r = await client.post(f"/api/v1/migration/items/{item['id']}/sign-off", headers=oh, json={})
        assert r.status_code == 200 and r.json()["status"] == "signed_off"

        # The report changes afterwards: the item says so.
        rep_row = await db_session.get(Report, rep.id)
        rep_row.revision = (rep_row.revision or 0) + 1
        await db_session.commit()
        got = (await client.get("/api/v1/migration/items", headers=oh)).json()["items"]
        assert next(i for i in got if i["id"] == item["id"])["report_changed_since_sign_off"] is True

        actions = set((await db_session.execute(select(AuditLogEntry.action).where(
            AuditLogEntry.action.like("migration.%")))).scalars())
        assert {"migration.import", "migration.item_update", "migration.reconcile", "migration.sign_off",
                "migration.sign_off_withdrawn"} <= actions

    async def test_only_the_owner_signs_off_and_an_admin_can_withdraw(self, client, auth_headers, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        owner, oh = await _member(db_session, org, "owner2-mig@example.com")
        _, other = await _member(db_session, org, "other-mig@example.com")
        admin = auth_headers["a"]
        r = await client.post("/api/v1/migration/items", headers=admin,
                              json={"name": "Nightly load", "kind": "job", "owner_id": owner.id})
        assert r.status_code == 201, r.text
        iid = r.json()["id"]
        assert (await client.post(f"/api/v1/migration/items/{iid}/sign-off", headers=admin,
                                  json={"note": "done"})).status_code == 403
        assert (await client.post(f"/api/v1/migration/items/{iid}/sign-off", headers=other,
                                  json={"note": "done"})).status_code == 403
        assert (await client.patch(f"/api/v1/migration/items/{iid}", headers=other,
                                   json={"notes": "x"})).status_code == 403
        r = await client.post(f"/api/v1/migration/items/{iid}/sign-off", headers=oh,
                              json={"note": "replaced by the nightly dataflow"})
        assert r.status_code == 200 and r.json()["sign_off"]["basis"] == "no_comparison"
        # The owner cannot hand the item to someone else; an admin can, and the sign-off goes with the old owner.
        assert (await client.patch(f"/api/v1/migration/items/{iid}", headers=oh,
                                   json={"owner_id": None})).status_code == 403
        r = await client.delete(f"/api/v1/migration/items/{iid}/sign-off", headers=admin)
        assert r.status_code == 200 and r.json()["status"] == "to_map"

    async def test_retiring_needs_a_reason(self, client, auth_headers, db_session, two_orgs):
        admin = auth_headers["a"]
        iid = (await client.post("/api/v1/migration/items", headers=admin, json={"name": "Unused"})).json()["id"]
        assert (await client.patch(f"/api/v1/migration/items/{iid}", headers=admin,
                                   json={"decision": "retire"})).status_code == 400
        r = await client.patch(f"/api/v1/migration/items/{iid}", headers=admin,
                               json={"decision": "retire", "notes": "nobody has opened it since 2021"})
        assert r.status_code == 200 and r.json()["status"] == "retired"

    async def test_a_report_the_reader_cannot_open_is_not_named(self, client, auth_headers, db_session, two_orgs, salesfile):
        org = two_orgs["a"]["org"]
        _, mh = await _member(db_session, org, "reader-mig@example.com")
        _, draft = await _report(db_session, org, salesfile, published=False, author=two_orgs["a"]["user"])
        admin = auth_headers["a"]
        await client.post("/api/v1/migration/items", headers=admin, json={"name": "Draft pack", "report_id": draft.id})
        item = (await client.get("/api/v1/migration/items", headers=mh)).json()["items"][0]
        assert item["report"] == {"id": draft.id, "name": None, "can_open": False}

    async def test_linking_needs_a_report_you_can_open(self, client, auth_headers, db_session, two_orgs, salesfile):
        org = two_orgs["a"]["org"]
        owner, oh = await _member(db_session, org, "owner3-mig@example.com")
        _, draft = await _report(db_session, org, salesfile, published=False, author=two_orgs["a"]["user"])
        iid = (await client.post("/api/v1/migration/items", headers=auth_headers["a"],
                                 json={"name": "X", "owner_id": owner.id})).json()["id"]
        r = await client.patch(f"/api/v1/migration/items/{iid}", headers=oh, json={"report_id": draft.id})
        assert r.status_code == 404

    async def test_recording_needs_the_linked_report_and_the_owner(self, client, auth_headers, db_session, two_orgs, salesfile):
        org = two_orgs["a"]["org"]
        owner, oh = await _member(db_session, org, "owner4-mig@example.com")
        _, other = await _member(db_session, org, "other4-mig@example.com")
        ds, rep = await _report(db_session, org, salesfile)
        admin = auth_headers["a"]
        iid = (await client.post("/api/v1/migration/items", headers=admin,
                                 json={"name": "Y", "owner_id": owner.id})).json()["id"]
        r = await _reconcile(client, oh, ds, rep, GOOD, iid)
        assert r.status_code == 400 and "not linked" in r.json()["detail"]
        await client.patch(f"/api/v1/migration/items/{iid}", headers=oh, json={"report_id": rep.id})
        r = await _reconcile(client, other, ds, rep, GOOD, iid)
        assert r.status_code == 403
        assert (await db_session.get(MigrationItem, iid)).reconciles is None

    async def test_another_org_s_items_do_not_exist(self, client, auth_headers, db_session, two_orgs):
        iid = (await client.post("/api/v1/migration/items", headers=auth_headers["a"], json={"name": "A's"})).json()["id"]
        assert (await client.get("/api/v1/migration/items", headers=auth_headers["b"])).json()["items"] == []
        assert (await client.patch(f"/api/v1/migration/items/{iid}", headers=auth_headers["b"],
                                   json={"notes": "x"})).status_code == 404
        assert (await client.delete(f"/api/v1/migration/items/{iid}", headers=auth_headers["b"])).status_code == 404

    async def test_members_cannot_import_or_create(self, client, db_session, two_orgs):
        _, mh = await _member(db_session, two_orgs["a"]["org"], "plain-mig@example.com")
        assert (await client.post("/api/v1/migration/items", headers=mh, json={"name": "Z"})).status_code == 403
        r = await client.post("/api/v1/migration/items/import", headers=mh,
                              files=[("files", ("i.csv", b"Name\nA\n"))])
        assert r.status_code == 403

    async def test_the_feature_map_is_served(self, client, auth_headers):
        rows = (await client.get("/api/v1/migration/feature-map", headers=auth_headers["a"])).json()
        assert {"key", "label", "target", "fit", "note"} == set(rows[0])
        assert any(r["key"] == "proc_tabulate" for r in rows)

    async def test_a_program_attached_to_an_item(self, client, auth_headers, db_session, two_orgs):
        admin = auth_headers["a"]
        iid = (await client.post("/api/v1/migration/items", headers=admin, json={"name": "Pack"})).json()["id"]
        r = await client.post(f"/api/v1/migration/items/{iid}/scan", headers=admin,
                              files={"file": ("pack.sas", b"proc tabulate data=a; run;")})
        assert r.status_code == 200 and r.json()["fit"] == "native"
