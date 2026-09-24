from app.models.models import Report


async def test_report_theme_defaults_to_default(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.theme == "default"


async def test_report_theme_can_be_set(db_session):
    report = Report(name="R", theme="ocean")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.theme == "ocean"
