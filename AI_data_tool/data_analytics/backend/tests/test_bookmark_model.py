from app.models.models import Report, Bookmark


async def test_bookmark_persists_state_json(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    bm = Bookmark(report_id=report.id, name="Q1 view", position=0,
                   state={"pageId": 1, "activeFilters": [], "promptValues": {}, "hiddenWidgetIds": []})
    db_session.add(bm)
    await db_session.commit()
    await db_session.refresh(bm)

    assert bm.state["pageId"] == 1
    assert bm.name == "Q1 view"
