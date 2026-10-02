"""Fitted models that can score rows they have never seen.

Every other analysis in this codebase refits and discards, which answers "what
could predict this, and how well" and never "score these new rows".
`automated_prediction` says so in its own caveats. This is the endpoint that
closes it -- SAS's automated prediction produces a champion you can then apply,
and until now ours produced a verdict you could only read.

A saved model carries a security property nothing else here has: **it contains
the influence of every column it was trained on.** So a caller denied one of
those columns is refused, and refused for a reason that is not obvious -- they
never have to name the column, and dropping it from their request would change
nothing, because the fitted model already holds it.

The rest is the security every dataset endpoint here has: `require_dataset_read`
for looking (404, never 403), `require_dataset_capability` for training (fitting
reads every row and column and stores the result -- that is authoring), row
security applied to any frame read from the dataset, and org scoping throughout.
"""
import asyncio
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import require_dataset_capability, require_dataset_read
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.rls import resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import Dataset, PredictionModel, User
from ..services.analysis.model_store import (ModelStoreError, PackagedModel,
                                             fit_and_package, score_frame)
from ..services.model_access import ModelAccessError, secured_frame, usable_model
from ..services.analytics import load_file
from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
from ..services.widget_data import apply_calculated_columns, apply_rls_filter

router = APIRouter(prefix="/datasets", tags=["prediction-models"])


class TrainRequest(BaseModel):
    name: str
    target: str
    predictors: list[str] | None = None
    #: A Partition column (prep step `partition`): fit on its Training rows
    #: only, so the saved model has never seen the Validation rows the canvas
    #: can later grade it on.
    partition: str | None = None


class ScoreRequest(BaseModel):
    """Either rows supplied by the caller, or the dataset's own rows.

    `from_dataset` scores the caller's SECURED frame -- their rows, not the
    table's -- which is what makes "score everything" safe to offer at all.
    """
    rows: list[dict] | None = None
    from_dataset: bool = False
    limit: int = 5000


CHAMPION, CANDIDATE = "champion", "candidate"


def _out(m: PredictionModel) -> dict:
    """The model as JSON. The artifact never travels: it is a pickle, and
    nothing outside this service has any use for it."""
    return {
        "id": m.id, "name": m.name, "dataset_id": m.dataset_id,
        "target": m.target, "features": m.features or [],
        "task": m.task, "model_family": m.model_family,
        "score": m.score, "score_name": m.score_name,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        # E13
        "version": m.version or 1, "status": m.status or CHAMPION,
        "promoted_at": m.promoted_at.isoformat() if m.promoted_at else None,
        # The training profile stays server-side: its category shares and
        # decile edges describe the training rows, and the list reaches people
        # whose row rule differs. Drift, which uses it, requires the same rows.
        "card": ({k: v for k, v in m.card.items() if k not in ("feature_profile", "drift_history")}
                 if m.card else None),
        "has_training_profile": bool((m.card or {}).get("feature_profile")),
        # E13: the latest kept drift check, as a level; the checks themselves
        # (per-predictor PSI) come from /drift-history, which needs the rows.
        "last_drift": _last_drift(m),
    }


def _last_drift(m: PredictionModel) -> dict | None:
    h = (m.card or {}).get("drift_history") or []
    return {"at": h[-1].get("at"), "overall": h[-1].get("overall")} if h else None


async def champion_of(db: AsyncSession, org_id: int, dataset_id: int, name: str) -> PredictionModel | None:
    """The version of `name` that "the current champion" means."""
    return (await db.execute(select(PredictionModel).where(
        PredictionModel.org_id == org_id, PredictionModel.dataset_id == dataset_id,
        PredictionModel.name == name, PredictionModel.status == CHAMPION)
        .order_by(PredictionModel.version.desc()))).scalars().first()


async def _dataset_for_read(dataset_id: int, db: AsyncSession, user: User) -> Dataset:
    await require_dataset_read(db, user, dataset_id)
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    return ds


@router.post("/{dataset_id}/prediction-models", status_code=201)
async def train_model(
    dataset_id: int, req: TrainRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Compare candidates, keep the champion.

    Gated as AUTHORING rather than reading: fitting reads every row and every
    column of the dataset and stores a derivative of them that outlives the
    request.
    """
    ds = await _dataset_for_read(dataset_id, db, current_user)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    live_frame = None
    live_note = None
    if ds.mode == "directquery" and ds.data_source_id:
        # HR re-test 2026-10-01: every model WIDGET fitted on the live
        # workforce dataset, but saving a model for the Score widget was
        # refused. Read through the same secured live frame the widgets and
        # analyses use (row rule pushed into the SQL, denied columns dropped).
        from ..services.analysis_frame import FrameUnavailable, load_directquery_frame
        try:
            got = await load_directquery_frame(
                db, ds, rls_filter_expr=await resolve_rls_expr(db, current_user, dataset_id),
                denied=set(await resolve_denied_columns(db, current_user, dataset_id) or ()))
        except FrameUnavailable as e:
            raise HTTPException(400, str(e))
        live_frame = got.frame
        if got.sampled:
            live_note = (f"Trained on a sample of {got.rows_analysed:,} of "
                         f"{got.total_rows:,} rows read live from the source.")
    elif not ds.filename:
        raise HTTPException(400, "This dataset has no data behind it to train on")

    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if req.target in (denied or []):
        raise HTTPException(400, f"column '{req.target}' is not available to you")

    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    def _run() -> PackagedModel:
        # The SAME sequence every other frame-reading endpoint uses: load,
        # secure the base frame, then prep and calculated columns. Training on
        # the raw file instead would fit a model to columns the dataset does
        # not actually have -- a joined or derived column would be missing,
        # and a renamed one would be the old name.
        if live_frame is not None:
            df = live_frame                      # already row-secured at the source
        else:
            df = load_file(ds.filename)
            df = apply_rls_filter(df, rls_expr)
        # A denied column must not become a predictor: the resulting model
        # would carry it, and every future caller would inherit the leak.
        # Dropped BEFORE prep and calculated columns, as every other read
        # does: dropped after, a calculated column over it (`salary * 1`)
        # survived as a feature carrying the same values (E01).
        for column in (denied or []):
            if column in df.columns:
                df = df.drop(columns=[column])
        df = apply_prep_steps(df, _steps, _aux)
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        if req.partition:
            if req.partition not in df.columns:
                raise ModelStoreError(f"Partition column '{req.partition}' is not in this dataset.")
            labels = df[req.partition].astype(str).str.strip().str.lower()
            df = df[labels.str.startswith("train") | (labels == "1")]
            if df.empty:
                raise ModelStoreError(f"Partition '{req.partition}' has no Training rows.")
        # A partition label is bookkeeping, never evidence: a model allowed to
        # use it would learn which rows it was shown.
        split_cols = {s.get("name") for s in _steps if isinstance(s, dict) and s.get("kind") == "partition"}
        split_cols.add(req.partition)
        df = df.drop(columns=[c for c in split_cols if c and c in df.columns and c != req.target])
        return fit_and_package(df, req.target, req.predictors)

    try:
        pkg = await asyncio.to_thread(_run)
    except ModelStoreError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    # E13: an existing name gets its next version, as a candidate beside the
    # champion a dashboard may be scoring with; a new name starts as champion.
    latest = (await db.execute(select(func.max(PredictionModel.version)).where(
        PredictionModel.org_id == current_user.org_id, PredictionModel.dataset_id == dataset_id,
        PredictionModel.name == req.name))).scalar()
    version = int(latest or 0) + 1
    card = {
        **(pkg.card or {}),
        "target": pkg.target, "task": pkg.task, "model_family": pkg.model_family,
        "score": pkg.score, "score_name": pkg.score_name,
        "partition": req.partition,
        # Whether a row rule narrowed what it saw -- the rule itself stays
        # with the administrators who wrote it.
        "row_scope": "restricted by a row rule" if rls_expr else "every row",
        **({"sample_note": live_note} if live_note else {}),
        # The data as it was: a later refresh makes these differ, which is
        # how a reader tells the model is older than the dataset.
        "dataset": {"id": ds.id, "name": ds.name, "row_count": ds.row_count,
                    "content_sha256": getattr(ds, "content_sha256", None),
                    "last_refreshed_at": ds.last_refreshed_at.isoformat()
                    if getattr(ds, "last_refreshed_at", None) else None},
        "trained_by": current_user.email,
        "trained_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    row = PredictionModel(
        org_id=current_user.org_id, dataset_id=dataset_id, name=req.name,
        target=pkg.target, features=pkg.features, feature_columns=pkg.feature_columns,
        categories=pkg.categories, task=pkg.task, model_family=pkg.model_family,
        score=pkg.score, score_name=pkg.score_name, artifact=pkg.artifact,
        # Recorded so the model can be refused to anyone who sees different
        # rows than it was fitted on.
        trained_rls=rls_expr,
        created_by=current_user.id,
        version=version, status=CHAMPION if version == 1 else CANDIDATE, card=card,
        promoted_at=datetime.utcnow() if version == 1 else None,
        promoted_by=current_user.id if version == 1 else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


@router.post("/{dataset_id}/prediction-models/{model_id}/promote")
async def promote_model(
    dataset_id: int, model_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Make this version the champion of its name (E13).

    The champion is what "use the current champion" scores with, so this is
    both promotion and rollback: promoting an older version is going back to
    it. The version it replaces stays, as a candidate. Authoring, like
    training."""
    await _dataset_for_read(dataset_id, db, current_user)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    model = await db.get(PredictionModel, model_id)
    if not model or model.dataset_id != dataset_id:
        raise HTTPException(404, "Model not found")
    check_org(model, current_user, "Model not found")
    # Promoting is choosing what others' dashboards score with: a version
    # this person could not use themselves is not theirs to choose.
    await load_usable_model(db, current_user, dataset_id, model_id)
    previous = await champion_of(db, current_user.org_id, dataset_id, model.name)
    if previous is not None and previous.id == model.id:
        return _out(model)
    await db.execute(update(PredictionModel).where(
        PredictionModel.org_id == current_user.org_id, PredictionModel.dataset_id == dataset_id,
        PredictionModel.name == model.name, PredictionModel.id != model.id)
        .values(status=CANDIDATE))
    model.status = CHAMPION
    model.promoted_at = datetime.utcnow()
    model.promoted_by = current_user.id
    from ..services.audit import record
    await record(db, current_user, "model.promote", "prediction_model", model.id,
                 f"{model.name} v{model.version} replaces "
                 f"{'v' + str(previous.version) if previous is not None else 'no champion'}")
    await db.commit()
    await db.refresh(model)
    return _out(model)


@router.get("/{dataset_id}/prediction-models")
async def list_models(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Models on this dataset that the caller may actually use.

    A model whose features include a denied column is omitted entirely rather
    than listed-and-refused: naming it would tell the caller that column exists
    and is worth predicting from, which is what the rule denies them.
    """
    await _dataset_for_read(dataset_id, db, current_user)
    denied = set(await resolve_denied_columns(db, current_user, dataset_id) or [])
    rows = (await db.execute(
        select(PredictionModel)
        .where(PredictionModel.dataset_id == dataset_id,
               PredictionModel.org_id == current_user.org_id)
        .order_by(PredictionModel.id.desc())
    )).scalars().all()
    return [_out(m) for m in rows
            if not (denied & set(m.features or []))]


async def load_usable_model(db: AsyncSession, user: User, dataset_id: int,
                            model_id: int) -> tuple[PredictionModel, PackagedModel]:
    """The saved model, packaged -- or the HTTPException that says why not.

    Shared by the score endpoint, the canvas scoring widget, promotion, drift
    and (through services/model_access.py, where the rule lives) the batch
    scoring job, so none of them can drift: the denied-feature refusal and
    the same-rows rule are the whole security story of a saved model, and a
    second copy is the one that would be forgotten."""
    try:
        return await usable_model(db, user, dataset_id, model_id)
    except ModelAccessError as e:
        raise HTTPException(e.status, e.message)


@router.post("/{dataset_id}/prediction-models/{model_id}/score")
async def score_model(
    dataset_id: int, model_id: int, req: ScoreRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Predictions for rows whose outcome is not known yet, from this version.

    The result names the version that scored, so a batch of predictions can
    be traced to the exact model that made it (E13)."""
    ds = await _dataset_for_read(dataset_id, db, current_user)
    # The denied-feature refusal and the same-rows rule live in one helper,
    # shared with the canvas scoring widget (see load_usable_model).
    model, pkg = await load_usable_model(db, current_user, dataset_id, model_id)

    if req.from_dataset:
        # The caller's OWN rows, prepared as the model was trained: the same
        # function the batch scoring job uses.
        try:
            frame = await secured_frame(db, current_user, ds, limit=max(1, min(req.limit, 50_000)))
        except ModelAccessError as e:
            raise HTTPException(e.status, e.message)
    elif req.rows:
        frame = pd.DataFrame(req.rows)
    else:
        raise HTTPException(400, "Provide rows to score, or set from_dataset")

    try:
        out = await asyncio.to_thread(score_frame, pkg, frame)
    except ModelStoreError as e:
        raise HTTPException(400, str(e))
    return {**out, "model": {"id": model.id, "name": model.name, "version": model.version or 1,
                             "status": model.status or CHAMPION}}


@router.get("/{dataset_id}/prediction-models/{model_id}/drift")
async def model_drift(
    dataset_id: int, model_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """How far the dataset's rows have moved from what this version was
    trained on (E13): a population stability index per predictor, over the
    rows the caller may see now. A version saved before training profiles
    were kept cannot be compared, and says so."""
    ds = await _dataset_for_read(dataset_id, db, current_user)
    model, pkg = await load_usable_model(db, current_user, dataset_id, model_id)
    profile = (model.card or {}).get("feature_profile")
    if not profile:
        raise HTTPException(409, "This version was saved before training profiles were kept, "
                                 "so there is nothing to compare today's rows with. Retrain it.")
    try:
        frame = await secured_frame(db, current_user, ds)
    except ModelAccessError as e:
        raise HTTPException(e.status, e.message)
    from ..services.analysis.model_store import drift_report
    report = await asyncio.to_thread(drift_report, profile, frame)
    return {**report, "model": {"id": model.id, "name": model.name, "version": model.version or 1},
            "trained_rows": (model.card or {}).get("n_fitted")}


@router.post("/{dataset_id}/prediction-models/{model_id}/drift-checks", status_code=201)
async def record_drift_check(
    dataset_id: int, model_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Check drift now and keep the check in the version's history (E13).
    Anyone who may use the version may check it: the rows it compares are
    the ones the version was trained on, whoever asks."""
    report = await model_drift(dataset_id, model_id, db, current_user)
    from ..services.model_drift import record, snapshot
    model = await db.get(PredictionModel, model_id)
    history = record(model, snapshot(report))
    await db.commit()
    return {**report, "history": history}


@router.get("/{dataset_id}/prediction-models/{model_id}/drift-history")
async def drift_history(
    dataset_id: int, model_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """The kept checks, newest last: the daily one the scheduler runs for each
    champion, and each one someone asked for."""
    await _dataset_for_read(dataset_id, db, current_user)
    model, _pkg = await load_usable_model(db, current_user, dataset_id, model_id)
    from ..services.model_drift import history_of
    return {"history": history_of(model)}


@router.post("/{dataset_id}/prediction-models/{model_id}/score-jobs", status_code=202)
async def queue_score_job(
    dataset_id: int, model_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Score every row the caller may see with this version, as a durable job
    that keeps the result as a new dataset (E13). Authoring: it creates one."""
    ds = await _dataset_for_read(dataset_id, db, current_user)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    model, _pkg = await load_usable_model(db, current_user, dataset_id, model_id)
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Scoring the dataset is available for import-mode datasets only")
    from ..services import jobs as job_service
    from ..services.model_scoring import MODEL_SCORE_KIND
    job, _created = await job_service.enqueue(
        db, user=current_user, kind=MODEL_SCORE_KIND,
        inputs={"dataset_id": dataset_id, "model_id": model.id},
        subject=f"Score {ds.name} with {model.name} v{model.version or 1}")
    return {"id": job.id, "state": job.state, "kind": job.kind, "subject": job.subject}


@router.delete("/{dataset_id}/prediction-models/{model_id}", status_code=204)
async def delete_model(
    dataset_id: int, model_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    await _dataset_for_read(dataset_id, db, current_user)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    model = await db.get(PredictionModel, model_id)
    if not model or model.dataset_id != dataset_id:
        raise HTTPException(404, "Model not found")
    check_org(model, current_user, "Model not found")
    # Deleting the champion hands the title to the newest remaining version,
    # so "use the current champion" keeps meaning a model.
    name, was_champion = model.name, (model.status or CHAMPION) == CHAMPION
    await db.delete(model)
    await db.flush()
    if was_champion:
        heir = (await db.execute(select(PredictionModel).where(
            PredictionModel.org_id == current_user.org_id, PredictionModel.dataset_id == dataset_id,
            PredictionModel.name == name).order_by(PredictionModel.version.desc()))).scalars().first()
        if heir is not None:
            heir.status = CHAMPION
            heir.promoted_at = datetime.utcnow()
            heir.promoted_by = current_user.id
    await db.commit()
