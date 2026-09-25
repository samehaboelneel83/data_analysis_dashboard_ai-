"""An upload with a header and no rows is refused, and creates nothing."""
from sqlalchemy import func, select

from app.models.models import Dataset


async def test_header_only_csv_is_rejected_and_creates_nothing(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))
    before = (await db_session.execute(select(func.count()).select_from(Dataset))).scalar_one()

    resp = await client.post("/api/v1/datasets", files={"file": ("empty.csv", b"a,b,c\n", "text/csv")},
                             data={"name": "Empty", "description": ""}, headers=auth_headers["a"])

    assert resp.status_code == 400, resp.text
    assert "no data rows" in resp.json()["detail"]
    after = (await db_session.execute(select(func.count()).select_from(Dataset))).scalar_one()
    assert after == before
    # The list must still load for everyone.
    listing = await client.get("/api/v1/datasets", headers=auth_headers["a"])
    assert listing.status_code == 200
