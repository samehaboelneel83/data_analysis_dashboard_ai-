"""E3: OpenTelemetry, opt-in.

Three guarantees are pinned here: (1) disabled means otel is never even
imported -- a broken/absent otel install can't brick startup; (2) enabled
produces real spans, for both a plain HTTP request (auto-instrumentation)
and an agent graph node (manual span), with question/SQL attributes carried
ONLY as sha256 hashes, never as text; (3) a setup failure is swallowed, not
fatal.
"""
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, select, text

from app.core import telemetry
from app.core.config import settings
from app.main import app
from app.models.models import (AgentStep, DataSource, Organization, Role,
                               SourceColumn, SourceObject, User)
from app.services.agent import executor
from app.services.agent.graph import run_agent

from .test_agent_graph import NOT_AMBIGUOUS, ONE_STEP, ScriptedClient


def test_disabled_never_imports_otel():
    """With settings.otel_enabled False (the default), importing app.main and
    running setup_telemetry must never pull `opentelemetry` into sys.modules.
    Run in a subprocess so this can't be polluted by other tests in this same
    file enabling telemetry earlier in the same pytest session."""
    code = (
        "import sys; "
        "assert 'opentelemetry' not in sys.modules; "
        "from app.main import app; "
        "assert 'opentelemetry' not in sys.modules, "
        "'app.main import triggered an otel import while disabled'; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_setup_failure_does_not_brick_startup(monkeypatch):
    """A broken otel install/config (any exception inside _setup_enabled)
    must be caught and logged, never raised -- setup_telemetry must return
    normally so app startup continues."""
    monkeypatch.setattr(settings, "otel_enabled", True)

    def _boom(app):
        raise RuntimeError("simulated otel setup failure")

    monkeypatch.setattr(telemetry, "_setup_enabled", _boom)
    telemetry.setup_telemetry(app)  # must not raise


@pytest.fixture(scope="module")
def _otel_enabled():
    """Enables real otel instrumentation for this module's tests only.
    Module-scoped so FastAPIInstrumentor/SQLAlchemyInstrumentor.instrument()
    -- which are not safely re-entrant against the same app/engine -- run
    exactly once."""
    prior_enabled, prior_endpoint = settings.otel_enabled, settings.otel_endpoint
    settings.otel_enabled = True
    settings.otel_endpoint = None  # console exporter branch
    # In the full suite, other test modules' `client` fixture has already sent
    # a request through `app` by the time this module runs, which makes
    # Starlette cache and freeze its middleware stack -- add_middleware()
    # (called by FastAPIInstrumentor.instrument_app) then raises "Cannot add
    # middleware after an application has started". Production never hits
    # this: setup_telemetry runs at import time, before any request. Here the
    # cached stack just needs invalidating so it rebuilds (with the new otel
    # middleware included) on the next request.
    app.middleware_stack = None
    telemetry.setup_telemetry(app)
    assert not isinstance(telemetry.tracer, telemetry._NullTracer), (
        "setup_telemetry did not install a real tracer")
    yield
    settings.otel_enabled, settings.otel_endpoint = prior_enabled, prior_endpoint


@pytest.fixture
def memory_exporter(_otel_enabled):
    """An in-memory span exporter attached to the CURRENT global tracer
    provider (opentelemetry only allows the global provider to be set once
    per process, so this must look it up live rather than trust a locally
    held reference)."""
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import \
        InMemorySpanExporter

    exporter = InMemorySpanExporter()
    otel_trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_enabled_emits_span_for_http_request(client, memory_exporter):
    resp = await client.get("/health")
    assert resp.status_code == 200
    spans = memory_exporter.get_finished_spans()
    assert spans, "no spans captured for the HTTP request"
    assert any("health" in (s.name or "").lower()
               or s.attributes.get("http.target") == "/health"
               or s.attributes.get("http.route") == "/health"
               for s in spans)


async def test_embed_token_never_reaches_exported_span_attributes(client, memory_exporter):
    """GET /api/v1/embed/report?token=<JWT> carries a live, up-to-24h
    host-signed credential in its query string. FastAPIInstrumentor's ASGI
    layer records the full URL (incl. query string) as http.url/http.target
    with no sanitizer for arbitrary param names -- the _QuerystringScrubber
    SpanProcessor must strip it from EVERY span before it can be exported,
    regardless of route."""
    resp = await client.get("/api/v1/embed/report", params={"token": "abc"})
    assert resp.status_code != 500

    spans = memory_exporter.get_finished_spans()
    assert spans, "no spans captured for the embed request"
    # No attribute anywhere carries the token value.
    for span in spans:
        for key, value in span.attributes.items():
            if isinstance(value, str):
                assert "abc" not in value, f"{key}={value!r} leaked the embed token"
    # The specific attributes the ASGI layer records the raw URL/path onto
    # must have their query string stripped entirely (not merely the token).
    url_spans = [s for s in spans
                if s.attributes.get("http.url") or s.attributes.get("http.target")]
    assert url_spans, "no span carried http.url/http.target to check"
    for span in url_spans:
        for key in ("http.url", "http.target"):
            value = span.attributes.get(key)
            if isinstance(value, str):
                assert "?" not in value, f"{key}={value!r} still carries a query string"


@pytest.fixture
async def world(db_session, tmp_path, monkeypatch):
    """Minimal single-org, single-source world -- same shape as
    test_agent_graph.world, kept local so this file doesn't depend on another
    test module's fixture wiring beyond the client script it reuses."""
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    role = Role(name="analyst", org_id=org.id)
    db_session.add(role)
    await db_session.flush()
    user = User(email="a@corp.com", password_hash="x", org_id=org.id, role_id=role.id)
    user.role = role
    db_session.add(user)

    path = tmp_path / "shop.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL, region TEXT)"))
        conn.execute(text("INSERT INTO orders VALUES (1, 10, 'west'), (2, 20, 'east')"))
    monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)

    ds = DataSource(name="shop", type="sqlite", org_id=org.id, config={"filepath": str(path)})
    db_session.add(ds)
    await db_session.flush()
    obj = SourceObject(data_source_id=ds.id, org_id=org.id, name="orders", kind="table")
    db_session.add(obj)
    await db_session.flush()
    for name, dtype in [("id", "integer"), ("total", "numeric"), ("region", "text")]:
        db_session.add(SourceColumn(source_object_id=obj.id, name=name, dtype=dtype))
    await db_session.commit()
    yield {"org": org, "user": user, "ds": ds}
    eng.dispose()


async def test_enabled_agent_node_span_hash_only_attributes(db_session, world, memory_exporter):
    question = "total sales"
    sql = "SELECT sum(total) AS total FROM orders"
    llm_client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[{"sql": sql}])

    run = await run_agent(db_session, question=question, source=world["ds"],
                          user=world["user"], client=llm_client)
    await db_session.commit()
    assert run.status == "ok"

    spans = memory_exporter.get_finished_spans()
    node_spans = [s for s in spans if s.name == "agent.node"]
    assert len(node_spans) == 1
    span = node_spans[0]
    attrs = dict(span.attributes)

    assert attrs["run_id"] == run.id
    assert attrs["node"] == "s1"
    assert attrs["status"] == "ok"
    assert isinstance(attrs["ms"], int)

    # Hash-only discipline: sha256 hex digests present, raw text absent from
    # every attribute value anywhere on the span.
    import hashlib
    assert attrs["question_hash"] == hashlib.sha256(question.encode()).hexdigest()
    assert attrs["sql_hash"] == hashlib.sha256(sql.encode()).hexdigest()
    for value in attrs.values():
        if isinstance(value, str):
            assert question not in value
            assert sql not in value

    steps = (await db_session.execute(select(AgentStep))).scalars().all()
    assert steps[0].sql == sql  # DB row keeps the SQL -- only the SPAN is hash-only
