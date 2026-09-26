"""A DirectQuery filter names a column; that name is spliced into SQL as an
identifier. Values are bound parameters, but an identifier cannot be, so the
only defence is that no name reaches the database unless it is a real column
of the dataset. The aggregate path checked that (`_validate_columns`); the
row-fetch path -- tables, KPIs, cards, every Top-N and every fallback -- did
not, and `_quote` did not escape a double quote inside the name. A filter
column could therefore close the identifier and append its own SQL.
"""
import sqlite3

import pandas as pd
import pytest

from app.core.security import create_access_token
from app.models.models import DataSource, Dataset, DatasetColumn
from app.services import direct_query

SECRET = "TOPSECRET-ROW"


@pytest.fixture(autouse=True)
def _no_cache():
    from app.services.widget_data import clear_widget_data_cache
    clear_widget_data_cache()
    yield


async def _dq(db_session, org_id, tmp_path):
    db = tmp_path / "dq.db"
    con = sqlite3.connect(db)
    pd.DataFrame({"region": ["North", "South"], "amount": [1, 2]}).to_sql("sales", con, index=False)
    pd.DataFrame({"s": [SECRET]}).to_sql("secret", con, index=False)
    con.close()
    src = DataSource(name="dq", type="sqlite", config={"filepath": str(db)}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="dq", org_id=org_id, mode="directquery", data_source_id=src.id, source_table="sales")
    db_session.add(ds)
    await db_session.flush()
    for c in ("region", "amount"):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="string"))
    await db_session.commit()
    return ds


#: Closes the identifier, then asks a yes/no question of another table: a
#: blind read, one character at a time, of anything the connection can see.
EVIL = 'region" = "region" AND substr((SELECT s FROM secret), 1, 1) = \'T\' AND "amount'


@pytest.mark.parametrize("widget_type,config", [
    ("table", {"columns": ["region", "amount"]}),
    ("kpi", {"measure": "amount", "aggregation": "sum"}),
    ("bar", {"dimension": "region", "measure": "amount", "aggregation": "sum",
             "rank": {"mode": "top", "n": 1}}),
    ("bar", {"dimension": "region", "measure": "amount", "aggregation": "sum"}),
    ("bar", {"dimension": "region"}),
])
async def test_a_filter_column_that_is_not_a_real_column_never_reaches_the_database(
        client, db_session, two_orgs, tmp_path, widget_type, config):
    org = two_orgs["a"]["org"].id
    ds = await _dq(db_session, org, tmp_path)
    # With value 1 the North row comes back exactly when the guess about the
    # secret's first character is right: before the fix, this ran (200).
    cfg = {**config, "filters": [{"column": EVIL, "op": "eq", "value": 1}]}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": widget_type, "config": cfg},
                          headers={"Authorization": f"Bearer {create_access_token(two_orgs['a']['user'].id, org)}"})
    assert SECRET not in r.text, f"{widget_type}: {r.status_code} {r.text[:300]}"
    assert r.status_code in (400, 422), f"{widget_type}: {r.status_code} {r.text[:300]}"


def test_quoting_an_identifier_escapes_an_embedded_quote():
    assert direct_query._quote('a"b') == '"a""b"'
