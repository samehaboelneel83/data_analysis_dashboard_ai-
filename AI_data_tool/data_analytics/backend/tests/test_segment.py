"""A2: KMeans segmentation with automatic k -- service-level fixture/degenerate
tests, an RLS pin mirroring test_analysis_rls.py's pattern, and a lazy-import
pin mirroring test_telemetry.py's test_disabled_never_imports_otel."""
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User
from app.services.analysis.segment import SegmentError, segment_dataframe


def _three_blobs(n_per_blob=50, seed=42):
    """Three well-separated 2D clusters -- centers 20 apart, std 1 -- so
    silhouette should cleanly prefer k=3 over any other candidate in 2..8."""
    rng = np.random.RandomState(seed)
    centers = [(0, 0), (20, 0), (0, 20)]
    rows = []
    for cx, cy in centers:
        xs = rng.normal(cx, 1.0, n_per_blob)
        ys = rng.normal(cy, 1.0, n_per_blob)
        rows.extend(zip(xs, ys))
    df = pd.DataFrame(rows, columns=["x", "y"])
    return df


def test_three_blob_fixture_finds_k_3():
    df = _three_blobs()
    contract = segment_dataframe(df)
    assert contract.kind == "segment"
    assert contract.meta["params"]["k"] == 3
    assert len(contract.meta["centroids"]) == 3
    assert contract.meta["sampled"] is False
    assert 0.0 < contract.meta["silhouette"] <= 1.0


def test_three_blob_fixture_labels_are_stable_across_runs():
    df = _three_blobs()
    labels_1 = [r["cluster"] for r in segment_dataframe(df, include_rows=True).rows]
    labels_2 = [r["cluster"] for r in segment_dataframe(df, include_rows=True).rows]
    assert labels_1 == labels_2


def test_default_response_carries_no_rows():
    """rows is opt-in (`include_rows=True`) -- the default response's rows
    list is empty; callers read the per-cluster centroid summary in meta."""
    df = _three_blobs()
    contract = segment_dataframe(df)
    assert contract.rows == []


def test_include_rows_returns_every_row_below_the_cap():
    df = _three_blobs()  # 150 rows, well under ROWS_RESPONSE_CAP (1000)
    contract = segment_dataframe(df, include_rows=True)
    assert len(contract.rows) == len(df)
    assert contract.meta["rows_truncated"] is False


def _big_two_blob_frame(n_per_blob=5100, seed=7):
    """>10,000 rows so FRAME_SAMPLE_THRESHOLD kicks in, and (after sampling
    to 10,000) still >ROWS_RESPONSE_CAP so include_rows truncation kicks in
    too. Two widely-separated blobs keep the clustering well-defined at any
    frame size."""
    rng = np.random.RandomState(seed)
    centers = [(0, 0), (30, 30)]
    rows = []
    for cx, cy in centers:
        xs = rng.normal(cx, 1.0, n_per_blob)
        ys = rng.normal(cy, 1.0, n_per_blob)
        rows.extend(zip(xs, ys))
    return pd.DataFrame(rows, columns=["x", "y"])


def test_large_frame_is_sampled_before_clustering():
    df = _big_two_blob_frame()
    assert len(df) > 10_000
    contract = segment_dataframe(df)
    assert contract.meta["sampled"] is True
    assert contract.meta["sample_size"] == 10_000
    assert contract.meta["n_rows_total"] == len(df)
    assert contract.meta["n_rows_used"] == 10_000
    assert contract.rows == []


def test_include_rows_caps_and_marks_truncation_on_a_large_frame():
    df = _big_two_blob_frame()
    contract = segment_dataframe(df, include_rows=True)
    assert len(contract.rows) == 1_000
    assert contract.meta["rows_truncated"] is True


def test_degenerate_single_numeric_column_raises():
    df = pd.DataFrame({"x": range(100)})
    with pytest.raises(SegmentError):
        segment_dataframe(df)


def test_degenerate_too_few_rows_raises():
    df = pd.DataFrame({"x": range(5), "y": range(5)})
    with pytest.raises(SegmentError):
        segment_dataframe(df)


async def test_router_400s_on_degenerate_input(client, db_session, tmp_path, auth_headers, two_orgs):
    csv_path = tmp_path / "tiny.csv"
    pd.DataFrame({"x": range(5), "y": range(5)}).to_csv(csv_path, index=False)
    ds = Dataset(name="Tiny", org_id=two_orgs["a"]["org"].id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/segment", json={}, headers=auth_headers["a"])
    assert resp.status_code == 400


async def _seed_dataset_with_file(db_session, tmp_path, org_id, df, name="Segment Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    df.to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id, rule_filter_expr):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


async def test_router_restricted_user_segments_only_their_rows(client, db_session, two_orgs, tmp_path):
    blobs = _three_blobs()
    blobs["region"] = "North"
    # South rows carry a value far outside anything in the blobs -- if it
    # leaked into a restricted user's result, this test would catch it.
    south = pd.DataFrame({"x": [99999.0] * 30, "y": [99999.0] * 30, "region": "South"})
    full = pd.concat([blobs, south], ignore_index=True)

    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, full)
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(f"/api/v1/datasets/{ds.id}/segment", json={"columns": ["x", "y"]}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "99999" not in resp.text
    assert body["meta"]["n_rows_total"] == len(blobs)  # South's 30 rows never reached the frame
    assert body["meta"]["params"]["k"] == 3
    assert body["rows"] == []  # include_rows defaults to False on the wire too


async def test_router_include_rows_flag_returns_labels(client, db_session, two_orgs, tmp_path, auth_headers):
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, _three_blobs())

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/segment",
        json={"columns": ["x", "y"], "include_rows": True},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 150
    assert body["meta"]["rows_truncated"] is False


def test_lazy_import_sklearn_not_pulled_in_at_app_import():
    """Mirrors test_telemetry.py's test_disabled_never_imports_otel: importing
    app.main must never pull sklearn into sys.modules -- it's imported lazily
    inside segment_dataframe on first use only."""
    code = (
        "import sys; "
        "assert 'sklearn' not in sys.modules; "
        "from app.main import app; "
        "assert 'sklearn' not in sys.modules, "
        "'app.main import triggered a sklearn import'; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
