from sqlalchemy import select

from app.models.models import CustomConnector, DataSource


async def _seed_preset(db_session, org_id, *, base_config=None, locked_fields=None):
    cc = CustomConnector(org_id=org_id, key="acme-pg", label="Acme Postgres", base_type="postgresql",
                          base_config=base_config or {"host": "acme-prod.internal", "port": 5432},
                          locked_fields=locked_fields if locked_fields is not None else ["host"])
    db_session.add(cc)
    await db_session.commit()
    await db_session.refresh(cc)
    return cc


class TestCreateFromPreset:
    async def test_locked_field_overrides_client_supplied_value(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)

        resp = await client.post("/api/v1/data-sources", headers=auth_headers["a"], json={
            "name": "Via preset", "type": "ignored-should-not-matter",
            "custom_connector_id": preset.id, "config": {"host": "attacker-supplied", "user": "alice"},
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "postgresql"
        assert body["custom_connector_id"] == preset.id
        assert body["custom_connector_label"] == "Acme Postgres"
        result = await db_session.execute(select(DataSource).where(DataSource.id == body["id"]))
        ds = result.scalar_one()
        assert ds.config["host"] == "acme-prod.internal"
        assert ds.config["user"] == "alice"

    async def test_cross_org_preset_id_is_rejected_and_does_not_leak_base_config(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)

        resp = await client.post("/api/v1/data-sources", headers=auth_headers["b"], json={
            "name": "Hijack attempt", "type": "postgresql", "custom_connector_id": preset.id, "config": {},
        })

        assert resp.status_code == 404
        assert "acme-prod.internal" not in resp.text

    async def test_non_locked_preset_value_is_a_default_only(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id, locked_fields=[])

        resp = await client.post("/api/v1/data-sources", headers=auth_headers["a"], json={
            "name": "Custom port", "type": "postgresql",
            "custom_connector_id": preset.id, "config": {"port": 9999},
        })

        result = await db_session.execute(select(DataSource).where(DataSource.id == resp.json()["id"]))
        assert result.scalar_one().config["port"] == 9999


class TestUpdateWithPreset:
    async def test_omitting_custom_connector_id_still_reapplies_existing_locks(self, client, db_session, two_orgs, auth_headers):
        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)
        ds = DataSource(name="Via preset", type="postgresql", config={"host": "acme-prod.internal", "user": "alice"},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=preset.id)
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        resp = await client.put(f"/api/v1/data-sources/{ds.id}", headers=auth_headers["a"], json={
            "config": {"host": "attacker-supplied", "user": "bob"},
        })

        assert resp.status_code == 200
        result = await db_session.execute(select(DataSource).where(DataSource.id == ds.id))
        refreshed = result.scalar_one()
        assert refreshed.config["host"] == "acme-prod.internal"
        assert refreshed.config["user"] == "bob"

    async def test_switching_to_a_cross_org_preset_is_rejected(self, client, db_session, two_orgs, auth_headers):
        preset_b = await _seed_preset(db_session, two_orgs["b"]["org"].id)
        ds = DataSource(name="A's connection", type="postgresql", config={}, org_id=two_orgs["a"]["org"].id)
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        resp = await client.put(f"/api/v1/data-sources/{ds.id}", headers=auth_headers["a"], json={
            "custom_connector_id": preset_b.id,
        })

        assert resp.status_code == 404

    async def test_changing_type_on_a_preset_attached_source_does_not_leak_the_locked_secret(self, client, db_session, two_orgs, auth_headers):
        from app.services import secrets as secrets_service

        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id,
                                     base_config={"host": "acme-prod.internal", "password": "SUPER-SECRET-PW"},
                                     locked_fields=["host", "password"])
        ds = DataSource(name="Via preset", type="postgresql",
                        config={"host": "acme-prod.internal", "password": secrets_service.encrypt_value("SUPER-SECRET-PW"), "user": "alice"},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=preset.id)
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        resp = await client.put(f"/api/v1/data-sources/{ds.id}", headers=auth_headers["a"], json={"type": "sqlite"})

        assert resp.status_code == 200
        assert "SUPER-SECRET-PW" not in resp.text
        result = await db_session.execute(select(DataSource).where(DataSource.id == ds.id))
        refreshed = result.scalar_one()
        assert refreshed.type == "postgresql"   # the preset's base_type wins, body.type is ignored
        assert refreshed.config.get("password") != "SUPER-SECRET-PW"   # still encrypted at rest, not plaintext

    async def test_name_only_update_does_not_change_type_or_touch_config(self, client, db_session, two_orgs, auth_headers):
        from app.services import secrets as secrets_service

        preset = await _seed_preset(db_session, two_orgs["a"]["org"].id)
        ds = DataSource(name="Via preset", type="postgresql",
                        config={"host": "acme-prod.internal", "password": secrets_service.encrypt_value("s3cret")},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=preset.id)
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        stored_before = dict(ds.config)

        resp = await client.put(f"/api/v1/data-sources/{ds.id}", headers=auth_headers["a"], json={"name": "Renamed"})

        assert resp.status_code == 200
        result = await db_session.execute(select(DataSource).where(DataSource.id == ds.id))
        refreshed = result.scalar_one()
        assert refreshed.type == "postgresql"
        assert refreshed.config == stored_before


class TestChangingPresetBaseTypeWhileInUse:
    async def test_changing_base_type_of_an_in_use_preset_is_rejected(self, client, db_session, two_orgs, auth_headers):
        from app.models.models import CustomConnector, DataSource

        preset = CustomConnector(org_id=two_orgs["a"]["org"].id, key="acme-pg", label="Acme Postgres",
                                  base_type="postgresql", base_config={"host": "h"}, locked_fields=["host"])
        db_session.add(preset)
        await db_session.commit()
        await db_session.refresh(preset)
        ds = DataSource(name="uses preset", type="postgresql", config={},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=preset.id)
        db_session.add(ds)
        await db_session.commit()

        resp = await client.put(f"/api/v1/custom-connectors/{preset.id}", headers=auth_headers["a"],
                                 json={"base_type": "sqlite", "base_config": {"path": "/x"}, "locked_fields": ["path"]})

        assert resp.status_code == 409
        result = await db_session.execute(select(CustomConnector).where(CustomConnector.id == preset.id))
        assert result.scalar_one().base_type == "postgresql"   # unchanged


class TestListConnectorsIncludesOrgPresets:
    async def test_catalog_includes_the_callers_org_preset(self, client, db_session, two_orgs, auth_headers):
        await _seed_preset(db_session, two_orgs["a"]["org"].id)

        resp = await client.get("/api/v1/data-sources/connectors", headers=auth_headers["a"])

        assert any(t.get("is_custom") for t in resp.json())

    async def test_catalog_excludes_other_orgs_presets(self, client, db_session, two_orgs, auth_headers):
        await _seed_preset(db_session, two_orgs["b"]["org"].id)

        resp = await client.get("/api/v1/data-sources/connectors", headers=auth_headers["a"])

        assert not any(t.get("is_custom") for t in resp.json())
