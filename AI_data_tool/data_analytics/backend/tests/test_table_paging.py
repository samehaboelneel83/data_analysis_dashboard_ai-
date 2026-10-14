"""A raw table reads its rows a page at a time.

Dashboard 213's "All data" table downloaded 10,000 rows (2.9 MB) on every
open and every filter change, and on a live source those were a RANDOM sample
of 112k rows. A page asks for the rows it can show; pages must add up to the
whole table, in a stable order, with the exact count and true totals.
"""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from app.models.models import DataSource, Dataset, DatasetColumn
from app.services.widget_data import clear_widget_data_cache, shape_series, table_page


@pytest.fixture(autouse=True)
def _clean():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


def test_page_is_clamped():
    assert table_page({"page": {"offset": -5, "size": 99999}}) == (0, 1000)
    assert table_page({}) is None
    assert table_page({"page": {"offset": "x"}}) is None


def test_shaper_pages_add_up_to_the_table():
    df = pd.DataFrame({"a": range(450), "b": np.arange(450) * 2.0})
    pages = [shape_series(df, {"page": {"offset": o, "size": 200}, "show_totals": True}) for o in (0, 200, 400)]
    rows = [r for p in pages for r in p["rows"]]
    assert [r[0] for r in rows] == list(range(450))
    assert all(p["total"] == 450 and p["page"]["total"] == 450 for p in pages)
    assert not pages[0]["truncation"]["applied"]
    assert pages[0]["totals"] == [sum(range(450)), sum(range(450)) * 2.0]   # every row, not the page


def test_no_page_keeps_the_old_shape():
    df = pd.DataFrame({"a": range(50)})
    out = shape_series(df, {})
    assert len(out["rows"]) == 50 and "page" not in out


# ── through the endpoint ────────────────────────────────────────────────────

N = 2345


@pytest.fixture
def orders(tmp_path):
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"id": np.arange(N), "region": rng.choice(["n", "s", "e", "w"], N),
                       "amount": np.round(rng.uniform(1, 500, N), 2), "secret": "x"})
    csv = tmp_path / "o.csv"
    df.to_csv(csv, index=False)
    db = tmp_path / "o.db"
    c = sqlite3.connect(str(db))
    df.to_sql("orders", c, index=False)
    c.close()
    return df, str(csv), str(db)


COLS = (("id", "numeric"), ("region", "categorical"), ("amount", "numeric"), ("secret", "text"))


async def _import(db, org, path):
    ds = Dataset(name="o", filename=path, org_id=org.id, mode="import")
    db.add(ds); await db.flush()
    for c, t in COLS:
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _live(db, org, path):
    src = DataSource(name="live", type="sqlite", config={"filepath": path}, org_id=org.id)
    db.add(src); await db.flush()
    ds = Dataset(name="o", org_id=org.id, mode="directquery", data_source_id=src.id, source_table="orders")
    db.add(ds); await db.flush()
    for c, t in COLS:
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _page(client, headers, ds_id, offset, size=500, **cfg):
    r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", headers=headers["a"],
                          json={"widget_type": "table",
                                "config": {"aggregation": "none", "page": {"offset": offset, "size": size}, **cfg}})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("mode", ["import", "live"])
async def test_pages_are_the_whole_table_once_each(client, db_session, two_orgs, auth_headers, orders, mode):
    df, csv, db = orders
    ds = await (_import if mode == "import" else _live)(db_session, two_orgs["a"]["org"], csv if mode == "import" else db)
    seen, off = [], 0
    while True:
        p = await _page(client, auth_headers, ds.id, off, columns=["id", "region", "amount"])
        assert p["total"] == N and not p.get("sampled")
        seen += [r[0] for r in p["rows"]]
        off += len(p["rows"])
        if off >= N or not p["rows"]:
            break
    assert sorted(seen) == list(range(N)) and len(seen) == N      # none skipped, none twice


@pytest.mark.parametrize("mode", ["import", "live"])
async def test_sort_and_filter_apply_to_the_whole_table(client, db_session, two_orgs, auth_headers, orders, mode):
    df, csv, db = orders
    ds = await (_import if mode == "import" else _live)(db_session, two_orgs["a"]["org"], csv if mode == "import" else db)
    p = await _page(client, auth_headers, ds.id, 0, size=5, columns=["id", "amount"],
                    sort_keys=[{"col": "amount", "dir": "desc"}],
                    filters=[{"column": "region", "op": "eq", "value": "n"}], show_totals=True)
    sel = df[df["region"] == "n"]
    assert p["total"] == len(sel)
    assert [r[1] for r in p["rows"]] == sorted(sel["amount"], reverse=True)[:5]
    assert p["totals"][1] == pytest.approx(sel["amount"].sum())


def test_a_live_page_never_shows_a_hidden_column(orders):
    from types import SimpleNamespace
    from app.services import direct_query
    _, _, db = orders
    ds = SimpleNamespace(source_table="orders", source_query=None,
                         columns=[SimpleNamespace(name=c, dtype=t) for c, t in COLS])
    out = direct_query._run_table_page({"type": "sqlite", "filepath": db}, ds,
                                       {"page": {"offset": 0, "size": 3}}, None, ["secret"])
    assert out["columns"] == ["id", "region", "amount"] and out["total"] == N and len(out["rows"]) == 3
