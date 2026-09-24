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

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import require_dataset_capability, require_dataset_read
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.rls import resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import Dataset, PredictionModel, User
from ..services.analysis.model_store import (ModelStoreError, PackagedModel,
                                             fit_and_package, score_frame)
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


def _out(m: PredictionModel) -> dict:
    """The model as JSON. The artifact never travels: it is a pickle, and
    nothing outside this service has any use for it."""
    return {
        "id": m.id, "name": m.name, "dataset_id": m.dataset_id,
        "target": m.target, "features": m.features or [],
        "task": m.task, "model_family": m.model_family,
        "score": m.score, "score_name": m.score_name,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _dataset_for_read(dataset_id: int, db: AsyncSession, user: User) -> Dataset:
    await require_dataset_read(db, user, dataset_id)
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    return ds


def _refuse_denied_features(features: list[str], denied: list[str]) -> None:
    """A model fitted on a column the caller may not read is not theirs to use.

    Refused by NAME so the caller can act on it. The subtlety worth stating:
    this is NOT solved by dropping the column from the request, because the
    model was fitted on it and its influence is inside the estimator. The only
    correct answer is to refuse the model.
    """
    hit = [c for c in features if c in (denied or [])]
    if hit:
        raise HTTPException(
            400,
            f"This model was trained on '{hit[0]}', which is not available to "
            f"you. Its predictions are derived from that column, so it cannot "
            f"be used on your behalf.")


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
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Training is available for import-mode datasets only")

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
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        # A denied column must not become a predictor: the resulting model
        # would carry it, and every future caller would inherit the leak.
        for column in (denied or []):
            if column in df.columns:
                df = df.drop(columns=[column])
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

    row = PredictionModel(
        org_id=current_user.org_id, dataset_id=dataset_id, name=req.name,
        target=pkg.target, features=pkg.features, feature_columns=pkg.feature_columns,
        categories=pkg.categories, task=pkg.task, model_family=pkg.model_family,
        score=pkg.score, score_name=pkg.score_name, artifact=pkg.artifact,
        # Recorded so the model can be refused to anyone who sees different
        # rows than it was fitted on.
        trained_rls=rls_expr,
        created_by=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)


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

    Shared by the score endpoint and the canvas scoring widget, so the two
    cannot drift: the denied-feature refusal and the same-rows rule below are
    the whole security story of a saved model, and a second copy is the one
    that would be forgotten."""
    model = await db.get(PredictionModel, model_id)
    if not model or model.dataset_id != dataset_id:
        raise HTTPException(404, "Model not found")
    check_org(model, user, "Model not found")
    denied = await resolve_denied_columns(db, user, dataset_id)
    _refuse_denied_features(list(model.features or []), denied)
    caller_rls = await resolve_rls_expr(db, user, dataset_id)
    if (model.trained_rls or None) != (caller_rls or None):
        raise HTTPException(
            400,
            "This model was trained on a different set of rows than you can "
            "see, so its answers are not yours to read. Train one under your "
            "own access instead.")
    return model, PackagedModel(
        artifact=bytes(model.artifact), target=model.target,
        features=list(model.features or []),
        feature_columns=list(model.feature_columns or []),
        categories=dict(model.categories or {}), task=model.task,
        model_family=model.model_family, score=model.score,
        score_name=model.score_name or "",
    )


@router.post("/{dataset_id}/prediction-models/{model_id}/score")
async def score_model(
    dataset_id: int, model_id: int, req: ScoreRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Predictions for rows whose outcome is not known yet."""
    ds = await _dataset_for_read(dataset_id, db, current_user)
    # The denied-feature refusal and the same-rows rule live in one helper,
    # shared with the canvas scoring widget (see load_usable_model).
    model, pkg = await load_usable_model(db, current_user, dataset_id, model_id)

    if req.from_dataset:
        if not ds.filename or ds.mode == "directquery":
            raise HTTPException(400, "Scoring the dataset is available for import-mode datasets only")
        rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
        # Column security too, as training does: a model never sees a column
        # this caller may not read -- not even through a calculated column or
        # a prep step derived from one.
        denied = await resolve_denied_columns(db, current_user, dataset_id) or []
        _steps = prep_steps_of(ds)
        _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

        def _load() -> pd.DataFrame:
            df = load_file(ds.filename)
            # The caller's OWN rows. Scoring the whole table for a restricted
            # viewer would hand back predictions for rows they cannot read.
            df = apply_rls_filter(df, rls_expr)
            df = df.drop(columns=[c for c in denied if c in df.columns])
            # And the same prep the model was TRAINED on: scoring raw rows
            # with a model fitted on prepped ones aligns nothing.
            df = apply_prep_steps(df, _steps, _aux)
            if ds.calculated_columns:
                df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
            df = df.drop(columns=[c for c in denied if c in df.columns])
            return df.head(max(1, min(req.limit, 50_000)))

        try:
            frame = await asyncio.to_thread(_load)
        except FileNotFoundError:
            raise HTTPException(404, "Dataset file not found on server — please re-upload the file")
    elif req.rows:
        frame = pd.DataFrame(req.rows)
    else:
        raise HTTPException(400, "Provide rows to score, or set from_dataset")

    try:
        return await asyncio.to_thread(score_frame, pkg, frame)
    except ModelStoreError as e:
        raise HTTPException(400, str(e))


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
    await db.delete(model)
    await db.commit()
