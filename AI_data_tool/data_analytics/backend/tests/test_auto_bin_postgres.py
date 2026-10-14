"""Auto-bin against a real Postgres (skipped when none is reachable).

Dashboard 213's delivery date is TEXT in its Postgres source, and
date_trunc(text) does not exist there: the bucket SQL must cast, and any SQL
the source still rejects must fall back to grouping fetched rows -- slower,
never an error on the dashboard.

Point it at a server with AUTO_BIN_PG_PORT (default 5433, the project's
test container); the user/password/database are dl/dl/dl or the container's.
"""
import os

import psycopg2
import pytest
from app.models.models import DataSource, Dataset, DatasetColumn
from app.services import auto_bin
from app.services.widget_data import clear_widget_data_cache

PORT = int(os.environ.get("AUTO_BIN_PG_PORT", "5433"))
CRED = ({"user": "dl", "password": "dl", "dbname": "dl"} if PORT != 5433
        else {"user": "datalytics", "password": "datalytics_secret", "dbname": "datalytics"})
CFG = {"type": "postgresql", "host": "localhost", "port": PORT, "username": CRED["user"],
       "password": CRED["password"], "database": CRED["dbname"]}


def _reachable() -> bool:
    try:
        psycopg2.connect(connect_timeout=2, host="localhost", port=PORT, **CRED).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason=f"no Postgres at localhost:{PORT}")

@pytest.fixture
def pg():
    c = psycopg2.connect(host="localhost", port=PORT, **CRED); c.autocommit = True
    cur = c.cursor()
    cur.execute("drop table if exists auto_bin_o; create table auto_bin_o (d_ts timestamp, d_txt text, d_bad text, price double precision)")
    cur.execute("insert into auto_bin_o select timestamp '2017-01-01' + (i || ' hours')::interval * 7, "
                "to_char(timestamp '2017-01-01' + (i || ' hours')::interval * 7, 'YYYY-MM-DD HH24:MI:SS'), "
                "case when i % 50 = 0 then 'n/a' else to_char(timestamp '2017-01-01' + (i || ' hours')::interval * 7, 'YYYY-MM-DD') end, "
                "(i % 997) * 1.5 from generate_series(1, 3000) i")
    yield
    cur.execute("drop table if exists auto_bin_o")
    c.close()

@pytest.mark.parametrize("col", ["d_ts", "d_txt", "d_bad"])
@pytest.mark.parametrize("gran", ["month", "week", None])
async def test_a_date_column_of_any_storage_draws(client, db_session, two_orgs, auth_headers, pg, col, gran):
    clear_widget_data_cache(); auto_bin.clear_stats_cache()
    org = two_orgs["a"]["org"]
    src = DataSource(name="pg", type="postgresql", config={k: v for k, v in CFG.items() if k != "type"}, org_id=org.id)
    db_session.add(src); await db_session.flush()
    ds = Dataset(name="o", org_id=org.id, mode="directquery", data_source_id=src.id,
                 source_query='SELECT "o"."d_ts", "o"."d_txt", "o"."d_bad", "o"."price" FROM "auto_bin_o" AS "o"')
    db_session.add(ds); await db_session.flush()
    for c, t in (("d_ts", "datetime"), ("d_txt", "datetime"), ("d_bad", "datetime"), ("price", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()
    cfg = {"dimension": col, "measure": "price", "aggregation": "sum", **({"dimension_granularity": gran} if gran else {})}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", headers=auth_headers["a"], json={"widget_type": "line", "config": cfg})
    assert r.status_code == 200, r.text[:300]
    rows = r.json()["rows"]
    # Dirty text dates ("n/a" among ISO dates) defeat the min/max the grain is
    # chosen from, so that column draws its raw days, as it did before
    # auto-bin -- correct, just not grouped. Clean columns are grouped.
    assert 0 < len(rows) <= (150 if col != "d_bad" or gran else 10_000)
    # Every row counted, whichever path answered.
    # (`d_bad`'s "n/a" rows are not dates: a date GRAIN leaves them out, as it always has;
    # drawn raw, "n/a" is one more category.)
    expected = sum((i % 997) * 1.5 for i in range(1, 3001) if col != "d_bad" or not gran or i % 50)
    assert sum(x["value"] for x in rows) == pytest.approx(expected, rel=1e-9)
