import asyncio
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.rls import resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import Dataset, DataSource, AnalysisResult, User
from ..schemas.schemas import (AssociationRulesRequest, AnalysisRequest, CompareGroupsRequest,
                               CorrelationTestRequest, GlmLogisticRequest,
                               IndependenceRequest, KeyInfluencersRequest,
                               MixedModelRequest, PairwiseRequest,
                               RegressionRequest, SegmentRequest,
                               SurvivalRequest)
from ..services.analytics import load_file, run_full_analysis
from ..core.capability import require_dataset_read
from ..services.analysis_contract import as_response, safe_clean
from ..services.analysis.segment import SegmentError, segment_dataframe
from ..services.analysis.influencers import InfluencerError, key_influencers
from ..services.analysis.restricted import explain_shortfall
from ..services.analysis import registry as analysis_registry
from ..services.direct_query import DirectQueryUnsupported, run_direct_query
from ..services.widget_data import apply_rls_filter

router = APIRouter(prefix="/datasets", tags=["analysis"])

# A4: registry.router is deliberately separate from `router` above (same
# pattern as routers/metadata.py's `router`/`stats_router` split) -- this
# endpoint is capability discovery, not scoped to a dataset, so it does not
# belong under the `/datasets` prefix the rest of this file uses.
registry_router = APIRouter(prefix="/analysis", tags=["analysis"])


class NarrateRequest(BaseModel):
    finding: dict


@registry_router.post("/narrate")
async def narrate_finding(body: NarrateRequest,
                          current_user: User = Depends(get_current_user)):
    """Guarded LLM polish for one finding's sentence -- display-only.

    The client sends back a finding IT ALREADY HOLDS (obtained through the
    secured insights endpoint), so nothing here reads data or crosses an
    identity: the worst a forged body can do is have its own text rephrased to
    its own sender. The digit guard and breaker live in narrate_one; a null
    sentence means "keep the template", never an error.
    """
    from ..services.insights import narrate_one
    sentence = await narrate_one(body.finding or {})
    return {"sentence": sentence}


@registry_router.get("/registry")
async def get_analysis_registry(current_user: User = Depends(get_current_user)):
    """A4: the machine-readable analysis tool catalogue -- name, description,
    params schema, result kind for every registered analysis. Org-authenticated
    only (any logged-in user may discover what analyses exist; there is no
    per-dataset or admin-only data behind this list, so no further gate is
    needed). Renders from the SAME registry the agent's prompt block does
    (services/agent/nodes/generate.py) -- see analysis/registry.py's
    docstring for why that is the single source of truth."""
    return {"analyses": [spec.to_dict() for spec in analysis_registry.all_analyses()]}



async def _directquery_frame(db: AsyncSession, ds, current_user: User,
                             rls_expr: str | None):
    """Rows from a live source, sized for ANALYSIS rather than for a preview.

    The previous implementation went through `run_direct_query(widget_type=
    "table")`, whose job is to fill a preview grid: it came back with 50 rows.
    Every statistic computed here then described those 50 rows while the UI
    presented it as the dataset's answer -- a clustering over 50 of 100,000 rows
    is a different answer, not a rougher one.

    `load_directquery_frame` pulls up to `analysis_row_cap` and says whether it
    got everything, so a caller can put that on screen instead of implying an
    exactness it does not have.
    """
    from ..services import analysis_frame as frames

    check_org(await db.get(DataSource, ds.data_source_id), current_user,
              "Data source not found")
    try:
        return await frames.load_directquery_frame(db, ds, rls_filter_expr=rls_expr)
    except frames.FrameUnavailable as exc:
        raise HTTPException(400, str(exc))


@router.post("/{dataset_id}/analysis")
async def run_analysis(dataset_id: int, req: AnalysisRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # selectinload(Dataset.columns): the DirectQuery branch's run_direct_query call
    # needs dataset.columns for RLS-expression column validation, and it runs
    # synchronously -- see the identical comment in datasets.py's data_preview.
    result = await db.execute(select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id))
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)

    if ds.mode == "directquery":
        live = await _directquery_frame(db, ds, current_user, rls_expr)
        df = live.frame
        # Same column-security drop as the import branch below.
        dq_denied = await resolve_denied_columns(db, current_user, dataset_id)
        dq_present = [c for c in dq_denied if c in df.columns]
        if dq_present:
            df = df.drop(columns=dq_present)
        analysis = run_full_analysis(df)
        analysis["sampled"] = live.sampled
        analysis["total_rows"] = live.total_rows
        analysis["measured"] = live.describe()
        if live.sampled:
            analysis["sample_size"] = live.rows_analysed
        return as_response(analysis)

    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    # Column security, not just row security. This path applied `rls_expr` and
    # stopped there, so a role denied a column still received that column in
    # `type_map` AND its full numeric profile -- mean, min, max, sum, every
    # percentile, and its correlations with every other column. Verified live
    # against dataset 32 before the fix: the widget path correctly returned
    # `{"type": "empty"}` for the same column while this one returned its sum.
    denied = await resolve_denied_columns(db, current_user, dataset_id)

    def _load_and_analyze():
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)
        return run_full_analysis(df)

    result = await asyncio.to_thread(_load_and_analyze)

    if rls_expr or denied:
        # A restricted role's result must never be written to the shared, org-wide
        # AnalysisResult cache (keyed only by dataset_id + analysis_type, with no
        # per-role dimension) — an unrestricted GET would otherwise read back a
        # restricted-shaped result, or a restricted GET could read back an
        # unrestricted admin's cached full result. Restricted callers always get a
        # freshly computed, uncached result instead.
        #
        # `or denied` covers COLUMN security, not just row security. A role with a
        # column rule but no row rule used to pass this guard, so its
        # column-restricted profile was written into the shared cache — and it
        # could read back an unrestricted one containing the very column its rule
        # hides. Both directions of that leak close here.
        return as_response(result)

    existing = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.dataset_id == dataset_id,
            AnalysisResult.analysis_type == req.analysis_type,
        )
    )
    ar = existing.scalar_one_or_none()
    if ar:
        ar.result = result
    else:
        ar = AnalysisResult(dataset_id=dataset_id, analysis_type=req.analysis_type, result=result)
        db.add(ar)

    await db.commit()
    return as_response(result)


@router.get("/{dataset_id}/analysis")
async def get_analysis(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if rls_expr or denied:
        # The cached AnalysisResult (if any) was only ever written by an unrestricted
        # caller — see run_analysis — so it may reflect the full, unrestricted dataset.
        # Serving it to a restricted caller would leak excluded rows' values, so
        # restricted callers never read the shared cache; they must POST for a live,
        # RLS-filtered result instead. `denied` extends that to column rules: the
        # cached profile carries every column, including the ones this role's rule
        # hides.
        raise HTTPException(404, "No analysis found — run POST first")

    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.dataset_id == dataset_id)
        # The insights engine now stores its scan in this table too
        # (analysis_type="insights_scan", routers/datasets.py). This endpoint
        # returns "the latest analysis" with no type filter, so without the
        # exclusion a fresh insight scan would SHADOW the profile: the Overview
        # tab would render a findings list where it expects column statistics.
        .where(AnalysisResult.analysis_type != "insights_scan")
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    ar = result.scalar_one_or_none()
    if not ar:
        raise HTTPException(404, "No analysis found — run POST first")
    return as_response(ar.result)


@router.post("/{dataset_id}/segment")
async def run_segment(dataset_id: int, req: SegmentRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """A2: KMeans segmentation over the SECURED base frame. Always computed live
    (never cached) -- unlike /analysis there is no shared AnalysisResult row to
    poison across roles, so this sidesteps that cache-vs-RLS problem entirely
    rather than needing to reproduce it.

    Uses `_secured_frame` rather than its own copy of the load sequence. It had
    one: row security was applied, column security was NOT, so a role denied a
    column could still cluster on it -- and the returned centroids reported that
    column's values back in original units. Verified against the live stack
    before the fix. Reusing the shared helper is what stops the two from drifting
    apart again.
    """
    df, denied = await _secured_frame(dataset_id, db, current_user)

    # Asking for a denied column by name is refused rather than silently
    # dropped, matching the statistics endpoints: clustering that quietly
    # ignored one of its inputs would answer a different question.
    if req.columns:
        _refuse_denied(list(req.columns), denied)

    restricted = bool(await resolve_rls_expr(db, current_user, dataset_id))
    try:
        contract = segment_dataframe(df, req.columns, include_rows=req.include_rows)
    except SegmentError as e:
        # A viewer narrowed by a row rule is told it is their access, not the
        # data -- and without the counts, which would describe the rows the
        # rule exists to hide. An author sees the original, useful message.
        raise HTTPException(400, explain_shortfall(str(e), restricted))
    return contract.to_dict()


@router.post("/{dataset_id}/association-rules")
async def run_association_rules(
    dataset_id: int, req: AssociationRulesRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Which values travel together, over the SECURED base frame.

    The RLS point is not incidental. A rule reports how often values co-occur,
    so a restricted viewer must see rules mined over their own rows -- mining
    the full frame would answer "what goes with what" from data the asker is
    not allowed to see, and the rule's supporting row count would state a
    number about rows they cannot open.

    Uses `_secured_frame` rather than its own load sequence, so row security,
    prep steps and the denied-column drop are applied exactly once, in one
    place. A denied column named explicitly is refused rather than silently
    ignored: a rule set that quietly dropped one of its inputs would answer a
    different question than the one asked.
    """
    df, denied = await _secured_frame(dataset_id, db, current_user)
    if req.columns:
        _refuse_denied(list(req.columns), denied)

    from ..services.analysis.patterns import PatternError, association_rules

    def _run():
        return association_rules(df, req.columns)

    restricted = bool(await resolve_rls_expr(db, current_user, dataset_id))
    try:
        contract = await asyncio.to_thread(_run)
    except PatternError as e:
        # A viewer narrowed by a row rule is told it is their access, not the
        # data -- and without the counts, which would describe the rows the
        # rule exists to hide. An author sees the original, useful message.
        raise HTTPException(400, explain_shortfall(str(e), restricted))
    return contract.to_dict()


@router.post("/{dataset_id}/key-influencers")
async def run_key_influencers(
    dataset_id: int, req: KeyInfluencersRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Which factors move an outcome, over the RLS-filtered base frame.

    Computed live, never cached, for the same reason segmentation is: there is
    no shared result row that could carry one role's slice to another.

    The RLS point is not incidental here. This analysis reports group RATES, so
    a restricted viewer must see influencers computed over their own rows --
    otherwise the platform would be quietly answering "what drives churn" from
    data the asker is not allowed to see.
    """
    result = await db.execute(select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id))
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    denied = await resolve_denied_columns(db, current_user, dataset_id)

    if ds.mode == "directquery":
        live = await _directquery_frame(db, ds, current_user, rls_expr)
        df = live.frame
    else:
        if not ds.filename:
            raise HTTPException(404, "Dataset not found")

        from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
        _steps = prep_steps_of(ds)
        _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

        def _load():
            frame = load_file(ds.filename)
            frame = apply_rls_filter(frame, rls_expr)
            frame = apply_prep_steps(frame, _steps, _aux)
            return frame

        df = await asyncio.to_thread(_load)

    # A denied column must not become an "influencer": naming it, with a rate
    # attached, would leak exactly what the rule hides.
    present = [c for c in (denied or []) if c in df.columns]
    if present:
        df = df.drop(columns=present)
        if req.target in present:
            raise HTTPException(400, f"column '{req.target}' is not available to you")

    try:
        contract = await asyncio.to_thread(
            key_influencers, df, req.target, req.target_value, req.factors)
    except InfluencerError as e:
        # A viewer narrowed by a row rule is told it is their access, not the
        # data -- and without the counts, which would describe the rows the
        # rule exists to hide. An author sees the original, useful message.
        raise HTTPException(400, explain_shortfall(str(e), bool(rls_expr)))
    return contract.to_dict()


# ── Inferential statistics ───────────────────────────────────────────────────
# Four endpoints rather than one dispatcher, matching how every other analysis
# here is exposed: each has its own typed request body, so a wrong parameter is
# a 422 naming the field rather than a runtime error inside the analysis.


async def _secured_frame(dataset_id: int, db: AsyncSession, current_user: User
                         ) -> tuple[pd.DataFrame, list[str]]:
    """The RLS-filtered, prep-applied frame for a dataset, plus its denied columns.

    Factored out of the four statistical endpoints rather than copied into each:
    a test computed over the wrong frame would report a p-value for rows the
    caller may not see, and four copies of this is four chances to get it wrong
    once. Mirrors `run_key_influencers` exactly, including the DirectQuery
    branch.
    """
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id))
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    denied = await resolve_denied_columns(db, current_user, dataset_id)

    if ds.mode == "directquery":
        live = await _directquery_frame(db, ds, current_user, rls_expr)
        df = live.frame
    else:
        if not ds.filename:
            raise HTTPException(404, "Dataset not found")

        from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
        _steps = prep_steps_of(ds)
        _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

        def _load():
            frame = load_file(ds.filename)
            frame = apply_rls_filter(frame, rls_expr)
            frame = apply_prep_steps(frame, _steps, _aux)
            return frame

        df = await asyncio.to_thread(_load)

    present = [c for c in (denied or []) if c in df.columns]
    if present:
        df = df.drop(columns=present)
    return df, present


def _refuse_denied(requested: list[str], denied: list[str]) -> None:
    """A column-security rule must not be defeated by asking for a p-value about
    the hidden column. Refused by NAME rather than silently dropped: a test that
    quietly ignored one of its inputs would answer a different question than the
    one asked."""
    hit = [c for c in requested if c in denied]
    if hit:
        raise HTTPException(400, f"column '{hit[0]}' is not available to you")


@router.post("/{dataset_id}/statistics/compare-groups")
async def run_compare_groups(
    dataset_id: int, req: CompareGroupsRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Welch's t-test or one-way ANOVA over the RLS-filtered base frame."""
    from ..services.analysis.inferential import StatisticalError, compare_groups

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied([req.value_col, req.group_col], denied)
    try:
        res = await asyncio.to_thread(compare_groups, df, req.value_col, req.group_col)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


@router.post("/{dataset_id}/statistics/independence")
async def run_independence(
    dataset_id: int, req: IndependenceRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Chi-square test of independence over the RLS-filtered base frame."""
    from ..services.analysis.inferential import StatisticalError, test_independence

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied([req.col_a, req.col_b], denied)
    try:
        res = await asyncio.to_thread(test_independence, df, req.col_a, req.col_b)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


@router.post("/{dataset_id}/statistics/correlation")
async def run_correlation_test(
    dataset_id: int, req: CorrelationTestRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Pearson or Spearman correlation with a p-value, over the secured frame."""
    from ..services.analysis.inferential import StatisticalError, correlation_test

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied([req.col_a, req.col_b], denied)
    try:
        res = await asyncio.to_thread(
            correlation_test, df, req.col_a, req.col_b, req.method)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


@router.post("/{dataset_id}/statistics/regression")
async def run_regression(
    dataset_id: int, req: RegressionRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Ordinary least squares over the RLS-filtered base frame."""
    from ..services.analysis.inferential import StatisticalError, regression

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied([req.target] + list(req.predictors or []), denied)
    try:
        res = await asyncio.to_thread(regression, df, req.target, req.predictors)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()

@router.post("/{dataset_id}/statistics/glm-logistic")
async def run_glm_logistic(
    dataset_id: int, req: GlmLogisticRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Logistic regression over the RLS-filtered base frame."""
    from ..services.analysis.inferential import StatisticalError, glm_logistic

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied([req.target] + list(req.predictors or []), denied)
    try:
        res = await asyncio.to_thread(
            glm_logistic, df, req.target, req.predictors, req.target_value)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


@router.post("/{dataset_id}/statistics/mixed-model")
async def run_mixed_model(
    dataset_id: int, req: MixedModelRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Random-intercept mixed model over the RLS-filtered base frame."""
    from ..services.analysis.inferential import StatisticalError, mixed_model

    df, denied = await _secured_frame(dataset_id, db, current_user)
    # The GROUPING column is checked too: a mixed model names its groups in the
    # output, so grouping by a denied column would leak exactly what the rule
    # hides -- the same reasoning key_influencers applies to its factors.
    _refuse_denied([req.target, req.group_col] + list(req.predictors or []), denied)
    try:
        res = await asyncio.to_thread(
            mixed_model, df, req.target, req.predictors, req.group_col)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


@router.post("/{dataset_id}/statistics/survival")
async def run_survival(
    dataset_id: int, req: SurvivalRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Cox proportional hazards over the RLS-filtered base frame."""
    from ..services.analysis.inferential import StatisticalError, survival

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied(
        [req.duration_col, req.event_col] + list(req.predictors or []), denied)
    try:
        res = await asyncio.to_thread(
            survival, df, req.duration_col, req.event_col, req.predictors)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


@router.post("/{dataset_id}/statistics/pairwise")
async def run_pairwise(
    dataset_id: int, req: PairwiseRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Pairwise group comparisons with multiple-comparison correction."""
    from ..services.analysis.inferential import StatisticalError, pairwise_comparisons

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied([req.value_col, req.group_col], denied)
    try:
        res = await asyncio.to_thread(
            pairwise_comparisons, df, req.value_col, req.group_col, req.method)
    except StatisticalError as e:
        raise HTTPException(400, str(e))
    return res.to_dict()


# ── One route for the whole catalogue ────────────────────────────────────────
# The eleven typed endpoints above stay. Each has its own request model, so a
# wrong parameter is a 422 naming the field -- a dispatcher taking an opaque
# `params` dict can never give that, and for a hand-written caller it is the
# better error.
#
# What the typed shape cannot do is GROW. Every analysis needed a route, a
# schema and a bespoke frontend caller, so adding one cost three edits in three
# layers, eight statistical tests waited on a panel somebody had to write by
# hand, and two analyses (`explain_response`, `goal_seek`) shipped without ever
# reaching the catalogue at all. This route is what makes `GET
# /analysis/registry` an invocation contract instead of a brochure: whatever
# the catalogue lists as runnable, this runs, and a client that builds its form
# from `params_schema` needs no per-analysis code.


class RunAnalysisRequest(BaseModel):
    name: str
    params: dict = {}


def _strings_in(value) -> list[str]:
    """Every string anywhere in the params, however nested.

    A typed endpoint knows which of its fields are column names. This one
    cannot: `params` is whatever the catalogue advertises. So the column-security
    check runs over ALL of it -- `regression.predictors` is a list, and a check
    that walked only top-level values would wave a denied column straight
    through inside one.

    Deliberately over-broad: `{"method": "holm"}` gets checked too. A false
    refusal on a column literally named "holm" is a worse outcome for one user
    than a silent leak is for every user, and only one of the two is recoverable.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings_in(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings_in(v)]
    return []


@router.post("/{dataset_id}/difference-check")
async def difference_check_endpoint(
    dataset_id: int, body: dict,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """"Is this difference real?" for two bars of a chart (Phase 7.2).

    Body: {dimension, groups: [a, b], measure?, aggregation?, granularity?,
    filters?} -- the chart's own roles and filters, so the test runs on the rows
    the chart drew from, secured exactly like every other read."""
    from ..services.analysis.inferential import difference_check
    from ..services.widget_data import _apply_filters

    await require_dataset_read(db, current_user, dataset_id)
    dimension = body.get("dimension")
    measure = body.get("measure") or None
    if not isinstance(dimension, str) or not dimension:
        raise HTTPException(400, "The chart needs a category to compare bars of")
    df, denied = await _secured_frame(dataset_id, db, current_user)
    filters = body.get("filters") if isinstance(body.get("filters"), list) else []
    _refuse_denied([dimension] + ([measure] if measure else [])
                   + [str(f.get("column")) for f in filters if isinstance(f, dict)], denied)

    def _run():
        frame = _apply_filters(df, filters)
        return difference_check(frame, dimension, body.get("groups") or [], measure,
                                str(body.get("aggregation") or ("sum" if measure else "count")),
                                body.get("granularity") or None)
    try:
        return await asyncio.to_thread(_run)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{dataset_id}/analysis/run")
async def run_catalogued_analysis(
    dataset_id: int, req: RunAnalysisRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Run any runnable analysis in the catalogue over this dataset's secured frame.

    `require_dataset_read` rather than `check_org` alone: a dataset somebody was
    never granted must be a 404 here for the same reason it is everywhere else,
    and a generic route is exactly where a narrower gate would be easiest to
    forget.
    """
    await require_dataset_read(db, current_user, dataset_id)

    spec = analysis_registry.get(req.name)
    if spec is None:
        raise HTTPException(404, f"No analysis named '{req.name}'")
    if spec.handler is None:
        # Listed but not yet reachable this way: a different problem from a
        # typo, and the caller can act on the difference.
        raise HTTPException(
            400, f"'{req.name}' is listed but cannot be run through this endpoint yet")

    df, denied = await _secured_frame(dataset_id, db, current_user)
    _refuse_denied(_strings_in(req.params), denied)

    try:
        result = await asyncio.to_thread(
            analysis_registry.run_analysis, req.name, df, req.params)
    except analysis_registry.UnknownAnalysisError:
        raise HTTPException(404, f"No analysis named '{req.name}'")
    except analysis_registry.NotRunnableError as e:
        raise HTTPException(400, str(e))
    except (SegmentError, InfluencerError) as e:
        raise HTTPException(400, str(e))
    except TypeError as e:
        # Wrong or missing kwargs. `test_analysis_dispatch` pins every
        # handler's signature against its published schema, so this is a
        # malformed request rather than catalogue drift -- 400, not 500.
        raise HTTPException(400, f"Bad parameters for '{req.name}': {e}")
    except ValueError as e:
        # Every analysis service refuses with a ValueError (GoalSeekError and
        # the inferential refusals both subclass it) and none raises
        # HTTPException, which is what keeps them callable off the HTTP path.
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(400, f"Column not found: {e}")

    # A flat envelope rather than `AnalysisContract`: that contract exists to
    # attach a uniform `result` key BESIDE legacy response bytes during a
    # migration. This route has no legacy bytes to preserve, so it says plainly
    # what ran and what kind of answer came back -- `result_kind` is how a
    # generic renderer chooses its view without inferring it from the request
    # it sent. `safe_clean` because handler output carries numpy scalars.
    return {
        "analysis": spec.name,
        "result_kind": spec.result_kind,
        "params": safe_clean(req.params),
        "result": safe_clean(result),
    }
