# Datalytics Python client

Governed data in a notebook (MASTER_PLAN Phase 7.6). Create an API key under
**Settings → API keys**; it acts as you, so a notebook sees exactly the rows,
columns and measures your dashboards show — row-level security, column
security, prep, calculated columns, named measures, export policy and
sensitivity labels all apply. Every call is in the audit log.

```python
from datalytics_client import Datalytics

dl = Datalytics("http://localhost:8000", api_key="dl_...")
dl.datasets()
df = dl.frame(120)                                    # secured rows
dl.query(120, dimensions=["region"],
         measures=["Share", {"column": "revenue", "agg": "sum"}])
```

Endpoints (Bearer API key or session token):

| Method | Path | What |
|---|---|---|
| GET | `/api/v1/semantic/datasets` | catalog: columns you may see, measures, sensitivity |
| GET | `/api/v1/semantic/datasets/{id}/rows?offset=&limit=&columns=&format=json\|csv` | secured rows, ≤ 50,000 per page |
| POST | `/api/v1/semantic/query` | `{dataset_id, dimensions, measures, filters, limit, format}` |
