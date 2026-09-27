"""Platform settings changed from the app (services/app_settings.py).

Every install-wide setting could only be changed in environment variables,
with a restart. Now a platform admin changes them on Admin -> Settings: the
value is validated with the setting's own type and bounds, stored (a secret
encrypted, and never sent back), applied at once, and audited by name.
"""
import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, settings
from app.models.models import AppSetting, AuditLogEntry
from app.services import app_settings, llm as llm_service

URL = "/api/v1/platform/settings"


@pytest.fixture(autouse=True)
def _platform_admin(monkeypatch):
    # Org A's admin (admin-a@example.com, from two_orgs) is the platform admin.
    monkeypatch.setattr(settings, "super_admin_emails", "admin-a@example.com")
    yield
    # The overrides live on the shared settings object: put them back.
    app_settings._apply({})
    app_settings._SEEN_STAMP = None


def _item(body, key):
    return next(s for c in body["categories"] for s in c["settings"] if s["key"] == key)


async def _put(client, headers, values):
    return await client.put(URL, headers=headers, json={"values": values})


class TestEverySettingIsOnThePage:
    def test_every_field_has_a_decision(self):
        """A new setting cannot be added without deciding how the page shows it."""
        assert set(Settings.model_fields) == set(app_settings.BY_KEY)
        assert {s.category for s in app_settings.SPECS} <= {c for c, _ in app_settings.CATEGORIES}

    def test_deploy_time_secrets_are_read_only(self):
        for key in ("database_url", "secret_key", "connector_secret_key", "super_admin_emails", "allowed_origins"):
            assert not app_settings.BY_KEY[key].editable, key


class TestWhoMaySee:
    async def test_an_org_admin_who_is_not_a_platform_admin_is_refused(self, client, two_orgs, auth_headers):
        assert (await client.get(URL, headers=auth_headers["b"])).status_code == 403
        assert (await _put(client, auth_headers["b"], {"llm_model": "x"})).status_code == 403
        assert (await client.post(URL + "/test-llm", headers=auth_headers["b"])).status_code == 403

    async def test_a_platform_admin_sees_every_category(self, client, two_orgs, auth_headers):
        r = await client.get(URL, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        keys = {s["key"] for c in r.json()["categories"] for s in c["settings"]}
        assert keys == set(Settings.model_fields)


class TestSecretsNeverLeave:
    async def test_no_secret_value_is_ever_sent(self, client, two_orgs, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "smtp_password", "hunter2-smtp")
        monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:db-pass-9@h/d")
        r = await client.get(URL, headers=auth_headers["a"])
        assert "hunter2-smtp" not in r.text and "db-pass-9" not in r.text
        pw = _item(r.json(), "smtp_password")
        assert pw["value"] is None and pw["is_set"] is True and pw["secret"] is True

    async def test_a_saved_secret_is_encrypted_used_and_not_returned(
            self, client, db_session, two_orgs, auth_headers):
        r = await _put(client, auth_headers["a"], {"llm_api_key": "sk-live-123"})
        assert r.status_code == 200, r.text
        assert "sk-live-123" not in r.text
        row = await db_session.get(AppSetting, "llm_api_key")
        assert row.value and row.value != "sk-live-123"            # encrypted at rest
        assert llm_service.get_client().api_key == "sk-live-123"   # and in use
        [entry] = (await db_session.execute(select(AuditLogEntry).where(
            AuditLogEntry.action == "platform.settings"))).scalars().all()
        assert entry.detail == "llm_api_key" and "sk-live" not in entry.detail


class TestSaving:
    async def test_a_change_applies_at_once_and_says_where_it_came_from(self, client, two_orgs, auth_headers):
        r = await _put(client, auth_headers["a"], {"llm_model": "qwen-next", "llm_timeout_s": 45})
        assert r.status_code == 200, r.text
        assert settings.llm_model == "qwen-next" and settings.llm_timeout_s == 45.0
        client_now = llm_service.get_client()
        assert (client_now.model, client_now.timeout) == ("qwen-next", 45.0)
        item = _item(r.json(), "llm_model")
        assert item["source"] == "saved" and item["updated_by"] == "admin-a@example.com"

    async def test_reset_puts_the_environment_value_back(self, client, db_session, two_orgs, auth_headers):
        before = settings.llm_model
        await _put(client, auth_headers["a"], {"llm_model": "temporary"})
        r = await _put(client, auth_headers["a"], {"llm_model": None})
        assert r.status_code == 200 and settings.llm_model == before
        assert _item(r.json(), "llm_model")["source"] == "environment"
        assert await db_session.get(AppSetting, "llm_model") is None

    @pytest.mark.parametrize("values, words", [
        ({"llm_timeout_s": -1}, "Request timeout"),
        ({"max_upload_mb": "lots"}, "Largest upload"),
        ({"max_upload_mb": 0}, "at least 1"),
        ({"smtp_port": 70000}, "at most 65535"),
        ({"rate_limit_bucket_cap": 0}, "Clients tracked"),
        ({"data_timezone": "Mars/Olympus"}, "not a time zone"),
        ({"llm_base_url": "ftp://models.local"}, "http(s)"),
        ({"llm_base_url": ""}, "cannot be empty"),
        ({"database_url": "sqlite://"}, "set by the deployment"),
        ({"no_such_setting": 1}, "is not a setting"),
    ])
    async def test_a_bad_value_is_refused_by_name(self, client, two_orgs, auth_headers, values, words):
        r = await _put(client, auth_headers["a"], values)
        assert r.status_code == 400 and words in r.json()["detail"], r.text

    async def test_one_bad_value_changes_nothing(self, client, db_session, two_orgs, auth_headers):
        before = settings.llm_model
        r = await _put(client, auth_headers["a"], {"llm_model": "would-be", "llm_timeout_s": 0})
        assert r.status_code == 400
        assert settings.llm_model == before
        assert (await db_session.execute(select(AppSetting))).first() is None

    async def test_a_startup_only_setting_says_it_needs_a_restart(self, client, two_orgs, auth_headers):
        r = await _put(client, auth_headers["a"], {"widget_work_max_concurrency": 6, "llm_model": "m"})
        assert r.json()["restart_required"] == ["widget_work_max_concurrency"]


class TestStartupAndOtherWorkers:
    async def test_saved_rows_are_applied_by_load(self, db_session):
        from app.services.secrets import encrypt_value
        db_session.add_all([AppSetting(key="import_row_cap", value=1234),
                            AppSetting(key="smtp_password", value=encrypt_value("pw-from-db"))])
        await db_session.commit()
        await app_settings.load(db_session)
        assert settings.import_row_cap == 1234 and settings.smtp_password == "pw-from-db"

    async def test_a_row_that_no_longer_validates_is_skipped_not_fatal(self, db_session):
        before = settings.max_upload_mb
        db_session.add_all([AppSetting(key="max_upload_mb", value=-5),
                            AppSetting(key="retired_setting", value=1),
                            AppSetting(key="database_url", value="sqlite://")])
        await db_session.commit()
        await app_settings.load(db_session)
        assert settings.max_upload_mb == before
        assert settings.database_url != "sqlite://"


class TestLlm:
    def test_the_api_key_is_sent_as_a_bearer_token(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        c = llm_service.LLMClient(base_url="http://m/v1", model="x", api_key="k1",
                                  transport=httpx.MockTransport(handler))
        assert c._headers()["Authorization"] == "Bearer k1"
        assert "Authorization" not in llm_service.LLMClient(base_url="http://m/v1", model="x")._headers()

    async def test_the_connection_test_uses_the_form_values(self, client, two_orgs, auth_headers, monkeypatch):
        used = {}

        async def fake_complete(self, messages, **kw):
            used.update(base=self.base_url, model=self.model, key=self.api_key)
            return "ok"
        monkeypatch.setattr(llm_service.LLMClient, "complete", fake_complete)
        r = await client.post(URL + "/test-llm", headers=auth_headers["a"],
                              json={"llm_base_url": "http://other:9000/v1", "llm_model": "m2", "llm_api_key": "k2"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert used == {"base": "http://other:9000/v1", "model": "m2", "key": "k2"}
        assert settings.llm_model != "m2"                           # testing does not save

    async def test_an_unreachable_endpoint_is_reported_not_raised(self, client, two_orgs, auth_headers, monkeypatch):
        async def fake_complete(self, messages, **kw):
            self.last_error = "connection refused"
            return None
        monkeypatch.setattr(llm_service.LLMClient, "complete", fake_complete)
        r = await client.post(URL + "/test-llm", headers=auth_headers["a"], json={})
        assert r.status_code == 200 and r.json() == {**r.json(), "ok": False, "detail": "connection refused"}
