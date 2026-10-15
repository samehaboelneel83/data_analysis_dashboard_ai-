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


# ── C-21: a page size the canvas and the exports honour ─────────────────────
# A FIXED frame is a size with both dimensions stored. A page with no stored
# dimensions -- every page made before C-21, whatever its `page_size` -- keeps
# the flowing "Fit to width" canvas, so existing dashboards do not change.
import pytest  # noqa: E402


async def _report_page(client, headers):
    r = await client.post("/api/v1/reports", json={"name": "Sized"}, headers=headers)
    rid = r.json()["id"]
    page_id = (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"][0]["id"]
    return rid, page_id


async def _page(client, headers, rid):
    return (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"][0]


@pytest.mark.asyncio
async def test_custom_width_and_height_round_trip(client, auth_headers):
    h = auth_headers["a"]
    rid, pid = await _report_page(client, h)
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{pid}",
                           json={"page_size": "custom", "custom_width": 1600, "custom_height": 1200}, headers=h)
    assert r.status_code == 200, r.text
    p = await _page(client, h, rid)
    assert (p["page_size"], p["custom_width"], p["custom_height"]) == ("custom", 1600, 1200)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"page_size": "custom", "custom_width": 100, "custom_height": 800},
    {"page_size": "custom", "custom_width": 1600, "custom_height": 20000},
    {"page_size": "custom", "custom_width": -5, "custom_height": 800},
    {"page_size": "A4"},
])
async def test_out_of_range_or_unknown_sizes_are_refused(client, auth_headers, body):
    h = auth_headers["a"]
    rid, pid = await _report_page(client, h)
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{pid}", json=body, headers=h)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_custom_without_both_dimensions_is_refused(client, auth_headers):
    h = auth_headers["a"]
    rid, pid = await _report_page(client, h)
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{pid}",
                           json={"page_size": "custom", "custom_width": 1600}, headers=h)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_fit_clears_the_stored_frame(client, auth_headers):
    h = auth_headers["a"]
    rid, pid = await _report_page(client, h)
    await client.patch(f"/api/v1/reports/{rid}/pages/{pid}",
                       json={"page_size": "4:3", "custom_width": 960, "custom_height": 720}, headers=h)
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{pid}", json={"page_size": "fit"}, headers=h)
    assert r.status_code == 200, r.text
    p = await _page(client, h, rid)
    assert (p["page_size"], p["custom_width"], p["custom_height"]) == ("fit", None, None)


@pytest.mark.asyncio
async def test_an_explicit_null_clears_a_dimension(client, auth_headers):
    # The builder's Undo sends the values the page had before: for a page that
    # had no frame that is `null`, which must clear the frame again.
    h = auth_headers["a"]
    rid, pid = await _report_page(client, h)
    await client.patch(f"/api/v1/reports/{rid}/pages/{pid}",
                       json={"page_size": "16:9", "custom_width": 1280, "custom_height": 720}, headers=h)
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{pid}",
                           json={"page_size": "16:9", "custom_width": None, "custom_height": None}, headers=h)
    assert r.status_code == 200, r.text
    p = await _page(client, h, rid)
    assert (p["custom_width"], p["custom_height"]) == (None, None)


@pytest.mark.asyncio
async def test_a_rename_leaves_the_size_alone(client, auth_headers):
    h = auth_headers["a"]
    rid, pid = await _report_page(client, h)
    await client.patch(f"/api/v1/reports/{rid}/pages/{pid}",
                       json={"page_size": "custom", "custom_width": 1600, "custom_height": 1200}, headers=h)
    await client.patch(f"/api/v1/reports/{rid}/pages/{pid}", json={"name": "Renamed"}, headers=h)
    p = await _page(client, h, rid)
    assert (p["page_size"], p["custom_width"], p["custom_height"]) == ("custom", 1600, 1200)


def test_shared_and_embedded_pages_carry_the_size():
    """C-21: guest-link and embed views draw a fixed page at its size, so the
    page shape they are served carries it -- from a live page or a snapshot."""
    from types import SimpleNamespace
    from app.routers.shared import _shape_page
    live = SimpleNamespace(id=1, name="P", page_type="normal", position=0, mobile_layout=None, widgets=[],
                           page_size="custom", custom_width=1600, custom_height=1200)
    assert {k: _shape_page(live)[k] for k in ("page_size", "custom_width", "custom_height")} == \
        {"page_size": "custom", "custom_width": 1600, "custom_height": 1200}
    snap = {"id": 1, "name": "P", "page_type": "normal", "widgets": [], "page_size": "4:3",
            "custom_width": 960, "custom_height": 720}
    assert _shape_page(snap)["custom_width"] == 960
    old_snap = {"id": 1, "name": "P", "widgets": []}
    assert _shape_page(old_snap)["custom_width"] is None
