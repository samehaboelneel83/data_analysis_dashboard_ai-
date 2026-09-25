import pytest

from app.models.models import CustomConnector
from app.services.custom_connectors import (
    CustomConnectorError, validate_custom_connector_def, apply_preset_locks,
)
from app.services import connectors


class TestValidateCustomConnectorDef:
    def test_unknown_base_type_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="Unknown connector type"):
            validate_custom_connector_def("not-a-real-type", {}, [])

    def test_base_config_key_not_on_the_base_type_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="Unknown config field"):
            validate_custom_connector_def("postgresql", {"not_a_field": "x"}, [])

    def test_locked_field_not_on_the_base_type_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="Unknown locked field"):
            validate_custom_connector_def("postgresql", {"host": "h"}, ["not_a_field"])

    def test_locked_field_with_no_base_config_value_is_rejected(self):
        with pytest.raises(CustomConnectorError, match="no value to lock"):
            validate_custom_connector_def("postgresql", {"host": "h"}, ["port"])

    def test_a_valid_definition_passes(self):
        validate_custom_connector_def("postgresql", {"host": "db.acme.internal", "port": 5432},
                                       ["host", "port"])


class TestApplyPresetLocks:
    def _preset(self, base_type="postgresql", base_config=None, locked_fields=None):
        return CustomConnector(id=1, org_id=1, key="acme-pg", label="Acme Postgres",
                                base_type=base_type, base_config=base_config or {},
                                locked_fields=locked_fields or [])

    def test_locked_field_overrides_a_client_supplied_value(self):
        preset = self._preset(base_config={"host": "acme-prod.internal"}, locked_fields=["host"])

        result = apply_preset_locks({"host": "attacker-supplied", "user": "alice"}, preset)

        assert result == {"host": "acme-prod.internal", "user": "alice"}

    def test_non_locked_preset_value_is_a_default_only(self):
        preset = self._preset(base_config={"port": 5432}, locked_fields=[])

        with_override = apply_preset_locks({"port": 9999}, preset)
        without_override = apply_preset_locks({}, preset)

        assert with_override == {"port": 9999}
        assert without_override == {"port": 5432}

    def test_locked_secret_field_is_decrypted_before_merge(self):
        from app.services import secrets

        preset = self._preset(base_config={"password": secrets.encrypt_value("s3cret")},
                               locked_fields=["password"])

        result = apply_preset_locks({"password": "attacker-supplied"}, preset)

        assert result == {"password": "s3cret"}


class TestCatalogPayloadWithPresets:
    def test_no_presets_argument_reproduces_todays_output(self):
        assert connectors.catalog_payload() == connectors.catalog_payload(None)

    def test_a_preset_appears_as_a_custom_tile_with_locked_fields_filtered(self):
        preset = CustomConnector(id=7, org_id=1, key="acme-pg", label="Acme Postgres",
                                  base_type="postgresql", base_config={"host": "h", "port": 5432},
                                  locked_fields=["host"])

        payload = connectors.catalog_payload([preset])

        tile = next(t for t in payload if t.get("is_custom"))
        assert tile["key"] == "custom:7"
        assert tile["label"] == "Acme Postgres"
        assert tile["base_type"] == "postgresql"
        assert tile["custom_connector_id"] == 7
        field_names = {f["name"] for f in tile["config_fields"]}
        assert "host" not in field_names   # locked -- not shown
        assert "port" in field_names       # not locked -- still editable/visible

    def test_a_preset_with_an_unknown_base_type_is_skipped_not_crashed(self):
        preset = CustomConnector(id=8, org_id=1, key="stale", label="Stale",
                                  base_type="not-a-real-type", base_config={}, locked_fields=[])

        payload = connectors.catalog_payload([preset])

        assert not any(t.get("custom_connector_id") == 8 for t in payload)


async def _create_preset(client, headers, **overrides):
    body = {"key": "acme-pg", "label": "Acme Postgres", "base_type": "postgresql",
            "base_config": {"host": "acme-prod.internal", "port": 5432}, "locked_fields": ["host"]}
    body.update(overrides)
    return await client.post("/api/v1/custom-connectors", json=body, headers=headers)


class TestCustomConnectorsApi:
    async def test_create_requires_org_admin(self, client, db_session, two_orgs):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User

        role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=two_orgs["a"]["org"].id, role_id=role.id,
                    email="viewer-cc@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

        resp = await _create_preset(client, headers)

        assert resp.status_code == 403

    async def test_create_rejects_invalid_definition(self, client, db_session, two_orgs, auth_headers):
        resp = await _create_preset(client, auth_headers["a"], base_config={"not_a_field": "x"})
        assert resp.status_code == 400

    async def test_create_then_list_round_trips(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()
        # "host" is not one of postgresql's secret fields (only "password" is),
        # so it round-trips in plaintext -- unlike DataSource.config, nothing
        # here needs redacting for a non-secret field.
        assert created["base_config"]["host"] == "acme-prod.internal"

        resp = await client.get("/api/v1/custom-connectors", headers=auth_headers["a"])

        assert resp.status_code == 200
        assert [p["key"] for p in resp.json()] == ["acme-pg"]

    async def test_duplicate_key_in_same_org_is_rejected(self, client, db_session, two_orgs, auth_headers):
        await _create_preset(client, auth_headers["a"])

        resp = await _create_preset(client, auth_headers["a"])

        assert resp.status_code == 409

    async def test_same_key_in_different_orgs_is_allowed(self, client, db_session, two_orgs, auth_headers):
        await _create_preset(client, auth_headers["a"])

        resp = await _create_preset(client, auth_headers["b"])

        assert resp.status_code == 200

    async def test_org_b_cannot_see_org_a_presets(self, client, db_session, two_orgs, auth_headers):
        await _create_preset(client, auth_headers["a"])

        resp = await client.get("/api/v1/custom-connectors", headers=auth_headers["b"])

        assert resp.json() == []

    async def test_update_cross_org_returns_404(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()

        resp = await client.put(f"/api/v1/custom-connectors/{created['id']}",
                                 json={"label": "Hijacked"}, headers=auth_headers["b"])

        assert resp.status_code == 404

    async def test_delete_with_no_referencing_data_source_succeeds(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()

        resp = await client.delete(f"/api/v1/custom-connectors/{created['id']}", headers=auth_headers["a"])

        assert resp.status_code == 204

    async def test_delete_with_a_referencing_data_source_is_rejected(self, client, db_session, two_orgs, auth_headers):
        from app.models.models import DataSource

        created = (await _create_preset(client, auth_headers["a"])).json()
        ds = DataSource(name="uses preset", type="postgresql", config={},
                        org_id=two_orgs["a"]["org"].id, custom_connector_id=created["id"])
        db_session.add(ds)
        await db_session.commit()

        resp = await client.delete(f"/api/v1/custom-connectors/{created['id']}", headers=auth_headers["a"])

        assert resp.status_code == 409
        assert "1" in resp.json()["detail"]

    async def test_delete_cross_org_returns_404(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()

        resp = await client.delete(f"/api/v1/custom-connectors/{created['id']}", headers=auth_headers["b"])

        assert resp.status_code == 404
        still_there = await db_session.get(CustomConnector, created["id"])
        assert still_there is not None

    async def test_put_redaction_sentinel_for_secret_field_keeps_stored_value(self, client, db_session, two_orgs, auth_headers):
        from app.services import secrets

        created = (await _create_preset(client, auth_headers["a"],
                                         base_config={"host": "acme-prod.internal", "password": "hunter2"},
                                         locked_fields=["password"])).json()
        assert created["base_config"]["password"] == secrets.REDACTED

        resp = await client.put(f"/api/v1/custom-connectors/{created['id']}",
                                 json={"label": "Renamed", "base_config": {"host": "acme-prod.internal",
                                                                            "password": secrets.REDACTED}},
                                 headers=auth_headers["a"])

        assert resp.status_code == 200
        stored = await db_session.get(CustomConnector, created["id"])
        decrypted = secrets.decrypt_config(stored.base_config or {}, ["password"])
        assert decrypted["password"] == "hunter2"

    async def test_non_admin_forbidden_for_get_put_and_delete(self, client, db_session, two_orgs, auth_headers):
        from app.core.security import create_access_token, hash_password
        from app.models.models import Role, User

        created = (await _create_preset(client, auth_headers["a"])).json()

        role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer2", is_org_admin=False)
        db_session.add(role)
        await db_session.flush()
        user = User(org_id=two_orgs["a"]["org"].id, role_id=role.id,
                    email="viewer-cc-2@example.com", password_hash=hash_password("pw"))
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

        get_resp = await client.get("/api/v1/custom-connectors", headers=headers)
        put_resp = await client.put(f"/api/v1/custom-connectors/{created['id']}",
                                     json={"label": "x"}, headers=headers)
        delete_resp = await client.delete(f"/api/v1/custom-connectors/{created['id']}", headers=headers)

        assert get_resp.status_code == 403
        assert put_resp.status_code == 403
        assert delete_resp.status_code == 403

    async def test_wrong_id_and_wrong_org_404s_are_indistinguishable(self, client, db_session, two_orgs, auth_headers):
        created_b = (await _create_preset(client, auth_headers["b"])).json()
        nonexistent_id = created_b["id"] + 99999

        wrong_id_resp = await client.put(f"/api/v1/custom-connectors/{nonexistent_id}",
                                          json={"label": "x"}, headers=auth_headers["a"])
        wrong_org_resp = await client.put(f"/api/v1/custom-connectors/{created_b['id']}",
                                           json={"label": "x"}, headers=auth_headers["a"])

        assert wrong_id_resp.status_code == wrong_org_resp.status_code
        assert wrong_id_resp.json()["detail"] == wrong_org_resp.json()["detail"]

    async def test_update_with_invalid_definition_returns_400(self, client, db_session, two_orgs, auth_headers):
        created = (await _create_preset(client, auth_headers["a"])).json()

        resp = await client.put(f"/api/v1/custom-connectors/{created['id']}",
                                 json={"base_config": {"not_a_field": "x"}}, headers=auth_headers["a"])

        assert resp.status_code == 400
