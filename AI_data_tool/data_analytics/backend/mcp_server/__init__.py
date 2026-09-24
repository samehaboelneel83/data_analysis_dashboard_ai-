"""datalytics MCP server — exposes datalytics's data and analytics to AI agents.

A thin, authenticated client of the datalytics HTTP API (`client.py`) wrapped as MCP
tools (`server.py`). Because every call goes through the same API a human uses, the
agent inherits all of datalytics's security: org isolation, row-level security,
per-report capability tiers and secret encryption. The agent can only ever see and do
what its token's user can.
"""
