"""QA E-14: a restricted reader's dataset counts are computed after row and
column security. EMEA saw "Columns 13 / Rows 2,000" while the Columns tab
showed 12 and the Data tab 514 -- revealing that a column is hidden and how
many rows exist in total."""
import pandas as pd

from app.core.security import create_access_token, hash_password
from app.models.models import ColumnSecurityRule, Dataset, DatasetColumn, Role, RowSecurityRule, User


async def _setup(db, org, tmp_path, *, rows_rule=True, cols_rule=True):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["EMEA", "EMEA", "APAC", "AMER", "AMER"],
                  "revenue": [1, 2, 3, 4, 5], "cost": [1, 1, 1, 1, 1]}).to_csv(p, index=False)
    ds = Dataset(name="Sales", filename=str(p), org_id=org.id, mode="import", row_count=5, col_count=3)
    db.add(ds)
    await db.flush()
    for c in ("region", "revenue", "cost"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    role = Role(org_id=org.id, name="EMEA", is_org_admin=False)
    db.add(role)
    await db.flush()
    if cols_rule:
        db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["cost"]))
    if rows_rule:
        db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'EMEA'"))
    user = User(org_id=org.id, role_id=role.id, email="emea@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    return ds, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def test_dataset_out_col_count_excludes_denied_columns(client, db_session, two_orgs, tmp_path):
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], tmp_path, rows_rule=False)
    one = (await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)).json()
    assert one["col_count"] == 2 == len(one["columns"])
    listed = next(d for d in (await client.get("/api/v1/datasets", headers=headers)).json() if d["id"] == ds.id)
    assert listed["col_count"] == 2
    assert not listed.get("row_count_restricted") and listed["row_count"] == 5


async def test_dataset_out_row_count_is_rls_filtered(client, db_session, two_orgs, auth_headers, tmp_path):
    ds, headers = await _setup(db_session, two_orgs["a"]["org"], tmp_path)
    one = (await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)).json()
    assert one["row_count"] == 2 and one["row_count_restricted"] is True
    listed = next(d for d in (await client.get("/api/v1/datasets", headers=headers)).json() if d["id"] == ds.id)
    assert listed["row_count"] == 2 and listed["row_count_restricted"] is True
    admin = (await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])).json()
    assert admin["row_count"] == 5 and admin["col_count"] == 3 and not admin.get("row_count_restricted")
