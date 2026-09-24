"""Two structural pins, both written because one instance is cheap and six is not.

STEPS MUST NOT BLOCK THE SHARED TICK
------------------------------------
`StepSpec`'s docstring already states the invariant: a step reads on the loop
and wraps its own blocking work in `asyncio.to_thread`, because the runner
cannot impose it once a step needs an `AsyncSession`. Step 1 honours it. The
question this pin answers is what happens at step 6, when the author is
whoever picks up the ticket and the docstring is three screens away.

A step that does pandas work inline stalls every OTHER run's tick, not just
its own -- the scheduler is shared. That failure is invisible in a unit test
(one step, one run, nothing to starve) and shows up in production as "the
whole queue is slow tonight".

So: a step either wraps blocking work in `to_thread`, or it declares itself
DB-only by name. Declaring is deliberate and reviewable; forgetting is not.

ANALYSES MUST DECIDE ABOUT COLUMN ROLES
---------------------------------------
Before step 2 there was no way for a dispatched analysis to see column roles
at all: `run_analysis` never passed `column_meta`, and all 18 runnable
handlers would have raised TypeError if it had. The result was Key
influencers ranking `student_id` as a top driver -- an identifier sliced into
quantile ranges, which describes row order, not a factor.

The fix is not "pass it to everything": a paired t-test has no use for roles,
and a parameter that every handler accepts and most ignore cannot be
distinguished from one that is consulted. So each spec DECLARES whether it
consumes roles, with no default, and this pin requires the declaration. A new
analysis cannot be registered without someone deciding.
"""
import ast
import inspect
import pathlib
import re

import app
from app.services import automation_runner
from app.services.analysis import registry

APP_ROOT = pathlib.Path(app.__file__).parent


# ── pin 1: every step is non-blocking, or says why not ───────────────────────

#: Steps that touch only the database and the session, and therefore have no
#: blocking work to thread. Adding a name here is a REVIEWED claim that the
#: step does no pandas, no file IO and no network call -- not a way to silence
#: the pin. Each entry carries the reason it is safe.
DB_ONLY_STEPS = {
    # `notify` writes a Notification row and nothing else. No frame is read,
    # no artifact is parsed. REVIEWED.
    "notify",
}


def _step_source(spec) -> str:
    """The source of a step's `run` callable, comments stripped.

    Stripped for the same reason `test_rls_base_frame_choke_point` strips
    them: a comment SAYING the work is threaded is exactly what a step that
    forgot would have. The pin demands code.
    """
    src = inspect.getsource(spec.run)
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


def _is_stub(spec) -> bool:
    """A stub returns a literal ref and does no work. Stubs are exempt: they
    are the placeholder the chain walks on before a step is real, and pinning
    them would only pin the placeholder."""
    return "(stub)" in inspect.getsource(spec.run)


def test_every_real_step_threads_its_blocking_work_or_is_declared_db_only():
    """WHAT THIS PIN CAN AND CANNOT SEE.

    It catches a step with NO threading at all -- the case that actually
    happens, because the author either knew about the rule or did not.

    It cannot catch a step that threads SOME of its blocking work. A mutation
    run removed one of `describe`'s two `to_thread` calls and this test still
    passed, which is the honest limit of a token check: proving that every
    blocking call in a function is wrapped needs to know which calls block,
    and that is not decidable from the source. Stated here rather than left
    for someone to discover, because a pin believed to be stronger than it is
    is worse than a weak one.
    """
    offenders = []
    for spec in automation_runner.STEPS:
        if _is_stub(spec) or spec.name in DB_ONLY_STEPS:
            continue
        if "to_thread" not in _step_source(spec):
            offenders.append(spec.name)
    assert not offenders, (
        "these steps do blocking work on the scheduler's loop -- wrap it in "
        "asyncio.to_thread, or add the step to DB_ONLY_STEPS with the reason "
        f"it genuinely touches nothing but the database: {offenders}")


def test_the_db_only_allowlist_names_real_steps():
    """An allowlist entry for a step that no longer exists would silently
    exempt nothing, and would hide the day someone renames a step."""
    names = {s.name for s in automation_runner.STEPS}
    stale = sorted(DB_ONLY_STEPS - names)
    assert not stale, f"DB_ONLY_STEPS names steps that do not exist: {stale}"


def test_the_pin_sees_every_step_in_the_chain():
    """Guards against the scan going stale and passing vacuously."""
    assert len(automation_runner.STEPS) >= 7


# ── pin 2: every analysis decides about column roles ─────────────────────────

def test_every_registered_analysis_declares_whether_it_consumes_column_meta():
    """No default on the field, so this cannot be satisfied by omission."""
    undeclared = [s.name for s in registry.all_analyses()
                  if not isinstance(getattr(s, "consumes_column_meta", None), bool)]
    assert not undeclared, (
        "these analyses do not say whether they read column roles -- set "
        "consumes_column_meta=True (and read it) or False (and say why in a "
        f"comment) on the spec: {undeclared}")


def test_an_analysis_that_claims_roles_actually_accepts_them():
    """Declaring True and not taking the parameter would raise TypeError on
    the first real dispatch -- at runtime, for a user, rather than here."""
    broken = []
    for spec in registry.all_analyses():
        if not (spec.handler and getattr(spec, "consumes_column_meta", False)):
            continue
        fn = registry.resolve_handler(spec)
        params = inspect.signature(fn).parameters
        takes = ("column_meta" in params
                 or any(p.kind is p.VAR_KEYWORD for p in params.values()))
        if not takes:
            broken.append(spec.name)
    assert not broken, (
        "these analyses declare consumes_column_meta=True but their handler "
        f"has no column_meta parameter: {broken}")


def test_an_analysis_that_declines_roles_is_not_handed_them():
    """The other direction, and the one that keeps the declaration honest: a
    handler that says False must not receive the kwarg, or the flag is
    decoration and every handler would need the parameter anyway."""
    seen = {}

    def _spy(df, **params):
        seen.update(params)
        return {"ok": True}

    spec = registry.AnalysisSpec(
        name="_pin_declines", description="", params_schema={},
        result_kind="dict", handler="_pin:_spy", consumes_column_meta=False)
    registry.register(spec)
    registry._HANDLERS["_pin:_spy"] = _spy
    try:
        registry.run_analysis("_pin_declines", None, {},
                              column_meta={"a": {"role": "identifier"}})
    finally:
        registry.unregister("_pin_declines")
        registry._HANDLERS.pop("_pin:_spy", None)
    assert "column_meta" not in seen


def test_the_registry_scan_is_not_vacuous():
    assert len(registry.all_analyses()) >= 20


def test_key_influencers_is_one_of_the_analyses_that_reads_roles():
    """The whole reason step 2 exists. If this ever flips to False, the
    student_id regression is back and nothing else in the suite would say so.
    """
    spec = registry.get("key_influencers")
    assert spec is not None
    assert spec.consumes_column_meta is True


# ── the fourth copy of the identifier heuristic is gone ──────────────────────

def test_influencers_uses_classify_role_rather_than_its_own_cardinality_rule():
    """Structural, because the value test cannot tell WHICH heuristic ran.

    Four copies existed: classify_role (canonical), widget_data's name-only
    check, columnRole.ts (frontend mirror), and influencers' own
    `levels > MAX_CATEGORICAL_LEVELS` rule -- which sat on the categorical
    branch only, so a NUMERIC identifier sailed through and got quantile-binned
    into "ranges" that describe row order. This requires the canonical one.
    """
    src = (APP_ROOT / "services/analysis/influencers.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "classify_role" in called, (
        "influencers does not call classify_role -- a fifth copy of the "
        "identifier heuristic is not the fix")


def test_the_identifier_check_covers_the_numeric_branch():
    """The bug was branch-specific: the categorical branch had a check and the
    numeric branch did not. A guard that only runs for object columns would
    satisfy the test above and still ship the bug.
    """
    src = (APP_ROOT / "services/analysis/influencers.py").read_text(encoding="utf-8")
    body = re.search(r"def _usable_factors\b.*?(?=\ndef )", src, re.S)
    assert body, "_usable_factors moved -- this pin needs updating with it"
    code = body.group(0)
    numeric_at = code.index("is_numeric_dtype")
    role_at = code.index("classify_role")
    assert role_at < numeric_at, (
        "classify_role must be consulted BEFORE the numeric/categorical split, "
        "or a numeric identifier takes the numeric branch and is never checked")


# ── the value test the structural pins cannot replace ────────────────────────

def test_key_influencers_does_not_rank_a_numeric_identifier():
    """The regression itself, asserted on OUTPUT rather than on source shape.

    A mutation run deleted the exclusion while leaving the classify_role call
    in place, and both structural pins above still passed -- they can see that
    the canonical heuristic is consulted, never that its answer is acted on.
    This is the test that fails when the answer is ignored.
    """
    import pandas as pd
    from app.services.analysis.influencers import key_influencers

    n = 120
    df = pd.DataFrame({
        # Numeric, unique per row: the exact column that was being cut into
        # quantile ranges and reported as a top driver.
        "student_id": range(1000, 1000 + n),
        "faculty": ["eng", "law", "med", "arts"] * (n // 4),
        "passed": ([1] * 3 + [0]) * (n // 4),
    })
    result = key_influencers(df, target="passed", target_value=1).to_dict()
    named = {row.get("factor") for row in (result.get("rows") or [])}
    assert "student_id" not in named, (
        f"an identifier was ranked as a driver: {named}")
    assert "faculty" in named or not named, (
        "the real factor was dropped along with the identifier")


def test_key_influencers_says_why_it_dropped_the_identifier():
    """Silence would leave the reader wondering where their column went."""
    import pandas as pd
    from app.services.analysis.influencers import key_influencers

    n = 120
    df = pd.DataFrame({
        "student_id": range(1000, 1000 + n),
        "faculty": ["eng", "law", "med", "arts"] * (n // 4),
        "passed": ([1] * 3 + [0]) * (n // 4),
    })
    result = key_influencers(df, target="passed", target_value=1).to_dict()
    text = " ".join(str(w) for w in (result.get("warnings") or []))
    assert "student_id" in text
