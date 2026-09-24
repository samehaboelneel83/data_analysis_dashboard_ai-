"""E3: OpenTelemetry, opt-in (settings.otel_enabled, default False).

Hard no-op when disabled: `setup_telemetry` returns immediately without
importing anything from the `opentelemetry` package, and every otel import
anywhere in this module is LAZY -- pulled in only inside the enabled branch.
A broken or absent otel install can therefore never brick startup or import
time, and importing this module at all (as main.py and the manual-span call
sites do unconditionally) never touches otel.

Manual spans (agent graph nodes, DirectQuery execution, dataset refresh) go
through the module-level `tracer` below. Call sites must reference it as
`telemetry.tracer` (import the module, not the name) -- `setup_telemetry`
reassigns the module attribute when it enables real tracing, and a
`from .telemetry import tracer` at another module's import time would freeze
a stale reference to the disabled no-op tracer forever. When disabled,
`tracer` is a tiny pure-Python null object: `start_as_current_span` returns a
context manager whose `set_attribute` etc. are no-ops that never call into
the real otel API, so the hot path pays no cost and needs no otel install.

Failure isolation mirrors main.py's `_run_secrets_migration`: any otel
import/setup error is logged and swallowed here, never bricking startup.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class _NullSpan:
    """No-op span used whenever otel is disabled. Never imports or calls the
    real otel API."""

    def set_attribute(self, key, value) -> None:
        pass

    def record_exception(self, exc) -> None:
        pass

    def set_status(self, status) -> None:
        pass

    def __enter__(self) -> "_NullSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _NullTracer:
    """Zero-cost stand-in for `opentelemetry.trace.Tracer`, installed as the
    module-level `tracer` until (and unless) `setup_telemetry` enables real
    tracing. Every call site uses this exact same interface (`with
    tracer.start_as_current_span(name) as span: span.set_attribute(...)`)
    regardless of whether otel is actually enabled."""

    def start_as_current_span(self, name: str, **kwargs) -> _NullSpan:
        return _NullSpan()


class _NullInstrument:
    """No-op counter/histogram. Same interface as the otel instruments, so a
    call site never branches on whether metrics are enabled."""

    def add(self, amount, attributes=None) -> None:
        pass

    def record(self, amount, attributes=None) -> None:
        pass


class _NullMeter:
    """Zero-cost stand-in for `opentelemetry.metrics.Meter`, installed as the
    module-level `meter` until (and unless) `setup_telemetry` enables real
    metrics. Mirrors `_NullTracer` exactly, including the reassignment rule:
    call sites must use `telemetry.<instrument>`, never a `from` import."""

    def create_counter(self, name, unit="", description="") -> _NullInstrument:
        return _NullInstrument()

    def create_histogram(self, name, unit="", description="") -> _NullInstrument:
        return _NullInstrument()

    def create_up_down_counter(self, name, unit="", description="") -> _NullInstrument:
        return _NullInstrument()


#: Module attribute, reassigned in place by `_setup_enabled` when otel is
#: turned on. Call sites MUST do `from ...core import telemetry` and use
#: `telemetry.tracer`, never `from ...core.telemetry import tracer` -- see
#: module docstring.
tracer: _NullTracer = _NullTracer()

#: Same reassignment rule as `tracer`: reference these as
#: `telemetry.widget_query_duration`, never `from .telemetry import ...`, or a
#: module importing at startup freezes the disabled no-op forever.
meter: _NullMeter = _NullMeter()

#: The instruments. Deliberately few: metrics are cheap to emit and expensive to
#: maintain, and a dashboard nobody reads is worse than no dashboard. Each of
#: these answers a question an operator actually asks during an incident.
#:
#:   widget_query_duration -- "is it slow, and which engine/dataset?"
#:   widget_query_total    -- "how much traffic, and how much of it is failing?"
#:   cache_operations      -- "is the cache working, or are we recomputing?"
#:   quota_rejections      -- "are tenants hitting limits?" (a support question
#:                            that currently requires reading logs)
widget_query_duration: _NullInstrument = _NullInstrument()
widget_query_total: _NullInstrument = _NullInstrument()
cache_operations: _NullInstrument = _NullInstrument()
quota_rejections: _NullInstrument = _NullInstrument()


def setup_telemetry(app) -> None:
    """Call once from main.py startup, after the FastAPI app is constructed.

    No-op when `settings.otel_enabled` is False (the default) -- returns
    immediately, no otel import executed. When enabled: instruments FastAPI
    + SQLAlchemy and exports spans via OTLP/HTTP to `settings.otel_endpoint`
    (a console exporter when that's None, e.g. local dev). Any failure here
    -- a missing package, a bad endpoint, an instrumentation error -- is
    caught, logged, and swallowed: telemetry setup can never brick startup.
    """
    from .config import settings
    if not settings.otel_enabled:
        return
    try:
        _setup_enabled(app)
    except Exception:
        logger.exception(
            "OpenTelemetry setup failed; continuing startup without instrumentation")


class _QuerystringScrubber:
    """SpanProcessor that strips the query string off `http.url`/`http.target`
    on EVERY span, before it can ever reach an exporter.

    FastAPIInstrumentor's ASGI layer records the full request URL including
    its query string, with no built-in sanitizer for arbitrary param names --
    it scrubs known credential-shaped headers, not query params. The embed
    surface (`GET /api/v1/embed/report?token=<JWT>`) puts a live, up-to-24h
    host-signed credential straight into that query string, so an unfiltered
    exporter ships it to whatever collector `otel_endpoint` points at. An
    `excluded_urls` allowlist on just the embed route would close today's
    leak but not tomorrow's -- this strips query strings from every span
    instead, so any future endpoint that carries a secret in a query param
    inherits the same protection for free.

    The SDK's `ReadableSpan.attributes` property is a read-only view over the
    span's private `_attributes` dict; there is no public setter for a
    finished span in the Python SDK, so mutating that dict in place -- the
    standard (if unofficial) technique for redacting span attributes here --
    is what every processor added to a TracerProvider ends up doing. It runs
    in `on_end`, not `on_start`: the ASGI instrumentation calls
    `span.set_attribute` again with the un-scrubbed value on its own code
    path AFTER span creation, which would undo an `on_start` scrub; `on_end`
    fires once the span is fully populated and about to be handed to an
    exporter, after which nothing else touches it.
    """

    _SCRUB_KEYS = ("http.url", "http.target")

    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span) -> None:
        attrs = getattr(span, "_attributes", None)
        if not attrs:
            return
        for key in self._SCRUB_KEYS:
            value = attrs.get(key)
            if isinstance(value, str) and "?" in value:
                attrs[key] = value.split("?", 1)[0]

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _metrics_endpoint_from(trace_endpoint: str) -> str:
    """Derive the metrics OTLP/HTTP URL from the traces one.

    `http://collector:4318/v1/traces` -> `http://collector:4318/v1/metrics`.
    An endpoint that does not end in the traces path is returned unchanged and
    left to the operator: guessing at a non-standard route would be worse than
    letting the exporter fail loudly against what was actually configured.
    """
    if trace_endpoint.endswith("/v1/traces"):
        return trace_endpoint[: -len("/v1/traces")] + "/v1/metrics"
    return trace_endpoint


def _setup_metrics(resource) -> None:
    """Install the real meter and instruments. Shares the tracer's Resource so
    metrics and spans carry the same `service.name` and correlate in a backend.

    Separated from `_setup_enabled` so a metrics-specific failure (a collector
    that speaks traces but not metrics, say) is caught by the caller and leaves
    tracing working, rather than taking both down together.
    """
    global meter, widget_query_duration, widget_query_total
    global cache_operations, quota_rejections

    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (ConsoleMetricExporter,
                                                  PeriodicExportingMetricReader)

    from .config import settings

    if settings.otel_endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import \
            OTLPMetricExporter
        # OTLP/HTTP routes the two signals to different paths. An explicit
        # otel_metrics_endpoint wins; otherwise derive it from the trace
        # endpoint by swapping the signal path, so the common case (one
        # collector, both signals) needs one setting rather than two.
        endpoint = settings.otel_metrics_endpoint or _metrics_endpoint_from(
            settings.otel_endpoint)
        exporter = OTLPMetricExporter(endpoint=endpoint)
    else:
        exporter = ConsoleMetricExporter()

    reader = PeriodicExportingMetricReader(
        exporter, export_interval_millis=settings.otel_metric_interval_ms)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    meter = metrics.get_meter(settings.otel_service_name)

    widget_query_duration = meter.create_histogram(
        "datalytics.widget.query.duration", unit="ms",
        description="Wall time of one widget query, by engine and outcome")
    widget_query_total = meter.create_counter(
        "datalytics.widget.query.total", unit="1",
        description="Widget queries, by engine and outcome")
    cache_operations = meter.create_counter(
        "datalytics.cache.operations", unit="1",
        description="Result-cache lookups, by result (hit/miss)")
    quota_rejections = meter.create_counter(
        "datalytics.quota.rejections", unit="1",
        description="Requests refused by a tenant quota, by which quota")


def _setup_enabled(app) -> None:
    global tracer

    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (BatchSpanProcessor,
                                                 ConsoleSpanExporter)

    from .config import settings
    from .database import engine

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    # Added before the exporting processor: on_end runs across processors in
    # add order, so the scrub is guaranteed to have already happened by the
    # time BatchSpanProcessor's own on_end (which only enqueues for later,
    # async export) runs -- though since both mutate/read the same span
    # object and actual export happens well after either on_end returns, the
    # ordering is belt-and-braces here, not load-bearing.
    provider.add_span_processor(_QuerystringScrubber())

    if settings.otel_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
            OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(settings.otel_service_name)

    FastAPIInstrumentor.instrument_app(app)
    # engine is an AsyncEngine; SQLAlchemyInstrumentor hooks the underlying
    # sync engine's event hooks, which the async engine delegates to.
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

    # Metrics are set up inside their own try: a collector that accepts traces
    # but rejects metrics (or a metrics-only misconfiguration) must degrade to
    # "tracing works, metrics do not" rather than losing both. Same isolation
    # stance as setup_telemetry's own guard around this whole function.
    if settings.otel_metrics_enabled:
        try:
            _setup_metrics(resource)
        except Exception:
            logger.exception(
                "OpenTelemetry metrics setup failed; tracing continues without metrics")

    logger.info(
        "OpenTelemetry instrumentation enabled (service=%s, endpoint=%s, metrics=%s)",
        settings.otel_service_name, settings.otel_endpoint or "console",
        settings.otel_metrics_enabled)
