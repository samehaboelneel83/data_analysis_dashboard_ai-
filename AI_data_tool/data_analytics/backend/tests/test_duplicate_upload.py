"""E07: uploading the same bytes twice says which dataset already holds them.

Advisory, never a refusal -- loading a file again on purpose is legitimate --
and only ever naming a dataset the uploader is allowed to see."""
import pytest

from app.core.config import settings

BODY = b"region,amount\nNorth,1\nSouth,2\n"


@pytest.fixture(autouse=True)
def _uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def _upload(client, headers, body=BODY, name="Sales", filename="sales.csv"):
    r = await client.post("/api/v1/datasets", files={"file": (filename, body, "text/csv")},
                          data={"name": name, "description": ""}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_the_second_upload_of_the_same_bytes_names_the_first(client, two_orgs, auth_headers):
    first = await _upload(client, auth_headers["a"])
    assert first["duplicate_of"] is None
    second = await _upload(client, auth_headers["a"], name="Sales again", filename="renamed.csv")
    assert second["id"] != first["id"]                       # still uploaded
    assert second["duplicate_of"] == {"id": first["id"], "name": "Sales"}


async def test_different_bytes_are_not_a_duplicate(client, two_orgs, auth_headers):
    await _upload(client, auth_headers["a"])
    other = await _upload(client, auth_headers["a"], body=BODY + b"East,3\n")
    assert other["duplicate_of"] is None


async def test_another_orgs_copy_is_never_named(client, two_orgs, auth_headers):
    """Naming it would tell org B what org A has uploaded."""
    await _upload(client, auth_headers["a"])
    theirs = await _upload(client, auth_headers["b"])
    assert theirs["duplicate_of"] is None


async def test_a_copy_the_uploader_cannot_read_is_never_named(client, db_session):
    """Datasets are per-user: a colleague's private upload must not be named,
    even in the same org -- the name alone can say too much."""
    from app.core.security import create_access_token, hash_password
    from app.models.models import Organization, Role, User
    org = Organization(name="Dupland")
    db_session.add(org)
    await db_session.flush()
    member = Role(org_id=org.id, name="member", is_org_admin=False)
    db_session.add(member)
    await db_session.flush()
    alice, bob = (User(org_id=org.id, role_id=member.id, email=e, password_hash=hash_password("pw"))
                  for e in ("alice@dup.test", "bob@dup.test"))
    db_session.add_all([alice, bob])
    await db_session.commit()
    hdr = lambda u: {"Authorization": f"Bearer {create_access_token(u.id, u.org_id)}"}  # noqa: E731
    first = await _upload(client, hdr(alice), name="Alice private")
    assert (await _upload(client, hdr(alice)))["duplicate_of"]["id"] == first["id"]
    assert (await _upload(client, hdr(bob)))["duplicate_of"] is None


async def test_the_batch_endpoint_reports_it_per_file(client, two_orgs, auth_headers):
    first = await _upload(client, auth_headers["a"])
    r = await client.post("/api/v1/datasets/batch",
                          files=[("files", ("x.csv", BODY, "text/csv")),
                                 ("files", ("y.csv", b"a\n1\n", "text/csv"))],
                          data={"name": "B", "description": "", "mode": "separate"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    dups = [i["dataset"]["duplicate_of"] for i in r.json()["items"]]
    assert dups == [{"id": first["id"], "name": "Sales"}, None]


async def test_the_hash_is_of_the_bytes_as_uploaded(client, db_session, two_orgs, auth_headers):
    """A semicolon CSV is rewritten into the canonical dialect; the same file
    must still match itself next time."""
    body = b"a;b\n1;2\n"
    first = await _upload(client, auth_headers["a"], body=body)
    second = await _upload(client, auth_headers["a"], body=body)
    assert second["duplicate_of"]["id"] == first["id"]
