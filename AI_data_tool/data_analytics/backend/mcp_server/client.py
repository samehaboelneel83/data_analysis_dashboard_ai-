"""Authenticated client of the datalytics HTTP API, used by the MCP tools.

Kept free of the MCP SDK so it can be unit-tested on its own against a mock transport.
Every method is a small wrapper over one endpoint; the agent-facing shaping (which
fields to keep, how errors read) lives here so the tool layer stays declarative.
"""
from __future__ import annotations

import httpx


class DatalyticsError(RuntimeError):
    """An API call failed; the message carries the server's own detail so the agent can
    read why (e.g. '403: Platform super-admin privileges required')."""


class DatalyticsClient:
    def __init__(self, base_url: str, token: str, *, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )

    # ── transport ─────────────────────────────────────────────────────────────
    @staticmethod
    def _raise(r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise DatalyticsError(f"{r.status_code}: {detail}")

    def _get(self, path: str, **kw):
        r = self._client.get(path, **kw)
        self._raise(r)
        return r.json()

    def _post(self, path: str, json: dict):
        r = self._client.post(path, json=json)
        self._raise(r)
        return r.json()

    def close(self) -> None:
        """Release the underlying HTTP connection pool. Safe to call once at process
        exit for a client that's reused across many tool calls."""
        self._client.close()

    # ── read ──────────────────────────────────────────────────────────────────
    def list_datasets(self) -> list[dict]:
        """Datasets the user can see, trimmed to what an agent needs to pick one."""
        return [{"id": d["id"], "name": d["name"], "rows": d.get("row_count", 0),
                 "columns": d.get("col_count", 0), "description": d.get("description")}
                for d in self._get("/datasets")]

    def get_dataset_schema(self, dataset_id: int) -> dict:
        """One dataset's columns (name + type), so an agent knows what it can query."""
        d = self._get(f"/datasets/{dataset_id}")
        return {"id": d["id"], "name": d["name"],
                "columns": [{"name": c["name"], "type": c["dtype"]} for c in d.get("columns", [])],
                "calculated_columns": [c.get("name") for c in d.get("calculated_columns", [])]}

    def query_data(self, dataset_id: int, *, dimension: str | None = None,
                   dimension2: str | None = None, measure: str | None = None,
                   aggregation: str = "sum", filters: list[dict] | None = None,
                   widget_type: str = "bar", limit: int = 1000) -> dict:
        """Run an aggregation and return the shaped result — the core capability.

        `filters` is a list of {column, op, value} (op ∈ eq/neq/gt/gte/lt/lte/in/like).
        Row-level security applies server-side, so the agent only ever gets rows its
        user may see."""
        config: dict = {"aggregation": aggregation, "limit": limit}
        if dimension:
            config["dimension"] = dimension
        if dimension2:
            config["dimension2"] = dimension2
        if measure:
            config["measure"] = measure
        if filters:
            config["filters"] = filters
        return self._post(f"/datasets/{dataset_id}/widget-data",
                          {"config": config, "widget_type": widget_type})

    def list_reports(self) -> list[dict]:
        return [{"id": r["id"], "name": r["name"], "description": r.get("description")}
                for r in self._get("/reports")]

    def list_data_sources(self) -> list[dict]:
        """Live connections (secrets are already redacted by the API)."""
        return [{"id": s["id"], "name": s["name"], "type": s["type"]}
                for s in self._get("/data-sources")]

    def list_connectors(self) -> list[dict]:
        """The connector catalog — what kinds of source can be connected."""
        return [{"key": c["key"], "label": c["label"], "category": c["category"]}
                for c in self._get("/data-sources/connectors")]

    # ── write ─────────────────────────────────────────────────────────────────
    def create_report(self, name: str, *, dataset_id: int | None = None,
                      description: str | None = None) -> dict:
        """Create a report. It comes with a first page already; the returned page id is
        where widgets go via add_widget."""
        body: dict = {"name": name}
        if dataset_id is not None:
            body["dataset_id"] = dataset_id
        if description:
            body["description"] = description
        r = self._post("/reports", body)
        return {"id": r["id"], "name": r["name"],
                "pages": [{"id": p["id"], "name": p["name"]} for p in r.get("pages", [])]}

    def add_widget(self, report_id: int, page_id: int, widget_type: str, config: dict,
                   *, title: str | None = None, layout: dict | None = None) -> dict:
        """Add a widget to a report page. `config` follows the same shape as query_data's
        (dimension/measure/aggregation/filters); `widget_type` is bar/line/pie/kpi/table/…"""
        body: dict = {"widget_type": widget_type, "config": config}
        if title:
            body["title"] = title
        if layout:
            body["layout"] = layout
        w = self._post(f"/reports/{report_id}/pages/{page_id}/widgets", body)
        return {"id": w["id"], "widget_type": w["widget_type"], "title": w.get("title")}

    def create_data_source(self, name: str, type: str, config: dict) -> dict:
        """Connect a data source. `type` is a connector key (see list_connectors);
        `config` holds host/database/username/password etc. Secrets are encrypted at
        rest and never returned."""
        s = self._post("/data-sources", {"name": name, "type": type, "config": config})
        return {"id": s["id"], "name": s["name"], "type": s["type"]}
