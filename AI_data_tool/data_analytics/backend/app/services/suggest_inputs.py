"""What every "suggest dashboards" engine starts from, assembled once.

The request path and the background panel job (suggest_jobs.py) must see the
SAME frame: the rows this person may read (row security applied, denied
columns dropped before anything is profiled), with the dataset's prep steps
and calculated columns. So the assembly lives here, not in the router, and
both call it with the person as they are now.

`prepare(db, user, ds)` returns a `SuggestInputs`: the secured frame, its
types and profile, what the catalogue knows about its columns, a `probe` that
draws a widget exactly as the browser will, and what each probe drew (so a
widget can say what it shows).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


class SuggestUnavailable(Exception):
    """The dataset cannot be suggested from; `message` is for the person."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def drawn_key(widget_type, config) -> str:
    return f"{widget_type}|{json.dumps(config, sort_keys=True, default=str)}"


@dataclass
class SuggestInputs:
    df: Any
    type_map: dict
    profile: dict
    knowledge: Any
    measures: list
    column_meta: dict
    description: str | None
    measured: dict
    drawn: dict = field(default_factory=dict)
    #: A live (DirectQuery) source's SQL family, None for an import: what a
    #: derived calculated column must translate to (sql_expr).
    sql_family: str | None = None
    live: bool = False

    async def probe(self, widget_type: str, config: dict) -> dict:
        """Run one proposed widget exactly as the browser will.

        On the already-secured frame, so a probe can never see more than the
        person asking would. Off the event loop: the shaping is pandas work.

        For a DirectQuery dataset the browser goes through `direct_query`,
        which never refuses a known widget the planner cannot push down -- it
        fetches the rows and computes it as import mode does. HR re-test
        2026-10-01: widgets dropped by a planner-first probe drew correctly on
        the dashboard. The live frame having loaded at all proves the source's
        dialect is one DirectQuery serves, so the frame is the right judge.
        """
        from .widget_data import get_widget_data_from_df
        result = await asyncio.to_thread(get_widget_data_from_df, self.df, config,
                                         widget_type, self.measures)
        self.drawn[drawn_key(widget_type, config)] = result
        return result

    def ineligible(self) -> set[str]:
        return {name for name, entry in self.column_meta.items()
                if isinstance(entry, dict) and entry.get("eligible_for_suggestion") is False}


async def prepare(db, user, ds) -> SuggestInputs:
    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from . import analysis_frame as frames
    from . import knowledge as knowledge_service
    from .analytics import detect_types, load_file
    from .dataset_profile import build_profile
    from .prep import apply_prep_steps, prep_steps_of, resolve_join_frames

    if not ds.filename and ds.mode != "directquery":
        raise SuggestUnavailable("This dataset has no rows to suggest from yet")

    denied = await resolve_denied_columns(db, user, ds.id)
    rls_expr = await resolve_rls_expr(db, user, ds.id)
    steps = prep_steps_of(ds)
    aux = await resolve_join_frames(db, user, steps) if steps else {}

    live = None
    if ds.mode == "directquery":
        try:
            live = await frames.load_directquery_frame(
                db, ds, rls_filter_expr=rls_expr, denied=set(denied))
        except frames.FrameUnavailable as exc:
            raise SuggestUnavailable(str(exc))

    calc, funcs = ds.calculated_columns, ds.custom_functions
    filename = ds.filename

    def _load():
        from .widget_data import apply_calculated_columns, apply_rls_filter
        if live is not None:
            df = live.frame
            if calc:
                df = apply_calculated_columns(df, calc, funcs)
            return df
        df = load_file(filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, steps, aux)
        # Dropped BEFORE profiling, not filtered out of the answer: the
        # profile is what goes to the model, and a column this role may not
        # see must never be in it.
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        if calc:
            df = apply_calculated_columns(df, calc, funcs)
        return df

    try:
        df = await asyncio.to_thread(_load)
    except FileNotFoundError:
        raise SuggestUnavailable("Dataset file not found on server", 404)

    meta = ds.column_meta or {}
    type_map = await asyncio.to_thread(detect_types, df)
    profile = await asyncio.to_thread(build_profile, df, type_map, meta)
    # What the platform KNOWS about these columns. `denied` is passed so a
    # column this role may not see cannot arrive in a prompt wearing a
    # description -- the same rule that dropped it from the frame above.
    know = await knowledge_service.for_dataset(db, ds, denied=denied)
    m = live or frames.imported_frame(df)
    measured = {"origin": m.origin, "rows_analysed": m.rows_analysed,
                "total_rows": m.total_rows, "sampled": m.sampled,
                "description": m.describe()}
    family = None
    if ds.mode == "directquery":
        from ..models.models import DataSource
        from .connectors import sql_family_of
        src = await db.get(DataSource, ds.data_source_id)
        if src is not None and src.org_id == ds.org_id:
            family = sql_family_of({**dict(src.config or {}), "type": src.type})
    return SuggestInputs(df=df, type_map=type_map, profile=profile, knowledge=know,
                         measures=ds.measures or [], column_meta=meta,
                         description=ds.description, measured=measured,
                         sql_family=family, live=ds.mode == "directquery")


Progress = Callable[[str, dict], Awaitable[None]]


def _with_derived(inputs: "SuggestInputs", roles: dict, ineligible: set[str], mixed: dict):
    """`(inputs, fields, widgets)`: the inputs with the derived fields drawn in
    (calculated columns on a copy of the frame, measures beside the dataset's
    own), what was derived, and the charts each field exists for."""
    from dataclasses import replace

    from .analytics import detect_types
    from .dataset_profile import build_profile
    from .derived_fields import as_definitions, augment_profile, propose, widgets_for
    from .insights import order_event_dates
    from .widget_data import apply_calculated_columns
    fields = propose(inputs.df, roles, ineligible, mixed)
    if inputs.live and fields["calculated_columns"]:
        # A live source computes a calculated column in its own SQL: only
        # offer the ones it can (a DATEDIFF on a family sql_expr writes).
        from .sql_expr import ExpressionTranslationError, calc_column_to_sql
        ok = []
        for c in fields["calculated_columns"]:
            try:
                calc_column_to_sql(c["expression"], set(map(str, inputs.df.columns)), inputs.sql_family)
                ok.append(c)
            except ExpressionTranslationError:
                pass
        fields = {**fields, "calculated_columns": ok,
                  "facts": [m["fact"] for m in fields["measures"]] + [c["fact"] for c in ok]}
    if not fields["measures"] and not fields["calculated_columns"]:
        return inputs, fields, []
    defs = as_definitions(fields)
    df = inputs.df
    type_map, profile = inputs.type_map, inputs.profile
    if defs["calculated_columns"]:
        df = apply_calculated_columns(df, defs["calculated_columns"])
        type_map = detect_types(df)
        profile = build_profile(df, type_map, inputs.column_meta)
    profile = augment_profile(profile, fields)
    dates = order_event_dates([c for c, t in roles.items() if t == "datetime"])
    new = replace(inputs, df=df, type_map=type_map, profile=profile,
                  measures=list(inputs.measures or []) + defs["measures"], drawn={})
    return new, fields, widgets_for(fields, profile, dates)


async def panel(inputs: SuggestInputs, goal: str | None, size: int,
                progress: Progress | None = None, client: Any = "default",
                fresh: bool = False) -> dict:
    """Several analyst lenses propose, everything is drawn, the data selects.

    Slower than the quick designer (one model call per lens, every idea
    executed), so it is its own mode and can run as a background job. Without
    a model the statistics engine's ideas go through the same gate.
    """
    from .analyst_panel import run_panel
    from .fact_sheet import build_facts
    from .insights import effective_roles, generate_insights
    meta = inputs.column_meta
    ineligible = inputs.ineligible()
    roles = effective_roles(inputs.type_map, meta)
    if progress:
        await progress("facts", {})
    facts = await asyncio.to_thread(build_facts, inputs.df, roles, meta, ineligible)
    # Fields an analyst would add first -- a rate of totals, a duration --
    # proposed from the data, added to a COPY of the frame for drawing, and
    # created on the dataset only if the person accepts (derived_fields).
    inputs, fields, extra = await asyncio.to_thread(_with_derived, inputs, roles, ineligible,
                                                    facts.get("mixed_units") or {})
    if fields["calculated_columns"]:
        roles = effective_roles(inputs.type_map, meta)
        facts = await asyncio.to_thread(build_facts, inputs.df, roles, meta, ineligible)
    if fields["facts"]:
        facts = {**facts, "text": (facts.get("text") or "") + "\n" + "\n".join(
            f"- Derived field: {t}." for t in fields["facts"])}
    result = await asyncio.to_thread(generate_insights, inputs.df, inputs.type_map, meta)
    if client == "default":
        try:
            from .llm import get_client
            client = get_client()
        except Exception:                                    # noqa: BLE001
            client = None
    out = await run_panel(df=inputs.df, profile=inputs.profile, roles=roles, column_meta=meta,
                          ineligible=ineligible, findings=result.get("findings") or [],
                          facts=facts, goal=goal or None, size=size, probe=inputs.probe,
                          client=client, knowledge=inputs.knowledge, progress=progress, extra=extra,
                          fresh=fresh)
    from .derived_fields import used_by
    chosen = [w for p in out["proposals"] for w in p["widgets"]]
    return {"proposals": [{**p, "source": "panel"} for p in out["proposals"]],
            # What accepting these pages adds to the dataset first.
            "derived": used_by(chosen, fields),
            "reason": out["reason"], "question": None, "profile": inputs.profile,
            "source": "panel", "panel": out["panel"], "refused": out.get("refused") or [],
            "facts": [f["text"] for f in facts["facts"]][:40],
            "measured": inputs.measured}
