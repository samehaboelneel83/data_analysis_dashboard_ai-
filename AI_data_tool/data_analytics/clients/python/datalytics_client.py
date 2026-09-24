"""Datalytics semantic-layer client: governed frames in a notebook.

    from datalytics_client import Datalytics
    dl = Datalytics("https://datalytics.example.com", api_key="dl_...")
    dl.datasets()                                   # what you may read
    df = dl.frame(120, columns=["date", "region", "revenue"])
    by_region = dl.query(120, dimensions=["region"],
                         measures=["Margin %", {"column": "revenue", "agg": "sum"}])

Every call runs AS the user who issued the API key: their row-level security,
column security, the dataset's prep, calculated columns and named measures,
its export policy and sensitivity label -- exactly what their dashboards show.
Needs `requests` and `pandas`.
"""
from __future__ import annotations

import pandas as pd
import requests

__all__ = ["Datalytics", "DatalyticsError"]


class DatalyticsError(RuntimeError):
    """The server refused; the message is its reason."""


class Datalytics:
    def __init__(self, base_url: str, api_key: str, timeout: float = 120.0):
        self.base = base_url.rstrip("/") + "/api/v1/semantic"
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {api_key}"
        self.timeout = timeout

    def _call(self, method: str, path: str, **kw) -> dict:
        r = self.s.request(method, self.base + path, timeout=self.timeout, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise DatalyticsError(f"{r.status_code}: {detail}")
        return r.json()

    def datasets(self) -> pd.DataFrame:
        """The datasets you may read, with their measures and sensitivity."""
        rows = self._call("GET", "/datasets")["datasets"]
        return pd.DataFrame([{"id": d["id"], "name": d["name"], "sensitivity": d["sensitivity"],
                              "columns": [c["name"] for c in d["columns"]],
                              "measures": [m["name"] for m in d["measures"]]} for d in rows])

    def frame(self, dataset_id: int, columns: list[str] | None = None, page_size: int = 50_000) -> pd.DataFrame:
        """All secured rows, fetched page by page."""
        parts, offset = [], 0
        while offset is not None:
            params = {"offset": offset, "limit": page_size}
            if columns:
                params["columns"] = ",".join(columns)
            page = self._call("GET", f"/datasets/{dataset_id}/rows", params=params)
            parts.append(pd.DataFrame(page["rows"], columns=page["columns"]))
            offset = page.get("next_offset")
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def query(self, dataset_id: int, dimensions: list[str] | None = None,
              measures: list | None = None, filters: list[dict] | None = None,
              limit: int | None = None) -> pd.DataFrame:
        """Group by `dimensions` and aggregate `measures` -- named dataset
        measures (strings) or {"column", "agg"} with agg in sum/avg/min/max/
        count/countd/median -- server-side, under your security."""
        body = {"dataset_id": dataset_id, "dimensions": dimensions or [], "measures": measures or [],
                "filters": filters or [], "format": "json"}
        if limit:
            body["limit"] = limit
        res = self._call("POST", "/query", json=body)
        return pd.DataFrame(res["rows"], columns=res["columns"])
