"""Guided setup D1: the AI sees exactly what the logged-in person sees.

Covers the three pieces of step 0b: a new connection lets the model describe
it unless the form says otherwise, the review catalog follows the Connections
list's visibility, and sample rows come through the person's own row rules
with personal values masked.
"""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import (DataSource, ObjectRowPolicy, Role, SourceColumn,
                               SourceObject, User)
from app.services.agent.policy import PolicyError
from app.services.guided_setup import access


async def _member(db_session, org_id, email="member@example.com"):
    role = Role(org_id=org_id, name="Member", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user, ["role"])
    return user


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


class TestNewConnectionDefault:
    async def test_model_may_describe_a_new_connection_by_default(
            self, client, db_session, auth_headers):
        resp = await client.post("/api/v1/data-sources", headers=auth_headers["a"],
                                 json={"name": "cars", "type": "postgresql", "config": {}})
        assert resp.status_code == 200
        src = (await db_session.execute(
            select(DataSource).where(DataSource.id == resp.json()["id"]))).scalar_one()
        assert src.allow_llm_sampling is True

    async def test_the_form_can_turn_it_off(self, client, db_session, auth_headers):
        resp = await client.post("/api/v1/data-sources", headers=auth_headers["a"],
                                 json={"name": "cars", "type": "postgresql", "config": {},
                                       "allow_llm_sampling": False})
        assert resp.status_code == 200
        src = (await db_session.execute(
            select(DataSource).where(DataSource.id == resp.json()["id"]))).scalar_one()
        assert src.allow_llm_sampling is False


class TestReviewVisibility:
    async def test_member_cannot_read_the_catalog_of_a_connection_hidden_from_them(
            self, client, db_session, two_orgs):
        a = two_orgs["a"]
        owner = await _member(db_session, a["org"].id, "owner@example.com")
        other = await _member(db_session, a["org"].id, "other@example.com")
        src = DataSource(name="private", type="postgresql", config={},
                         org_id=a["org"].id, created_by=owner.id)
        db_session.add(src)
        await db_session.commit()

        assert (await client.get(f"/api/v1/data-sources/{src.id}/review",
                                 headers=_headers(other))).status_code == 404
        assert (await client.get(f"/api/v1/data-sources/{src.id}/review",
                                 headers=_headers(owner))).status_code == 200

    async def test_admin_still_reads_every_connection(self, client, db_session, two_orgs, auth_headers):
        a = two_orgs["a"]
        owner = await _member(db_session, a["org"].id, "owner2@example.com")
        src = DataSource(name="private", type="postgresql", config={},
                         org_id=a["org"].id, created_by=owner.id)
        db_session.add(src)
        await db_session.commit()
        assert (await client.get(f"/api/v1/data-sources/{src.id}/review",
                                 headers=auth_headers["a"])).status_code == 200


class TestSampleSql:
    def test_plain_sample_quotes_names(self):
        obj = SourceObject(name="cars_hatla2ee", schema_name="public")
        sql = access.sample_sql(obj, "postgresql", 5, {})
        assert sql == 'SELECT * FROM "public"."cars_hatla2ee" LIMIT 5'

    def test_row_rule_is_parsed_into_the_where(self):
        obj = SourceObject(name="cars_hatla2ee", schema_name="public")
        sql = access.sample_sql(obj, "postgresql", 5, {"cars_hatla2ee": "governorate = 'Cairo'"})
        assert "WHERE" in sql and "governorate = 'Cairo'" in sql

    def test_limit_is_capped(self):
        obj = SourceObject(name="t", schema_name=None)
        assert access.sample_sql(obj, "postgresql", 10_000, {}).endswith(f"LIMIT {access.MAX_SAMPLE_ROWS}")

    def test_a_rule_that_does_not_parse_refuses(self):
        with pytest.raises(PolicyError):
            access.sample_sql(SourceObject(name="t"), "postgresql", 5, {"t": "((("})


class TestSampleRows:
    @pytest.fixture
    async def catalog(self, db_session, two_orgs):
        a = two_orgs["a"]
        src = DataSource(name="cars", type="postgresql", config={}, org_id=a["org"].id)
        db_session.add(src)
        await db_session.flush()
        obj = SourceObject(data_source_id=src.id, org_id=a["org"].id, name="owners",
                           schema_name="public", kind="table")
        db_session.add(obj)
        await db_session.flush()
        db_session.add(SourceColumn(source_object_id=obj.id, name="email", position=1,
                                    dtype="text", semantic_type="email"))
        await db_session.commit()
        return src, obj

    @pytest.fixture
    def ran(self, monkeypatch):
        seen = {}

        def fake_preview(cfg, table, query, limit):
            seen["sql"] = query
            return {"columns": ["email", "city"],
                    "rows": [["sara@example.com", "Cairo"], ["omar@example.com", "Giza"]],
                    "total": 2}
        monkeypatch.setattr("app.services.connections.preview_table", fake_preview)
        return seen

    async def test_admin_sees_rows_with_personal_values_masked(
            self, db_session, two_orgs, catalog, ran):
        src, obj = catalog
        admin = two_orgs["a"]["user"]
        await db_session.refresh(admin, ["role"])
        out = await access.sample_rows(db_session, admin, src, obj, limit=5)
        assert out["restricted"] is False and out["error"] is None
        assert [r["city"] for r in out["rows"]] == ["Cairo", "Giza"]
        assert "sara@example.com" not in str(out["rows"])
        assert "WHERE" not in ran["sql"]

    async def test_member_rows_come_through_their_row_rule(
            self, db_session, two_orgs, catalog, ran):
        src, obj = catalog
        member = await _member(db_session, two_orgs["a"]["org"].id)
        db_session.add(ObjectRowPolicy(org_id=member.org_id, source_object_id=obj.id,
                                       role_id=member.role_id, predicate="city = 'Cairo'"))
        await db_session.commit()
        out = await access.sample_rows(db_session, member, src, obj, limit=5)
        assert out["restricted"] is True
        assert "city = 'Cairo'" in ran["sql"]

    async def test_an_unreachable_source_still_answers(self, db_session, two_orgs, catalog, monkeypatch):
        src, obj = catalog

        def boom(*a, **k):
            raise RuntimeError("connection refused")
        monkeypatch.setattr("app.services.connections.preview_table", boom)
        admin = two_orgs["a"]["user"]
        await db_session.refresh(admin, ["role"])
        out = await access.sample_rows(db_session, admin, src, obj)
        assert out == {"columns": [], "rows": [], "restricted": False, "error": "unreachable"}
