from app.models.models import Report, ReportPage


async def test_mobile_layout_defaults_to_none(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1")
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.mobile_layout is None


async def test_mobile_layout_can_be_set_and_reloaded(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1",
                       mobile_layout={"order": [3, 1, 2], "hidden": [2]})
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.mobile_layout == {"order": [3, 1, 2], "hidden": [2]}
