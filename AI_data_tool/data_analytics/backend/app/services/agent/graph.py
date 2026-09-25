"""One question's journey: classify -> (clarify) -> context -> plan -> DAG of
[generate -> ladder -> policy -> execute -> sanity] -> explain.

The repair loop (D4.4) lives HERE, inside the per-step node: at most
MAX_ATTEMPTS generations, each retry fed the specific rung and detail that
rejected the last. It is a bounded retry inside a node, not a graph edge —
which is precisely why the graph stays acyclic and the executor stays 80
lines (spec S5).
"""
from __future__ import annotations

import asyncio
import logging
import hashlib
import re
import time

from sqlalchemy import select as sa_select

from ...core import telemetry
from ...core.config import settings
from ...core.rls import resolve_denied_columns, resolve_rls_expr
from ...models.models import AgentRun, AgentStep, DataSource, Dataset
from .. import analytics, widget_data
from ..retrieval import rank_objects
from . import memory
from .results import coerce_scalar, redact_credentials, snapshot_rows
from .context import (SchemaContext, dataset_table_names, load_context,
                      load_dataset_context, suggest_join_route)
from .charts import pick_axes, validated_axes
from .dag import run_dag
from .executor import execute_on_datasets, execute_sql, sanity_check
from .nodes.analyze import ANALYSIS_FOR_INTENT, choose_analysis
from .nodes.classify import classify, is_dashboard_request

log = logging.getLogger(__name__)
from .nodes.clarify import clarify
from .nodes.converse import FALLBACK as CHAT_FALLBACK
from .nodes.converse import converse
from .nodes.explain import describe as describe_result
from .nodes.explain import explain, render_fallback
from .nodes.followup import last_result
from .nodes.followup import resolve as resolve_followup
from .nodes.generate import generate_sql
from .overview import catalog_overview
from .plan import plan_steps
from .policy import PolicyError, apply_policies, load_policies
from .state import StepResult, StepSpec, sink_step_ids
from .validate import validate_sql

#: Total generation attempts per step — the original plus two repairs (D4.4:
#: "maximum three repair attempts, each with the specific error fed back.
#: Then fail honestly with what was tried.")
MAX_ATTEMPTS = 3

#: How long the EXTRA query beside a description may take before the
#: description is sent without it. Measured live on a 17-table Moodle
#: connection: "data have what?" spent 31 seconds inside one generate call
#: that returned no SQL at all, while the answer -- the catalog listing -- had
#: been ready in under a second. A description is not worth half a minute of
#: waiting for a number that may never come, and when the query IS writable it
#: has come back in ~6s. This bounds the wait; it never cancels an ordinary
#: question, which has nothing to fall back on.
#:
#: 8, not 15: every writable query in the trace came back in about 5 seconds
#: end to end (run 160: 6.2s including the narration), and every unwritable
#: one ran the full budget. The budget only ever costs time in the case where
#: nothing is coming, so it is sized just above the case where something is.
DESCRIBE_QUERY_BUDGET_S = 8.0

#: Ask AI answers questions; dashboards are built on /reports (or by the page
#: copilot). A dataset-scoped "create a dashboard" used to run SQL and narrate
#: totals as if the dashboard existed.
DASHBOARD_CHAT_REFUSAL = (
    "I can't create or edit dashboards from Ask AI. "
    "Open Dashboards to build one, or use the page copilot on an open dashboard."
)


async def run_agent(db, *, question: str, source: DataSource | None = None,
                    datasets: list[Dataset] | None = None, user, client,
                    conversation_id: int | None = None,
                    history: list[dict] | None = None) -> AgentRun:
    """The DirectQuery path (`source`) and the multi-mode path (`datasets` —
    import and multi-file both funnel here, spec's multi-mode amendment)
    share every node except context and execution. Exactly one of the two
    must be given: this is a single agent, not two agents that happen to
    share a file.

    `history` is the conversation so far, oldest first, as
    `[{role, content, sql, results}, ...]` (the router loads it; see
    routers/agent._history). It lets a follow-up ("the same for Cairo",
    "as a table") resolve against earlier turns instead of starting cold."""
    if (source is None) == (datasets is None):
        raise ValueError("run_agent requires exactly one of source or datasets")

    started = time.monotonic()
    run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                   question=question, status="running")
    db.add(run)
    await db.flush()

    dataset_mode = datasets is not None
    source_id = None if dataset_mode else source.id
    dataset_key = (",".join(str(i) for i in sorted(d.id for d in datasets))
                  if dataset_mode else None)
    table_names = dataset_table_names([d.name for d in datasets]) if dataset_mode else []
    # The prose names a dataset as its author did, not by its query table
    # (BUG-032); source mode's tables are real and have no other name.
    display_names = (dict(zip(table_names, (d.name for d in datasets)))
                     if dataset_mode else None)

    # Column security (R1): what this user's role must not see, per table.
    # Dataset mode maps each dataset's rules onto its DuckDB table name;
    # source mode maps the rules of any dataset BOUND to this source onto
    # its source_table -- the same rules the widget DirectQuery path fails
    # closed on, so chatting about a table never shows more than charting
    # it would. Resolved once; consumed in three places below (context
    # strip, V6 validation via context.denied_columns, and the dataset-mode
    # frame drop).
    denied_by_table: dict[str, set[str]] = {}
    if dataset_mode:
        for ds, tname in zip(datasets, table_names):
            denied = await resolve_denied_columns(db, user, ds.id)
            if denied:
                denied_by_table[tname] = set(denied)
    else:
        bound = (await db.execute(sa_select(Dataset).where(
            Dataset.data_source_id == source.id,
            Dataset.org_id == user.org_id,
            Dataset.source_table.isnot(None)))).scalars().all()
        for ds in bound:
            denied = await resolve_denied_columns(db, user, ds.id)
            if denied:
                denied_by_table.setdefault(ds.source_table, set()).update(denied)

    async def get_context() -> SchemaContext:
        if dataset_mode:
            ctx = await load_dataset_context(db, [d.id for d in datasets], user.org_id)
        else:
            ctx = await load_context(db, source.id, user.org_id)
        if denied_by_table:
            # Removed, not marked: the model cannot ask for a column it
            # never saw. V6 (validate.py) is the fail-closed net for a
            # query that names one anyway.
            lowered = {t.casefold(): cols for t, cols in denied_by_table.items()}
            for name, obj in ctx.objects.items():
                cols = lowered.get(name.casefold())
                if cols:
                    folded = {x.casefold() for x in cols}
                    obj.columns = {c: dt for c, dt in obj.columns.items()
                                   if c.casefold() not in folded}
                    # The render only ever walks `columns`, so dropping there
                    # is already enough for the prompt. These two go as well
                    # because they are the only places a denied column's
                    # MEANING is held, and a future consumer that iterates
                    # them directly must not be the thing that leaks it.
                    obj.enum_labels = {c: v for c, v in obj.enum_labels.items()
                                       if c.casefold() not in folded}
                    obj.descriptions = {c: v for c, v in obj.descriptions.items()
                                        if c.casefold() not in folded}
            ctx.denied_columns = {t: set(cols) for t, cols in denied_by_table.items()}
        return ctx

    _frames: dict | None = None

    async def dataset_frames() -> dict:
        """Each dataset's SECURED base frame, keyed by DuckDB table name.

        Dataset RLS is applied to the BASE frame, before it is registered in
        DuckDB -- pre-aggregation filtering, the same WHERE-before-GROUP-BY
        guarantee F4 requires of policy.py's SQL predicate injection, just
        enforced by pandas instead of an injected AST node. Column security
        follows import-path semantics: the denied columns cease to exist before
        the frame enters DuckDB, so no SQL -- however it was produced -- can
        read them.

        Memoised, and shared with the analysis short-circuit below, so there is
        exactly ONE place a dataset frame is built and secured. A second
        loader for the analysis path is precisely the shape of bug the
        apply_rls_filter choke-point pin exists to prevent -- two readers, one
        of which somebody forgets to secure.
        """
        nonlocal _frames
        if _frames is not None:
            return _frames
        built: dict = {}
        for ds, tname in zip(datasets, table_names):
            frame = await asyncio.to_thread(analytics.load_file, ds.filename)
            expr = await resolve_rls_expr(db, user, ds.id)
            frame = widget_data.apply_rls_filter(frame, expr)
            denied_here = denied_by_table.get(tname)
            if denied_here:
                present = [c for c in frame.columns
                           if c.casefold() in {x.casefold() for x in denied_here}]
                if present:
                    frame = frame.drop(columns=present)
            built[tname] = frame
        _frames = built
        return _frames

    # A follow-up is read against the conversation before any node sees it
    # (nodes/followup.py). A presentation-only message -- "as a table",
    # "as a bar chart", "execute it and show the result" when the rows
    # already exist -- is answered from the earlier run's snapshot and never
    # reaches classify, which used to call it a vague new question. A data
    # follow-up is rewritten to stand alone, so every node downstream keeps
    # seeing complete questions. `run.question` stays what was typed.
    #
    # Two of the four kinds never become SQL and both leave here: `chat`
    # (the message asks nothing about the data) and `describe` (it asks what
    # the rows already on screen MEAN). Letting either through was the bug --
    # "thanks" got rewritten into a standalone data question and queried, and
    # "explain this chart" reached classify, whose `explain` intent means the
    # key-influencers analysis and answered about a column nobody named.
    effective_question = question
    # A chart asked for before anything has been queried: the pair of columns
    # is settled from the DATA (see _chart_from_scratch) and the run then
    # continues as a data question, so there are rows to draw. Carried here
    # and applied at the single success exit -- there is no other way to say
    # "answer this, and draw the answer".
    chart_request: dict | None = None
    if history:
        resolved = await resolve_followup(question, history, client)
        if resolved is not None:
            kind = resolved["kind"]
            if kind == "chat":
                return await _chat_reply(run, started, question,
                                         await get_context(), history, client)
            # A CHART reaches past a catalog listing to the last real
            # result. The listing describes the data (column / type /
            # description); it is not the data, and charting it refuses every
            # time -- traced live as a four-turn loop that ended with the
            # person pasting their own numbers into the chat. With no real
            # result behind it the chart request falls through to
            # `_chart_from_scratch` below, which reads the dataset itself.
            charting = (kind == "presentation"
                        and (resolved.get("format") or "") in _CHART_FORMATS)
            prev = (last_result(history, chartable=charting)
                    if kind in ("presentation", "describe") else None)
            if prev is not None:
                if kind == "describe":
                    return await _describe(db, run, started, prev, resolved, client,
                                           names=display_names)
                return _present(db, run, started, prev, resolved)
            if charting:
                # "i need chart" with nothing charted yet: not a re-show, and
                # not a vague question either. What is missing is which two
                # columns -- which the data can answer, or be asked about.
                decided = await _chart_from_scratch(
                    run, started, resolved,
                    await dataset_frames() if dataset_mode else {})
                if isinstance(decided, AgentRun):
                    return decided
                effective_question, chart_request = decided
            else:
                effective_question = resolved["question"]

    # "Suggest a dashboard" never becomes SQL, so it leaves the pipeline before
    # planning. The word check runs FIRST: the model classifying it as `lookup`
    # would send the person a confused answer, and classifying it as ambiguous
    # would ask them to decide the very thing they asked the agent to decide.
    #
    # On a dataset Ask AI is not the dashboard editor (the page copilot is).
    # Routing "create a dashboard with a KPI" into planning produced a query
    # that looked like the dashboard had been built.
    if is_dashboard_request(effective_question):
        if dataset_mode:
            run.intent = "chat"
            return _finish(run, started, status="ok", answer=DASHBOARD_CHAT_REFUSAL)
        run.intent = "suggest_dashboard"
        return await _suggest_dashboards(db, run, started, source, user,
                                         effective_question, client)

    verdict = await classify(effective_question, await get_context(), client,
                             history=history)
    if verdict is None:
        return _finish(run, started, status="failed",
                       error="the model endpoint could not classify the question")
    run.intent = verdict["intent"]

    # The message that is not a question about the data at all. Checked BEFORE
    # ambiguity on purpose: "hi" is not a tie between two readings, so asking
    # "which table did you mean?" back would be as wrong as the ten rows of a
    # table it used to answer with.
    if run.intent == "chat":
        return await _chat_reply(run, started, question,
                                 await get_context(), history, client)

    # The classifier can also say `suggest_dashboard` -- for a request that
    # never used the word "dashboard" and so missed the word check above.
    # Measured live: that verdict fell through to planning and answered
    # "choose the best table to draw a useful graph for me" with a LIMIT 10
    # dump. A verdict the enum offers has to lead somewhere; this is where.
    if run.intent == "suggest_dashboard":
        if dataset_mode:
            return _finish(run, started, status="ok", answer=DASHBOARD_CHAT_REFUSAL)
        return await _suggest_dashboards(db, run, started, source, user,
                                         effective_question, client)

    # "What IS this data?" -- answered from the CATALOG, which knows every
    # table in scope, and then answered AGAIN by the query the pipeline writes
    # anyway. Not one or the other: measured live, the query alone counted
    # four tables the model picked out of seventeen and never said so, and the
    # catalog alone would have listed seventeen tables with no numbers in
    # sight. The run continues from here; the listing is injected as a first
    # sink below, so it is narrated and drawn beside the rows.
    overview = None
    if run.intent == "describe_data":
        overview = await catalog_overview(
            db, await get_context(),
            source_id=source_id, org_id=user.org_id,
            frames=await dataset_frames() if dataset_mode else None)

    if verdict["ambiguous"]:
        ask = await clarify(question, verdict["ambiguity_reason"] or "", client)
        return _finish(run, started, status="needs_clarification",
                       answer=ask or "Could you make the question more specific?")

    # ── The question that is not a SQL question ──────────────────────────
    # "Is revenue really different between regions?" became a GROUP BY
    # returning four averages. Those four numbers are the arithmetic; whether
    # they differ by more than chance is a t-test, and the catalogue has had
    # one for months -- reachable by every surface except this one, because
    # `render_prompt_block` told the model these analyses existed and gave it
    # no way to run one.
    #
    # Dataset mode only, and one dataset only: an analysis takes a DataFrame,
    # so this needs a frame to run on and no way to guess which of several is
    # meant. Anything it cannot serve returns None and the run continues to
    # SQL exactly as before -- the feature is additive or it is a regression.
    if dataset_mode and len(datasets) == 1 and run.intent in ANALYSIS_FOR_INTENT:
        analysed = await _run_analysis_intent(
            await dataset_frames(), effective_question, run.intent, client)
        if analysed is not None:
            run.presentation = analysed
            return _finish(run, started, status="ok",
                           answer=_analysis_answer(analysed))

    context = await get_context()
    if not context.objects:
        return _finish(run, started, status="failed",
                       error="no catalog for this source — run a metadata sync first")

    # "Tables considered": the retrieval ranking the context uses to order
    # its prompt, kept on the run so a wrong table choice can be seen from
    # the chat instead of a log dive. rank_objects never raises; an empty
    # ranking (nothing close to the question) is stored as None, not [].
    run.context_objects = [name for name, _ in
                           rank_objects(context, effective_question, k=5)] or None

    steps = await plan_steps(effective_question, run.intent, context, client)
    run.plan = [{"id": s.id, "question": s.question,
                 "depends_on": s.depends_on} for s in steps]

    cfg: dict = {}
    frames: dict = await dataset_frames() if dataset_mode else {}
    if dataset_mode:
        # load_policies (V4) is skipped in dataset mode: RLS was applied to the
        # BASE frame inside `dataset_frames` above, so there is no per-table SQL
        # predicate left to bind -- the rows it would have filtered are already
        # gone.
        policies: dict[str, str] = {}
    else:
        policies = await load_policies(db, context, user)
        cfg = dict(source.config or {})
        cfg["type"] = source.type

    # Memory is scoped by dataset_key in dataset mode (the sorted dataset
    # ids), not by source_id — recall(source_id=None) would otherwise pull
    # the ORG's DirectQuery few-shot examples, SQL written against tables
    # that may not even exist in this dataset's catalog. The pollution is
    # prevented by scoping, not by skipping memory: a dataset-mode run
    # recalls and remembers examples keyed to its own exact dataset set,
    # invisible to source-mode runs and to any other dataset combination.
    examples = await memory.recall(db, user.org_id, source_id,
                                   dataset_key=dataset_key,
                                   question=effective_question)

    async def node(step: StepSpec, parents: dict[str, StepResult]) -> StepResult:
        # E3: one span per DAG node, attributes limited to run_id/node/status/
        # ms plus sha256 hashes of question/SQL -- never the text itself, the
        # same discipline query_runs.sql_hash already enforces. tracer is a
        # module-attribute lookup (not a bound name) so this stays live if
        # setup_telemetry swaps it in after import; it's a cheap no-op object
        # when otel is disabled (the default), no otel API touched at all.
        with telemetry.tracer.start_as_current_span("agent.node") as span:
            span.set_attribute("run_id", run.id)
            span.set_attribute("node", step.id)
            span.set_attribute(
                "question_hash", hashlib.sha256(step.question.encode()).hexdigest())
            result = await _node_body(step, parents)
            span.set_attribute("status", result.status)
            span.set_attribute("ms", result.ms)
            if result.sql:
                span.set_attribute(
                    "sql_hash", hashlib.sha256(result.sql.encode()).hexdigest())
            return result

    async def _node_body(step: StepSpec, parents: dict[str, StepResult]) -> StepResult:
        node_start = time.monotonic()
        failures: list[dict] = []
        feedback: str | None = None
        # Round-5 bug: the old parent_facts showed 5 sample rows with no
        # total count and no marker — a downstream step whose parent
        # returned 32 rows saw only the 5 and enumerated them literally in a
        # `NOT IN (...)`, confidently wrong. Now every fact states the TOTAL
        # row count and an explicit rule: re-derive via SQL, never hand-copy
        # the sample as literals — unless the sample IS the whole result.
        _PARENT_SAMPLE_K = 5
        _parent_lines = []
        for pid, p in parents.items():
            if not p.rows:
                continue
            n = len(p.rows)
            sample = p.rows[:_PARENT_SAMPLE_K]
            if n <= _PARENT_SAMPLE_K:
                _parent_lines.append(
                    f"\nStep {pid} returned all {n} rows: {sample!r}. "
                    "RULE: you may use these values directly.")
            else:
                _parent_lines.append(
                    f"\nStep {pid} returned {n} rows (showing first "
                    f"{_PARENT_SAMPLE_K}): {sample!r}. RULE: if you need "
                    f"these rows in SQL, re-derive them with a subquery or "
                    f"JOIN of step {pid}'s logic — NEVER enumerate the "
                    "sampled values as literals, the sample is incomplete.")
        parent_facts = "".join(_parent_lines)

        # T4: two or more known tables named in the step's own question, with
        # no direct edge between them, get a resolved multi-hop route handed
        # to generate — the same "append extra context to the question"
        # mechanism parent_facts already uses. suggest_join_route returns
        # None (added text becomes "") whenever fewer than two tables are
        # named, or any leg of the chain has no path.
        detected_tables = _detect_tables(step.question, context)
        route = (suggest_join_route(context, detected_tables)
                if len(detected_tables) >= 2 else None)
        route_hint = f"\n{route}" if route else ""
        step_question_text = step.question + parent_facts + route_hint

        for attempt in range(MAX_ATTEMPTS):
            sql = await generate_sql(step_question_text, context,
                                     examples, client, feedback=feedback,
                                     history=history)
            if sql is None:
                failures.append({"rung": "generate", "detail": "no SQL produced"})
                break

            failure = validate_sql(sql, context)
            if failure is not None:
                failures.append({"rung": failure.rung, "detail": failure.detail})
                feedback = f"{failure.rung}: {failure.detail}"
                if failure.rung == "V3":
                    # Live Q24: a planner-added lookup step whose join isn't
                    # even proposed exhausted all repairs re-attempting the
                    # same refused join, failing a run whose earlier step
                    # already held the complete answer. A refused join must
                    # not be retried in another form — the repair must drop
                    # it and answer from the permitted tables' own columns.
                    feedback += (" Do not attempt this join again in any "
                                "form — rewrite the query without it, "
                                "using identifiers from the permitted "
                                "tables.")
                continue

            if dataset_mode:
                final_sql = sql
                # T5: dataset_id is only meaningful for a single-dataset
                # question -- a multi-dataset run's rows don't belong to any
                # one dataset, so it's left null rather than picking one
                # arbitrarily.
                rows, error = await execute_on_datasets(
                    final_sql, frames, org_id=user.org_id,
                    dataset_id=datasets[0].id if len(datasets) == 1 else None,
                )
            else:
                try:
                    final_sql = apply_policies(sql, policies, context.family)
                except PolicyError as exc:
                    # A policy that cannot bind is a REFUSAL, not a repair
                    # target: the model cannot fix a predicate it never sees.
                    failures.append({"rung": "V4", "detail": str(exc)})
                    break
                rows, error = await execute_sql(
                    final_sql, cfg, context.family,
                    org_id=user.org_id, data_source_id=source_id,
                )

            if error is not None:
                failures.append({"rung": "V5", "detail": error})
                feedback = f"execution failed: {error}"
                continue

            # Once, at the choke point: parent facts, explain's prompt, the
            # remembered examples and the chat snapshot all descend from
            # these rows, so credential-named columns are masked here and
            # nowhere needs to remember to do it again.
            rows = redact_credentials(rows)

            return StepResult(step_id=step.id, status="ok", sql=final_sql,
                              rows=rows, error=None,
                              validation_failures=failures,
                              repair_attempts=attempt,
                              ms=int((time.monotonic() - node_start) * 1000))

        return StepResult(step_id=step.id, status="failed", sql=None, rows=None,
                          error=failures[-1]["detail"] if failures else "unknown",
                          validation_failures=failures,
                          repair_attempts=len(failures),
                          ms=int((time.monotonic() - node_start) * 1000))

    gate = asyncio.Semaphore(settings.metadata_sample_concurrency)
    query_gave_up = False
    if overview is not None:
        # The description is already in hand, so the query is on a clock.
        try:
            results = await asyncio.wait_for(run_dag(steps, node, gate),
                                             DESCRIBE_QUERY_BUDGET_S)
        except asyncio.TimeoutError:
            log.info("describe_data: query budget exhausted; answering from "
                     "the catalog alone")
            results, query_gave_up = {}, True
    else:
        results = await run_dag(steps, node, gate)

    # The DAG's sinks (state.sink_step_ids): the question's actual final
    # answer. Only their rows are snapshotted for the chat -- an
    # intermediate step's rows were consumed by parent_facts above and
    # re-showing them as if they were an answer is the H6 failure explain()
    # closes below, applied to the grid instead of the prose.
    sinks = sink_step_ids(steps)

    if overview is not None:
        # FIRST, so the description is read before the numbers it frames --
        # and as a StepResult like any other, so explain() narrates it and
        # the chat draws it through the same grid. It carries no SQL because
        # no SQL produced it; `_run_payload` marks it as catalog-sourced so
        # the reader is never told a query returned these rows.
        columns = overview["columns"]
        results = {"catalog": StepResult(
            step_id="catalog", status="ok", sql=None,
            rows=[dict(zip(columns, row)) for row in overview["rows"]],
            error=None, validation_failures=[], repair_attempts=0, ms=0),
            **results}
        sinks = sinks | {"catalog"}

    for r in results.values():
        db.add(AgentStep(agent_run_id=run.id, node=r.step_id, status=r.status,
                         sql=r.sql, rows_returned=len(r.rows or []) if r.rows is not None else None,
                         result_rows=(snapshot_rows(r.rows)
                                      if r.step_id in sinks and r.status == "ok"
                                      else None),
                         validation_failures=r.validation_failures or None,
                         repair_attempts=r.repair_attempts, ms=r.ms))

    failed = [r for r in results.values() if r.status != "ok"]
    if failed:
        # A description stands on its own. Measured live: "what this data"
        # reached the catalog listing (17 tables, computed, sitting right
        # there) and then the model could not write SQL for the fragment --
        # and the failed step deleted the listing on its way out. The query is
        # the EXTRA here, so its failure is a note on the answer, never the
        # answer. Any other run still fails honestly: a question whose only
        # step failed has nothing left to say.
        if overview is None or "catalog" not in results:
            return _finish(run, started, status="failed",
                           error=f"step {failed[0].step_id}: {failed[0].error}")
        results = {k: r for k, r in results.items() if r.status == "ok"}
        sinks = {k for k in sinks if k in results}

    concerns = [c for r in results.values()
                if (c := sanity_check(r.rows or [], step_question(steps, r.step_id)))]
    if (failed or query_gave_up) and overview is not None:
        # Said in the answer, not swallowed: the person asked for a
        # description and got one, and should still know a query was tried.
        concerns.append(
            "the query beside this description timed out" if query_gave_up
            else "no query could be written for this question, so the "
                 "description below is from the catalog only")
    # H6 follow-up: explain sees only the DAG's SINK steps' rows (the
    # question's actual final answer), never an intermediate step's raw
    # dump — those exist solely to feed a later step's SQL (parent_facts,
    # above) and were already consumed there. A model re-deriving its own
    # (wrong) set arithmetic over intermediate rows on top of an
    # already-correct final result is the failure this closes structurally,
    # not just by prompt instruction.
    answer = await explain(effective_question, results, concerns, client,
                           sink_ids=sinks, names=display_names)
    run.answer = answer or render_fallback(results, concerns, sink_ids=sinks,
                                           names=display_names)

    if not concerns:
        # Only a sane, successful answer is worth teaching from — see
        # dataset_key scoping above for why dataset mode writes here too.
        # The STANDALONE question is what gets remembered: "the same for
        # west" is no use as a few-shot example, its rewrite is.
        single = [r for r in results.values() if r.sql]
        if len(single) == 1:
            await memory.remember(db, user.org_id, source_id, effective_question,
                                  single[0].sql, user_id=user.id,
                                  dataset_key=dataset_key)

    if chart_request is not None:
        # The rows exist now. The axes were chosen from the dataset, so they
        # are usually columns of this result too -- but the SQL that fetched
        # them may have aliased or aggregated, so they are re-checked against
        # what actually came back, and re-picked from it when they do not
        # match. A result that cannot be charted is shown as a table rather
        # than drawn wrong: the prose answer is still the answer.
        snap = next((snapshot_rows(r.rows) for r in results.values()
                     if r.step_id in sinks and r.rows), None)
        if snap:
            x, y = validated_axes(chart_request.get("x"), chart_request.get("y"),
                                  snap["columns"])
            if x is None:
                picked = pick_axes(snap["columns"], snap["rows"],
                                   bool(snap.get("truncated")))
                if picked["outcome"] == "ok":
                    x, y = picked["x"], picked["y"]
            if x is not None:
                run.presentation = {"format": chart_request["format"],
                                    "limit": None, "x": x, "y": y}
    return _finish(run, started, status="ok")


_PRESENT_ANSWERS = {
    "table": "Here is the result as a table.",
    "bar": "Here is the result as a bar chart.",
    "line": "Here is the result as a line chart.",
    "pie": "Here is the result as a pie chart.",
    "csv": "Here is the result. Use Download CSV to save it.",
}


def _is_catalog(result: dict) -> bool:
    """A result that DESCRIBES the data rather than being it.

    The listing behind "what is this data" -- `column` / `type` /
    `description` -- rides on the same turn as the query beside it, and it
    comes FIRST. Anything that reaches for "the rows" by taking the first
    result with rows therefore gets the description, which is how "i need bar
    chart to explain this data" kept being refused with "only column, type
    varies" while the real 35-row result sat behind it on the same turn."""
    return result.get("source") == "catalog" or result.get("step") == "catalog"


def _copy_prev_steps(db, run: AgentRun, prev: dict,
                     limit: int | None = None,
                     only: dict | None = None) -> list[tuple[str, dict]]:
    """The earlier run's snapshots, copied onto THIS run's steps so the chat
    draws them and "Show SQL" still explains them. Returns `(sql, snapshot)`
    per step for a caller that also wants to read the rows.

    Shared by the two follow-ups that answer from rows that already exist:
    re-showing them (`_present`) and explaining them (`_describe`). One copy
    routine, so the provenance a re-show carries is exactly the provenance an
    explanation carries."""
    sqls = list(prev.get("sql") or [])
    out: list[tuple[str, dict]] = []
    results = prev.get("results") or []
    if only is not None:
        # A chart is ONE picture. Re-showing a describe turn as a chart used
        # to copy its catalog listing too, so the pane drew a chart of the
        # column names beside the chart of the data.
        results = [r for r in results if r is only]
    for i, res in enumerate(results):
        snap = {k: res.get(k) for k in ("columns", "rows", "total", "truncated")}
        rows = list(snap.get("rows") or [])
        if limit and limit < len(rows):
            snap = {**snap, "rows": rows[:limit], "truncated": True}
        sql = sqls[i] if i < len(sqls) else None
        db.add(AgentStep(agent_run_id=run.id, node=res.get("step") or f"s{i + 1}",
                         status="ok", sql=sql,
                         rows_returned=snap.get("total"), result_rows=snap,
                         repair_attempts=0, ms=0))
        out.append((sql, snap))
    return out


async def _chat_reply(run: AgentRun, started: float, question: str,
                      context: SchemaContext | None, history: list[dict] | None,
                      client) -> AgentRun:
    """A message that asks nothing about the data, answered in words.

    No step, no SQL, no snapshot -- there is nothing to show, and inventing
    something to show is precisely the bug this path exists to end. A model
    that cannot be reached still gets a true answer out (nodes/converse
    .FALLBACK): a greeting does not need a model to be answered, so it must
    not fail when one is missing."""
    run.intent = "chat"
    reply = await converse(question, context, client, history=history)
    return _finish(run, started, status="ok", answer=reply or CHAT_FALLBACK)


async def _describe(db, run: AgentRun, started: float, prev: dict,
                    resolved: dict, client, names: dict[str, str] | None = None) -> AgentRun:
    """"Explain this chart" -- the rows already exist, so the answer is prose
    ABOUT them and no query runs.

    The narration is nodes/explain.describe -- explain()'s sibling, sharing
    its figures block and its never-invent-a-number rule but asked a different
    question. explain()'s own prompt answers a QUESTION from figures, and run
    through it "explain this chart" came back refusing to draw a chart that
    was already drawn (measured live).

    The snapshot is capped (results.RESULT_ROW_CAP) and `_facts` counts the
    rows it is handed, so a truncated snapshot goes in with a note saying so:
    an answer that says "10 rows" about a 200-row sample of 4,000 is the
    failure `_facts` already learned once."""
    copied = _copy_prev_steps(db, run, prev)
    results: dict[str, StepResult] = {}
    concerns: list[str] = []
    for i, (sql, snap) in enumerate(copied):
        step_id = f"s{i + 1}"
        columns = snap.get("columns") or []
        rows = [dict(zip(columns, r)) for r in (snap.get("rows") or [])]
        total = snap.get("total")
        if isinstance(total, int) and total > len(rows):
            concerns.append(f"step {step_id} shows {len(rows)} of {total} rows")
        results[step_id] = StepResult(step_id=step_id, status="ok", sql=sql,
                                      rows=rows, error=None,
                                      validation_failures=[], repair_attempts=0,
                                      ms=0)
    run.intent = "describe"
    prose = await describe_result(resolved.get("question") or run.question,
                                  results, concerns, client, names=names)
    return _finish(run, started, status="ok",
                   answer=prose or render_fallback(results, concerns, names=names))


#: Formats that need two columns chosen before anything can be drawn.
_CHART_FORMATS = ("bar", "line", "pie")


def _ask_choices(run: AgentRun, started: float, question: str,
                 options: list[str]) -> AgentRun:
    """Ask back, offering the concrete ways to continue.

    The generic ask-with-options channel. `options` are ready-to-send
    MESSAGES: the chat draws each as a button and sending one is exactly the
    same as typing it, so the answer travels the ordinary path and nothing
    here needs to know what a choice means. The run ends
    `needs_clarification` -- the same honest "I did not guess" the classifier
    already uses -- and the options ride on `presentation`, the channel the
    chat already dispatches by kind.

    Whoever fills `options` must build them from things that EXIST (real
    column names, real formats). An invented option is a button that leads
    nowhere, which is worse than a plain question."""
    run.presentation = {"kind": "choices", "options": options}
    return _finish(run, started, status="needs_clarification", answer=question)


#: Rows of the dataset read to decide what is worth charting. Enough for a
#: constant column to give itself away; small enough to be free.
_CHART_SAMPLE = 500


async def _chart_from_scratch(run: AgentRun, started: float, resolved: dict,
                              frames: dict):
    """"i need chart" with nothing charted yet.

    There is no earlier result to re-draw, and the two answers the product
    used to give were both wrong: "I can't generate charts directly" (it can)
    and a chart of whichever columns came first. So the DATA decides, exactly
    as it does for a result already on screen (charts.pick_axes) -- read a
    sample of the dataset, and either

    * name the pair, and return the question to ask the database for it, so
      the run continues and there are rows to draw, or
    * ASK which pair, offering the columns that would actually draw something.

    Returns an `AgentRun` when it answered (a question back), or
    `(question, chart_request)` when the run should continue as a data
    question and be drawn at the end.

    Source mode has no frame to read -- the rows live in someone else's
    database and fetching a sample to decide what to offer is a query this
    node has no business running. It asks, without options: an honest
    question with nothing behind it beats five guesses.
    """
    fmt = resolved.get("format") or "bar"
    df = next(iter(frames.values()), None) if len(frames) == 1 else None
    if df is None or df.empty:
        return _ask_choices(
            run, started,
            "What should the chart show? Tell me the two columns to use — "
            "one to label the marks and one to size them — or ask a question "
            "first and I will draw its answer.", [])

    columns = [str(c) for c in df.columns]
    rows = [[coerce_scalar(v) for v in row]
            for row in df.head(_CHART_SAMPLE).itertuples(index=False, name=None)]
    truncated = len(df) > _CHART_SAMPLE

    x, y = validated_axes(resolved.get("x"), resolved.get("y"), columns)
    if x is None:
        picked = pick_axes(columns, rows, truncated)
        if picked["outcome"] != "ok":
            return _ask_choices(run, started, picked["question"],
                                [o for o in picked["options"]
                                 if o != "Show the rows as a table"])
        x, y = picked["x"], picked["y"]

    # The one rewrite that is safe to make without a model: both names came
    # from the dataset's own columns a moment ago.
    return f"{y} by {x}", {"format": fmt, "x": x, "y": y}


def _present(db, run: AgentRun, started: float, prev: dict, resolved: dict) -> AgentRun:
    """A presentation-only follow-up. The rows already exist on an earlier
    run (`prev`, the history entry that carries them), so they are copied
    onto this run's own step -- sliced to `limit` when fewer were asked
    for -- and the run is finished without classify, plan, SQL or explain.

    The source SQL rides along so "Show SQL" still explains the rows, but
    nothing is remembered: "as a table" is not a verified question for that
    SQL, and this function returns before the remember path.

    A CHART is the one presentation that needs more than a format. "i need
    chart" says how to draw, not what to draw, and the frontend used to guess
    the two columns -- drawing the id column against itself, or thirty-three
    identical bars. So the axes are settled HERE, on the rows, before
    anything is copied: named in the message if it named them, otherwise
    picked when the rows determine one pair, otherwise ASKED (charts.py)."""
    fmt = resolved.get("format") or "table"
    limit = resolved.get("limit")
    x = y = None

    snap = None
    if fmt in _CHART_FORMATS:
        # The first result with rows that is not a DESCRIPTION of the data.
        # A describe turn carries its catalog listing first and the query's
        # own rows behind it; charting the listing is charting column names.
        snap = next((r for r in (prev.get("results") or [])
                     if r.get("rows") and not _is_catalog(r)), None)
        if snap is None:
            # Nothing here but a description. Drawing it is the bug above, and
            # drawing nothing is a blank picture, so it is shown as what it
            # is -- a table -- rather than silently as an empty chart.
            fmt = "table"
        else:
            x, y = validated_axes(resolved.get("x"), resolved.get("y"),
                                  snap.get("columns") or [])
            if x is None:
                picked = pick_axes(snap.get("columns") or [],
                                   snap.get("rows") or [],
                                   bool(snap.get("truncated")))
                if picked["outcome"] == "ok":
                    x, y = picked["x"], picked["y"]
                else:
                    # Ambiguous, or nothing in the rows varies enough to draw.
                    # Either way the rows are not copied: this run shows a
                    # question, not a result.
                    return _ask_choices(run, started, picked["question"],
                                        picked["options"])

    _copy_prev_steps(db, run, prev, limit, only=snap)
    run.intent = "present"
    run.presentation = {"format": fmt, "limit": limit, "x": x, "y": y}
    return _finish(run, started, status="ok",
                   answer=_PRESENT_ANSWERS.get(fmt, _PRESENT_ANSWERS["table"]))


def _detect_tables(question: str, context: SchemaContext) -> list[str]:
    """T4: known table/view names mentioned in a step's question, in the
    order they appear — case-insensitive whole-word match against
    `context.objects`. Feeds `suggest_join_route`, which needs the tables in
    the order the question implies a join chain between them, not the
    catalog's arbitrary dict order."""
    lower_q = question.casefold()
    found: list[tuple[int, str]] = []
    for name in context.objects:
        m = re.search(rf"\b{re.escape(name.casefold())}\b", lower_q)
        if m:
            found.append((m.start(), name))
    found.sort(key=lambda pair: pair[0])
    return [name for _, name in found]


def step_question(steps: list[StepSpec], step_id: str) -> str:
    return next((s.question for s in steps if s.id == step_id), "")


async def _suggest_dashboards(db, run: AgentRun, started: float, source, user,
                              question: str, client=None) -> AgentRun:
    """Hand the connection's catalog to the designer and put the proposals on
    `presentation`, which the chat already renders for its other structured
    replies. Nothing is created here: the person picks one and the client builds
    it from the calls it already has."""
    from ..suggest_dashboard import (load_catalog, load_data_range, load_joins,
                                     stated_persona, suggest_dashboards)

    # Who it is for: what they SAID, else their role in this system. The role
    # is a fact about permissions, not about the job the dashboard serves --
    # "i am a department manager" was designed for a Platform Admin until the
    # request itself was read for this.
    role_name = (await stated_persona(question, client)
                 or getattr(getattr(user, "role", None), "name", None)
                 or "analyst")
    catalog = await load_catalog(db, source.id)
    joins = await load_joins(db, source.id)
    data_range = await load_data_range(db, source.id)
    if not catalog:
        return _finish(run, started, status="failed",
                       error="no catalog for this source — run a metadata sync first")

    cfg = dict(source.config)
    cfg["type"] = source.type

    #: The first row and column names of each accepted query, keyed by its SQL.
    #: Kept from the probe run rather than fetched again: the attribute review
    #: below needs to know whether a dimension has five values or four hundred,
    #: and that is unanswerable from the schema alone.
    shapes: dict[str, dict] = {}

    async def probe(sql: str) -> str | None:
        """Run it. An error is a rejection, and so is an empty result: the first
        dashboard built from this chat executed perfectly and drew six blank
        tiles, because it asked about the last 7 days of a database whose newest
        row was three months old."""
        from ..connections import preview_table
        try:
            got = await asyncio.to_thread(preview_table, cfg, None, sql, 1)
        except Exception as exc:                          # noqa: BLE001
            return str(exc)[:300]
        rows = (got or {}).get("rows")
        if not rows:
            return "the query is valid but returned no rows"
        shapes[sql] = {"columns": got.get("columns") or [], "row": rows[0]}
        return None

    proposals, why = await suggest_dashboards(catalog, role_name, question,
                                              count=3, probe=probe, joins=joins,
                                              data_range=data_range)
    if not proposals:
        return _finish(run, started, status="failed",
                       error=why or "no dashboard could be designed for this data")

    # Every proposal is valid by here. This second pass makes each chart READABLE
    # -- a limit on the bar chart of 400 courses, a sort on the ranking table, a
    # monthly bucket on the line chart of raw timestamps -- and attaches the
    # reason to each widget so the person can disagree with it.
    from ..ingest import detect_types
    from ..widget_review import review_attributes

    import pandas as pd

    async def _review(proposal: dict) -> None:
        shape = shapes.get(proposal["sql"])
        if not shape or not shape["columns"]:
            log.warning("no probed shape for %r (probed %d queries) -- skipping "
                        "attribute review", proposal.get("title"), len(shapes))
            return
        try:
            frame = pd.DataFrame([shape["row"]], columns=shape["columns"])
            column_types = detect_types(frame)
            sample = dict(zip(shape["columns"], shape["row"]))
            proposal["widgets"] = await review_attributes(
                proposal["widgets"], column_types, sample)
        except Exception:                                 # noqa: BLE001
            # An improvement, never a requirement -- a proposal with plain
            # attributes is still a proposal. But LOGGED: a silent `continue`
            # here cost an hour of guessing why every widget came back untuned.
            log.exception("attribute review failed for %r", proposal.get("title"))

    # Concurrently, not one after another. Three proposals reviewed in sequence
    # pushed a request that took 25s past six minutes, which is not a feature
    # anybody waits for. The model endpoint already bounds its own concurrency
    # (llm_max_concurrency), so this queues there rather than piling on.
    await asyncio.gather(*(_review(p) for p in proposals))

    run.presentation = {"kind": "dashboard_proposals",
                        "source_id": source.id,
                        "for_role": role_name,
                        "proposals": proposals}
    one = len(proposals) == 1
    # "a Instructor" reads as a bug in the very first sentence the feature shows.
    article = "an" if role_name[:1].lower() in "aeiou" else "a"
    return _finish(run, started, status="ok",
                   answer=f"Here {'is' if one else 'are'} {len(proposals)} "
                          f"{'dashboard' if one else 'dashboards'} I would build "
                          f"for {article} {role_name} from this data. "
                          f"Pick one to create it.")


def _finish(run: AgentRun, started: float, *, status: str,
            answer: str | None = None, error: str | None = None) -> AgentRun:
    run.status = status
    if answer is not None:
        run.answer = answer
    if error is not None:
        run.error = error
    run.ms = int((time.monotonic() - started) * 1000)
    return run


# ── Analysis intents ─────────────────────────────────────────────────────────


async def _run_analysis_intent(frames: dict, question: str, intent: str,
                               client) -> dict | None:
    """Choose an analysis for the question and run it over the secured frame.

    Returns the same envelope `POST /datasets/{id}/analysis/run` answers with,
    under a `kind` the chat's presentation union understands -- so the chat
    renders it with the analysis panel's renderer rather than a second one
    written to look the same.

    None means "this is not one we can serve": no suitable columns, a model
    reply that named something it was not offered, or the analysis itself
    refusing the data. In every one of those the caller falls through to SQL.
    """
    df = next(iter(frames.values()), None)
    if df is None or df.empty:
        return None

    chosen = await choose_analysis(question, intent, df, client)
    if chosen is None:
        return None

    from ..analysis.registry import get as get_analysis
    from ..analysis.registry import run_analysis

    spec = get_analysis(chosen["analysis"])
    try:
        result = await asyncio.to_thread(
            run_analysis, chosen["analysis"], df, chosen["params"])
    except Exception:
        # A refusal here is the analysis saying the data cannot support it
        # ("only 3 event(s)", "needs two groups"). That is not a failed run --
        # SQL can still answer the question, and did yesterday.
        log.info("analysis %r declined for this frame; falling back to SQL",
                 chosen["analysis"], exc_info=True)
        return None

    from ..analysis_contract import safe_clean
    return {"kind": "analysis_result",
            "analysis": chosen["analysis"],
            "result_kind": spec.result_kind,
            "params": chosen["params"],
            "result": safe_clean(result)}


def _analysis_answer(analysed: dict) -> str:
    """One sentence of prose, taken from the analysis rather than written about
    it. `interpretation` is already a plain-English sentence the statistics
    layer stands behind; paraphrasing it through a model would put a number in
    the answer that no test guards."""
    result = analysed.get("result") or {}
    sentence = result.get("interpretation")
    if sentence:
        return sentence
    if analysed["analysis"] == "explain_response":
        factors = result.get("factors") or []
        if factors:
            return (f"The strongest influence on {result.get('response')} is "
                    f"{factors[0]['column']}. These factors move with the "
                    f"outcome; that is not proof they cause it.")
    return "Here is what the analysis found."
