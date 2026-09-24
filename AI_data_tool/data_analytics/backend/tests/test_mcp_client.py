"""The datalytics MCP server's API client (mcp_server/client.py).

Tested against an httpx mock transport so the tool logic — endpoints called, request
shaping, response trimming, error surfacing — is pinned without a running server.
"""
import httpx
import pytest

from mcp_server.client import DatalyticsClient, DatalyticsError


def _client(handler) -> DatalyticsClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="http://api/api/v1", transport=transport,
                        headers={"Authorization": "Bearer t"})
    return DatalyticsClient("http://api/api/v1", "t", client=http)


def test_list_datasets_trims_to_the_agent_facing_fields():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/datasets")
        assert req.headers["Authorization"] == "Bearer t"        # auth carried through
        return httpx.Response(200, json=[{"id": 1, "name": "Sales", "row_count": 10,
                                          "col_count": 3, "description": "d", "filename": "x.csv"}])
    out = _client(handler).list_datasets()
    assert out == [{"id": 1, "name": "Sales", "rows": 10, "columns": 3, "description": "d"}]


def test_get_dataset_schema_returns_columns_with_types():
    def handler(req):
        assert req.url.path.endswith("/datasets/7")
        return httpx.Response(200, json={"id": 7, "name": "S", "columns": [
            {"name": "region", "dtype": "text"}, {"name": "revenue", "dtype": "numeric"}],
            "calculated_columns": [{"name": "margin"}]})
    schema = _client(handler).get_dataset_schema(7)
    assert schema["columns"] == [{"name": "region", "type": "text"}, {"name": "revenue", "type": "numeric"}]
    assert schema["calculated_columns"] == ["margin"]


def test_query_data_builds_the_widget_config_and_posts_it():
    seen = {}

    def handler(req):
        assert req.method == "POST" and req.url.path.endswith("/datasets/88/widget-data")
        import json
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"type": "series", "rows": [{"name": "US", "value": 5}]})

    out = _client(handler).query_data(88, dimension="region", measure="revenue",
                                      aggregation="avg", filters=[{"column": "region", "op": "eq", "value": "US"}])
    assert out["rows"][0]["value"] == 5
    assert seen["widget_type"] == "bar"
    assert seen["config"] == {"aggregation": "avg", "limit": 1000, "dimension": "region",
                              "measure": "revenue", "filters": [{"column": "region", "op": "eq", "value": "US"}]}


def test_an_api_error_surfaces_the_server_detail():
    def handler(req):
        return httpx.Response(403, json={"detail": "Not allowed"})
    with pytest.raises(DatalyticsError) as e:
        _client(handler).list_reports()
    assert "403" in str(e.value) and "Not allowed" in str(e.value)


def test_list_connectors_and_data_sources_trim_their_fields():
    def handler(req):
        if req.url.path.endswith("/data-sources/connectors"):
            return httpx.Response(200, json=[{"key": "postgresql", "label": "PostgreSQL",
                                              "category": "PostgreSQL-compatible", "config_fields": []}])
        return httpx.Response(200, json=[{"id": 3, "name": "PG", "type": "postgresql",
                                          "config": {"password": "__SECRET_UNCHANGED__"}}])
    c = _client(handler)
    assert c.list_connectors() == [{"key": "postgresql", "label": "PostgreSQL", "category": "PostgreSQL-compatible"}]
    assert c.list_data_sources() == [{"id": 3, "name": "PG", "type": "postgresql"}]   # no config/secret leaks out


def test_create_report_posts_and_returns_the_first_page():
    def handler(req):
        assert req.method == "POST" and req.url.path.endswith("/reports")
        import json
        assert json.loads(req.content) == {"name": "Q4", "dataset_id": 88}
        return httpx.Response(201, json={"id": 5, "name": "Q4",
                                         "pages": [{"id": 50, "name": "Page 1", "widgets": []}]})
    out = _client(handler).create_report("Q4", dataset_id=88)
    assert out == {"id": 5, "name": "Q4", "pages": [{"id": 50, "name": "Page 1"}]}


def test_add_widget_posts_to_the_page_and_trims_the_result():
    def handler(req):
        assert req.method == "POST" and req.url.path.endswith("/reports/5/pages/50/widgets")
        import json
        body = json.loads(req.content)
        assert body["widget_type"] == "bar" and body["config"]["measure"] == "revenue"
        return httpx.Response(201, json={"id": 99, "widget_type": "bar", "title": "Rev", "config": {}})
    out = _client(handler).add_widget(5, 50, "bar", {"dimension": "region", "measure": "revenue"}, title="Rev")
    assert out == {"id": 99, "widget_type": "bar", "title": "Rev"}


def test_create_data_source_never_returns_the_secret():
    def handler(req):
        assert req.method == "POST" and req.url.path.endswith("/data-sources")
        return httpx.Response(200, json={"id": 7, "name": "PG", "type": "postgresql",
                                         "config": {"password": "__SECRET_UNCHANGED__"}})
    out = _client(handler).create_data_source("PG", "postgresql", {"host": "h", "password": "p"})
    assert out == {"id": 7, "name": "PG", "type": "postgresql"}   # config/secret not surfaced
