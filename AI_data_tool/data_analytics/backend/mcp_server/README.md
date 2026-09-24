# datalytics MCP server

Exposes datalytics's data and analytics to MCP-capable AI agents (Claude Desktop,
Claude Code, and any other MCP client) over the standard **stdio** transport.

It is a thin, authenticated client of the datalytics HTTP API, so the agent inherits
**all** of datalytics's security: org isolation, row-level security (including
`USEREMAIL()` rules), per-report capability tiers and secret encryption. An agent can
only ever see and do what its token's user can — it cannot bypass anything.

## Tools

| Tool | What it does |
|------|--------------|
| `list_datasets` | Datasets the user can access (id, name, row/column counts) |
| `get_dataset_schema` | One dataset's columns (name + type) |
| `query_data` | Aggregate a dataset — group by a dimension, aggregate a measure, filter; returns shaped rows. RLS applies. |
| `list_reports` | Reports the user can access |
| `list_data_sources` | Live connections (secrets redacted) |
| `list_connectors` | The connector catalog |
| `create_report` | Create a report (comes with a first page); returns the page id |
| `add_widget` | Add a widget to a report page (same config shape as `query_data`) |
| `create_data_source` | Connect a data source (secrets encrypted at rest) |

## Configuration

Two environment variables:

- `DATALYTICS_URL` — base API URL (default `http://localhost:8000/api/v1`)
- `DATALYTICS_TOKEN` — a bearer token from `POST /auth/login`

### Claude Desktop / Claude Code

Add to the MCP servers config:

```json
{
  "mcpServers": {
    "datalytics": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/data_analytics/backend",
      "env": {
        "DATALYTICS_URL": "http://localhost:8000/api/v1",
        "DATALYTICS_TOKEN": "<bearer token>"
      }
    }
  }
}
```

Then ask the agent things like *"list my datasets"*, *"what columns does the sales
dataset have?"*, or *"sum revenue by region for dataset 88, top 5"*.

## Requirements

The MCP server runs as its own process, so its dependencies are **separate** from the
backend image (the `mcp` SDK needs a newer `pydantic-settings` than the API pins):

```bash
pip install -r backend/mcp_server/requirements.txt   # mcp + httpx
python -m mcp_server.server
```
