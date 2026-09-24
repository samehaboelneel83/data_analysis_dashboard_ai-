"""The join match check: the geography panel's pattern applied to joins."""
import pandas as pd

from app.services.prep import join_match_report

ORDERS = pd.DataFrame({"cust": ["a", "a", "b", "c", "x", None], "amt": [1, 2, 3, 4, 5, 6]})
CUSTOMERS = pd.DataFrame({"id": ["a", "b", "b", "c"], "name": ["A", "B1", "B2", "C"]})


def test_it_reports_matches_misses_and_the_row_multiplier():
    r = join_match_report(ORDERS, CUSTOMERS, [("cust", "id")], how="left")
    assert r["rows"] == 6 and r["matched_rows"] == 4 and r["pct_rows"] == 66
    assert r["unmatched"] == [{"key": "x", "rows": 1}] and r["blank_keys"] == 1
    assert r["duplicate_right_keys"] == 1 and r["duplicate_examples"] == [{"key": "b", "count": 2}]
    # b's order is duplicated by its two customer rows: 6 rows become 7.
    assert r["rows_after"] == 7
    real = ORDERS.merge(CUSTOMERS, how="left", left_on="cust", right_on="id")
    assert len(real) == 7


def test_inner_join_row_count_matches_pandas():
    r = join_match_report(ORDERS, CUSTOMERS, [("cust", "id")], how="inner")
    assert r["rows_after"] == len(ORDERS.merge(CUSTOMERS, how="inner", left_on="cust", right_on="id"))


def test_a_number_joined_to_text_is_flagged():
    left = pd.DataFrame({"k": [1, 2]})
    right = pd.DataFrame({"k": ["1", "2"]})
    r = join_match_report(left, right, [("k", "k")])
    assert r["pct_rows"] == 100 and r["type_mismatch"]


def test_a_missing_column_is_named():
    assert "'nope'" in join_match_report(ORDERS, CUSTOMERS, [("nope", "id")])["error"]


# ── over HTTP, with the same fixtures the join tests use ─────────────────────
import pytest  # noqa: E402

from tests.test_prep_join import _join_step, _pair, two_files  # noqa: E402,F401


@pytest.mark.asyncio
async def test_the_editor_can_check_a_join_before_saving_it(client, auth_headers, db_session, two_orgs, two_files):
    left, right = await _pair(db_session, two_orgs["a"]["org"], two_files)
    r = await client.post(f"/api/v1/datasets/{left.id}/join-check",
                          json={"steps": [_join_step(right.id)], "index": 0}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pct_rows"] == 100 and body["rows_after"] == 3


@pytest.mark.asyncio
async def test_a_dataset_from_another_org_cannot_be_checked(client, auth_headers, db_session, two_orgs, two_files):
    left, _ = await _pair(db_session, two_orgs["a"]["org"], two_files)
    _, theirs = await _pair(db_session, two_orgs["b"]["org"], two_files)
    r = await client.post(f"/api/v1/datasets/{left.id}/join-check",
                          json={"steps": [_join_step(theirs.id)], "index": 0}, headers=auth_headers["a"])
    assert r.status_code == 404
