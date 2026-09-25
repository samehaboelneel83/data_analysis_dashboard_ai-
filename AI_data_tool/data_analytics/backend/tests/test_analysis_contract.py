"""A1: uniform AnalysisContract envelope.

Pins that the existing (pre-contract) wire shape of the /datasets/{id}/analysis
endpoints is preserved byte-for-byte after the AnalysisContract refactor, and
that the new `result` envelope is present and correctly derived, additively.
"""
import pandas as pd
import pytest

from app.services.analysis_contract import as_response, full_profile_to_contract, safe_clean
from app.services.analytics import run_full_analysis


def _fixture_df():
    return pd.DataFrame({
        "region": ["North", "South", "North", "East", "South"],
        "sales": [100, 200, 150, 300, 250],
        "signed_up": pd.to_datetime(
            ["2024-01-01", "2024-01-02", "2024-01-05", "2024-02-01", "2024-02-10"]
        ),
    })


LEGACY_KEYS = {"type_map", "numeric", "categorical", "datetime", "overview"}


async def _seed_dataset_with_file(db_session, tmp_path, org_id, df, name="Contract Dataset"):
    from app.models.models import Dataset

    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    df.to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


class TestGoldenWireShape:
    """Golden-style: record the pre-refactor JSON shape on a fixture dataset,
    assert the router's response still contains it byte-for-byte."""

    async def test_post_analysis_preserves_legacy_top_level_keys(
        self, client, db_session, two_orgs, auth_headers, tmp_path
    ):
        df = _fixture_df()
        ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, df)
        expected_legacy = run_full_analysis(df.copy())

        resp = await client.post(
            f"/api/v1/datasets/{ds.id}/analysis", json={"analysis_type": "full"},
            headers=auth_headers["a"],
        )
        assert resp.status_code == 200
        body = resp.json()

        # Every pre-existing top-level key is present and unchanged.
        for key in LEGACY_KEYS:
            assert body[key] == expected_legacy[key], key

        # New, additive-only envelope.
        assert "result" in body
        assert body["result"]["kind"] == "full_profile"
        assert set(body.keys()) - LEGACY_KEYS - {"result"} == set()

    async def test_get_analysis_matches_post(
        self, client, db_session, two_orgs, auth_headers, tmp_path
    ):
        df = _fixture_df()
        ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, df)
        post_resp = await client.post(
            f"/api/v1/datasets/{ds.id}/analysis", json={"analysis_type": "full"},
            headers=auth_headers["a"],
        )
        assert post_resp.status_code == 200

        get_resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])
        assert get_resp.status_code == 200
        assert get_resp.json() == post_resp.json()


class TestContractShape:
    def test_full_profile_contract_fields(self):
        df = _fixture_df()
        analysis = run_full_analysis(df.copy())
        contract = full_profile_to_contract(analysis)

        assert contract.kind == "full_profile"
        assert {c["name"] for c in contract.columns} == set(analysis["type_map"].keys())
        assert contract.rows == []
        assert contract.meta["method"] == "full_profile"
        assert contract.meta["detail"]["overview"] == analysis["overview"]
        assert "type_map" not in contract.meta["detail"]

    def test_as_response_is_additive_and_byte_preserves_legacy(self):
        df = _fixture_df()
        analysis = run_full_analysis(df.copy())
        response = as_response(analysis)

        for key, value in analysis.items():
            assert response[key] == value
        assert response["result"]["columns"]
        assert isinstance(response["result"]["warnings"], list)

    def test_safe_clean_strips_numpy_scalars(self):
        import numpy as np

        dirty = {"a": np.int64(3), "b": np.float64(1.5), "c": np.float64("nan"),
                  "d": [np.bool_(True)], "e": float("nan")}
        clean = safe_clean(dirty)
        assert clean == {"a": 3, "b": 1.5, "c": None, "d": [True], "e": None}
        assert isinstance(clean["a"], int) and not isinstance(clean["a"], np.integer)
