"""Layer 1 routes: org scoping, admin gating, and the review round trip.

The scoping tests are the ones that matter most. Every route here exposes
catalog structure — table names, column names, sample-derived value lists — and
a leak across an org boundary hands one tenant a map of another's database.

The project's convention is 404 rather than 403 for a cross-org object, because
403 would itself confirm the object exists. These tests assert 404 specifically.
"""
import pytest
from sqlalchemy import select

from app.models.models import (ColumnStats, Dataset, DataSource, DatasetColumn,
                               Relationship, Role, SourceColumn, SourceObject,
                               SourceRelationship, User)
from app.services.metadata import store


@pytest.fixture
async def seeded(db_session, two_orgs):
    """A data source with two tables in org A, and one in org B."""
    a, b = two_orgs["a"], two_orgs["b"]

    src_a = DataSource(name="wh-a", type="postgresql", org_id=a["org"].id)
    src_b = DataSource(name="wh-b", type="postgresql", org_id=b["org"].id)
    db_session.add_all([src_a, src_b])
    await db_session.flush()

    customers = Dataset(name="customers", org_id=a["org"].id, data_source_id=src_a.id)
    orders = Dataset(name="orders", org_id=a["org"].id, data_source_id=src_a.id)
    secret = Dataset(name="b_secrets", org_id=b["org"].id, data_source_id=src_b.id)
    db_session.add_all([customers, orders, secret])
    await db_session.flush()

    cust_id = DatasetColumn(dataset_id=customers.id, name="id", dtype="integer")
    status = DatasetColumn(dataset_id=customers.id, name="status", dtype="categorical")
    ord_cust = DatasetColumn(dataset_id=orders.id, name="customer_id", dtype="integer")
    db_session.add_all([cust_id, status, ord_cust])
    await db_session.flush()

    db_session.add(ColumnStats(
        dataset_column_id=status.id, null_ratio=0.0, distinct_count=2,
        top_k=[{"value": "active", "count": 80, "ratio": 0.8},
               {"value": "churned", "count": 20, "ratio": 0.2}],
        exact=False,
    ))

    # The source catalog: what the CONNECTION can see, which is what the review
    # endpoints serve. Deliberately includes a table nobody made a dataset from,
    # because those are the ones a newcomer most needs told about.
    obj_customers = SourceObject(data_source_id=src_a.id, org_id=a["org"].id,
                                 name="customers", kind="table")
    obj_orders = SourceObject(data_source_id=src_a.id, org_id=a["org"].id,
                              name="orders", kind="table")
    obj_audit = SourceObject(data_source_id=src_a.id, org_id=a["org"].id,
                             name="audit_log", kind="table")
    obj_theirs = SourceObject(data_source_id=src_b.id, org_id=b["org"].id,
                              name="b_secrets", kind="table")
    db_session.add_all([obj_customers, obj_orders, obj_audit, obj_theirs])
    await db_session.flush()

    col_cust_id = SourceColumn(source_object_id=obj_customers.id, name="id",
                               position=0, dtype="integer", is_primary_key=True)
    col_status = SourceColumn(source_object_id=obj_customers.id, name="status",
                              position=1, dtype="text",
                              description="A guessed description.",
                              description_source="inferred")
    col_ord_cust = SourceColumn(source_object_id=obj_orders.id, name="customer_id",
                                position=0, dtype="integer")
    db_session.add_all([col_cust_id, col_status, col_ord_cust])
    await db_session.flush()

    src_rel = SourceRelationship(
        data_source_id=src_a.id, org_id=a["org"].id,
        from_object_id=obj_orders.id, from_column="customer_id",
        to_object_id=obj_customers.id, to_column="id",
        source="inferred", confidence=0.92,
        evidence={"overlap": 0.92, "name_score": 1.0},
        cardinality="many_to_one",
    )
    db_session.add(src_rel)
    await db_session.commit()

    return {"src_a": src_a, "src_b": src_b, "customers": customers,
            "orders": orders, "secret": secret, "rel": src_rel,
            "status_col": col_status, "obj_customers": obj_customers,
            "obj_audit": obj_audit}


class TestOrgScoping:
    async def test_review_of_another_orgs_source_is_404(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_b'].id}/review",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_sync_of_another_orgs_source_is_404(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_b'].id}/sync",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_stats_of_another_orgs_dataset_is_404(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/datasets/{seeded['secret'].id}/columns/x/stats",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_drift_of_another_orgs_source_is_404(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_b'].id}/drift",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_cross_org_is_404_not_403(self, client, auth_headers, seeded):
        """403 would confirm the object exists, which is the leak the convention
        exists to close."""
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_b'].id}/review",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404
        assert "403" not in r.text

    async def test_unauthenticated_is_rejected(self, client, seeded):
        r = await client.get(f"/api/v1/data-sources/{seeded['src_a'].id}/review")
        assert r.status_code == 401


class TestReview:
    async def test_lists_inferred_relationships_with_evidence(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        body = r.json()
        rel = body["relationships"][0]
        assert rel["from_column"] == "customer_id"
        assert rel["needs_review"] is True
        assert rel["evidence"]["overlap"] == 0.92
        # Names, not just ids — the graph has to render labels.
        assert rel["from_dataset"] == "orders"
        assert rel["to_dataset"] == "customers"

    async def test_returns_every_table_the_connection_can_see(
        self, client, auth_headers, seeded
    ):
        """Including audit_log, which nobody imported as a dataset. A catalog
        limited to datasets would describe only what someone already knew
        about."""
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        assert {d["name"] for d in r.json()["datasets"]} == {
            "customers", "orders", "audit_log"}

    async def test_confirming_promotes_and_survives(self, client, auth_headers, seeded, db_session):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"relationship_ids": [seeded["rel"].id]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        assert r.json()["confirmed"] == 1

        await db_session.refresh(seeded["rel"])
        assert seeded["rel"].source == "confirmed"
        assert seeded["rel"].confidence == 1.0

    async def test_confirmed_items_no_longer_need_review(self, client, auth_headers, seeded):
        await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"relationship_ids": [seeded["rel"].id]},
            headers=auth_headers["a"],
        )
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        assert r.json()["relationships"][0]["needs_review"] is False

    async def test_rejecting_deletes_so_it_is_not_re_proposed(
        self, client, auth_headers, seeded, db_session
    ):
        """A rejected proposal left in place would be re-proposed by the next
        sync, and the user would spend every morning rejecting it again."""
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"rejected_relationship_ids": [seeded["rel"].id]},
            headers=auth_headers["a"],
        )
        assert r.json()["rejected"] == 1
        rows = (await db_session.execute(select(SourceRelationship))).scalars().all()
        assert rows == []

    async def test_editing_a_description_marks_it_confirmed(
        self, client, auth_headers, seeded, db_session
    ):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"column_updates": [
                {"id": seeded["status_col"].id, "description": "Lifecycle state"}
            ]},
            headers=auth_headers["a"],
        )
        assert r.json()["columns_updated"] == 1
        await db_session.refresh(seeded["status_col"])
        assert seeded["status_col"].description == "Lifecycle state"
        assert seeded["status_col"].description_source == "confirmed"

    async def test_cannot_confirm_another_orgs_relationship(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"relationship_ids": [seeded["rel"].id]},
            headers=auth_headers["b"],
        )
        assert r.status_code == 404


class TestCanonicalFlag:
    """T1 — an admin's assertion that an object is the source of truth for
    what it describes (agent/nodes/generate.py's canonical preference)."""

    async def test_review_exposes_is_canonical(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        assert all("is_canonical" in d for d in r.json()["datasets"])
        assert next(d for d in r.json()["datasets"]
                    if d["id"] == seeded["obj_customers"].id)["is_canonical"] is False

    async def test_toggling_it_on_round_trips(self, client, auth_headers, seeded, db_session):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"object_updates": [
                {"id": seeded["obj_customers"].id, "is_canonical": True}
            ]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        assert r.json()["columns_updated"] == 1

        await db_session.refresh(seeded["obj_customers"])
        assert seeded["obj_customers"].is_canonical is True

        r2 = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        row = next(d for d in r2.json()["datasets"] if d["id"] == seeded["obj_customers"].id)
        assert row["is_canonical"] is True

    async def test_toggling_it_off_round_trips(self, client, auth_headers, seeded, db_session):
        seeded["obj_customers"].is_canonical = True
        await db_session.commit()

        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"object_updates": [
                {"id": seeded["obj_customers"].id, "is_canonical": False}
            ]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        await db_session.refresh(seeded["obj_customers"])
        assert seeded["obj_customers"].is_canonical is False

    async def test_cannot_toggle_another_orgs_object(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"object_updates": [
                {"id": seeded["obj_customers"].id, "is_canonical": True}
            ]},
            headers=auth_headers["b"],
        )
        assert r.status_code == 404


class TestEnumLabels:
    """T2 — what a coded column's values MEAN, editable by a human and never
    overwritten by a later sync once confirmed."""

    async def test_setting_labels_marks_them_confirmed(
        self, client, auth_headers, seeded, db_session
    ):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"column_updates": [
                {"id": seeded["status_col"].id,
                 "enum_labels": {"active": "Currently subscribed", "churned": "Left"}}
            ]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        await db_session.refresh(seeded["status_col"])
        assert seeded["status_col"].enum_labels == {
            "active": "Currently subscribed", "churned": "Left"}
        assert seeded["status_col"].enum_labels_source == "confirmed"

    async def test_review_exposes_enum_labels(self, client, auth_headers, seeded, db_session):
        seeded["status_col"].enum_labels = {"active": "Currently subscribed"}
        seeded["status_col"].enum_labels_source = "confirmed"
        await db_session.commit()

        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        col = next(c for c in r.json()["columns"] if c["id"] == seeded["status_col"].id)
        assert col["enum_labels"] == {"active": "Currently subscribed"}
        assert col["enum_labels_source"] == "confirmed"

    async def test_a_non_string_label_is_422(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"column_updates": [
                {"id": seeded["status_col"].id, "enum_labels": {"active": 1}}
            ]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422

    async def test_too_many_labels_is_422(self, client, auth_headers, seeded):
        too_many = {str(i): f"label {i}" for i in range(25)}
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"column_updates": [
                {"id": seeded["status_col"].id, "enum_labels": too_many}
            ]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422

    async def test_a_non_object_value_is_422(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"column_updates": [
                {"id": seeded["status_col"].id, "enum_labels": ["not", "an", "object"]}
            ]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422


class TestAdminGating:
    async def _demote(self, db_session, user):
        role = await db_session.get(Role, user.role_id)
        role.is_org_admin = False
        await db_session.commit()

    async def test_sync_requires_admin(self, client, auth_headers, seeded, db_session, two_orgs):
        await self._demote(db_session, two_orgs["a"]["user"])
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/sync",
            headers=auth_headers["a"],
        )
        assert r.status_code == 403

    async def test_confirm_requires_admin(self, client, auth_headers, seeded, db_session, two_orgs):
        await self._demote(db_session, two_orgs["a"]["user"])
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review/confirm",
            json={"relationship_ids": [seeded["rel"].id]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 403

    async def test_reading_the_review_queue_does_not_require_admin(
        self, client, auth_headers, seeded, db_session, two_orgs
    ):
        """Report authors need to SEE the model to build against it."""
        await self._demote(db_session, two_orgs["a"]["user"])
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/review",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200


class TestColumnStats:
    async def test_returns_top_k(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/datasets/{seeded['customers'].id}/columns/status/stats",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["profiled"] is True
        assert [e["value"] for e in body["top_k"]] == ["active", "churned"]

    async def test_reports_whether_the_numbers_are_exact(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/datasets/{seeded['customers'].id}/columns/status/stats",
            headers=auth_headers["a"],
        )
        assert r.json()["exact"] is False

    async def test_an_unprofiled_column_is_not_an_error(self, client, auth_headers, seeded):
        """Statistics arrive with the first sync; asking before then is normal."""
        r = await client.get(
            f"/api/v1/datasets/{seeded['customers'].id}/columns/id/stats",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        assert r.json()["profiled"] is False

    async def test_a_missing_column_is_404(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/datasets/{seeded['customers'].id}/columns/nope/stats",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404


class TestSyncStatus:
    async def test_never_run_is_reported_not_404(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/sync/latest",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        assert r.json()["status"] == "never_run"

    async def test_drift_history_is_empty_before_any_sync(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/drift",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        assert r.json() == []


class TestGlossary:
    """T3 — admin CRUD for the business glossary, org-scoped like every other
    Layer 1 route."""

    async def test_create_round_trips(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "GMV", "definition": "Gross merchandise value.",
                 "synonyms": ["إجمالي المبيعات", "gross sales"],
                 "maps_to_object": "orders", "maps_to_column": "total"},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        body = r.json()
        assert body["term"] == "GMV"
        assert body["synonyms"] == ["إجمالي المبيعات", "gross sales"]
        assert body["maps_to_object"] == "orders"

        r2 = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            headers=auth_headers["a"],
        )
        assert r2.status_code == 200
        assert [t["term"] for t in r2.json()] == ["GMV"]

    async def test_empty_term_is_422(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "   "},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422

    async def test_missing_term_is_422(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422

    async def test_a_blank_synonym_is_422(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "GMV", "synonyms": ["ok", "   "]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422

    async def test_a_non_string_synonym_is_422(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "GMV", "synonyms": [123]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 422

    async def test_non_admin_cannot_create(self, client, auth_headers, seeded,
                                           two_orgs, db_session):
        role = await db_session.get(Role, two_orgs["a"]["user"].role_id)
        role.is_org_admin = False
        await db_session.commit()
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "GMV"},
            headers=auth_headers["a"],
        )
        assert r.status_code == 403

    async def test_delete_round_trips(self, client, auth_headers, seeded, db_session):
        created = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "GMV"},
            headers=auth_headers["a"],
        )
        term_id = created.json()["id"]
        r = await client.delete(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary/{term_id}",
            headers=auth_headers["a"],
        )
        assert r.status_code == 204
        remaining = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            headers=auth_headers["a"],
        )
        assert remaining.json() == []

    async def test_org_wide_term_loads_for_the_source(self, client, auth_headers,
                                                       seeded, db_session):
        """data_source_id NULL — an org-wide term still shows up when listing
        one specific source's glossary."""
        from app.models.models import GlossaryTerm
        db_session.add(GlossaryTerm(org_id=seeded["src_a"].org_id,
                                    data_source_id=None, term="ARR",
                                    definition="Annual recurring revenue."))
        await db_session.commit()
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            headers=auth_headers["a"],
        )
        assert "ARR" in [t["term"] for t in r.json()]

    async def test_glossary_of_another_orgs_source_is_404(self, client, auth_headers, seeded):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_b'].id}/glossary",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_creating_on_another_orgs_source_is_404(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_b'].id}/glossary",
            json={"term": "GMV"},
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_deleting_another_orgs_term_is_404(self, client, auth_headers, seeded):
        created = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary",
            json={"term": "GMV"},
            headers=auth_headers["a"],
        )
        term_id = created.json()["id"]
        r = await client.delete(
            f"/api/v1/data-sources/{seeded['src_a'].id}/glossary/{term_id}",
            headers=auth_headers["b"],
        )
        assert r.status_code == 404


class TestEntities:
    """Task R3 / spec section 5 (E2) — list/confirm/edit for named business
    objects, org-scoped like every other Layer 1 route."""

    @pytest.fixture
    async def with_entity(self, db_session, seeded):
        from app.models.models import Entity
        entity = Entity(
            org_id=seeded["src_a"].org_id, data_source_id=seeded["src_a"].id,
            name="customer", business_name="Customer",
            grain="One row per customer.",
            description="A person who placed orders.",
            primary_object="customers", source="inferred",
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    async def test_list_returns_the_drafted_row(self, client, auth_headers, seeded, with_entity):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities",
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["name"] == "customer"
        assert body[0]["source"] == "inferred"
        assert body[0]["grain"] == "One row per customer."

    async def test_confirm_flips_provenance(self, client, auth_headers, seeded, with_entity):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities/confirm",
            json={"updates": [{"id": with_entity.id, "confirm": True}]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200
        assert r.json()["updated"] == 1

        listed = await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities",
            headers=auth_headers["a"],
        )
        assert listed.json()[0]["source"] == "confirmed"

    async def test_editing_a_field_also_confirms_it(self, client, auth_headers, seeded, with_entity):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities/confirm",
            json={"updates": [{"id": with_entity.id, "business_name": "Buyer"}]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 200

        listed = (await client.get(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities",
            headers=auth_headers["a"],
        )).json()
        assert listed[0]["business_name"] == "Buyer"
        assert listed[0]["source"] == "confirmed"

    async def test_non_admin_cannot_confirm(self, client, auth_headers, seeded,
                                            two_orgs, db_session, with_entity):
        role = await db_session.get(Role, two_orgs["a"]["user"].role_id)
        role.is_org_admin = False
        await db_session.commit()
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities/confirm",
            json={"updates": [{"id": with_entity.id, "confirm": True}]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 403

    async def test_entities_of_another_orgs_source_is_404(self, client, auth_headers, seeded, with_entity):
        r = await client.get(
            f"/api/v1/data-sources/{seeded['src_b'].id}/entities",
            headers=auth_headers["a"],
        )
        assert r.status_code == 404

    async def test_confirming_another_orgs_entity_is_404(self, client, auth_headers, seeded, with_entity):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_b'].id}/entities/confirm",
            json={"updates": [{"id": with_entity.id, "confirm": True}]},
            headers=auth_headers["b"],
        )
        assert r.status_code == 404

    async def test_confirming_a_nonexistent_entity_is_404(self, client, auth_headers, seeded):
        r = await client.post(
            f"/api/v1/data-sources/{seeded['src_a'].id}/entities/confirm",
            json={"updates": [{"id": 999999, "confirm": True}]},
            headers=auth_headers["a"],
        )
        assert r.status_code == 404
