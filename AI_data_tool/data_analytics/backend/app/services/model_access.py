"""Who may use a saved model, and on which rows (E13).

A saved model carries the influence of every column it was trained on and of
the rows it saw, so using one is refused to anyone denied one of its features
or who sees different rows than it was trained on. That rule used to live in
the prediction-models router alone; batch scoring runs as a durable job,
outside any request, and must apply exactly the same rule -- so it lives here,
once, and the router and the job both call it.

Raises `ModelAccessError(status, message)` rather than an HTTP exception:
this module is a service (tests/test_layer_conformance.py), and the router
turns the status into its response.
"""
from __future__ import annotations

import asyncio

import pandas as pd

from ..core.rls import resolve_denied_columns, resolve_rls_expr
from ..models.models import Dataset, PredictionModel, User
from .analysis.model_store import PackagedModel


class ModelAccessError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def packaged(model: PredictionModel) -> PackagedModel:
    return PackagedModel(
        artifact=bytes(model.artifact), target=model.target,
        features=list(model.features or []),
        feature_columns=list(model.feature_columns or []),
        categories=dict(model.categories or {}), task=model.task,
        model_family=model.model_family, score=model.score,
        score_name=model.score_name or "", card=dict(model.card or {}),
    )


async def usable_model(db, user: User, dataset_id: int,
                       model_id: int) -> tuple[PredictionModel, PackagedModel]:
    """The saved model, packaged -- or the refusal that says why not."""
    model = await db.get(PredictionModel, model_id)
    if not model or model.dataset_id != dataset_id or model.org_id != user.org_id:
        raise ModelAccessError(404, "Model not found")
    denied = await resolve_denied_columns(db, user, dataset_id) or []
    hit = [c for c in (model.features or []) if c in denied]
    if hit:
        # Not solved by dropping the column from the request: the model was
        # fitted on it and its influence is inside the estimator.
        raise ModelAccessError(
            400,
            f"This model was trained on '{hit[0]}', which is not available to "
            f"you. Its predictions are derived from that column, so it cannot "
            f"be used on your behalf.")
    caller_rls = await resolve_rls_expr(db, user, dataset_id)
    if (model.trained_rls or None) != (caller_rls or None):
        raise ModelAccessError(
            400,
            "This model was trained on a different set of rows than you can "
            "see, so its answers are not yours to read. Train one under your "
            "own access instead.")
    return model, packaged(model)


async def secured_frame(db, user: User, ds: Dataset, limit: int | None = None) -> pd.DataFrame:
    """The dataset's rows as this person may see them, prepared as a model
    trained on it saw them: their row rule, no denied column (not even through
    a prep step or a calculated column), the dataset's prep and calculated
    columns. Import-mode datasets only."""
    from .analytics import load_file
    from .prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    from .widget_data import apply_calculated_columns, apply_rls_filter

    if not ds.filename or ds.mode == "directquery":
        raise ModelAccessError(400, "Scoring the dataset is available for import-mode datasets only")
    rls_expr = await resolve_rls_expr(db, user, ds.id)
    denied = await resolve_denied_columns(db, user, ds.id) or []
    steps = prep_steps_of(ds)
    aux = await resolve_join_frames(db, user, steps) if steps else {}
    calc, funcs = ds.calculated_columns, ds.custom_functions

    def _load() -> pd.DataFrame:
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = df.drop(columns=[c for c in denied if c in df.columns])
        df = apply_prep_steps(df, steps, aux)
        if calc:
            df = apply_calculated_columns(df, calc, funcs)
        df = df.drop(columns=[c for c in denied if c in df.columns])
        return df if limit is None else df.head(max(1, limit))

    try:
        return await asyncio.to_thread(_load)
    except FileNotFoundError:
        raise ModelAccessError(404, "Dataset file not found on server — please re-upload the file")
