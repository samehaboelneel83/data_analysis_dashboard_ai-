"""GET /datasets/{id}/opportunities: remembered once, read as the reader
(docs/discovery/PLAN.md, phase 1)."""
import numpy as np
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import ColumnSecurityRule, Dataset, DatasetColumn, Role, User
from app.services.discovery import profile as store


@pytest.fixture
def data_csv(tmp_path):
    rng = np.random.default_rng(2)
    n = 400
    group = rng.choice(["a", "b", "c"], n)
    pd.DataFrame({
        "row_id": np.arange(n) + 1, "g": group, "h": rng.choice(["x", "y"], n),
        "when": (pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, 600, n), "D")).astype(str),
        "v1": rng.uniform(5, 300, n).round(2), "v2": rng.normal(40, 6, n).round(3),
        "secret": rng.uniform(1, 9, n).round(2),
    }).to_csv(tmp_path / "d.csv", index=False)
    return str(tmp_path / "d.csv")


async def _world(db, org, path, *, deny=None):
    ds = Dataset(name="D", filename=path, org_id=org.id, mode="import", row_count=400)
    db.add(ds)
    await db.flush()
    for c, t in (("row_id", "numeric"), ("g", "categorical"), ("h", "categorical"), ("when", "datetime"),
                 ("v1", "numeric"), ("v2", "numeric"), ("secret", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    role = Role(org_id=org.id, name="reader", is_org_admin=False)
    db.add(role)
    await db.flush()
    if deny:
        db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=deny))
    user = User(org_id=org.id, role_id=role.id, email="reader@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    ds.created_by = user.id
    await db.commit()
    return ds, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def test_the_profile_is_measured_once_and_then_read_from_the_store(client, two_orgs, db_session, data_csv,
                                                                          monkeypatch):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    first = (await client.get(f"/api/v1/datasets/{ds.id}/opportunities?fresh=true", headers=headers)).json()
    assert first["profile_from_store"] is False and first["mode"] == "deterministic" and first["cards"]

    from app.models.models import DatasetProfile
    kept = await db_session.get(DatasetProfile, ds.id)
    await db_session.refresh(kept)
    assert kept.version == store.fingerprint(ds)
    assert kept.body["columns"]["v1"]["kind"] == "number" and kept.body["columns"]["g"]["distinct"] == 3

    # ...and NOT where every dataset payload would hand it to any reader:
    # the ranges and labels of the whole table are not a restricted reader's.
    await db_session.refresh(ds)
    assert "__profile__" not in (ds.column_meta or {})
    payload = (await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)).json()
    assert all(not (c.get("stats") or {}).get("kind") for c in payload["columns"])

    # What the data SUPPORTS is then answered without reading a single row.
    def no_rows(*_a, **_k):
        raise AssertionError("tier 0 read the data")
    monkeypatch.setattr("app.services.suggest_inputs.prepare", no_rows)
    again = await client.get(f"/api/v1/datasets/{ds.id}/opportunities?depth=0&fresh=true", headers=headers)
    assert again.status_code == 200 and again.json()["profile_from_store"] is True
    assert {"segment", "association_rules"} <= {c["capability"] for c in again.json()["cards"]}


async def test_every_card_keeps_fit_evidence_claim_and_cost_apart(client, two_orgs, db_session, data_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    got = (await client.get(f"/api/v1/datasets/{ds.id}/opportunities?fresh=true", headers=headers)).json()
    for card in got["cards"]:
        assert card["claim"] in ("observation", "association", "prediction", "hypothesis")
        assert card["cost"]["tier"] in (0, 1, 2) and card["source"] == "deterministic"
        assert card["action"]["kind"] in ("add_widget", "run_analysis", "open", "decision_problem")
        assert card["evidence"] is None or card["evidence"]["band"] in ("strong", "moderate", "weak")
    assert all("confidence" not in card for card in got["cards"])                 # no single score


async def test_a_hidden_column_never_appears_and_is_never_stored(client, two_orgs, db_session, data_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv, deny=["secret"])
    got = (await client.get(f"/api/v1/datasets/{ds.id}/opportunities?fresh=true", headers=headers)).json()
    text = str(got)
    assert got["restricted"] is True and "secret" not in text
    # A reader who cannot see the whole dataset does not get to write its profile.
    from app.models.models import DatasetProfile
    assert await db_session.get(DatasetProfile, ds.id) is None


async def test_a_goal_brings_what_it_names_to_the_top(client, two_orgs, db_session, data_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    got = (await client.get(f"/api/v1/datasets/{ds.id}/opportunities?fresh=true&goal=how did it change over when",
                            headers=headers)).json()
    assert "when" in got["cards"][0]["fields"] and got["cards"][0]["relevance"] == {"matches_goal": True}
    plain = (await client.get(f"/api/v1/datasets/{ds.id}/opportunities?fresh=true", headers=headers)).json()
    assert plain["cards"][0]["relevance"] is None                              # no goal: nothing to match


async def test_another_organisation_gets_nothing(client, auth_headers, two_orgs, db_session, data_csv):
    ds, _ = await _world(db_session, two_orgs["a"]["org"], data_csv)
    assert (await client.get(f"/api/v1/datasets/{ds.id}/opportunities", headers=auth_headers["b"])).status_code == 404


async def test_the_registry_is_served(client, auth_headers):
    got = (await client.get("/api/v1/datasets/capabilities/registry", headers=auth_headers["a"])).json()
    names = {c["name"] for c in got["capabilities"]}
    assert {"bar", "forecast", "key_influencers", "segment"} <= names and "text" not in names


async def test_the_builder_reads_the_same_engine_through_its_report(client, two_orgs, db_session, data_csv):
    """The Suggest pane's door: same cards, the report's name as the goal, and
    the model analyses offered as widgets that can be added to the page."""
    from app.models.models import Report
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    report = Report(name="How things change over when", org_id=two_orgs["a"]["org"].id, dataset_id=ds.id,
                    created_by=ds.created_by)
    db_session.add(report)
    await db_session.commit()
    got = await client.get(f"/api/v1/reports/{report.id}/opportunities?fresh=true", headers=headers)
    assert got.status_code == 200
    body = got.json()
    assert body["goal"] == "How things change over when" and body["cards"][0]["relevance"]["matches_goal"] is True
    addable = {c["action"]["widget_type"] for c in body["cards"] if c["action"]["kind"] == "add_widget"}
    assert {"model_cluster", "model_rules"} <= addable                      # groups of rows, values that go together
    other = await client.get(f"/api/v1/reports/{report.id}/opportunities",
                             headers={"Authorization": "Bearer nope"})
    assert other.status_code in (401, 403)


async def test_the_profile_endpoint_serves_each_columns_card(client, two_orgs, db_session, data_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv)
    got = (await client.get(f"/api/v1/datasets/{ds.id}/profile", headers=headers)).json()
    by = {c["column"]: c for c in got["columns"]}
    assert got["rows"] == 400 and got["restricted"] is False
    assert by["g"]["most_common"][1] > 0 and by["v1"]["valid"]["pct"] == 100.0 and by["when"]["kind"] == "date"
    again = (await client.get(f"/api/v1/datasets/{ds.id}/profile", headers=headers)).json()
    assert again["from_store"] is True


async def test_the_profile_endpoint_hides_what_the_reader_may_not_see(client, two_orgs, db_session, data_csv):
    ds, headers = await _world(db_session, two_orgs["a"]["org"], data_csv, deny=["secret"])
    got = (await client.get(f"/api/v1/datasets/{ds.id}/profile", headers=headers)).json()
    assert got["restricted"] is True and "secret" not in {c["column"] for c in got["columns"]}
