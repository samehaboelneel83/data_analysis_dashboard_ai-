"""A page background image, with widgets that can let it show through.

The SAS page this was measured against is a photograph with a bar chart, two
big numbers and a line chart floating on top of it — no card, no border, no
panel behind any of them. Two things are needed and neither existed: somewhere
to put the image, and a way for an object to stop drawing its own background.

The URL rule is the one this codebase already applies to every author-typed
address (image widget, web content, custom visual, precision container): http(s)
or a same-origin path, never `javascript:` or `data:`. An author-supplied URL is
a string from a person, and the only safe thing to do with one is to refuse
anything that is not a plain fetchable address.
"""
import pytest


async def _report_page(client, headers):
    r = await client.post("/api/v1/reports", json={"name": "Backdrop"}, headers=headers)
    rid = r.json()["id"]
    page_id = (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"][0]["id"]
    return rid, page_id


@pytest.mark.asyncio
async def test_a_page_carries_a_background_image(client, auth_headers):
    rid, page_id = await _report_page(client, auth_headers["a"])
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                           json={"background_url": "https://cdn.example/shop.jpg"},
                           headers=auth_headers["a"])
    assert r.status_code == 200, r.text

    page = (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["pages"][0]
    assert page["background_url"] == "https://cdn.example/shop.jpg"


@pytest.mark.asyncio
async def test_a_same_origin_path_is_allowed(client, auth_headers):
    # The demo content and anything uploaded into this app is served from here.
    rid, page_id = await _report_page(client, auth_headers["a"])
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                           json={"background_url": "/uploads/shop.jpg"},
                           headers=auth_headers["a"])
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox",
])
async def test_a_page_background_must_be_a_fetchable_address(client, auth_headers, bad):
    rid, page_id = await _report_page(client, auth_headers["a"])
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                           json={"background_url": bad}, headers=auth_headers["a"])
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_the_background_can_be_cleared(client, auth_headers):
    rid, page_id = await _report_page(client, auth_headers["a"])
    await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                       json={"background_url": "https://cdn.example/shop.jpg"},
                       headers=auth_headers["a"])
    r = await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                           json={"background_url": ""}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    page = (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["pages"][0]
    assert not page["background_url"]


@pytest.mark.asyncio
async def test_editing_something_else_leaves_the_background_alone(client, auth_headers):
    # PATCH is partial everywhere else in this router; a page rename must not
    # silently drop the backdrop.
    rid, page_id = await _report_page(client, auth_headers["a"])
    await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                       json={"background_url": "https://cdn.example/shop.jpg"},
                       headers=auth_headers["a"])
    await client.patch(f"/api/v1/reports/{rid}/pages/{page_id}",
                       json={"name": "Renamed"}, headers=auth_headers["a"])
    page = (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["pages"][0]
    assert page["name"] == "Renamed"
    assert page["background_url"] == "https://cdn.example/shop.jpg"
