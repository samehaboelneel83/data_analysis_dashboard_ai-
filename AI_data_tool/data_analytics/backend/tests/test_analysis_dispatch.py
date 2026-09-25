"""The analysis registry becomes a dispatcher.

`AnalysisSpec` carried name, description, params_schema and result_kind -- all
metadata, no callable. Nothing anywhere mapped an analysis name to the function
that runs it, so the registry could only ever answer "what exists", never "run
it". Two consequences fell out of that:

  * Adding an analysis meant three hand-edits (registry entry, a bespoke router,
    a bespoke frontend renderer), and the eight statistical tests sat with no
    frontend entry point at all until someone wrote one panel by hand.
  * `render_prompt_block`'s own docstring says it is "capability discovery, not
    an invocation contract: today's agent only writes SQL." The assistant could
    read the catalogue and not use it.

A `handler` closes that. It is a **dotted string**, not a function object,
because `registry.py` is imported by router wiring and by the agent's hot
prompt-building path, and two of the analysis modules exist specifically to keep
sklearn and pyod off the app-import path. A function reference would drag them
back in at import time; a string is resolved on first call and cached.
"""
import pandas as pd
import pytest

from app.services.analysis import registry
from app.services.analysis.registry import (
    AnalysisSpec, NotRunnableError, UnknownAnalysisError, all_analyses,
    run_analysis,
)


@pytest.fixture
def frame():
    return pd.DataFrame({
        "group": ["a", "b"] * 30,
        # A second, genuinely different categorical -- a chi-square of a column
        # against itself is degenerate and tests nothing.
        "cohort": ["x", "x", "y"] * 20,
        "value": list(range(60)),
        "other": [i * 2 for i in range(60)],
    })


@pytest.fixture
def fake_spec():
    """A registered analysis whose handler is this module's own function."""
    spec = AnalysisSpec(
        name="_probe", description="test only",
        params_schema={"type": "object", "properties": {}},
        result_kind="probe",
        handler="tests.test_analysis_dispatch:_probe_handler")
    registry.register(spec)
    yield spec
    registry.unregister("_probe")


def _probe_handler(df, **params):
    return {"rows": len(df), "params": params}


class TestDispatch:
    def test_it_runs_the_registered_handler(self, frame, fake_spec):
        got = run_analysis("_probe", frame, {})
        assert got["rows"] == 60

    def test_it_passes_the_parameters_through(self, frame, fake_spec):
        got = run_analysis("_probe", frame, {"target": "value"})
        assert got["params"] == {"target": "value"}

    def test_an_unknown_analysis_says_so(self, frame):
        with pytest.raises(UnknownAnalysisError) as e:
            run_analysis("no_such_analysis", frame, {})
        assert "no_such_analysis" in str(e.value)

    def test_a_catalogue_only_entry_is_a_different_error(self, frame):
        """"Not runnable" and "does not exist" are different problems for a
        caller: one is a typo, the other is an analysis that exists but has no
        generic entry point yet."""
        spec = AnalysisSpec(name="_listed_only", description="x",
                            params_schema={"type": "object"}, result_kind="x")
        registry.register(spec)
        try:
            with pytest.raises(NotRunnableError):
                run_analysis("_listed_only", frame, {})
        finally:
            registry.unregister("_listed_only")


class TestTheHandlersAreReal:
    """A dotted string cannot be checked by the type system, so it is checked
    here. Every handler the registry declares must import and be callable."""

    @pytest.mark.parametrize(
        "name", [s.name for s in all_analyses() if s.handler])
    def test_the_handler_resolves_to_something_callable(self, name):
        spec = registry.get(name)
        assert callable(registry.resolve_handler(spec))

    def test_at_least_the_statistical_tests_are_wired(self):
        wired = {s.name for s in all_analyses() if s.handler}
        assert {"compare_groups", "test_independence", "correlation_test",
                "regression"} <= wired


class TestClientsCanSeeWhatIsRunnable:
    def test_the_dict_says_whether_it_can_be_invoked(self):
        spec = registry.get("compare_groups")
        assert spec.to_dict()["runnable"] is True

    def test_the_handler_itself_is_not_published(self):
        """An import path is internal wiring; a client has no use for it and
        it names our module layout."""
        assert "handler" not in registry.get("compare_groups").to_dict()


class TestNothingHeavyIsImportedToRegister:
    def test_importing_the_registry_does_not_pull_in_sklearn(self):
        """Two analysis modules exist solely to keep sklearn and pyod off the
        app-import path. Resolving handlers lazily is what preserves that; a
        function reference in the spec would undo it silently."""
        import subprocess
        import sys
        code = ("import sys; import app.services.analysis.registry as r; "
                "print('sklearn' in sys.modules or 'pyod' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, cwd=".")
        assert out.stdout.strip() == "False", out.stdout + out.stderr


@pytest.mark.parametrize("name,params", [
    ("compare_groups", {"value_col": "value", "group_col": "group"}),
    ("test_independence", {"col_a": "group", "col_b": "cohort"}),
    ("correlation_test", {"col_a": "value", "col_b": "other"}),
])
def test_a_real_analysis_runs_end_to_end(frame, name, params):
    """Proof the dispatcher reaches real code, not just the probe."""
    got = run_analysis(name, frame, params)
    assert got is not None


class TestTheSchemaMatchesTheSignature:
    """A generic client builds its kwargs from `params_schema.properties` and
    the dispatcher spreads them: `handler(df, **params)`. So a property the
    handler has no parameter for is not a documentation slip -- it is a
    TypeError and a 500 the first time a panel calls it.

    `TestTheHandlersAreReal` checks the dotted string resolves. This checks the
    other half of the same untypeable contract: that what the catalogue
    promises callers may send is what the function agrees to receive.
    """

    @pytest.mark.parametrize(
        "name", [s.name for s in all_analyses() if s.handler])
    def test_every_documented_parameter_is_accepted(self, name):
        import inspect
        spec = registry.get(name)
        fn = registry.resolve_handler(spec)
        sig = inspect.signature(fn)
        if any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in sig.parameters.values()):
            return  # **kwargs accepts anything the catalogue advertises
        accepted = set(sig.parameters)
        documented = set((spec.params_schema or {}).get("properties") or {})
        assert documented <= accepted, (
            f"{name}: catalogue advertises {sorted(documented - accepted)}, "
            f"which {fn.__module__}.{fn.__name__} does not accept")

    @pytest.mark.parametrize(
        "name", [s.name for s in all_analyses() if s.handler])
    def test_every_required_parameter_is_documented(self, name):
        """The mirror: a parameter with no default that the schema never
        mentions is one a client cannot know to send."""
        import inspect
        spec = registry.get(name)
        sig = inspect.signature(registry.resolve_handler(spec))
        params = list(sig.parameters.items())[1:]  # [0] is the frame
        mandatory = {n for n, p in params
                     if p.default is inspect.Parameter.empty
                     and p.kind not in (inspect.Parameter.VAR_KEYWORD,
                                        inspect.Parameter.VAR_POSITIONAL)}
        documented = set((spec.params_schema or {}).get("properties") or {})
        assert mandatory <= documented, (
            f"{name}: {sorted(mandatory - documented)} must be supplied but "
            f"the catalogue never mentions them")


class TestTheSchemaSaysWhichFieldsAreColumns:
    """A generic form cannot guess, and guessing wrong is visible on screen.

    `StatisticsPanel` builds its inputs from `params_schema` and had three
    shapes: enum, array, and "anything else", where anything else rendered a
    dropdown of the dataset's columns. That held only while every analysis took
    column names and nothing else. `goal_seek.target_y` is a number -- the
    value the user wants to reach -- and would have rendered as a column
    picker, with no way to type a number into it at all.

    So the schema says it: `format: "column"` marks a property whose value is a
    column name. It also gives the run endpoint's column-security walk a
    precise set to check, though that walk stays deliberately broad as the
    fail-closed backstop.
    """

    #: Names that have always meant "a column in this dataset".
    #: `factors` is on this list because the heuristic missed it once: the
    #: name says nothing about columns, and only its description ("Columns to
    #: consider") gives it away.
    _COLUMNISH = ("_col", "_column", "columns", "predictors", "response",
                  "target", "col_a", "col_b", "factors")

    @pytest.mark.parametrize("name", [s.name for s in all_analyses()])
    def test_every_column_valued_property_is_marked(self, name):
        spec = registry.get(name)
        props = (spec.params_schema or {}).get("properties") or {}
        def numeric(prop):
            """A declared number is never a column reference, whatever it is
            called. `target` names a column in `regression` and a VALUE in
            `forecast_goal` -- the type says which, and the name cannot."""
            types = prop.get("type")
            types = types if isinstance(types, list) else [types]
            return "number" in types or "integer" in types

        missing = [k for k, p in props.items()
                   if k.endswith(self._COLUMNISH)
                   and not numeric(p)
                   and p.get("format") != "column"]
        assert not missing, (
            f"{name}: {missing} name columns but do not declare "
            f"format: 'column', so a generic form cannot tell them from free text")

    @pytest.mark.parametrize("name", [s.name for s in all_analyses()])
    def test_nothing_numeric_claims_to_be_a_column(self, name):
        spec = registry.get(name)
        props = (spec.params_schema or {}).get("properties") or {}
        for key, prop in props.items():
            if prop.get("format") != "column":
                continue
            types = prop.get("type")
            types = types if isinstance(types, list) else [types]
            assert "number" not in types and "integer" not in types, (
                f"{name}.{key} is marked as a column but typed numeric")

    def test_a_number_parameter_exists_and_is_not_marked(self):
        """The case that forced this: without it the panel would have shown a
        column dropdown where a target value belongs."""
        props = registry.get("goal_seek").params_schema["properties"]
        assert props["target_y"]["type"] == "number"
        assert "format" not in props["target_y"]
