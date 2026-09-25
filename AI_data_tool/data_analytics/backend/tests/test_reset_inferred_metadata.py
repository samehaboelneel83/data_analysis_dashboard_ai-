"""Clearing what inference got wrong.

The sync only ever PROPOSES. It writes a description or a semantic type where
none exists and never retracts one, which is right while the inference is right
and a trap when it is not: after the PII classifier was fixed so it no longer
calls every Unix timestamp a `national_id`, a fresh sync inferred nothing wrong
(`semantic_types: 0`) — and the catalog still showed all 41 bad labels from the
first run, because nothing removes a value once written.

There was no way to clear them from anywhere in the product. So an organisation
that synced before a metadata fix keeps the bad metadata forever, and the fix
looks like it did not work.

THE AUTHOR STILL WINS
---------------------
Only values whose `description_source` is `inferred` are cleared. Anything a
person typed is theirs; that is the same rule `infer_semantic.py` applies when
writing, and it would be a strange kind of repair that threw away the
corrections somebody made by hand *because* the inference was wrong.
"""
import pytest
from sqlalchemy import select

from app.models.models import DataSource, SourceColumn, SourceObject


async def _synced_source(db_session, org_id):
    """A catalog in the state the bad classifier left behind."""
    src = DataSource(name="Moodle-ish", type="sqlite",
                     config={"filepath": "/tmp/x.db"}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()

    obj = SourceObject(data_source_id=src.id, org_id=org_id, name="mdl_course",
                       kind="table", description="Courses.",
                       description_source="inferred")
    db_session.add(obj)
    await db_session.flush()

    db_session.add_all([
        # what the broken classifier wrote
        SourceColumn(source_object_id=obj.id, name="startdate", position=0,
                     dtype="integer", semantic_type="national_id",
                     description="An integer timestamp.", description_source="inferred"),
        SourceColumn(source_object_id=obj.id, name="timecreated", position=1,
                     dtype="integer", semantic_type="national_id",
                     description="When the row was made.", description_source="inferred"),
        # what a person fixed by hand afterwards
        SourceColumn(source_object_id=obj.id, name="fullname", position=2,
                     dtype="text", semantic_type=None,
                     description="The course title, as printed on the transcript.",
                     description_source="author"),
    ])
    await db_session.commit()
    await db_session.refresh(src)
    return src, obj


async def _columns(db_session, obj_id):
    return {c.name: c for c in (await db_session.execute(
        select(SourceColumn).where(SourceColumn.source_object_id == obj_id)
    )).scalars().all()}


async def test_inferred_semantic_types_are_cleared(client, db_session, two_orgs, auth_headers):
    src, obj = await _synced_source(db_session, two_orgs["a"]["org"].id)
    obj_id, src_id = obj.id, src.id

    r = await client.post(f"/api/v1/data-sources/{src_id}/review/reset-inferred",
                          headers=auth_headers["a"])

    assert r.status_code == 200, r.text
    db_session.expire_all()
    cols = await _columns(db_session, obj_id)
    assert cols["startdate"].semantic_type is None
    assert cols["timecreated"].semantic_type is None


async def test_inferred_descriptions_are_cleared(client, db_session, two_orgs, auth_headers):
    src, obj = await _synced_source(db_session, two_orgs["a"]["org"].id)
    obj_id, src_id = obj.id, src.id
    await client.post(f"/api/v1/data-sources/{src_id}/review/reset-inferred",
                      headers=auth_headers["a"])
    db_session.expire_all()
    cols = await _columns(db_session, obj_id)
    assert cols["startdate"].description is None


async def test_what_a_person_wrote_is_left_alone(client, db_session, two_orgs, auth_headers):
    """The rule that makes this safe to press."""
    src, obj = await _synced_source(db_session, two_orgs["a"]["org"].id)
    obj_id, src_id = obj.id, src.id
    await client.post(f"/api/v1/data-sources/{src_id}/review/reset-inferred",
                      headers=auth_headers["a"])
    db_session.expire_all()
    cols = await _columns(db_session, obj_id)
    assert cols["fullname"].description == "The course title, as printed on the transcript."
    assert cols["fullname"].description_source == "author"


async def test_it_reports_how_much_it_cleared(client, db_session, two_orgs, auth_headers):
    """An admin pressing this needs to know whether it did anything."""
    src, _ = await _synced_source(db_session, two_orgs["a"]["org"].id)
    r = await client.post(f"/api/v1/data-sources/{src.id}/review/reset-inferred",
                          headers=auth_headers["a"])
    body = r.json()
    assert body["columns_cleared"] == 2
    assert body["objects_cleared"] == 1


async def test_another_organisation_cannot_clear_this_catalog(client, db_session,
                                                              two_orgs, auth_headers):
    src, _ = await _synced_source(db_session, two_orgs["a"]["org"].id)
    r = await client.post(f"/api/v1/data-sources/{src.id}/review/reset-inferred",
                          headers=auth_headers["b"])
    assert r.status_code == 404


async def test_a_member_cannot_clear_a_catalog(client, db_session, two_orgs, auth_headers):
    """Metadata is org-wide: one member's reset would rewrite what everybody reads."""
    from app.core.security import create_access_token
    from app.models.models import Role, User

    org = two_orgs["a"]["org"]
    role = Role(org_id=org.id, name="Member", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    member = User(org_id=org.id, role_id=role.id, email="member@a.invalid",
                  password_hash="x", is_active=True)
    db_session.add(member)
    await db_session.commit()

    src, _ = await _synced_source(db_session, org.id)
    r = await client.post(
        f"/api/v1/data-sources/{src.id}/review/reset-inferred",
        headers={"Authorization":
                 f"Bearer {create_access_token(member.id, member.org_id)}"})
    assert r.status_code in (401, 403)
