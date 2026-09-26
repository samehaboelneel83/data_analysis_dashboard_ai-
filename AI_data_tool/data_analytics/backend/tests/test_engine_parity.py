"""E04: the three engines give the same answer after aggregation.

docs/EVALUATION_ORDER.md fixes one order for every engine. The pushdown
engines (DuckDB over the file, DirectQuery over the source) aggregate in SQL
and hand the import shaper one row per group -- and, for DirectQuery, only the
top `limit` groups. Whatever the shaper then does over EVERY group, or over the
raw rows, came out different: HAVING and percent-of-total over the page only,
suppression counting one row per group, dates grouped raw and then
re-bucketed, a drill filter compared to the raw date, a box plot's quartiles
over group totals. Each case below runs on all three engines and must equal
the import (pandas) answer row for row.
"""
import sqlite3
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from app.core.config import settings
from app.services import widget_data as wd
from app.services.direct_query import run_direct_query

# 70 days over three months (more distinct dates than the default limit of
# 50), three regions of different sizes.
_START = date(2024, 1, 1)
ROWS = [((_START + timedelta(days=i)).isoformat(),
         ("North", "South", "East")[i % 3 if i % 5 else 0],
         float((i * 37) % 101) + 1)
        for i in range(70)]
COLS = ["day", "region", "amount"]


@pytest.fixture(autouse=True)
def _clean():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


@pytest.fixture
def data(tmp_path):
    frame = pd.DataFrame(ROWS, columns=COLS)
    csv = tmp_path / "parity.csv"
    frame.to_csv(csv, index=False)
    db = tmp_path / "parity.db"
    con = sqlite3.connect(db)
    frame.to_sql("t", con, index=False)
    con.close()
    return {"csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)},
            "dataset": SimpleNamespace(source_table="t", source_query=None,
                                       columns=[SimpleNamespace(name="day", dtype="datetime"),
                                                SimpleNamespace(name="region", dtype="string"),
                                                SimpleNamespace(name="amount", dtype="number")])}


def _run(engine, data, config, widget_type, monkeypatch):
    if engine == "directquery":
        return run_direct_query(data["source"], data["dataset"], dict(config),
                                widget_type=widget_type, cache_ttl_seconds=0)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", engine == "duckdb")
    wd.clear_widget_data_cache()
    return wd.get_widget_data(data["csv"], dict(config), widget_type=widget_type, use_cache=False)


def _rows(result):
    out = []
    for r in result.get("rows") or []:
        out.append({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    return out


CASES = [
    ("date buckets, average", "bar",
     {"dimension": "day", "dimension_granularity": "month", "measure": "amount", "aggregation": "avg"}),
    ("percent of total over two shown", "bar",
     {"dimension": "region", "measure": "amount", "aggregation": "sum",
      "quick_calc": "percent_of_total", "limit": 2}),
    ("HAVING on the group total", "bar",
     {"dimension": "region", "measure": "amount", "aggregation": "sum",
      "having": [{"op": "gt", "value": 1000}]}),
    ("small-cell suppression", "bar",
     {"dimension": "region", "measure": "amount", "aggregation": "sum", "suppress_below": 20}),
    ("a drill filter on a month", "bar",
     {"dimension": "region", "measure": "amount", "aggregation": "sum",
      "filters": [{"column": "day", "op": "eq", "value": "2024-02", "granularity": "month"}]}),
    ("custom category order", "bar",
     {"dimension": "region", "measure": "amount", "aggregation": "sum",
      "sort_custom": ["South", "East", "North"]}),
    ("a box plot", "box_plot", {"dimension": "region", "measure": "amount"}),
]


@pytest.mark.parametrize("engine", ["duckdb", "directquery"])
@pytest.mark.parametrize("name,widget_type,config", CASES, ids=[c[0] for c in CASES])
def test_the_pushdown_engines_agree_with_import(engine, name, widget_type, config, data, monkeypatch):
    expected = _run("pandas", data, config, widget_type, monkeypatch)
    assert expected.get("rows"), f"{name}: the import engine returned nothing to compare"
    got = _run(engine, data, config, widget_type, monkeypatch)
    assert _rows(got) == _rows(expected), f"{name} on {engine}"


def test_every_test_the_evaluation_order_cites_exists():
    """docs/EVALUATION_ORDER.md names the tests that pin each step. A renamed
    or deleted test must not leave the document citing evidence that is gone."""
    import glob
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    doc = (root.parent / "docs" / "EVALUATION_ORDER.md").read_text(encoding="utf-8")
    refs = set(re.findall(r"`(test_[A-Za-z0-9_*]+\.py)(?:::(\w+))?`", doc))
    assert refs
    missing = []
    for name, cls in sorted(refs):
        files = glob.glob(str(root / "tests" / name))
        found = bool(files) and (not cls or any(
            re.search(rf"^(class|def) {cls}\b", Path(f).read_text(encoding="utf-8"), re.M) for f in files))
        if not found:
            missing.append(f"{name}::{cls}" if cls else name)
    assert not missing, f"docs/EVALUATION_ORDER.md cites tests that do not exist: {missing}"
