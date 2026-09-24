"""Metrics: emitted when otel is on, free when it is off.

Two properties matter, and they pull in opposite directions:

  1. With otel disabled (the default) the instruments are pure-Python no-ops.
     Nothing imports `opentelemetry`, nothing allocates, and a broken or absent
     otel install cannot affect a render. This is the same contract the tracer
     has had since E3.
  2. With otel enabled the counters actually count, with the labels an operator
     needs to answer "which engine, and was it cached".

A metric that is missing from one of `get_widget_data`'s three return paths
(cache hit, DuckDB, pandas) silently skews every rate computed from it, so each
path is asserted separately.
"""
import pandas as pd
import pytest

from app.core import telemetry
from app.core.config import settings
from app.services import widget_data as wd
from app.services.widget_data import get_widget_data


CONFIG = {"dimension": "region", "measure": "sales", "aggregation": "sum"}


class _RecordingInstrument:
    """Stands in for a counter/histogram and remembers what it was given."""

    def __init__(self):
        self.calls = []

    def add(self, amount, attributes=None):
        self.calls.append((amount, attributes or {}))

    def record(self, amount, attributes=None):
        self.calls.append((amount, attributes or {}))


@pytest.fixture
def instruments(monkeypatch):
    """Swap the module-level instruments for recorders.

    Patching `telemetry.<name>` is exactly how the real setup installs them --
    module attribute reassignment -- so this exercises the same lookup the
    production path uses, and would fail if a call site ever switched to a
    `from telemetry import ...` import that froze the no-op.
    """
    recorded = {name: _RecordingInstrument() for name in (
        "widget_query_total", "widget_query_duration",
        "cache_operations", "quota_rejections")}
    for name, instrument in recorded.items():
        monkeypatch.setattr(telemetry, name, instrument)
    return recorded


@pytest.fixture(autouse=True)
def _clean():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


def _csv(tmp_path):
    path = tmp_path / "m.csv"
    pd.DataFrame({"region": ["A", "B", "A"], "sales": [1.0, 2.0, 3.0]}).to_csv(
        path, index=False)
    return str(path)


class TestDisabledIsFree:
    def test_the_default_instruments_are_no_ops(self):
        assert type(telemetry.widget_query_total).__name__ == "_NullInstrument"
        assert type(telemetry.meter).__name__ == "_NullMeter"

    def test_no_op_instruments_accept_the_real_api_without_erroring(self):
        telemetry.widget_query_total.add(1, {"executor": "pandas"})
        telemetry.widget_query_duration.record(12.5, {"executor": "duckdb"})
        telemetry.cache_operations.add(1)

    def test_a_render_works_with_metrics_disabled(self, tmp_path):
        """The hot path must not depend on otel being installed or enabled."""
        result = get_widget_data(_csv(tmp_path), CONFIG, widget_type="bar",
                                 use_cache=False)
        assert len(result["rows"]) == 2


class TestWidgetMetrics:
    def test_a_pandas_render_is_counted(self, tmp_path, instruments, monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        get_widget_data(_csv(tmp_path), CONFIG, widget_type="bar", use_cache=False)

        total = instruments["widget_query_total"].calls
        assert len(total) == 1
        assert total[0][1]["executor"] == "pandas"
        assert total[0][1]["cache_hit"] == "false"

    def test_duration_is_recorded_alongside_the_count(self, tmp_path, instruments,
                                                      monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        get_widget_data(_csv(tmp_path), CONFIG, widget_type="bar", use_cache=False)

        durations = instruments["widget_query_duration"].calls
        assert len(durations) == 1
        assert durations[0][0] >= 0          # milliseconds, never negative
        assert durations[0][1]["executor"] == "pandas"

    def test_a_duckdb_render_is_labelled_duckdb(self, tmp_path, instruments,
                                                monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        get_widget_data(_csv(tmp_path), CONFIG, widget_type="bar", use_cache=False)

        total = instruments["widget_query_total"].calls
        assert len(total) == 1
        assert total[0][1]["executor"] == "duckdb", (
            "an eligible query took the pandas path, or the metric is mislabelled")

    def test_a_cache_hit_is_counted_as_a_hit(self, tmp_path, instruments,
                                             monkeypatch):
        """The third return path. Without its own metric call, cache hits would
        be invisible and the hit rate would read as 0%."""
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        path = _csv(tmp_path)
        get_widget_data(path, CONFIG, widget_type="bar")   # populate
        get_widget_data(path, CONFIG, widget_type="bar")   # hit

        cache = instruments["cache_operations"].calls
        assert [c[1]["result"] for c in cache] == ["miss", "hit"]

    def test_every_return_path_emits_exactly_one_count(self, tmp_path, instruments,
                                                       monkeypatch):
        """Guards against double-counting as much as against missing counts:
        a render that emitted twice would inflate every rate built on it."""
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        path = _csv(tmp_path)
        get_widget_data(path, CONFIG, widget_type="bar")
        get_widget_data(path, CONFIG, widget_type="bar")

        assert len(instruments["widget_query_total"].calls) == 2
        assert len(instruments["widget_query_duration"].calls) == 2


class TestQuotaMetrics:
    def test_a_rejection_is_counted_with_its_kind(self, instruments):
        from app.services.quotas import QuotaExceeded

        with pytest.raises(QuotaExceeded):
            raise QuotaExceeded("nope", kind="queries_per_day")

        calls = instruments["quota_rejections"].calls
        assert len(calls) == 1
        assert calls[0][1] == {"quota": "queries_per_day"}

    def test_the_label_is_the_kind_not_the_message(self, instruments):
        """Low cardinality on purpose: labelling by message would create a new
        time series every time someone rewords an error, and storage-quota
        messages interpolate the limit into the text."""
        from app.services.quotas import QuotaExceeded

        with pytest.raises(QuotaExceeded):
            raise QuotaExceeded("Storage quota exceeded (500 MB limit ...)",
                                status_code=413, kind="storage_mb")

        assert instruments["quota_rejections"].calls[0][1] == {"quota": "storage_mb"}


class TestEndpointDerivation:
    @pytest.mark.parametrize("traces,metrics", [
        ("http://collector:4318/v1/traces", "http://collector:4318/v1/metrics"),
        ("https://otel.example.com/v1/traces", "https://otel.example.com/v1/metrics"),
    ])
    def test_the_metrics_path_is_derived_from_the_traces_path(self, traces, metrics):
        """OTLP/HTTP routes the two signals to different paths, so one endpoint
        setting cannot serve both verbatim."""
        assert telemetry._metrics_endpoint_from(traces) == metrics

    def test_a_non_standard_endpoint_is_left_alone(self):
        """Guessing at a custom route would be worse than failing loudly against
        what the operator actually configured."""
        custom = "http://collector:4318/ingest"
        assert telemetry._metrics_endpoint_from(custom) == custom
