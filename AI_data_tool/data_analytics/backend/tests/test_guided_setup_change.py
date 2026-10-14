"""Change the data behind a dataset (2026-10-08): add a left-out column (the
car's link) without SQL, keep the dataset's id, never remove what is used."""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import (DataSource, Dataset, DatasetColumn, Job, Report, ReportPage,
                               ReportWidget, Role, SourceColumn, SourceObject, User)
from app.services.guided_setup import change


class TestQueryShapes:
    def test_one_table_reads_can_be_extended(self):
        sql = "SELECT price, make FROM cars WHERE year >= 2015"
        assert change.simple_table(sql, "postgresql") == ("cars", None)
        out = change.add_columns(sql, ["item_url", "make"], "postgresql")
        assert out == 'SELECT price, make, "item_url" FROM cars WHERE year >= 2015'

    def test_an_alias_is_kept(self):
        out = change.add_columns("SELECT c.price FROM cars AS c", ["item_url"], "postgresql")
        assert out == 'SELECT c.price, "c"."item_url" FROM cars AS c'

    @pytest.mark.parametrize("sql", [
        "SELECT a.x FROM a JOIN b ON a.id = b.id",
        "SELECT make, AVG(price) FROM cars GROUP BY make",
        "SELECT DISTINCT make FROM cars",
        "WITH x AS (SELECT * FROM cars) SELECT * FROM x",
    ])
    def test_other_shapes_go_through_plain_words(self, sql):
        assert change.simple_table(sql, "postgresql") is None
        with pytest.raises(ValueError):
            change.add_columns(sql, ["y"], "postgresql")


@pytest.fixture
async def world(db_session, two_orgs, monkeypatch):
    org = two_orgs["a"]["org"].id
    src = DataSource(name="Cars DB", type="postgresql", config={}, org_id=org, allow_llm_sampling=True,
                     sync_status="ok")
    db_session.add(src)
    await db_session.flush()
    obj = SourceObject(data_source_id=src.id, org_id=org, name="cars", schema_name="public", kind="table",
                       row_count_estimate=10)
    db_session.add(obj)
    await db_session.flush()
    for i, (n, d) in enumerate([("price", "numeric"), ("make", "text"), ("item_url", "text")]):
        db_session.add(SourceColumn(source_object_id=obj.id, name=n, position=i, dtype=d,
                                    description="The car's web link" if n == "item_url" else None))
    ds = Dataset(name="Cars 2015+", org_id=org, data_source_id=src.id, mode="import",
                 source_query="SELECT price, make FROM cars", filename="x.parquet", row_count=10)
    db_session.add(ds)
    await db_session.flush()
    db_session.add_all([DatasetColumn(dataset_id=ds.id, name="price", dtype="numeric"),
                        DatasetColumn(dataset_id=ds.id, name="make", dtype="categorical")])
    report = Report(name="Pricing", org_id=org, dataset_id=ds.id)
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=page.id, widget_type="bar", title="By make",
                                config={"dimension": "make", "measure": "price", "aggregation": "avg"}))
    await db_session.commit()

    def fake_preview(cfg, table, query, limit):
        if "COUNT(*)" in query:
            return {"columns": ["n"], "rows": [[10]], "total": 1}
        cols = [c for c in ("price", "make", "item_url") if c in query]
        return {"columns": cols, "rows": [[{"price": 1, "make": "Kia", "item_url": "https://x/1"}[c] for c in cols]],
                "total": 1}
    monkeypatch.setattr("app.services.connections.preview_table", fake_preview)
    return src, ds


class TestRoutes:
    async def test_the_left_out_column_is_offered_with_its_meaning(self, client, auth_headers, world):
        src, ds = world
        body = (await client.get(f"/api/v1/setup/datasets/{ds.id}/change", headers=auth_headers["a"])).json()
        assert body["can_change"] is True
        assert [(c["name"], c["description"]) for c in body["addable"]] == [("item_url", "The car's web link")]

    async def test_preview_then_apply_reloads_the_same_dataset(self, client, db_session, auth_headers, world):
        src, ds = world
        prev = (await client.post(f"/api/v1/setup/datasets/{ds.id}/change/preview", headers=auth_headers["a"],
                                  json={"add": ["item_url"]})).json()
        assert prev["error"] is None and prev["adds"] == ["item_url"] and prev["removes"] == []
        r = await client.post(f"/api/v1/setup/datasets/{ds.id}/change/apply", headers=auth_headers["a"],
                              json={"sql": prev["sql"]})
        assert r.status_code == 200, r.text
        job = (await db_session.execute(select(Job))).scalars().one()
        assert job.inputs["dataset_id"] == ds.id and "item_url" in job.inputs["query"]
        assert job.inputs["dataset_name"] == ds.name

    async def test_a_column_a_chart_uses_is_never_removed(self, client, auth_headers, world):
        src, ds = world
        r = await client.post(f"/api/v1/setup/datasets/{ds.id}/change/apply", headers=auth_headers["a"],
                              json={"sql": "SELECT price FROM cars"})
        assert r.status_code == 409
        assert r.json()["detail"]["blocked"][0]["column"] == "make"

    async def test_plain_words_go_through_the_model(self, client, auth_headers, world, monkeypatch):
        src, ds = world

        class Model:
            enabled = True
            last_error = None

            async def complete_json(self, messages, schema, **kw):
                assert "I need the link of each car" in messages[1]["content"]
                return {"proposal": {"name": "x", "purpose": "", "sql": "SELECT price, make, item_url FROM cars",
                                     "includes": [], "leaves_out": [], "why": ""}, "reply": "Added the link."}
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: Model())
        prev = (await client.post(f"/api/v1/setup/datasets/{ds.id}/change/preview", headers=auth_headers["a"],
                                  json={"message": "I need the link of each car"})).json()
        assert prev["adds"] == ["item_url"] and prev["reply"] == "Added the link."

    async def test_only_an_admin_may_change_it(self, client, db_session, world):
        src, ds = world
        role = Role(org_id=ds.org_id, name="Member", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        m = User(org_id=ds.org_id, role_id=role.id, email="m@example.com", password_hash=hash_password("x"))
        db_session.add(m)
        await db_session.commit()
        h = {"Authorization": f"Bearer {create_access_token(m.id, m.org_id)}"}
        r = await client.post(f"/api/v1/setup/datasets/{ds.id}/change/apply", headers=h,
                              json={"sql": "SELECT price, make FROM cars"})
        assert r.status_code in (403, 404)

    async def test_an_uploaded_file_says_why_not(self, client, db_session, two_orgs, auth_headers):
        up = Dataset(name="upload.csv", org_id=two_orgs["a"]["org"].id, filename="u.parquet")
        db_session.add(up)
        await db_session.commit()
        body = (await client.get(f"/api/v1/setup/datasets/{up.id}/change", headers=auth_headers["a"])).json()
        assert body["can_change"] is False and body["reason"] == "not_from_connection"
