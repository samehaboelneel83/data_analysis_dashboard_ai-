"""F3: watermark-driven full/incremental refresh.

`refresh_dataset` (app/services/dataset_refresh.py) is unit-tested directly for
the load-mode semantics; the router test covers wiring -- org scoping,
last_refreshed_at, and the Watermark row round-trip -- with
`connections.import_to_dataframe` monkeypatched so no real DB connection is
needed. `query_log`'s writer is pointed at an isolated file-backed sqlite DB
(same technique as test_query_runs.py) to prove a refresh is recorded.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
from sqlalchemy import create_engine

from app.core.database import Base
from app.models.models import DataSource, Dataset, Materialization, Watermark
from app.services import query_log
from app.services.dataset_refresh import build_incremental_query, refresh_dataset
from app.services.frame_cache import sidecar_path


# ── refresh_dataset (unit) ──────────────────────────────────────────────────

def test_full_mode_replaces_data_wholesale(tmp_path, monkeypatch):
    path = tmp_path / "d.csv"
    pd.DataFrame([{"id": 1, "v": "old"}]).to_csv(path, index=False)

    fresh = pd.DataFrame([{"id": 1, "v": "new"}, {"id": 2, "v": "new"}])
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: fresh)

    out = refresh_dataset({"type": "sqlite"}, str(path), "t", None, "full", None, None)

    assert out["mode"] == "full"
    assert out["rows_added"] == 2
    on_disk = pd.read_csv(path)
    assert len(on_disk) == 2 and set(on_disk["v"]) == {"new"}


def test_incremental_mode_appends_only_new_rows_and_advances_cursor(tmp_path, monkeypatch):
    path = tmp_path / "d.csv"
    pd.DataFrame([{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}]).to_csv(path, index=False)

    captured = {}

    def fake_import(cfg, table, query, params=None):
        captured["query"] = query
        captured["params"] = params
        return pd.DataFrame([{"id": 3, "updated_at": 30}])

    monkeypatch.setattr("app.services.connections.import_to_dataframe", fake_import)

    out = refresh_dataset({"type": "sqlite"}, str(path), "t", None,
                          "incremental", "updated_at", "20")

    assert out["mode"] == "incremental"
    assert out["rows_added"] == 1
    assert out["cursor_value"] == "30"
    assert captured["params"] == {"cursor_val": "20"}
    on_disk = pd.read_csv(path)
    assert sorted(on_disk["id"].tolist()) == [1, 2, 3]


def test_incremental_first_run_with_no_baseline_cursor_does_a_full_load():
    """No prior cursor_value -- nothing to be incremental FROM -- so this run
    fetches everything and establishes the baseline cursor for every run after."""
    def fake_import(cfg, table, query, params=None):
        assert params is None  # a full fetch, not filtered
        return pd.DataFrame([{"id": 1, "updated_at": 5}, {"id": 2, "updated_at": 9}])

    import app.services.connections as connections
    orig = connections.import_to_dataframe
    connections.import_to_dataframe = fake_import
    try:
        out = refresh_dataset({"type": "sqlite"}, None, "t", None,
                              "incremental", "updated_at", None)
    finally:
        connections.import_to_dataframe = orig

    assert out["mode"] == "full"
    assert out["cursor_value"] == "9"
    assert out["warning"] is None


def test_incremental_with_unknown_cursor_column_falls_back_to_full_with_warning(tmp_path, monkeypatch):
    path = tmp_path / "d.csv"
    pd.DataFrame([{"id": 1, "v": "a"}]).to_csv(path, index=False)

    def fake_import(cfg, table, query, params=None):
        assert params is None  # fell back to the plain full query
        return pd.DataFrame([{"id": 1, "v": "a"}, {"id": 2, "v": "b"}])

    monkeypatch.setattr("app.services.connections.import_to_dataframe", fake_import)

    out = refresh_dataset({"type": "sqlite"}, str(path), "t", None,
                          "incremental", "not_a_real_column", "5")

    assert out["mode"] == "full"
    assert out["warning"] is not None
    assert "not_a_real_column" in out["warning"]
    assert out["rows_added"] == 2


def test_incremental_query_wraps_a_stored_source_query_as_a_subquery():
    sql = build_incremental_query(None, "SELECT * FROM orders;", "updated_at", "20")
    assert sql == 'SELECT * FROM (SELECT * FROM orders) AS _base WHERE "updated_at" > :cursor_val'


def test_incremental_query_against_a_bare_table():
    sql = build_incremental_query("orders", None, "updated_at", "20")
    assert sql == 'SELECT * FROM "orders" WHERE "updated_at" > :cursor_val'


def test_incremental_query_rejects_a_column_not_in_the_allowlist():
    """cursor_column is user-settable (the watermark config); when the caller
    supplies the dataset's actual column names, anything outside that set
    must be rejected before it ever reaches SQL, not merely escaped."""
    with pytest.raises(ValueError):
        build_incremental_query("orders", None, "updated_at", "20", valid_columns={"id", "name"})


def test_incremental_query_accepts_a_column_in_the_allowlist():
    sql = build_incremental_query("orders", None, "updated_at", "20", valid_columns={"updated_at", "id"})
    assert sql == 'SELECT * FROM "orders" WHERE "updated_at" > :cursor_val'


def test_incremental_query_escapes_a_quote_in_the_cursor_column():
    """Defense in depth even for an allowlisted (or unchecked) name: a column
    name carrying a literal quote can't break out of its own quoting."""
    sql = build_incremental_query("orders", None, 'x"; DROP TABLE orders; --', "20")
    assert sql == 'SELECT * FROM "orders" WHERE "x""; DROP TABLE orders; --" > :cursor_val'


def test_incremental_refresh_rejects_unknown_cursor_column_via_valid_columns_and_falls_back(monkeypatch):
    """No cached file on disk yet (existing_df stays None), so the only
    allowlist available is the caller-supplied valid_columns -- an
    unrecognized cursor_column must still fall back to a full refresh rather
    than reach SQL unescaped."""
    def fake_import(cfg, table, query, params=None):
        assert params is None  # never reached the incremental (parameterized) path
        return pd.DataFrame([{"id": 1, "updated_at": 5}])

    monkeypatch.setattr("app.services.connections.import_to_dataframe", fake_import)

    out = refresh_dataset({"type": "sqlite"}, None, "t", None, "incremental",
                          'x"; DROP TABLE t; --', "20", valid_columns={"id", "updated_at"})

    assert out["mode"] == "full"
    assert out["warning"] is not None


# ── router (wiring) ─────────────────────────────────────────────────────────

async def _seeded_dataset(db_session, org_id, tmp_path, name="ds"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame([{"id": 1, "updated_at": 10}]).to_csv(path, index=False)
    src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    ds = Dataset(name=name, filename=str(path), org_id=org_id, row_count=1, col_count=2,
                 data_source_id=src.id, source_table="t")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_refresh_full_via_endpoint_replaces_rows_and_sets_last_refreshed(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    fresh = pd.DataFrame([{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}])
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: fresh)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 2
    assert body["last_refreshed_at"] is not None


async def test_refresh_incremental_via_endpoint_advances_the_watermark(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    wm = Watermark(dataset_id=ds.id, strategy="incremental", cursor_column="updated_at", cursor_value="10")
    db_session.add(wm)
    await db_session.commit()

    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame([{"id": 2, "updated_at": 25}]))

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "incremental"}, headers=auth_headers["a"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 2  # 1 existing + 1 appended

    await db_session.refresh(wm)
    assert wm.cursor_value == "25"


async def test_refresh_carries_forward_semantic_type_by_column_name(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    """semantic_type comes from metadata sync / a manual edit, never from the
    refresh's own type detection -- the delete+recreate of DatasetColumn rows
    on refresh must not silently wipe it, or the codeless RLS builder and
    auto-generate degrade until the next metadata sync."""
    from app.models.models import DatasetColumn

    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    db_session.add_all([
        DatasetColumn(dataset_id=ds.id, name="id", dtype="int", semantic_type=None),
        DatasetColumn(dataset_id=ds.id, name="updated_at", dtype="int", semantic_type="email"),
    ])
    await db_session.commit()

    fresh = pd.DataFrame([{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}])
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: fresh)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])

    assert resp.status_code == 200
    cols = {c["name"]: c["semantic_type"] for c in resp.json()["columns"]}
    assert cols["updated_at"] == "email"
    assert cols["id"] is None


async def test_refresh_cross_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seeded_dataset(db_session, two_orgs["b"]["org"].id, tmp_path)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])

    assert resp.status_code == 404


@pytest.fixture
def query_run_db(tmp_path, monkeypatch):
    """Points query_log's own sync writer at an isolated file-backed sqlite DB,
    same technique as test_query_runs.py's app_db fixture -- the writer never
    touches the app's async engine."""
    from app.core.config import settings

    db_path = tmp_path / "runs.db"
    setup_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(setup_engine)
    setup_engine.dispose()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(query_log, "_sync_engine", None)
    yield db_path
    monkeypatch.setattr(query_log, "_sync_engine", None)


async def test_refresh_is_recorded_in_query_runs(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path, query_run_db,
):
    from app.models.models import QueryRun

    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame([{"id": 1, "updated_at": 10}]))

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])
    assert resp.status_code == 200

    engine = create_engine(f"sqlite:///{query_run_db}")
    try:
        with engine.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(QueryRun.__table__.select())]
    finally:
        engine.dispose()

    refresh_rows = [r for r in rows if r["source_kind"] == "refresh"]
    assert len(refresh_rows) == 1
    assert refresh_rows[0]["dataset_id"] == ds.id


# ── O3: materialization manifest ────────────────────────────────────────────

async def test_refresh_writes_a_materialization_manifest_row_with_pinned_row_count(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    fresh = pd.DataFrame([{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}, {"id": 3, "updated_at": 30}])
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: fresh)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])
    assert resp.status_code == 200

    from sqlalchemy import select as _select
    rows = (await db_session.execute(
        _select(Materialization).where(Materialization.dataset_id == ds.id)
    )).scalars().all()

    assert len(rows) == 1
    mat = rows[0]
    assert mat.row_count == 3  # value-pinned
    assert mat.kind == "full"
    assert mat.path == sidecar_path(ds.filename)
    assert set(mat.columns) == {"id", "updated_at"}
    assert os.path.exists(mat.path)


async def test_second_refresh_supersedes_the_manifest_row_and_prunes_the_old_one(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    """Still exactly ONE manifest row per dataset after a second refresh --
    the prior row is pruned, and since the sidecar path never changes across
    refreshes of the same dataset, the file it pointed at must NOT be
    unlinked (it's the same file the new row references)."""
    from sqlalchemy import select as _select

    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame([{"id": 1, "updated_at": 10}]))
    resp1 = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                              json={"mode": "full"}, headers=auth_headers["a"])
    assert resp1.status_code == 200
    first_rows = (await db_session.execute(
        _select(Materialization).where(Materialization.dataset_id == ds.id)
    )).scalars().all()
    assert len(first_rows) == 1
    first_id = first_rows[0].id

    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame(
                            [{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}]))
    resp2 = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                              json={"mode": "full"}, headers=auth_headers["a"])
    assert resp2.status_code == 200

    rows = (await db_session.execute(
        _select(Materialization).where(Materialization.dataset_id == ds.id)
    )).scalars().all()
    assert len(rows) == 1  # superseded row pruned, not accumulated
    # dataset_id is UNIQUE: supersede updates the surviving row in place, so
    # the id is stable -- the refreshed CONTENT proves the new manifest landed.
    assert rows[0].id == first_id
    assert rows[0].row_count == 2
    assert os.path.exists(rows[0].path)  # file still there -- never unlinked while referenced


async def test_loader_prefers_the_refresh_written_parquet_over_a_csv_reparse(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    """The materialization's parquet IS the frame_cache sidecar (same path) --
    after a refresh, get_frame must load from it rather than re-parsing the
    CSV. Proven by making a CSV re-parse explode: if the loader still
    succeeds, it never touched the CSV."""
    from app.services.frame_cache import clear_frame_cache, get_frame

    ds = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame(
                            [{"id": 1, "updated_at": 10}, {"id": 2, "updated_at": 20}]))
    resp = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])
    assert resp.status_code == 200
    assert os.path.exists(sidecar_path(ds.filename))

    clear_frame_cache()
    real_read_csv = pd.read_csv

    def _boom(*a, **k):
        raise AssertionError("CSV was re-parsed even though a fresh sidecar exists")

    monkeypatch.setattr(pd, "read_csv", _boom)
    try:
        df = get_frame(ds.filename)
    finally:
        monkeypatch.setattr(pd, "read_csv", real_read_csv)
    assert len(df) == 2


async def test_loader_falls_back_to_csv_when_the_parquet_is_stale(tmp_path):
    """mtime discipline, shared with the sidecar: an older parquet next to a
    newer CSV is never trusted."""
    from app.services.frame_cache import clear_frame_cache, get_frame

    clear_frame_cache()
    path = tmp_path / "d.csv"
    pd.DataFrame([{"id": 1}]).to_csv(path, index=False)
    pq = sidecar_path(str(path))
    pd.DataFrame([{"id": 999}]).to_parquet(pq, index=False)  # stale content, older mtime
    old_time = os.path.getmtime(pq) - 1000
    os.utime(pq, (old_time, old_time))

    df = get_frame(str(path))
    assert df["id"].tolist() == [1]  # CSV won, not the stale parquet


async def test_materialization_manifest_is_org_scoped(
    client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path,
):
    from sqlalchemy import select as _select

    ds_a = await _seeded_dataset(db_session, two_orgs["a"]["org"].id, tmp_path, name="a")
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame([{"id": 1, "updated_at": 10}]))
    resp = await client.post(f"/api/v1/datasets/{ds_a.id}/refresh",
                             json={"mode": "full"}, headers=auth_headers["a"])
    assert resp.status_code == 200

    # Org b's lineage graph must never see org a's materialization.
    graph = await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["b"])
    assert graph.status_code == 200
    assert all(d["id"] != ds_a.id for d in graph.json()["datasets"])

    rows = (await db_session.execute(
        _select(Materialization).where(Materialization.dataset_id == ds_a.id)
    )).scalars().all()
    assert len(rows) == 1  # exists, but scoped away from org b's view above


# ── E05: a refresh that drops a column something uses is refused ────────────

class TestARefreshCannotSilentlyBreakWhatUsesIt:
    """A source that renamed or dropped a column used to be refreshed anyway:
    the file was overwritten, the column rows recreated, and every widget,
    measure or filter naming the old column broke at once. The refresh now
    compares the new columns with what find_dependents reports FIRST."""

    async def _world(self, db_session, org_id, tmp_path):
        from app.models.models import DatasetColumn, Report, ReportPage, ReportWidget
        ds = await _seeded_dataset(db_session, org_id, tmp_path)
        for col in ("id", "updated_at"):
            db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype="numeric", missing_pct=0, stats={}))
        report = Report(name="R", org_id=org_id, dataset_id=ds.id)
        db_session.add(report)
        await db_session.flush()
        page = ReportPage(report_id=report.id, name="P", position=0)
        db_session.add(page)
        await db_session.flush()
        db_session.add(ReportWidget(page_id=page.id, widget_type="kpi", title="Latest",
                                    config={"measure": "updated_at"}, layout={"x": 0, "y": 0, "w": 3, "h": 3}))
        await db_session.commit()
        return ds

    async def test_it_is_refused_before_the_file_changes_with_a_suggested_mapping(
            self, client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
        ds = await self._world(db_session, two_orgs["a"]["org"].id, tmp_path)
        before = open(ds.filename, encoding="utf-8").read()
        renamed = pd.DataFrame([{"id": 1, "Updated At": 10}, {"id": 2, "Updated At": 20}])
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: renamed)

        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full"},
                              headers=auth_headers["a"])

        assert r.status_code == 409, r.text
        body = r.json()
        assert body["code"] == "schema_break" and body["missing"] == ["updated_at"]
        assert body["suggestions"] == {"updated_at": ["Updated At"]}
        assert [d["kind"] for d in body["dependents"]["updated_at"]] == ["widget"]
        assert open(ds.filename, encoding="utf-8").read() == before      # untouched

    async def test_the_mapping_reattaches_the_renamed_column(
            self, client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
        ds = await self._world(db_session, two_orgs["a"]["org"].id, tmp_path)
        renamed = pd.DataFrame([{"id": 1, "Updated At": 10}, {"id": 2, "Updated At": 20}])
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: renamed)

        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                              json={"mode": "full", "column_map": {"Updated At": "updated_at"}},
                              headers=auth_headers["a"])

        assert r.status_code == 200, r.text
        assert r.json()["row_count"] == 2
        # The file is what every widget reads: it carries the OLD name, so
        # the KPI on `updated_at` still resolves after the source renamed it.
        assert list(pd.read_csv(ds.filename).columns) == ["id", "updated_at"]

    async def test_force_accepts_the_break_knowingly(
            self, client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
        ds = await self._world(db_session, two_orgs["a"]["org"].id, tmp_path)
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: pd.DataFrame([{"id": 1}]))
        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full", "force": True},
                              headers=auth_headers["a"])
        assert r.status_code == 200

    async def test_an_unused_column_may_disappear(
            self, client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
        ds = await self._world(db_session, two_orgs["a"]["org"].id, tmp_path)
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: pd.DataFrame([{"updated_at": 5}]))
        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full"},
                              headers=auth_headers["a"])
        assert r.status_code == 200       # `id` went, and nothing named it
        # ...and the response says so: it used to echo the column list the
        # request STARTED with, because the re-select reused the loaded one.
        assert [c["name"] for c in r.json()["columns"]] == ["updated_at"]


async def test_the_scheduler_refuses_the_same_break_and_says_so(db_session, two_orgs, monkeypatch, tmp_path):
    from sqlalchemy import select as _select
    from app.models.models import ScheduleFailure
    from app.services.refresh_scheduler import refresh_one
    world = TestARefreshCannotSilentlyBreakWhatUsesIt()
    ds = await world._world(db_session, two_orgs["a"]["org"].id, tmp_path)
    before = open(ds.filename, encoding="utf-8").read()
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: pd.DataFrame([{"id": 1}]))

    assert await refresh_one(db_session, ds) is True

    assert open(ds.filename, encoding="utf-8").read() == before
    failure = (await db_session.execute(_select(ScheduleFailure).where(
        ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == ds.id))).scalar_one()
    assert "updated_at" in failure.last_error and "Not refreshed" in failure.last_error
