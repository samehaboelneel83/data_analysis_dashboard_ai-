from app.models.models import Report, ReportPage


async def test_page_size_defaults_to_16_9(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1")
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.page_size == "16:9"
    assert page.custom_width is None


async def test_page_size_can_be_set_to_custom_dimensions(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1", page_size="custom", custom_width=1200, custom_height=800)
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.custom_width == 1200
    assert page.custom_height == 800


async def test_page_layout_mode_is_null_until_the_builder_auto_packs(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1")
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.layout_mode is None
    assert page.layout_template is None


async def test_page_layout_mode_can_be_packed_or_free(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1",
                      layout_mode="packed", layout_template="executive")
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.layout_mode == "packed"
    assert page.layout_template == "executive"
