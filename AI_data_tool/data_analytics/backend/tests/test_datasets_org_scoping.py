import pytest
from sqlalchemy import select
from app.models.models import Dataset


async def _seed_dataset(db_session, org_id, name="Test Dataset"):
    ds = Dataset(name=name, org_id=org_id, filename=None)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_list_datasets_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    await _seed_dataset(db_session, two_orgs["a"]["org"].id, "A's dataset")
    await _seed_dataset(db_session, two_orgs["b"]["org"].id, "B's dataset")

    resp = await client.get("/api/v1/datasets", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert names == ["A's dataset"]


async def test_get_dataset_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_dataset_same_org_succeeds(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json()["id"] == ds.id


async def test_upload_dataset_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "upload_dir", str(tmp_path))

    resp = await client.post(
        "/api/v1/datasets",
        files={"file": ("test.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
        data={"name": "Uploaded Dataset", "description": ""},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    dataset_id = resp.json()["id"]
    result = await db_session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ds = result.scalar_one()
    assert ds.org_id == two_orgs["a"]["org"].id


async def test_delete_dataset_cross_org_returns_404_and_does_not_delete(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    resp = await client.delete(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
    result = await db_session.execute(select(Dataset).where(Dataset.id == ds.id))
    assert result.scalar_one_or_none() is not None  # still exists


async def test_sub_resource_endpoints_are_org_scoped(client, db_session, two_orgs, auth_headers):
    """Parametrized-in-spirit check that the identical check_org pattern was actually
    applied to the calculated-columns/column-formats/filter sub-resource endpoints,
    not just copy-pasted incorrectly onto some of them."""
    ds = await _seed_dataset(db_session, two_orgs["b"]["org"].id)

    save_resp = await client.put(
        f"/api/v1/datasets/{ds.id}/calculated-columns",
        json={"name": "calc1", "expression": "1+1"},
        headers=auth_headers["a"],
    )
    assert save_resp.status_code == 404

    formats_resp = await client.get(f"/api/v1/datasets/{ds.id}/column-formats", headers=auth_headers["a"])
    assert formats_resp.status_code == 404

    filter_resp = await client.patch(
        f"/api/v1/datasets/{ds.id}/filter", json={"expression": "a > 1"}, headers=auth_headers["a"],
    )
    assert filter_resp.status_code == 404


async def test_list_datasets_requires_authentication(client, db_session):
    resp = await client.get("/api/v1/datasets")
    assert resp.status_code == 401


# ── What a dataset read tells the client its columns MEAN ────────────────────

@pytest.mark.asyncio
class TestResolvedMeaningOnTheDatasetPayload:
    """The builder draws the chart, so the builder needs the labels. Resolved
    per dataset READ, never per widget request: widget data is the hottest path
    in the application and a description changes when somebody edits it, not
    when somebody clicks a bar.
    """

    async def _described(self, db, org, user_id=None):
        from app.models.models import (Dataset, DatasetColumn, DataSource,
                                       Entity, SourceColumn, SourceObject)
        from app.services import knowledge

        src = DataSource(name="warehouse", type="postgresql", config={}, org_id=org.id)
        db.add(src)
        await db.flush()
        obj = SourceObject(data_source_id=src.id, org_id=org.id, name="orders",
                           kind="table")
        db.add(obj)
        await db.flush()
        db.add_all([
            SourceColumn(source_object_id=obj.id, name="status", dtype="integer",
                         description="Where the order is in fulfilment.",
                         enum_labels={"1": "new", "2": "paid"}),
            SourceColumn(source_object_id=obj.id, name="total", dtype="float",
                         comment="Order total, excluding tax."),
        ])
        db.add(Entity(org_id=org.id, data_source_id=src.id, name="order",
                      business_name="Order", grain="One row per order placed.",
                      primary_object="orders", source="confirmed"))
        await db.flush()

        ds = Dataset(name="Orders", org_id=org.id, mode="import",
                     data_source_id=src.id, source_table="orders",
                     created_by=user_id)
        db.add(ds)
        await db.flush()
        db.add_all([
            DatasetColumn(dataset_id=ds.id, name="status", dtype="numeric"),
            DatasetColumn(dataset_id=ds.id, name="total", dtype="numeric"),
        ])
        await db.flush()
        await knowledge.link_columns(db, ds)
        await db.commit()
        return ds

    async def test_reading_one_dataset_returns_its_meaning(
            self, client, auth_headers, db_session, two_orgs):
        ds = await self._described(db_session, two_orgs["a"]["org"])
        r = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["column_descriptions"]["status"] == "Where the order is in fulfilment."
        assert body["column_descriptions"]["total"] == "Order total, excluding tax."
        assert body["value_labels"]["status"] == {"1": "new", "2": "paid"}
        assert body["grain"] == "One row per order placed."
        assert body["business_name"] == "Order"

    async def test_the_list_stays_cheap_and_says_nothing(
            self, client, auth_headers, db_session, two_orgs):
        """A shelf of two hundred datasets must not each pay a catalog
        resolution to draw a list of names."""
        await self._described(db_session, two_orgs["a"]["org"])
        r = await client.get("/api/v1/datasets", headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert all(d["column_descriptions"] == {} for d in r.json())
        assert all(d["value_labels"] == {} for d in r.json())

    async def test_an_upload_reads_back_unchanged(
            self, client, auth_headers, db_session, two_orgs):
        from app.models.models import Dataset, DatasetColumn

        ds = Dataset(name="sheet", org_id=two_orgs["a"]["org"].id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        db_session.add(DatasetColumn(dataset_id=ds.id, name="total", dtype="numeric"))
        await db_session.commit()

        r = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["column_descriptions"] == {}
        assert r.json()["value_labels"] == {}
        assert r.json()["grain"] is None


@pytest.mark.asyncio
class TestDescribingAColumnWritesWhereItBelongs:
    """A column that came from a connected table is described ONCE, on the source
    catalog, and every dataset built from that table reads the same sentence.

    Writing the edit back onto the dataset row instead would recreate exactly the
    divergence the resolver exists to prevent: two datasets from one table, each
    describing `status` differently, with no way to tell which is current.
    """

    async def _linked(self, db, org):
        from app.models.models import (Dataset, DatasetColumn, DataSource,
                                       SourceColumn, SourceObject)
        from app.services import knowledge

        src = DataSource(name="warehouse", type="postgresql", config={}, org_id=org.id)
        db.add(src)
        await db.flush()
        obj = SourceObject(data_source_id=src.id, org_id=org.id, name="orders",
                           kind="table")
        db.add(obj)
        await db.flush()
        db.add(SourceColumn(source_object_id=obj.id, name="status", dtype="integer",
                            description="A guess.", description_source="inferred"))
        await db.flush()

        made = []
        for name in ("Orders A", "Orders B"):
            ds = Dataset(name=name, org_id=org.id, mode="import",
                         data_source_id=src.id, source_table="orders")
            db.add(ds)
            await db.flush()
            db.add(DatasetColumn(dataset_id=ds.id, name="status", dtype="numeric"))
            await db.flush()
            await knowledge.link_columns(db, ds)
            made.append(ds)
        await db.commit()
        return made

    async def test_describing_it_once_describes_it_for_every_dataset(
            self, client, auth_headers, db_session, two_orgs):
        from app.services import knowledge

        a, b = await self._linked(db_session, two_orgs["a"]["org"])
        # Ids captured BEFORE the request: the endpoint commits on this same
        # session, which expires every instance, and reading `b.id` afterwards
        # is a lazy refresh in a sync context -- MissingGreenlet, not a failure
        # anyone can read.
        a_id, b_id = a.id, b.id
        r = await client.patch(
            f"/api/v1/datasets/{a_id}/columns/status/description",
            json={"description": "Where the order is in fulfilment."},
            headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["written_to"] == "source"
        assert r.json()["shared"] is True

        # The other dataset, which nobody edited, now says the same thing.
        from app.models.models import Dataset as _Dataset
        db_session.expire_all()
        fresh = await db_session.get(_Dataset, b_id)
        other = await knowledge.for_dataset(db_session, fresh)
        assert other.column("status").description == "Where the order is in fulfilment."
        # And at the terminal rung, so no later sync may overwrite it.
        assert other.column("status").description_source == "confirmed"

    async def test_an_unlinked_column_writes_to_its_own_dataset(
            self, client, auth_headers, db_session, two_orgs):
        """An upload has nowhere else for the sentence to go."""
        from app.models.models import Dataset, DatasetColumn

        ds = Dataset(name="sheet", org_id=two_orgs["a"]["org"].id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        db_session.add(DatasetColumn(dataset_id=ds.id, name="total", dtype="numeric"))
        await db_session.commit()

        r = await client.patch(f"/api/v1/datasets/{ds.id}/columns/total/description",
                               json={"description": "Sum of the row."},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["written_to"] == "dataset"
        assert r.json()["shared"] is False

    async def test_a_column_this_role_may_not_see_is_not_found(
            self, client, auth_headers, db_session, two_orgs):
        """404, not 403: confirming the column exists is itself the leak."""
        from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn,
                                       Role, User)
        from app.core.security import create_access_token, hash_password

        org = two_orgs["a"]["org"]
        ds = Dataset(name="payroll", org_id=org.id, mode="import")
        db_session.add(ds)
        await db_session.flush()
        db_session.add(DatasetColumn(dataset_id=ds.id, name="salary", dtype="numeric"))
        role = Role(org_id=org.id, name="analyst", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id,
                                          denied_columns=["salary"]))
        user = User(org_id=org.id, role_id=role.id, email="a@example.com",
                    password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.flush()
        ds.created_by = user.id
        await db_session.commit()

        r = await client.patch(f"/api/v1/datasets/{ds.id}/columns/salary/description",
                               json={"description": "what they are paid"},
                               headers={"Authorization":
                                        f"Bearer {create_access_token(user.id, org.id)}"})
        assert r.status_code == 404

    async def test_another_org_cannot_reach_the_column(
            self, client, auth_headers, db_session, two_orgs):
        a, _ = await self._linked(db_session, two_orgs["a"]["org"])
        a_id = a.id
        r = await client.patch(f"/api/v1/datasets/{a_id}/columns/status/description",
                               json={"description": "mine now"},
                               headers=auth_headers["b"])
        assert r.status_code == 404
