"""Report-layer joins as a prep step: merge semantics, and the security spine --
the joined dataset's own RLS, column mask and org boundary all hold through the
join, as the requesting identity."""
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import ColumnSecurityRule, Dataset, DatasetColumn, RowSecurityRule, Role, User
from app.services.prep import apply_prep_steps, validate_prep_steps


# ── pure merge semantics ─────────────────────────────────────────────────────

def orders():
    return pd.DataFrame({"cust": ["a", "b", "c"], "amount": [10.0, 20.0, 30.0]})


def customers():
    return pd.DataFrame({"id": ["a", "b", "d"], "segment": ["SMB", "ENT", "SMB"],
                         "amount": [1.0, 2.0, 4.0]})


def test_left_join_brings_matching_columns_and_suffixes_collisions():
    out = apply_prep_steps(orders(), [{"kind": "join", "dataset_id": 9, "how": "left",
                                       "left_on": "cust", "right_on": "id"}],
                           {9: customers()})
    assert list(out["segment"])[:2] == ["SMB", "ENT"]
    assert pd.isna(out["segment"].iloc[2])          # 'c' has no customer row
    assert "amount_2" in out.columns                # collision suffixed, not clobbered
    assert list(out["amount"]) == [10.0, 20.0, 30.0]


def test_inner_and_full_row_counts():
    def step(how):
        return [{"kind": "join", "dataset_id": 9, "how": how, "left_on": "cust", "right_on": "id"}]
    assert len(apply_prep_steps(orders(), step("inner"), {9: customers()})) == 2
    assert len(apply_prep_steps(orders(), step("full"), {9: customers()})) == 4   # c and d both survive


def test_missing_aux_frame_degrades_to_noop_never_leaks():
    out = apply_prep_steps(orders(), [{"kind": "join", "dataset_id": 9, "how": "left",
                                       "left_on": "cust", "right_on": "id"}], None)
    assert list(out.columns) == ["cust", "amount"]


def test_validation_knows_the_joined_columns():
    validate_prep_steps([{"kind": "join", "dataset_id": 9, "how": "left",
                          "left_on": "cust", "right_on": "id"},
                         {"kind": "fill_nulls", "column": "segment", "method": "value", "value": "None"}],
                        {"cust", "amount"}, {9: {"id", "segment", "amount"}})
    with pytest.raises(ValueError, match="does not exist on the joined dataset"):
        validate_prep_steps([{"kind": "join", "dataset_id": 9, "how": "left",
                              "left_on": "cust", "right_on": "wrong"}],
                            {"cust"}, {9: {"id"}})


# ── API + security ───────────────────────────────────────────────────────────

@pytest.fixture
def two_files(tmp_path):
    o = tmp_path / "orders.csv"
    pd.DataFrame({"cust": ["a", "b", "c"], "amount": [10.0, 20.0, 30.0]}).to_csv(o, index=False)
    c = tmp_path / "customers.csv"
    pd.DataFrame({"id": ["a", "b", "c"], "segment": ["SMB", "ENT", "GOV"],
                  "credit_limit": [100.0, 200.0, 300.0]}).to_csv(c, index=False)
    return str(o), str(c)


async def _pair(db, org, two_files):
    opath, cpath = two_files
    left = Dataset(name="Orders", filename=opath, org_id=org.id, mode="import")
    right = Dataset(name="Customers", filename=cpath, org_id=org.id, mode="import")
    db.add_all([left, right])
    await db.flush()
    for ds, cols in ((left, ["cust", "amount"]), (right, ["id", "segment", "credit_limit"])):
        for c in cols:
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    await db.commit()
    return left, right


def _join_step(right_id):
    return {"kind": "join", "dataset_id": right_id, "how": "left", "left_on": "cust", "right_on": "id"}


@pytest.mark.asyncio
async def test_widget_reads_across_the_join(client, auth_headers, db_session, two_orgs, two_files):
    left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
    r = await client.put(f"/api/v1/datasets/{left.id}/prep-steps", json=[_join_step(right.id)],
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/datasets/{left.id}/widget-data",
                          json={"widget_type": "bar",
                                "config": {"dimension": "segment", "measure": "amount", "aggregation": "sum"}},
                          headers=auth_headers["a"])
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"SMB": 10.0, "ENT": 20.0, "GOV": 30.0}


@pytest.mark.asyncio
async def test_cannot_join_a_dataset_from_another_org(client, auth_headers, db_session, two_orgs, two_files):
    left, _ = await _pair(db_session, two_orgs["a"]["org"], two_files)
    _, foreign = await _pair(db_session, two_orgs["b"]["org"], two_files)
    r = await client.put(f"/api/v1/datasets/{left.id}/prep-steps", json=[_join_step(foreign.id)],
                         headers=auth_headers["a"])
    assert r.status_code == 400
    assert "does not exist" in r.json()["detail"]


@pytest.mark.asyncio
async def test_joined_datasets_rls_holds_through_the_join(client, db_session, two_orgs, two_files):
    """The join must not become an RLS bypass: a role restricted on Customers
    sees NULL segment for hidden customers even when reading via Orders."""
    org = two_orgs["a"]["org"]
    left, right = await _pair(db_session, org, two_files)
    role = Role(org_id=org.id, name="smb-only", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=right.id, filter_expr="`segment` == 'SMB'"))
    user = User(org_id=org.id, role_id=role.id, email="smb@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    left.column_meta = {"__prep_steps__": [_join_step(right.id)]}
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

    r = await client.post(f"/api/v1/datasets/{left.id}/widget-data",
                          json={"widget_type": "table", "config": {"columns": ["cust", "segment"]}},
                          headers=headers)
    text = str(r.json())
    assert "SMB" in text
    assert "ENT" not in text and "GOV" not in text


@pytest.mark.asyncio
async def test_joined_datasets_column_mask_holds_through_the_join(client, db_session, two_orgs, two_files):
    org = two_orgs["a"]["org"]
    left, right = await _pair(db_session, org, two_files)
    role = Role(org_id=org.id, name="no-credit", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=right.id,
                                      denied_columns=["credit_limit"]))
    user = User(org_id=org.id, role_id=role.id, email="nocredit@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    left.column_meta = {"__prep_steps__": [_join_step(right.id)]}
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}

    r = await client.post(f"/api/v1/datasets/{left.id}/widget-data",
                          json={"widget_type": "table",
                                "config": {"columns": ["cust", "segment", "credit_limit"]}},
                          headers=headers)
    body = str(r.json())
    assert "segment" in body
    assert "credit_limit" not in body and "300" not in body


@pytest.mark.asyncio
async def test_prep_preview_resolves_joins_for_the_editor(client, auth_headers, db_session, two_orgs, two_files):
    left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
    r = await client.post(f"/api/v1/datasets/{left.id}/prep-preview", json=[_join_step(right.id)],
                          headers=auth_headers["a"])
    body = r.json()
    assert "segment" in body["after"]["columns"]
    assert body["after"]["rows"] == 3


# ── composite (multi-column) keys ────────────────────────────────────────────

def _shipments():
    return pd.DataFrame({"region": ["EU", "EU", "US"], "as_of": ["Q1", "Q2", "Q1"],
                         "units": [5, 6, 7]})


def _sales():
    return pd.DataFrame({"region": ["EU", "EU", "US"], "date": ["Q1", "Q2", "Q2"],
                         "amount": [10.0, 20.0, 30.0]})


def _composite(dataset_id=9, how="left"):
    return {"kind": "join", "dataset_id": dataset_id, "how": how,
            "left_ons": ["region", "date"], "right_ons": ["region", "as_of"]}


def test_a_composite_key_matches_on_every_column():
    """A single-column join on `region` alone would match EU rows to both EU
    shipments and multiply them; the second key is what keeps the grain."""
    out = apply_prep_steps(_sales(), [_composite()], {9: _shipments()})

    assert len(out) == 3, "the join changed the row count"
    by_key = {(r.region, r.date): r for r in out.itertuples()}
    assert by_key[("EU", "Q1")].units == 5
    assert by_key[("EU", "Q2")].units == 6
    assert pd.isna(by_key[("US", "Q2")].units)   # no US/Q2 shipment


def test_one_column_alone_would_have_fanned_out():
    """The contrast that shows the composite key is doing something: the same
    data joined on region only produces more rows than it started with."""
    single = {"kind": "join", "dataset_id": 9, "how": "left",
              "left_on": "region", "right_on": "region"}
    out = apply_prep_steps(_sales(), [single], {9: _shipments()})
    assert len(out) > 3


def test_the_single_key_shape_still_works():
    """Every pipeline saved before composite keys existed uses `left_on`/
    `right_on`, and those live in deployed databases -- they are read as-is."""
    out = apply_prep_steps(orders(), [{"kind": "join", "dataset_id": 9, "how": "left",
                                       "left_on": "cust", "right_on": "id"}],
                           {9: customers()})
    assert list(out["segment"])[:2] == ["SMB", "ENT"]


def test_a_missing_key_column_skips_the_whole_join():
    """Dropping one column of a composite key would silently widen the match
    and multiply rows -- worse than not joining."""
    out = apply_prep_steps(_sales(), [
        {"kind": "join", "dataset_id": 9, "how": "left",
         "left_ons": ["region", "gone"], "right_ons": ["region", "as_of"]},
    ], {9: _shipments()})
    assert list(out.columns) == ["region", "date", "amount"]


def test_validation_accepts_a_composite_key():
    validate_prep_steps([_composite()], {"region", "date", "amount"},
                        {9: {"region", "as_of", "units"}})


def test_validation_rejects_mismatched_key_counts():
    """Keys pair position for position, so a ragged pair would join the wrong
    columns together."""
    with pytest.raises(ValueError, match="same number of key columns"):
        validate_prep_steps([{"kind": "join", "dataset_id": 9, "how": "left",
                              "left_ons": ["region", "date"], "right_ons": ["region"]}],
                            {"region", "date"}, {9: {"region", "as_of"}})


def test_validation_rejects_a_composite_key_naming_an_unknown_column():
    with pytest.raises(ValueError, match="does not exist on the joined dataset"):
        validate_prep_steps([{"kind": "join", "dataset_id": 9, "how": "left",
                              "left_ons": ["region", "date"], "right_ons": ["region", "nope"]}],
                            {"region", "date"}, {9: {"region", "as_of"}})


def test_validation_rejects_a_join_with_no_keys_at_all():
    with pytest.raises(ValueError, match="needs a key column"):
        validate_prep_steps([{"kind": "join", "dataset_id": 9, "how": "left"}],
                            {"region"}, {9: {"region"}})
