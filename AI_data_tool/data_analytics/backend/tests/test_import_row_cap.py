"""Hardening task 2.3: the import/pandas path is bounded.

DirectQuery has always had `DEFAULT_ROW_CAP`; the import path had nothing, so a
single widget could materialise an entire dataset to answer a five-row question.
Measured 2026-08-28: a 406 MB / 2M-row / 30-column CSV costs ~1.8 GB of RSS
there, and every concurrent render holds its own frame.

The behaviour these tests pin, in order of importance:

  1. Over the cap FAILS. It does not truncate. A truncated frame would produce
     totals over an arbitrary subset with no way to say so in the result -- a
     confident wrong number, which is worse than an error.
  2. The cap is ON by default (2,000,000 since 2026-08-29). 0 disables it,
     which is what an operator with the memory to spare sets deliberately.
  3. The error names the cap AND the actual size, so an operator can raise
     it deliberately rather than guess.
  4. A reader sees 413 with that message -- not a 500, and never a
     truncated frame presented as a complete one.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import widget_data as wd
from app.services.widget_data import ImportRowCapExceeded, get_widget_data


CONFIG = {"dimension": "region", "measure": "sales", "aggregation": "sum"}


@pytest.fixture
def csv_500(tmp_path):
    """500 rows across 5 regions."""
    path = tmp_path / "d.csv"
    pd.DataFrame({
        "region": ["North", "South", "East", "West", "Central"] * 100,
        "sales": list(range(500)),
    }).to_csv(path, index=False)
    return str(path)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    # The cap guards the PANDAS path: it exists because that path materialises
    # the whole frame. The DuckDB path never does, so it is deliberately exempt
    # (see TestDuckDBIsExempt below). These tests pin the cap itself, so they
    # pin the engine too rather than inheriting whatever the environment sets.
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


class TestTheShippedDefault:
    def test_the_cap_is_on_by_default(self):
        """Changed from 0 (off) to 2M rows on 2026-08-29.

        The original default was argued as "a memory ceiling on by default
        would start refusing datasets that render fine today", which is true
        and turned out to be the weaker half of the trade. Uncapped, ONE
        oversized upload exhausts the container for every tenant sharing it,
        and the failure arrives as an OOM kill with no attribution -- nobody
        can tell which dataset did it. A 413 naming the dataset size and the
        limit is a worse outcome for one user and a far better one for
        everybody else.

        2M rows is roughly where the measured ~1.8 GB-per-render cost stops
        being survivable on a shared box. An operator with the memory can still
        set 0 and get the old behaviour exactly.
        """
        assert settings.import_row_cap == 2_000_000

    def test_disabled_cap_loads_any_size(self, csv_500, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 0)
        result = get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)
        assert len(result["rows"]) == 5


class TestEnforcement:
    def test_over_the_cap_raises(self, csv_500, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 100)
        with pytest.raises(ImportRowCapExceeded):
            get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)

    def test_under_the_cap_is_untouched(self, csv_500, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 1000)
        result = get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)
        assert len(result["rows"]) == 5

    def test_boundary_is_value_pinned(self, csv_500, monkeypatch):
        """Exactly at the cap passes; one below it fails. Pins which comparison
        is used, so a later `>=` typo is a test failure rather than a silent
        off-by-one that rejects a dataset of exactly the allowed size."""
        monkeypatch.setattr(settings, "import_row_cap", 500)
        get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)

        monkeypatch.setattr(settings, "import_row_cap", 499)
        with pytest.raises(ImportRowCapExceeded):
            get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)

    def test_it_refuses_rather_than_truncating(self, csv_500, monkeypatch):
        """The whole point. A truncated result would look like a valid answer."""
        monkeypatch.setattr(settings, "import_row_cap", 0)
        full = get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)
        full_total = sum(r["value"] for r in full["rows"])

        monkeypatch.setattr(settings, "import_row_cap", 100)
        with pytest.raises(ImportRowCapExceeded):
            get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)

        # And the uncapped total is still what it was -- no partial state left behind.
        monkeypatch.setattr(settings, "import_row_cap", 0)
        wd.clear_widget_data_cache()
        again = get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)
        assert sum(r["value"] for r in again["rows"]) == full_total


class TestDuckDBIsExempt:
    """An eligible DuckDB query is not subject to the cap, on purpose.

    The cap exists because the pandas path materialises the entire frame; that
    is the thing being bounded. DuckDB streams the file and materialises only
    the grouped result -- measured 1545 MB -> 60 MB on a 422 MB source -- so
    applying a row cap there would refuse a query whose memory cost is already
    bounded, for no benefit.

    Pinned rather than left emergent: someone reading `import_row_cap` should
    find this stated, and someone changing the gate should break a test rather
    than silently start refusing large datasets that render fine.
    """

    def test_pushdown_answers_a_dataset_over_the_cap(self, csv_500, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 100)
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        result = get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)
        assert len(result["rows"]) == 5
        assert result["total"] == 500

    def test_an_ineligible_config_still_hits_the_cap(self, csv_500, monkeypatch):
        """Enabling pushdown must not disable the cap for queries that still
        take the pandas path -- otherwise the flag would quietly remove a
        memory bound the operator deliberately set."""
        monkeypatch.setattr(settings, "import_row_cap", 100)
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        with pytest.raises(ImportRowCapExceeded):
            # A NEGATED rule. A positive RLS rule became DuckDB-eligible on
            # 2026-09-12 (test_duck_agg_governed.py); `!=` stays on pandas
            # because SQL drops NULL rows under it and pandas keeps them.
            get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False,
                            rls_filter_expr="region != 'West'")


class TestTheMessage:
    def test_names_the_cap_and_the_actual_size(self, csv_500, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 100)
        with pytest.raises(ImportRowCapExceeded) as exc:
            get_widget_data(csv_500, CONFIG, widget_type="bar", use_cache=False)
        message = str(exc.value)
        assert "500" in message, "must say how big the dataset actually is"
        assert "100" in message, "must say what the cap is"
        assert "import_row_cap" in message, "must name the setting to change"

class TestWhatTheReaderActuallySees:
    """The service raising is half the behaviour; the other half is the status.

    Everything above this class tests `_enforce_import_row_cap` directly. The
    mapping to 413 lives in `routers/widget_data.py` and had no test, which is
    the shape that has bitten this repo before: the service layer correct and
    the endpoint still answering something else. A 500 here would send the
    operator to our logs for a limit they configured."""

    @pytest.mark.asyncio
    async def test_a_dataset_over_the_cap_is_a_413_naming_both_numbers(
            self, client, auth_headers, db_session, two_orgs, tmp_path,
            monkeypatch):
        from app.models.models import Dataset, DatasetColumn

        monkeypatch.setattr(settings, "import_row_cap", 3)
        path = tmp_path / "big.csv"
        pd.DataFrame({"region": list("abcdefghij"),
                      "amount": range(10)}).to_csv(path, index=False)
        ds = Dataset(name="Too big", filename=str(path), mode="import",
                     org_id=two_orgs["a"]["org"].id)
        db_session.add(ds)
        await db_session.flush()
        for c in ("region", "amount"):
            db_session.add(DatasetColumn(dataset_id=ds.id, name=c,
                                         dtype="categorical"))
        await db_session.commit()
        await db_session.refresh(ds)

        resp = await client.post(
            f"/api/v1/datasets/{ds.id}/widget-data",
            json={"widget_type": "table",
                  "config": {"columns": ["region", "amount"]},
                  "calculated_columns": [], "parameters": {}},
            headers=auth_headers["a"])

        assert resp.status_code == 413, resp.text
        body = resp.text
        assert "10" in body, "the actual size is missing"
        assert "3" in body, "the configured cap is missing"
        assert "internal server error" not in body.lower()
