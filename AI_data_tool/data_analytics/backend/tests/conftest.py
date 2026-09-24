import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def _no_embeddings_backend_by_default(monkeypatch):
    """Task M2: compose enables Backend B by default (`EMBEDDING_BASE_URL`
    etc. on the `backend` service), so `docker compose exec backend pytest`
    inherits a REAL, reachable embeddings endpoint. Tests must stay
    deterministic (Backend A/lexical) unless a test opts in -- this resets
    the three embedding settings to unconfigured before every test; a test
    that wants Backend B calls its own `monkeypatch.setattr(retrieval.
    settings, ...)` afterward, which simply overrides this for that test."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "embedding_base_url", None)
    monkeypatch.setattr(settings, "embedding_model", None)
    monkeypatch.setattr(settings, "embedding_dim", None)


@pytest.fixture(autouse=True)
def _no_duckdb_pushdown_by_default(monkeypatch):
    """Pin `widget_duckdb_pushdown` OFF for the suite.

    No longer the shipping default -- that flipped to True on 2026-08-29 -- but
    still what most of this suite must run against: these tests assert on
    pandas-path internals, and the DuckDB path is a pre-aggregation in front of
    them that legitimately changes those internals without changing an answer.
    Pinning here keeps that distinction explicit instead of letting the
    production default decide which engine the assertions describe.

    Same reasoning as the embeddings fixture above: an ambient environment
    variable must not decide which engine the suite exercises. Tests that assert
    on pandas-path internals -- how many times `load_file` was called, the
    `executor` tag written to query_runs -- would otherwise pass or fail
    depending on how pytest happened to be invoked.

    `tests/test_duck_agg.py` opts in per test; that is the file that owns the
    DuckDB path's behaviour, and it verifies parity by running BOTH engines over
    the same fixture rather than trusting a global.

    To sweep the WHOLE suite through the DuckDB path -- which is how the
    `measure2` eligibility gap was found -- set
    `DATALYTICS_TEST_DUCKDB_PUSHDOWN=1`. That is deliberately a different
    variable from the production `WIDGET_DUCKDB_PUSHDOWN`: the production one
    configures a deployment and must not silently change what the suite tests,
    while this one says "I am testing the other engine on purpose".
    """
    import os

    from app.core.config import settings
    if os.environ.get("DATALYTICS_TEST_DUCKDB_PUSHDOWN") == "1":
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    else:
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)


@pytest_asyncio.fixture
async def db_session():
    """A fresh in-memory SQLite DB per test, with every model's table created.
    StaticPool keeps a single connection alive for the engine's lifetime — SQLite
    in-memory databases are otherwise per-connection and would vanish between
    queries under the default pool."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless asked, and this suite runs on SQLite
    # while production runs on Postgres -- which always enforces them. Without
    # this PRAGMA the two disagree on `ON DELETE CASCADE`: deleting a Report
    # leaves its parameters, share links, embed configs and schedules behind
    # here, and removes them there. Ten of the twelve tables that reference
    # `reports.id` have no ORM-level cascade and rely entirely on the database,
    # so a test suite with foreign keys off cannot see a cascade regression at
    # all -- it would report success for a delete that orphaned live rows.
    #
    # Verified 2026-08-28 on a two-table fixture: FKs off leaves the child row,
    # FKs on removes it.
    @sa_event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """An httpx.AsyncClient wired to the FastAPI app, with get_db overridden to
    yield the same db_session — lets a test seed data via the ORM and then hit
    the real HTTP endpoints against that same in-memory database."""
    async def _override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def two_orgs(db_session):
    """Two separate, fully-provisioned organizations for org-isolation tests."""
    from app.services.auth_provisioning import create_organization_with_admin

    org_a, role_a, user_a = await create_organization_with_admin(db_session, "Org A", "admin-a@example.com", "password-a")
    org_b, role_b, user_b = await create_organization_with_admin(db_session, "Org B", "admin-b@example.com", "password-b")
    await db_session.commit()
    return {
        "a": {"org": org_a, "role": role_a, "user": user_a},
        "b": {"org": org_b, "role": role_b, "user": user_b},
    }


@pytest_asyncio.fixture
async def auth_headers(two_orgs):
    """Bearer-token Authorization headers for org A's and org B's admin users."""
    from app.core.security import create_access_token

    return {
        "a": {"Authorization": f"Bearer {create_access_token(two_orgs['a']['user'].id, two_orgs['a']['user'].org_id)}"},
        "b": {"Authorization": f"Bearer {create_access_token(two_orgs['b']['user'].id, two_orgs['b']['user'].org_id)}"},
    }
