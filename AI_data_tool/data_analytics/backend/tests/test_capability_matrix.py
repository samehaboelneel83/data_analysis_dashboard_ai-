"""E01: docs/CAPABILITY_MATRIX.md is a tested specification, not prose.

The first table in that document (between the `matrix:start` and `matrix:end`
markers) states, for six kinds of person, whether they may read a dataset,
change its model, open a draft and a published report, and read the data
behind that published report. This test builds exactly the scenario the
document describes and checks every cell against `app/core/capability.py`.
Change the rule, and this fails until the document says the same thing; edit
the document, and this fails until the code agrees.
"""
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.core.capability import (can_read_dataset, effective_capability,
                                 require_dataset_capability)
from app.core.security import hash_password
from app.models.models import (Dataset, DatasetShare, Organization, Report,
                               ReportUserGrant, Role, User)

DOC = Path(__file__).resolve().parents[2] / "docs" / "CAPABILITY_MATRIX.md"

ACTORS = {
    "Organization admin": "admin",
    "Olivia, the owner": "olivia",
    "Colleague with a DatasetShare on D": "ds_grantee",
    "Colleague with a 'view' grant on R": "report_grantee",
    "Colleague with no grant": "colleague",
    "Admin of another organization": "stranger",
}
COLUMNS = ["Read D", "Edit D's model", "Open R", "Open P", "Read E"]


def _matrix() -> dict[str, dict[str, str]]:
    text = DOC.read_text(encoding="utf-8")
    body = text.split("<!-- matrix:start -->", 1)[1].split("<!-- matrix:end -->", 1)[0]
    rows = [r.strip() for r in body.strip().splitlines() if r.strip().startswith("|")]
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    assert header == ["Actor", *COLUMNS], f"matrix columns changed: {header}"
    out = {}
    for r in rows[2:]:
        cells = [c.strip() for c in r.strip("|").split("|")]
        out[cells[0]] = dict(zip(COLUMNS, cells[1:]))
    assert set(out) == set(ACTORS), f"matrix actors changed: {sorted(out)}"
    return out


@pytest_asyncio.fixture
async def scenario(db_session, tmp_path):
    org = Organization(name="Matrix")
    other = Organization(name="Other")
    db_session.add_all([org, other])
    await db_session.flush()
    admin_role = Role(org_id=org.id, name="admin", is_org_admin=True)
    member = Role(org_id=org.id, name="member", is_org_admin=False)
    other_admin = Role(org_id=other.id, name="admin", is_org_admin=True)
    db_session.add_all([admin_role, member, other_admin])
    await db_session.flush()

    def mk(email, role, org_id):
        return User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))

    people = {
        "admin": mk("admin@m.test", admin_role, org.id),
        "olivia": mk("olivia@m.test", member, org.id),
        "ds_grantee": mk("share@m.test", member, org.id),
        "report_grantee": mk("grant@m.test", member, org.id),
        "colleague": mk("colleague@m.test", member, org.id),
        "stranger": mk("admin@other.test", other_admin, other.id),
    }
    db_session.add_all(people.values())
    await db_session.flush()

    csv = tmp_path / "x.csv"
    csv.write_text("a\n1\n", encoding="utf-8")
    d = Dataset(name="D", filename=str(csv), org_id=org.id, created_by=people["olivia"].id)
    e = Dataset(name="E", filename=str(csv), org_id=org.id, created_by=people["olivia"].id)
    db_session.add_all([d, e])
    await db_session.flush()
    r = Report(name="R", org_id=org.id, created_by=people["olivia"].id, dataset_id=d.id, published=False)
    p = Report(name="P", org_id=org.id, created_by=people["olivia"].id, dataset_id=e.id, published=True)
    db_session.add_all([r, p])
    await db_session.flush()
    db_session.add_all([
        DatasetShare(dataset_id=d.id, user_id=people["ds_grantee"].id),
        ReportUserGrant(report_id=r.id, user_id=people["report_grantee"].id, level="view"),
    ])
    await db_session.commit()
    for u in people.values():
        await db_session.refresh(u, ["role"])
    return {"people": people, "D": d, "E": e, "R": r, "P": p}


async def _observe(db, s, who) -> dict[str, str]:
    u = s["people"][who]

    async def edit_ok() -> str:
        try:
            await require_dataset_capability(db, u, s["D"].id, "data")
            return "yes"
        except HTTPException:
            return "no"

    async def read(ds) -> str:
        # Another organization's object is refused by the org check before the
        # read rule runs; mirror that here so the cell means what a request sees.
        if ds.org_id != u.org_id:
            return "no"
        return "yes" if await can_read_dataset(db, u, ds.id) else "no"

    return {
        "Read D": await read(s["D"]),
        "Edit D's model": await edit_ok() if s["D"].org_id == u.org_id else "no",
        "Open R": await effective_capability(db, u, s["R"].id),
        "Open P": await effective_capability(db, u, s["P"].id),
        "Read E": await read(s["E"]),
    }


@pytest.mark.parametrize("actor", list(ACTORS))
async def test_the_documented_matrix_is_what_the_code_does(db_session, scenario, actor):
    expected = _matrix()[actor]
    observed = await _observe(db_session, scenario, ACTORS[actor])
    assert observed == expected, (
        f"docs/CAPABILITY_MATRIX.md says {actor}: {expected}; the code does {observed}")
