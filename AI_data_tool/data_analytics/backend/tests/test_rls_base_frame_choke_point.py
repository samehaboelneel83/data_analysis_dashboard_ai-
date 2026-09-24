"""S1 structural pin: every apply_rls_filter call site in the source tree sits at the
BASE frame -- immediately after (or directly wrapping) a load_file() read, before any
prep/aggregation/shaping touches the frame. This is a static, source-level regression
guard: a future call site that filters an already-shaped RESULT (e.g. an aggregated
table, a widget response) instead of the base frame would fail this test even if its
own feature test happened to pass with unfiltered data by coincidence.

Companion to the runtime value-pinning tests (test_widget_data_rls_enforcement.py,
test_analysis_rls.py, test_data_preview_rls.py, test_prep_steps_api.py, and the alert
tests in test_scheduled_delivery.py) which prove the RESULT is correct; this test
proves the SHAPE of the code stays correct too.
"""
import pathlib
import re

import app

APP_ROOT = pathlib.Path(app.__file__).parent

# Files allowed to contain the call. Anything else calling apply_rls_filter is new
# code this pin doesn't know about yet -- fail loudly rather than silently pass it.
_ALLOWED_FILES = {
    "services/widget_data.py",   # the def, plus the two base-frame choke points inside it
    "services/prep.py",          # resolve_join_frames: secures each joined aux frame
    "services/alerts.py",        # check_alert: secures the frame before condition_holds
    "routers/analysis.py",
    "routers/datasets.py",
    "routers/reports.py",
    "routers/widget_data.py",
    "services/agent/graph.py",   # dataset-mode: secures each frame before DuckDB registration
    # _rebuild_derived: a scheduled rebuild has nobody at the keyboard, so it
    # resolves RLS as the dataset's recorded builder and filters the base frame
    # on the line after load_file, before the recipe is replayed. REVIEWED.
    "services/refresh_scheduler.py",
    # _profile_step: step 1 of a Power Pi automation run. Nobody is at the
    # keyboard, so it resolves RLS as the run's RECORDED CREATOR and filters
    # the base frame on the line after load_file, before prep and calculated
    # columns. Denied columns are dropped on the next line -- before
    # build_profile, not after, because the profile is what reaches a model in
    # step 4 and it carries sample VALUES. REVIEWED.
    "services/automation_runner.py",
    # Both call sites filter the BASE frame on the line after load_file,
    # before prep and calculated columns -- the same order every other
    # frame-reading endpoint uses. Training secures the frame a model is
    # FITTED on, so a restricted author cannot mint a model that saw rows
    # they cannot; scoring secures the rows being scored, so a restricted
    # reader gets predictions for their own rows rather than the table's.
    # REVIEWED.
    "routers/prediction_models.py",
    # _governed_frame: the semantic-layer API (Phase 7.6). Filters the BASE
    # frame inside load_file's own call, drops the caller's denied and
    # classification-redacted columns on the next line -- before prep, author
    # filters and calculated columns -- and again after them, so a derived
    # column cannot carry a hidden one out. REVIEWED 24 Sep.
    "routers/semantic.py",
}


def _call_sites() -> list[tuple[str, int, str]]:
    sites = []
    for path in APP_ROOT.rglob("*.py"):
        rel = path.relative_to(APP_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if re.search(r"(?<!def )(?<!\.)\bapply_rls_filter\(", line) and "def apply_rls_filter" not in line:
                sites.append((rel, i, line.strip()))
    return sites


def test_every_call_site_is_in_a_known_base_frame_location():
    sites = _call_sites()
    assert sites, "apply_rls_filter has no call sites at all -- the choke point vanished"
    unexpected = [(rel, ln, txt) for rel, ln, txt in sites if rel not in _ALLOWED_FILES]
    assert not unexpected, (
        f"apply_rls_filter called from an unreviewed location -- confirm it filters the "
        f"BASE frame (immediately after load_file, before prep/aggregation/shaping), "
        f"then add its file to _ALLOWED_FILES: {unexpected}"
    )


def test_every_call_site_reads_a_freshly_loaded_frame_not_a_shaped_result():
    """Each call's dataframe argument must trace to a load_file() read on the same or
    immediately preceding line, not to a variable that has already been through
    apply_prep_steps / get_widget_data_from_df / result shaping."""
    for rel, ln, txt in _call_sites():
        text = (APP_ROOT / rel).read_text(encoding="utf-8").splitlines()
        window = "\n".join(text[max(0, ln - 10):ln])  # this line + up to 9 lines above
        # "load_file" alone (not "load_file(") also matches asyncio.to_thread(load_file, ...)
        # call sites, where load_file is passed by reference rather than invoked inline.
        assert "load_file" in window, (
            f"{rel}:{ln} -- '{txt}' does not sit directly on a load_file() read; "
            f"this looks like result-path (post-hoc) filtering, which S1 forbids"
        )
        # A prep/shaping call between the load and the RLS filter would mean RLS ran
        # AFTER those steps instead of before them -- the exact bug S1 fixes.
        assert "apply_prep_steps(" not in window, f"{rel}:{ln} -- prep ran before RLS"
        assert "get_widget_data_from_df(" not in window, f"{rel}:{ln} -- shaping ran before RLS"


def _enclosing_function_code(rel: str, ln: int) -> str:
    """The top-level function containing line `ln`, with comments stripped.

    Comments are stripped so the pin cannot be satisfied by prose: a docstring
    or comment SAYING column security is handled is exactly what the leaking
    endpoints would have had if anyone had thought about it -- the pin demands
    code.
    """
    lines = (APP_ROOT / rel).read_text(encoding="utf-8").splitlines()
    start = 0
    for j in range(ln - 1, -1, -1):
        if re.match(r"(async )?def \w+", lines[j]):
            start = j
            break
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"(async )?def \w+", lines[j]) or re.match(r"class \w+", lines[j]):
            end = j
            break
    return chr(10).join(l.split("#", 1)[0] for l in lines[start:end])


def test_every_secured_frame_also_handles_column_security():
    """Row security alone is HALF a secured frame.

    This companion pin exists because seven endpoints satisfied the two tests
    above -- apply_rls_filter, at the base frame, straight after load_file --
    and still leaked: run_analysis returned a denied column's full statistical
    profile, run_segment clustered on it, data_preview returned its RAW ROW
    VALUES, the measure preview computed SUM over it, the filter preview
    answered predicates about it, expression parameters would surface its
    aggregates, and alerts evaluated conditions their creator's rules hide.
    All verified against the running stack before being fixed.

    The pattern of the miss was always the same: the function resolved
    `rls_expr` and stopped, because nothing demanded the second call. So this
    demands it: every function that secures a base frame with apply_rls_filter
    must also handle denied columns IN CODE (resolve_denied_columns /
    _secured_frame / a denied-columns parameter), not in a comment.
    """
    sites = _call_sites()
    assert len(sites) >= 15, (
        f"only {len(sites)} apply_rls_filter sites found -- the scan has gone "
        f"stale, which would make this pin pass vacuously")
    offenders = []
    for rel, ln, txt in sites:
        code = _enclosing_function_code(rel, ln)
        if "def apply_rls_filter" in code:
            continue            # the definition itself secures nothing
        if "denied" not in code:
            offenders.append(f"{rel}:{ln} ({txt})")
    assert not offenders, (
        "these functions apply ROW security to a base frame but never touch "
        "column security -- resolve the caller's denied columns and drop (or "
        "refuse by name) before any value leaves the frame: "
        + "; ".join(offenders)
    )

