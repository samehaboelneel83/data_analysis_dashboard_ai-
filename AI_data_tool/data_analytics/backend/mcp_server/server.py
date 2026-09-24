"""datalytics MCP server (stdio transport).

Exposes datalytics's read/query capabilities to any MCP-capable agent. Configure it in
the agent's MCP config with two environment variables:

    DATALYTICS_URL    base API URL   (default http://localhost:8000/api/v1)
    DATALYTICS_TOKEN  a bearer token (from POST /auth/login)

The agent then acts AS that token's user — org isolation, row-level security and
report capabilities all apply, so it can never see or do more than that user can.

Run:  python -m mcp_server.server
"""
import atexit
import os
import threading

from mcp.server.fastmcp import FastMCP

from .client import DatalyticsClient

mcp = FastMCP("datalytics")

# Lazily-created, process-wide client singleton. Every tool call used to build a new
# DatalyticsClient (and its own httpx connection pool) per invocation; now the first
# call constructs it (reading DATALYTICS_TOKEN/DATALYTICS_URL exactly once) and every
# later call reuses it. `_client_lock` makes the once-init race-safe if the MCP
# transport ever dispatches tool calls concurrently.
_client_instance: DatalyticsClient | None = None
_client_lock = threading.Lock()


def _client() -> DatalyticsClient:
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:  # re-check: another thread may have won the race
                token = os.environ.get("DATALYTICS_TOKEN", "")
                if not token:
                    raise RuntimeError("Set DATALYTICS_TOKEN to a datalytics bearer token")
                base = os.environ.get("DATALYTICS_URL", "http://localhost:8000/api/v1")
                instance = DatalyticsClient(base, token)
                atexit.register(instance.close)
                _client_instance = instance
    return _client_instance


def reset_client() -> None:
    """Test hook: drop the cached client so the next `_client()` call builds a fresh
    one (and re-reads DATALYTICS_TOKEN/DATALYTICS_URL). Not used by the server itself."""
    global _client_instance
    with _client_lock:
        _client_instance = None


@mcp.tool()
def list_datasets() -> list[dict]:
    """List the datasets the current user can access (id, name, row/column counts)."""
    return _client().list_datasets()


@mcp.tool()
def get_dataset_schema(dataset_id: int) -> dict:
    """Get one dataset's columns (name and type) so you know what you can query."""
    return _client().get_dataset_schema(dataset_id)


@mcp.tool()
def query_data(dataset_id: int, dimension: str | None = None, measure: str | None = None,
               aggregation: str = "sum", dimension2: str | None = None,
               filters: list[dict] | None = None, widget_type: str = "bar",
               limit: int = 1000) -> dict:
    """Aggregate a dataset and return the result rows.

    dimension  - the column to group by (e.g. 'region'); omit for a raw table.
    measure    - the numeric column to aggregate (e.g. 'revenue').
    aggregation- sum | avg | min | max | count | median (default sum).
    dimension2 - a second grouping for a crosstab.
    filters    - list of {column, op, value}; op in eq/neq/gt/gte/lt/lte/in/like.
    Row-level security applies, so you only receive rows this user may see.
    """
    return _client().query_data(
        dataset_id, dimension=dimension, dimension2=dimension2, measure=measure,
        aggregation=aggregation, filters=filters, widget_type=widget_type, limit=limit)


@mcp.tool()
def list_reports() -> list[dict]:
    """List the reports the current user can access."""
    return _client().list_reports()


@mcp.tool()
def list_data_sources() -> list[dict]:
    """List the live data-source connections (secrets are redacted)."""
    return _client().list_data_sources()


@mcp.tool()
def list_connectors() -> list[dict]:
    """List the connector catalog — the kinds of database/source that can be connected."""
    return _client().list_connectors()


@mcp.tool()
def create_report(name: str, dataset_id: int | None = None, description: str | None = None) -> dict:
    """Create a report. It is created with a first page; use the returned page id with
    add_widget to place visuals on it."""
    return _client().create_report(name, dataset_id=dataset_id, description=description)


@mcp.tool()
def add_widget(report_id: int, page_id: int, widget_type: str, config: dict,
               title: str | None = None, layout: dict | None = None) -> dict:
    """Add a widget to a report page.

    widget_type - bar | line | pie | donut | kpi | table | area | scatter | ... .
    config      - same shape as query_data: {dimension, measure, aggregation, filters}.
    Get a page_id from create_report (its first page) or get_report.
    """
    return _client().add_widget(report_id, page_id, widget_type, config, title=title, layout=layout)


@mcp.tool()
def create_data_source(name: str, type: str, config: dict) -> dict:
    """Connect a data source. `type` is a connector key (see list_connectors); `config`
    holds host/database/username/password etc. Secrets are encrypted at rest."""
    return _client().create_data_source(name, type, config)


def main() -> None:
    mcp.run()   # stdio transport


if __name__ == "__main__":
    main()
