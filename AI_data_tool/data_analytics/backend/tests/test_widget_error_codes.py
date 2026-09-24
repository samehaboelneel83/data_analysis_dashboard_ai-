"""Every widget-data error carries a code the frontend can act on.

The widget endpoint answered errors as ad hoc HTTPExceptions -- 400 for six
different things, 403 for two, plus a SECOND channel nobody on the frontend
read: a 200 with `{"type": "error", "message": ...}` for a measure that could
not be evaluated, which the widget rendered as an empty chart with the message
discarded.

This makes the code a contract: `{"detail": <unchanged text>, "code": <one of
error_codes.WIDGET_ERROR_CODES>}` on every error the widget path produces,
both channels. `detail` stays a string, so nothing that reads it today
changes; `code` is additive.

Two kinds of pin. The endpoint tests prove specific errors carry their code.
The structural pin proves NO error can be raised without one: a bare
`HTTPException(` in the widget router fails the suite, so the next 400 added
in a hurry is coded or it does not ship.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from app.core.config import settings
from app.models.models import DataSource, Dataset, DatasetColumn
from app.core.widget_errors import CodedHTTPException, widget_error
from app.services.error_codes import WIDGET_ERROR_CODES

ROUTER = Path(__file__).resolve().parents[1] / "app" / "routers" / "widget_data.py"


class TestTheContract:
    def test_the_code_set_is_closed_and_documented(self):
        assert WIDGET_ERROR_CODES >= {
            "parameter", "unsupported", "forbidden_column", "not_found",
            "row_cap", "source_unavailable", "measure_error", "internal", "quota",
        }
        for c in WIDGET_ERROR_CODES:
            assert re.fullmatch(r"[a-z_]+", c), c

    def test_widget_error_refuses_an_unknown_code(self):
        """A typo in a code is a new, undocumented code. Refused at the raise
        site, where the author is looking, not discovered in a log."""
        with pytest.raises(ValueError, match="not a widget error code"):
            widget_error(400, "row_capp", "x")

    def test_widget_error_is_an_httpexception_with_a_code(self):
        e = widget_error(413, "row_cap", "too big")
        assert isinstance(e, CodedHTTPException)
        assert e.status_code == 413 and e.detail == "too big" and e.code == "row_cap"

    def test_no_bare_httpexception_remains_in_the_widget_router(self):
        """The structural pin. Every raise goes through widget_error, so every
        error has a code by construction."""
        src = ROUTER.read_text(encoding="utf-8")
        bare = [m.start() for m in re.finditer(r"\bHTTPException\(", src)]
        lines = [src.count("\n", 0, i) + 1 for i in bare]
        assert not bare, f"bare HTTPException( at lines {lines} -- use widget_error(status, code, msg)"


@pytest.fixture
def import_ds(db_session, two_orgs, tmp_path):
    async def _make(rows=None):
        path = tmp_path / "d.csv"
        pd.DataFrame(rows or {"region": ["N", "S"], "amount": [1.0, 2.0]}).to_csv(path, index=False)
        ds = Dataset(name="D", filename=str(path), org_id=two_orgs["a"]["org"].id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        for c in ("region", "amount"):
            db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db_session.commit()
        await db_session.refresh(ds)
        return ds
    return _make


BAR = {"widget_type": "bar",
       "config": {"dimension": "region", "measure": "amount", "aggregation": "sum"},
       "calculated_columns": [], "parameters": {}}


class TestTheHttpChannel:
    @pytest.mark.asyncio
    async def test_row_cap(self, client, auth_headers, db_session, two_orgs, import_ds, monkeypatch):
        monkeypatch.setattr(settings, "import_row_cap", 1)
        ds = await import_ds()
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=BAR,
                              headers=auth_headers["a"])
        assert r.status_code == 413
        assert r.json()["code"] == "row_cap"
        assert "row cap" in r.json()["detail"]          # the text is untouched

    @pytest.mark.asyncio
    async def test_not_found(self, client, auth_headers):
        r = await client.post("/api/v1/datasets/999999/widget-data", json=BAR,
                              headers=auth_headers["a"])
        assert r.status_code == 404
        assert r.json()["code"] == "not_found"

    @pytest.mark.asyncio
    async def test_source_unavailable(self, client, auth_headers, db_session, two_orgs, monkeypatch):
        from sqlalchemy.exc import OperationalError
        src = DataSource(name="Warehouse", type="postgresql", org_id=two_orgs["a"]["org"].id,
                         config={"host": "db.internal", "port": 5432, "database": "s",
                                 "username": "r", "password": "p"})
        db_session.add(src)
        await db_session.flush()
        ds = Dataset(name="Live", org_id=two_orgs["a"]["org"].id, mode="directquery",
                     data_source_id=src.id, source_table="orders")
        db_session.add(ds)
        await db_session.flush()
        for c in ("region", "amount"):
            db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
        await db_session.commit()

        def _boom(*a, **kw):
            raise OperationalError("conn", {}, Exception("down"))
        monkeypatch.setattr("app.services.direct_query._run_direct_query_inner", _boom)

        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=BAR,
                              headers=auth_headers["a"])
        assert r.status_code == 502
        assert r.json()["code"] == "source_unavailable"

    @pytest.mark.asyncio
    async def test_an_unsupported_directquery_feature(self, client, auth_headers, db_session, two_orgs):
        src = DataSource(name="W", type="postgresql", org_id=two_orgs["a"]["org"].id,
                         config={"host": "h", "port": 5432, "database": "s",
                                 "username": "r", "password": "p"})
        db_session.add(src)
        await db_session.flush()
        ds = Dataset(name="Live", org_id=two_orgs["a"]["org"].id, mode="directquery",
                     data_source_id=src.id, source_table="orders")
        db_session.add(ds)
        await db_session.commit()
        body = dict(BAR, calculated_columns=[{"name": "x", "formula": "amount * 2"}])
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body,
                              headers=auth_headers["a"])
        assert r.status_code == 400
        assert r.json()["code"] == "unsupported"


class TestTheQuotaChannel:
    @pytest.mark.asyncio
    async def test_a_429_carries_a_code(self, client, auth_headers, db_session, two_orgs, import_ds):
        """QuotaExceeded is not an HTTPException, so the router's widget_error()
        and the structural pin never see it -- its handler in main.py has to
        write the code itself. The one path a bare 'every error' claim missed."""
        from datetime import datetime
        from app.models.models import Quota, QueryRun
        from app.services import quotas
        org_id = two_orgs["a"]["org"].id
        ds = await import_ds()
        db_session.add(Quota(org_id=org_id, max_queries_per_day=1))
        db_session.add(QueryRun(org_id=org_id, source_kind="import", duration_ms=1,
                                executor="pandas", created_at=datetime.utcnow()))
        await db_session.commit()
        quotas.invalidate_quota_cache(org_id)
        r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=BAR,
                              headers=auth_headers["a"])
        assert r.status_code == 429, r.text
        assert r.json()["code"] == "quota"
        assert "Retry-After" in r.headers


class TestTheSecondChannel:
    def test_a_measure_that_cannot_be_evaluated_is_coded(self, tmp_path):
        """The 200-with-type:error body. It was the one error nobody read.

        Asserted on the service result rather than through the endpoint,
        because the router deliberately ignores client-supplied `measures`
        (a request body cannot smuggle its own definitions) -- and the
        service result IS the body the frontend receives, unchanged."""
        from app.services.widget_data import get_widget_data
        path = tmp_path / "m.csv"
        pd.DataFrame({"region": ["E", "W"], "amount": [1.0, 2.0]}).to_csv(path, index=False)
        result = get_widget_data(
            str(path), {"dimension": "region", "measure": "Bad"}, widget_type="bar",
            measures=[{"name": "Bad", "expression": "SUM(no_such_column)"}],
            use_cache=False)
        assert result["type"] == "error"
        assert result["code"] == "measure_error"
        assert result["message"]
