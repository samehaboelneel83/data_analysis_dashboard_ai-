"""A viewer's filtered page list must never be written back.

`Report.pages` cascades delete-orphan. Endpoints narrow `report.pages` in
memory for a role that may not see some pages; if that list were ever
flushed, the pages would be deleted for everyone."""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import PageRoleVisibility, Report, ReportPage, Role, User


@pytest.mark.asyncio
async def test_opening_a_report_as_a_restricted_viewer_deletes_nothing(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    report = Report(name="R", org_id=org.id)
    db_session.add(report)
    await db_session.flush()
    open_page = ReportPage(report_id=report.id, name="Open", position=0)
    secret = ReportPage(report_id=report.id, name="Board only", position=1)
    db_session.add_all([open_page, secret])
    board = Role(org_id=org.id, name="Board", is_org_admin=False)
    viewer_role = Role(org_id=org.id, name="Viewer", is_org_admin=False)
    db_session.add_all([board, viewer_role])
    await db_session.flush()
    db_session.add(PageRoleVisibility(page_id=secret.id, role_id=board.id))
    viewer = User(org_id=org.id, role_id=viewer_role.id, email="v@example.com", password_hash=hash_password("pw"))
    db_session.add(viewer)
    await db_session.commit()
    await db_session.refresh(viewer)
    headers = {"Authorization": f"Bearer {create_access_token(viewer.id, org.id)}"}

    for path in (f"/api/v1/reports/{report.id}", f"/api/v1/reports/{report.id}/pdf",
                 f"/api/v1/reports/{report.id}/package"):
        await client.get(path, headers=headers)

    names = (await db_session.execute(
        select(ReportPage.name).where(ReportPage.report_id == report.id).execution_options(populate_existing=True)
    )).scalars().all()
    assert sorted(names) == ["Board only", "Open"]
