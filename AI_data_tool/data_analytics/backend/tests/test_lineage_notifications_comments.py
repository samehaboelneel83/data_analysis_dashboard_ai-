"""Lineage graph, in-app notifications, and report comments."""
import pandas as pd
import pytest

from app.models.models import Dataset, DatasetColumn, Notification, Report, ReportPage, ReportWidget
from app.services.notifications import MAX_PER_USER, notify


@pytest.fixture
def csvfile(tmp_path):
    p = tmp_path / "d.csv"
    pd.DataFrame({"k": ["a"], "v": [1.0]}).to_csv(p, index=False)
    return str(p)


async def _dataset(db, org, path, name="D"):
    ds = Dataset(name=name, filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c in ("k", "v"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db.commit()
    return ds


# ── lineage ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lineage_links_sources_joins_and_widget_level_reads(client, auth_headers, db_session, two_orgs, csvfile):
    org = two_orgs["a"]["org"]
    a = await _dataset(db_session, org, csvfile, "Orders")
    b = await _dataset(db_session, org, csvfile, "Customers")
    c = await _dataset(db_session, org, csvfile, "Unrelated")
    # a joins b via prep
    a.column_meta = {"__prep_steps__": [{"kind": "join", "dataset_id": b.id, "how": "left",
                                         "left_on": "k", "right_on": "k"}]}
    # report declares a, but one widget reads c directly
    r = Report(name="Sales", dataset_id=a.id, org_id=org.id)
    db_session.add(r)
    await db_session.flush()
    page = ReportPage(report_id=r.id, name="P1", position=0)
    db_session.add(page)
    await db_session.flush()
    db_session.add(ReportWidget(page_id=page.id, widget_type="bar",
                                config={"dataset_id": c.id, "dimension": "k"}))
    await db_session.commit()

    resp = await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    g = resp.json()
    ds_a = next(d for d in g["datasets"] if d["id"] == a.id)
    assert ds_a["joins"] == [b.id]
    rep = next(x for x in g["reports"] if x["id"] == r.id)
    assert set(rep["dataset_ids"]) == {a.id, c.id}


@pytest.mark.asyncio
async def test_lineage_is_org_scoped(client, auth_headers, db_session, two_orgs, csvfile):
    await _dataset(db_session, two_orgs["a"]["org"], csvfile, "Private")
    resp = await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["b"])
    assert all(d["name"] != "Private" for d in resp.json()["datasets"])


# ── F4: lineage carries ETL metadata ────────────────────────────────────────

@pytest.mark.asyncio
async def test_lineage_reports_etl_fields_and_excludes_disabled_steps(
    client, auth_headers, db_session, two_orgs, csvfile,
):
    from datetime import datetime, timezone
    from app.models.models import Watermark

    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, csvfile, "Orders")
    ds.column_meta = {"__prep_steps__": [
        {"kind": "filter_rows", "column": "v", "op": "gt", "value": 0},
        {"kind": "sort", "columns": ["v"], "directions": ["asc"]},
        {"kind": "rename", "from": "k", "to": "key", "disabled": True},
    ]}
    ds.last_refreshed_at = datetime.now(timezone.utc)
    db_session.add(Watermark(dataset_id=ds.id, strategy="incremental", cursor_column="v", cursor_value="1"))
    await db_session.commit()

    resp = await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    node = next(d for d in resp.json()["datasets"] if d["id"] == ds.id)

    assert node["extraction_kind"] == "csv"
    assert node["transform"]["count"] == 2
    assert node["transform"]["kinds"] == ["filter_rows", "sort"]
    assert node["load"]["strategy"] == "incremental"
    assert node["load"]["cursor_column"] == "v"
    assert node["load"]["last_refreshed_at"] is not None
    assert node["load"]["staleness"] == "fresh"


# ── O3: lineage carries the materialization manifest flag ──────────────────

@pytest.mark.asyncio
async def test_lineage_flags_a_materialized_dataset_with_its_manifest_row_count(
    client, auth_headers, db_session, two_orgs, csvfile,
):
    from app.models.models import Materialization

    org = two_orgs["a"]["org"]
    materialized = await _dataset(db_session, org, csvfile, "Materialized")
    unmaterialized = await _dataset(db_session, org, csvfile, "UploadOnly")
    db_session.add(Materialization(
        dataset_id=materialized.id, path=csvfile + ".parquet", kind="full",
        row_count=42, columns=["k", "v"],
    ))
    await db_session.commit()

    resp = await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    nodes = {d["id"]: d for d in resp.json()["datasets"]}

    assert nodes[materialized.id]["materialized"] is True
    assert nodes[materialized.id]["materialized_row_count"] == 42
    assert nodes[unmaterialized.id]["materialized"] is False
    assert nodes[unmaterialized.id]["materialized_row_count"] is None


@pytest.mark.asyncio
async def test_lineage_never_refreshed_dataset_has_null_load_info(
    client, auth_headers, db_session, two_orgs, csvfile,
):
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org, csvfile, "NeverRefreshed")

    resp = await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    node = next(d for d in resp.json()["datasets"] if d["id"] == ds.id)

    assert node["load"]["last_refreshed_at"] is None
    assert node["load"]["strategy"] is None
    assert node["load"]["cursor_column"] is None
    assert node["load"]["staleness"] == "never"
    assert node["transform"]["count"] == 0


# ── notifications ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bell_lists_own_only_and_mark_read(client, auth_headers, db_session, two_orgs):
    ua, ub = two_orgs["a"]["user"], two_orgs["b"]["user"]
    await notify(db_session, ua.org_id, ua.id, "alert", "Revenue alert is firing")
    await notify(db_session, ub.org_id, ub.id, "alert", "Other org's business")
    await db_session.commit()

    r = await client.get("/api/v1/notifications", headers=auth_headers["a"])
    body = r.json()
    assert body["unread"] == 1
    assert [n["text"] for n in body["notifications"]] == ["Revenue alert is firing"]

    r = await client.post("/api/v1/notifications/mark-read", headers=auth_headers["a"])
    assert r.json()["marked"] == 1
    r = await client.get("/api/v1/notifications", headers=auth_headers["a"])
    assert r.json()["unread"] == 0
    # org b's row untouched
    r = await client.get("/api/v1/notifications", headers=auth_headers["b"])
    assert r.json()["unread"] == 1


@pytest.mark.asyncio
async def test_notification_cap_trims_oldest(db_session, two_orgs):
    ua = two_orgs["a"]["user"]
    for i in range(MAX_PER_USER + 5):
        await notify(db_session, ua.org_id, ua.id, "alert", f"n{i}")
    await db_session.commit()
    from sqlalchemy import func, select
    count = (await db_session.execute(
        select(func.count()).select_from(Notification).where(Notification.user_id == ua.id)
    )).scalar_one()
    assert count == MAX_PER_USER


# ── comments ─────────────────────────────────────────────────────────────────

async def _report(db, org):
    r = Report(name="R", org_id=org.id)
    db.add(r)
    await db.commit()
    return r


@pytest.mark.asyncio
async def test_comment_round_trip_and_participant_notification(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    r = await _report(db_session, org)
    # admin comments first; a second user comments after -- the admin gets the bell
    resp = await client.post(f"/api/v1/reports/{r.id}/comments", json={"text": "First!"},
                             headers=auth_headers["a"])
    assert resp.status_code == 201

    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User
    role = Role(org_id=org.id, name="commenter", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    u2 = User(org_id=org.id, role_id=role.id, email="c2@example.com",
              password_hash=hash_password("pw"))
    db_session.add(u2)
    await db_session.commit()
    h2 = {"Authorization": f"Bearer {create_access_token(u2.id, org.id)}"}

    await client.post(f"/api/v1/reports/{r.id}/comments", json={"text": "Replying"}, headers=h2)
    resp = await client.get(f"/api/v1/reports/{r.id}/comments", headers=auth_headers["a"])
    comments = resp.json()
    assert [c["text"] for c in comments] == ["First!", "Replying"]
    assert comments[0]["mine"] is True and comments[1]["mine"] is False

    bell = (await client.get("/api/v1/notifications", headers=auth_headers["a"])).json()
    assert any("commented on" in n["text"] for n in bell["notifications"])
    # the second author gets no self-notification
    bell2 = (await client.get("/api/v1/notifications", headers=h2)).json()
    assert not any("commented on" in n["text"] for n in bell2["notifications"])


@pytest.mark.asyncio
async def test_only_own_comments_deletable_by_non_admin(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    r = await _report(db_session, org)
    resp = await client.post(f"/api/v1/reports/{r.id}/comments", json={"text": "Admin's words"},
                             headers=auth_headers["a"])
    cid = resp.json()["id"]

    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User
    role = Role(org_id=org.id, name="viewer2", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    u2 = User(org_id=org.id, role_id=role.id, email="v2@example.com",
              password_hash=hash_password("pw"))
    db_session.add(u2)
    await db_session.commit()
    h2 = {"Authorization": f"Bearer {create_access_token(u2.id, org.id)}"}

    resp = await client.delete(f"/api/v1/reports/{r.id}/comments/{cid}", headers=h2)
    assert resp.status_code == 403
    resp = await client.delete(f"/api/v1/reports/{r.id}/comments/{cid}", headers=auth_headers["a"])
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_comments_are_org_scoped(client, auth_headers, db_session, two_orgs):
    r = await _report(db_session, two_orgs["a"]["org"])
    resp = await client.get(f"/api/v1/reports/{r.id}/comments", headers=auth_headers["b"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lineage_shows_where_a_materialized_dataset_came_from(
    client, auth_headers, db_session, two_orgs, csvfile, tmp_path, monkeypatch,
):
    """A materialized dataset has no prep steps of its own -- the joins were
    consumed into its file -- so `joins` is empty for it and the derivation
    would be invisible without a separate edge.

    The two edges mean different things and the graph must not conflate them:
    `joins` is live and re-evaluated on every read, `derived_from` is a snapshot
    taken once at `built_at`.
    """
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    org = two_orgs["a"]["org"]
    a = await _dataset(db_session, org, csvfile, "Orders")
    b = await _dataset(db_session, org, csvfile, "Customers")

    resp = await client.post(
        f"/api/v1/datasets/{a.id}/materialize",
        json={"name": "Joined", "steps": [{"kind": "join", "dataset_id": b.id,
                                           "how": "left", "left_on": "k", "right_on": "k"}]},
        headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    new_id = resp.json()["id"]

    g = (await client.get("/api/v1/datasets/lineage/graph", headers=auth_headers["a"])).json()
    node = next(d for d in g["datasets"] if d["id"] == new_id)

    assert node["derived_from"] == sorted([a.id, b.id])
    assert node["built_at"], "a snapshot edge needs the time it was taken"
    assert node["joins"] == [], "the joins were consumed into the file, not re-run"
