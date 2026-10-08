"""Guided setup 2b/2d: Choose data -- proposals checked, run as the person, refined."""
import pytest

from app.models.models import (ColumnStats, DataSource, ObjectRowPolicy, SourceColumn,
                               SourceObject, SourceRelationship)
from app.services.guided_setup import datasets


class FakeClient:
    enabled = True
    last_error = None

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else None


CATALOG = [{"name": "cars", "columns": [{"name": "price"}, {"name": "make"}]},
           {"name": "makes", "columns": [{"name": "name"}]}]


class TestCheckSql:
    def test_a_plain_select_passes(self):
        sql, why = datasets.check_sql("SELECT price, make FROM cars;", "postgresql", CATALOG)
        assert why is None and sql.startswith("SELECT")

    @pytest.mark.parametrize("sql,needle", [
        ("DELETE FROM cars", "SELECT"),
        ("SELECT 1; DROP TABLE cars", "one statement"),
        ("SELECT * FROM salaries", "not in this database"),
        ("SELECT c.mileage FROM cars c", "no column"),
        ("", "empty"),
    ])
    def test_anything_else_is_refused(self, sql, needle):
        clean, why = datasets.check_sql(sql, "postgresql", CATALOG)
        assert clean is None and needle in why

    def test_a_cte_is_a_read(self):
        sql, why = datasets.check_sql("WITH x AS (SELECT price FROM cars) SELECT * FROM x", "postgresql", CATALOG)
        assert why is None


@pytest.fixture
async def cars(db_session, two_orgs):
    org = two_orgs["a"]["org"].id
    src = DataSource(name="Cars DB", type="postgresql", config={}, org_id=org,
                     allow_llm_sampling=True, sync_status="ok")
    db_session.add(src)
    await db_session.flush()
    listings = SourceObject(data_source_id=src.id, org_id=org, name="cars", schema_name="public",
                            kind="table", row_count_estimate=14269)
    db_session.add(listings)
    await db_session.flush()
    cols = [SourceColumn(source_object_id=listings.id, name=n, position=i, dtype=d, semantic_type=s)
            for i, (n, d, s) in enumerate([("price", "numeric", None), ("make", "text", None),
                                           ("make_ar", "text", None), ("seller_email", "text", "email"),
                                           ("listed", "datetime", None), ("title", "text", None)])]
    db_session.add_all(cols)
    await db_session.flush()
    db_session.add(ColumnStats(source_column_id=cols[5].id, null_ratio=0.95, exact=False))
    await db_session.commit()
    return src, listings


@pytest.fixture
def ran(monkeypatch):
    seen = []

    def fake_preview(cfg, table, query, limit):
        seen.append(query)
        if "COUNT(*)" in query:
            return {"columns": ["n"], "rows": [[14269]], "total": 1}
        if "broken" in query:
            raise RuntimeError('column "broken" does not exist\nLINE 1: ...')
        return {"columns": ["price", "make"], "rows": [[100, "Audi"]], "total": 1}
    monkeypatch.setattr("app.services.connections.preview_table", fake_preview)
    return seen


async def _admin(two_orgs, db_session):
    u = two_orgs["a"]["user"]
    await db_session.refresh(u, ["role"])
    return u


class TestPropose:
    async def test_good_proposals_are_run_and_kept(self, db_session, two_orgs, cars, ran):
        src, _ = cars
        client = FakeClient({"proposals": [
            {"name": "Car prices", "purpose": "Prices by brand", "sql": "SELECT price, make FROM cars",
             "includes": ["Price", "Brand"], "leaves_out": ["Arabic copies"], "why": "You price cars."},
            {"name": "Invented", "purpose": "x", "sql": "SELECT * FROM salaries",
             "includes": [], "leaves_out": [], "why": "x"},
        ]})
        items, reason = await datasets.propose(db_session, await _admin(two_orgs, db_session), src,
                                               {"work": "I price used cars"}, None, "en", client)
        assert reason is None
        assert [p["name"] for p in items] == ["Car prices"]      # the invented table was dropped
        p = items[0]
        assert p["test"]["row_count"] == 14269 and p["test"]["rows"] == [{"price": 100, "make": "Audi"}]
        assert p["tables"] == ["cars"] and p["includes"] == ["Price", "Brand"]
        # The person's work reached the model as a hint.
        assert "I price used cars" in client.calls[0][1]["content"]

    async def test_a_failing_query_gets_one_repair_with_the_databases_error(
            self, db_session, two_orgs, cars, ran):
        src, _ = cars
        client = FakeClient(
            {"proposals": [{"name": "A", "purpose": "p", "sql": "SELECT price AS broken FROM cars",
                            "includes": [], "leaves_out": [], "why": "w"}]},
            {"proposal": {"name": "A", "purpose": "p", "sql": "SELECT price FROM cars",
                          "includes": [], "leaves_out": [], "why": "w"}, "reply": "fixed"})
        items, _ = await datasets.propose(db_session, await _admin(two_orgs, db_session), src,
                                          None, None, "en", client)
        assert len(items) == 1 and items[0]["sql"] == "SELECT price FROM cars"
        assert 'column "broken" does not exist' in client.calls[1][1]["content"]

    async def test_without_the_model_a_plain_proposal_from_the_facts(self, db_session, two_orgs, cars, ran):
        src, _ = cars
        src.allow_llm_sampling = False
        items, reason = await datasets.propose(db_session, await _admin(two_orgs, db_session), src,
                                               None, None, "en", FakeClient())
        assert reason == "off" and len(items) == 1
        p = items[0]
        assert p["source"] == "auto"
        # Personal, mostly-empty and other-language copies are left out.
        assert set(p["leaves_out"]) == {"make_ar", "seller_email", "title"}
        assert '"price"' in p["sql"] and "seller_email" not in p["sql"]

    async def test_proposals_run_through_the_persons_row_rule(self, db_session, two_orgs, cars, ran):
        from app.core.security import hash_password
        from app.models.models import Role, User
        src, listings = cars
        role = Role(org_id=src.org_id, name="Branch", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        member = User(org_id=src.org_id, role_id=role.id, email="b@example.com", password_hash=hash_password("x"))
        db_session.add(member)
        await db_session.flush()
        db_session.add(ObjectRowPolicy(org_id=src.org_id, source_object_id=listings.id, role_id=role.id,
                                       predicate="make = 'Audi'"))
        await db_session.commit()
        await db_session.refresh(member, ["role"])
        run = await datasets.test_run(db_session, member, src, "SELECT price, make FROM cars")
        assert run["error"] is None
        assert all("make = 'Audi'" in q for q in ran)


class TestRefine:
    async def test_the_revision_keeps_its_id_and_the_conversation(self, db_session, two_orgs, cars, ran):
        src, _ = cars
        current = {"id": "abc", "name": "Car prices", "purpose": "p", "sql": "SELECT price, make FROM cars",
                   "includes": [], "leaves_out": [], "why": "w", "history": []}
        client = FakeClient({"proposal": {"name": "Car prices", "purpose": "p", "sql": "SELECT price FROM cars",
                                          "includes": ["Price"], "leaves_out": ["Brand"], "why": "w"},
                             "reply": "Removed the brand."})
        revised, reply = await datasets.refine(db_session, await _admin(two_orgs, db_session), src, None, None,
                                               current, "drop the brand", "en", client)
        assert revised["id"] == "abc" and revised["sql"] == "SELECT price FROM cars"
        assert reply == "Removed the brand."
        assert revised["history"][-2:] == [{"role": "user", "text": "drop the brand"},
                                          {"role": "assistant", "text": "Removed the brand."}]


class TestRoutes:
    @pytest.fixture(autouse=True)
    def inline(self, monkeypatch, db_session):
        from app.routers import guided_setup

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)

    @pytest.fixture
    def model(self, monkeypatch):
        client = FakeClient(*[{"proposals": [{"name": f"Set {i}", "purpose": "p", "sql": "SELECT price FROM cars",
                                              "includes": [], "leaves_out": [], "why": "w"}]} for i in range(5)])
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: client)
        return client

    async def test_proposals_are_asked_once_and_kept(self, client, auth_headers, cars, ran, model):
        src, _ = cars
        first = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
        assert first["can_create"] is True
        # Nothing is asked until the page asks (after About you, or Skip).
        assert first["proposals"]["asked"] is False and model.calls == []
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        again = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
        assert [p["name"] for p in again["proposals"]["items"]] == ["Set 0"]
        assert len(model.calls) == 1
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        third = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
        assert [p["name"] for p in third["proposals"]["items"]] == ["Set 1"]
        assert len(model.calls) == 2

    async def test_refining_an_unknown_proposal_is_404(self, client, auth_headers, cars, ran, model):
        src, _ = cars
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        r = await client.post(f"/api/v1/setup/{src.id}/datasets/nope/refine", headers=auth_headers["a"],
                              json={"message": "x"})
        assert r.status_code == 404

    async def test_a_failed_refinement_keeps_the_proposal_and_says_so(self, client, auth_headers, cars, ran, model):
        src, _ = cars
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        body = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
        pid = body["proposals"]["items"][0]["id"]
        model.replies = [None]
        await client.post(f"/api/v1/setup/{src.id}/datasets/{pid}/refine", headers=auth_headers["a"],
                          json={"message": "only Toyota"})
        after = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
        p = after["proposals"]["items"][0]
        assert p["id"] == pid and p["refine_failed"] == "failed" and "refining" not in p


class TestCreate:
    @pytest.fixture(autouse=True)
    def inline(self, monkeypatch, db_session):
        from app.routers import guided_setup

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)
        client = FakeClient({"proposals": [{"name": "Car prices", "purpose": "p", "sql": "SELECT price FROM cars",
                                            "includes": [], "leaves_out": [], "why": "w"}]})
        monkeypatch.setattr("app.services.llm.get_client", lambda *a, **k: client)

    async def test_an_import_is_queued_once_even_if_clicked_twice(self, client, db_session, auth_headers, cars, ran):
        from sqlalchemy import select
        from app.models.models import Job
        src, _ = cars
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        pid = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()["proposals"]["items"][0]["id"]
        body = {"items": [{"id": pid, "name": "Car prices"}], "mode": "import"}
        a = (await client.post(f"/api/v1/setup/{src.id}/datasets/create", headers=auth_headers["a"], json=body)).json()
        b = (await client.post(f"/api/v1/setup/{src.id}/datasets/create", headers=auth_headers["a"], json=body)).json()
        assert a["items"][0]["job_id"] and a["items"][0]["job_id"] == b["items"][0]["job_id"]
        job = (await db_session.execute(select(Job))).scalars().one()
        assert job.kind == "dataset.import" and job.inputs["query"] == "SELECT price FROM cars"
        assert job.inputs["dataset_name"] == "Car prices"

    async def test_a_proposal_that_no_longer_exists_is_reported(self, client, auth_headers, cars, ran):
        src, _ = cars
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        r = (await client.post(f"/api/v1/setup/{src.id}/datasets/create", headers=auth_headers["a"],
                               json={"items": [{"id": "gone", "name": "x"}]})).json()
        assert r["items"][0]["error"] and r["items"][0]["job_id"] is None

    async def test_only_an_admin_creates(self, client, db_session, cars, ran):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User
        src, _ = cars
        role = Role(org_id=src.org_id, name="Member", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        m = User(org_id=src.org_id, role_id=role.id, email="m2@example.com", password_hash=hash_password("x"))
        db_session.add(m)
        await db_session.commit()
        h = {"Authorization": f"Bearer {create_access_token(m.id, m.org_id)}"}
        step = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=h)).json()
        assert step["can_create"] is False
        r = await client.post(f"/api/v1/setup/{src.id}/datasets/create", headers=h,
                              json={"items": [{"id": "x", "name": "x"}]})
        assert r.status_code == 403


class TestRobustness:
    async def test_a_proposal_without_sql_is_repaired_or_dropped_never_a_crash(self, db_session, two_orgs, cars, ran):
        src, _ = cars
        client = FakeClient({"proposals": [{"name": "A", "purpose": "p", "includes": [], "leaves_out": [], "why": "w"}]},
                            {"proposal": {"name": "A", "purpose": "p", "sql": "SELECT price FROM cars",
                                          "includes": [], "leaves_out": [], "why": "w"}, "reply": "ok"})
        items, reason = await datasets.propose(db_session, await _admin(two_orgs, db_session), src,
                                               None, None, "en", client)
        assert reason is None and items[0]["sql"] == "SELECT price FROM cars"
        assert "(missing -- write one)" in client.calls[1][1]["content"]

    async def test_a_crash_is_recorded_as_failed_with_plain_proposals(self, client, db_session, auth_headers, cars, ran, monkeypatch):
        from app.routers import guided_setup

        async def run_now(db, user, tag, job, on_error=None):
            await job(db_session)
        monkeypatch.setattr(guided_setup, "_background", run_now)

        async def boom(*a, **k):
            raise RuntimeError("model client exploded")
        monkeypatch.setattr("app.services.guided_setup.datasets.propose", boom)
        src, _ = cars
        await client.post(f"/api/v1/setup/{src.id}/datasets/suggest", headers=auth_headers["a"])
        body = (await client.get(f"/api/v1/setup/{src.id}/datasets", headers=auth_headers["a"])).json()
        assert body["proposals"]["pending"] is False and body["proposals"]["failed"] == "failed"
        assert body["proposals"]["items"] and body["proposals"]["items"][0]["source"] == "auto"


class TestNeverStuck:
    async def test_dates_in_preview_rows_are_saved_as_text(self, db_session, two_orgs, cars, monkeypatch):
        import datetime as dt
        import json

        def fake_preview(cfg, table, query, limit):
            if "COUNT(*)" in query:
                return {"columns": ["n"], "rows": [[3]], "total": 1}
            return {"columns": ["day", "price"], "rows": [[dt.date(2023, 12, 12), 1.5]], "total": 1}
        monkeypatch.setattr("app.services.connections.preview_table", fake_preview)
        src, _ = cars
        run = await datasets.test_run(db_session, await _admin(two_orgs, db_session), src, "SELECT price FROM cars")
        assert run["rows"] == [{"day": "2023-12-12", "price": 1.5}]
        json.dumps(run)

    async def test_a_job_that_dies_while_saving_is_marked_failed(self, db_session, two_orgs, cars):
        from app.models.models import SetupJourney
        from app.routers.guided_setup import _failer
        src, _ = cars
        j = SetupJourney(org_id=src.org_id, user_id=two_orgs["a"]["user"].id, data_source_id=src.id,
                         proposals={"attempt": "a1", "pending": True, "items": []},
                         designs={"attempt": "d1", "items": [{"id": "x", "changing": "c1"}]})
        db_session.add(j)
        await db_session.commit()
        await _failer(j.id, "proposals", "a1")(db_session)
        await _failer(j.id, "designs", "c1", item="x", flag="changing")(db_session)
        await db_session.refresh(j)
        assert j.proposals == {"attempt": "a1", "items": [], "failed": "failed"}
        assert j.designs["items"] == [{"id": "x", "change_failed": "failed"}]
        # A newer attempt is never overwritten by an older one's failure.
        j.proposals = {"attempt": "a2", "pending": True, "items": []}
        await db_session.commit()
        await _failer(j.id, "proposals", "a1")(db_session)
        await db_session.refresh(j)
        assert j.proposals["pending"] is True
