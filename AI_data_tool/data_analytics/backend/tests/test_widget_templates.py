"""Object templates: save a configured widget by name and reuse it org-wide."""
import pytest


@pytest.mark.asyncio
async def test_create_list_and_delete_roundtrip(client, auth_headers):
    body = {"name": "Sales bar", "widget_type": "bar",
            "config": {"dimension": "region", "measure": "sales", "series_patterns": True}}
    r = await client.post("/api/v1/widget-templates", json=body, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["widget_type"] == "bar"
    assert r.json()["config"]["dimension"] == "region"

    lst = await client.get("/api/v1/widget-templates", headers=auth_headers["a"])
    assert lst.status_code == 200
    assert any(t["id"] == tid and t["name"] == "Sales bar" for t in lst.json())

    d = await client.delete(f"/api/v1/widget-templates/{tid}", headers=auth_headers["a"])
    assert d.status_code == 204
    lst2 = await client.get("/api/v1/widget-templates", headers=auth_headers["a"])
    assert all(t["id"] != tid for t in lst2.json())


@pytest.mark.asyncio
async def test_reserved_and_placement_keys_do_not_travel(client, auth_headers):
    body = {"name": "T", "widget_type": "table",
            "config": {"dimension": "region", "__export_policy": "deny",
                       "container_id": 7, "table_banding": True}}
    r = await client.post("/api/v1/widget-templates", json=body, headers=auth_headers["a"])
    cfg = r.json()["config"]
    assert "__export_policy" not in cfg      # reserved keys stripped
    assert "container_id" not in cfg          # placement does not travel
    assert cfg["table_banding"] is True       # real formatting is kept


@pytest.mark.asyncio
async def test_templates_are_org_scoped(client, auth_headers):
    r = await client.post("/api/v1/widget-templates",
                          json={"name": "Only A", "widget_type": "pie", "config": {}},
                          headers=auth_headers["a"])
    tid = r.json()["id"]
    # org B cannot see or delete org A's template
    lst_b = await client.get("/api/v1/widget-templates", headers=auth_headers["b"])
    assert all(t["id"] != tid for t in lst_b.json())
    d = await client.delete(f"/api/v1/widget-templates/{tid}", headers=auth_headers["b"])
    assert d.status_code == 404


@pytest.mark.asyncio
async def test_blank_name_rejected(client, auth_headers):
    r = await client.post("/api/v1/widget-templates",
                          json={"name": "   ", "widget_type": "bar", "config": {}},
                          headers=auth_headers["a"])
    assert r.status_code == 400
