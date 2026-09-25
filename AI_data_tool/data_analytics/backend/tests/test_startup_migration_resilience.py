"""S5 review fix: a transient DB error during the enc:v1->v2 startup migration
must not brick app startup -- the migration is idempotent, so it simply
retries next boot. app.main._run_secrets_migration isolates the call in its
own try/except for exactly this."""
import logging

from app.main import _run_secrets_migration


async def test_startup_continues_when_migration_raises(monkeypatch, caplog):
    async def _boom(session):
        raise RuntimeError("transient DB error")

    monkeypatch.setattr("app.services.secrets.migrate_v1_to_v2", _boom)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        await _run_secrets_migration(session=None)   # must not raise

    assert any("migration failed" in r.message for r in caplog.records)


async def test_startup_logs_the_migrated_count_on_success(monkeypatch, caplog):
    async def _ok(session):
        return 3

    monkeypatch.setattr("app.services.secrets.migrate_v1_to_v2", _ok)

    with caplog.at_level(logging.INFO, logger="app.main"):
        await _run_secrets_migration(session=None)

    assert any("3 data source" in r.message for r in caplog.records)
