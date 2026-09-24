"""The semantic layer as an API (Phase 7.6): Python comes to the governed data.

A notebook (or any script) authenticates with an API key -- which acts AS the
user who issued it -- and asks for a dataset's rows or aggregates. What comes
back is exactly what that user would see in a dashboard: their row-level
security, their column security, the dataset's prep recipe, its author filter
and calculated columns, its named measures evaluated at the requested grain,
its export policy and its sensitivity label (personal-data columns redacted
from Confidential data; Restricted data only for data-level access). Every
call is audited. No second copy of the rules exists for the API to drift from.

    GET  /semantic/datasets                  the catalog: columns, measures, labels
    POST /semantic/query                     group by dimensions, aggregate measures
    GET  /semantic/datasets/{id}/rows        secured rows, paged
"""
from __future__ import annotations

import asyncio
import io

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.capability import readable_dataset_ids, require_dataset_read
from ..core.database import get_db
from ..core.rls import expand_author_expressions, resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user
from ..models.models import Dataset, User
from ..services.audit import record as audit

router = APIRouter(prefix="/semantic", tags=["semantic"])

MAX_GROUPS = 100_000
MAX_ROWS_PAGE = 50_000
AGGS = {"sum": "sum", "avg": "mean", "mean": "mean", "min": "min", "max": "max",
        "count": "count", "countd": "nunique", "median": "median"}


async def _governed(db: AsyncSession, user: User, dataset_id: int) -> tuple[Dataset, pd.DataFrame, list[dict]]:
    """The frame as `user` may see it, plus the dataset's measure definitions."""
    from ..services.ingest import load_file
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    from ..services.sensitivity import redacted_columns
    from ..services.widget_data import apply_calculated_columns, apply_filter_expr, apply_rls_filter
    from .datasets import _dataset_has_security, _exports_disabled, _policy_dataset
    from .shared import download_gate

    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    if ds is None or ds.org_id != user.org_id:
        raise HTTPException(404, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    if ds.mode == "directquery" or not ds.filename:
        raise HTTPException(400, "The semantic API serves import datasets; query a live source through its dashboards")
    if _exports_disabled(await _policy_dataset(db, ds), "api", await _dataset_has_security(db, dataset_id)):
        raise HTTPException(403, "Exports are disabled for this dataset, and the API is an export")
    label = await download_gate(db, user, dataset_id=dataset_id)
    rls = await resolve_rls_expr(db, user, dataset_id)
    denied = set(await resolve_denied_columns(db, user, dataset_id) or []) \
        | set(await redacted_columns(db, dataset_id, label))
    steps = prep_steps_of(ds)
    aux = await resolve_join_frames(db, user, steps) if steps else {}
    author_filter, calc_cols, measures = await expand_author_expressions(
        db, user, ds.default_filter_expr, list(ds.calculated_columns or []), list(ds.measures or []))

    def build() -> pd.DataFrame:
        frame = apply_rls_filter(load_file(ds.filename), rls)
        frame = frame.drop(columns=[c for c in denied if c in frame.columns])
        if steps:
            frame = apply_prep_steps(frame, steps, aux)
        if author_filter:
            frame = apply_filter_expr(frame, author_filter, silent=True)
        if calc_cols:
            frame = apply_calculated_columns(frame, calc_cols, ds.custom_functions)
        return frame.drop(columns=[c for c in denied if c in frame.columns])
    try:
        return ds, await asyncio.to_thread(build), measures or []
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server")


def _respond(frame: pd.DataFrame, fmt: str, name: str, meta: dict):
    if fmt == "csv":
        buf = io.BytesIO(frame.to_csv(index=False).encode("utf-8-sig"))
        return StreamingResponse(buf, media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    if fmt != "json":
        raise HTTPException(400, "format must be json or csv")
    from ..services.widget_shaping import safe
    return {**meta, "columns": list(map(str, frame.columns)),
            "rows": [[safe(v) for v in row] for row in frame.itertuples(index=False)]}


@router.get("/datasets")
async def catalog(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.sensitivity import dataset_effective
    readable = await readable_dataset_ids(db, current_user)
    q = select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.org_id == current_user.org_id)
    out = []
    for ds in (await db.execute(q)).scalars().all():
        if readable is not None and ds.id not in readable:
            continue
        denied = set(await resolve_denied_columns(db, current_user, ds.id) or [])
        label, _ = await dataset_effective(db, ds.id)
        out.append({
            "id": ds.id, "name": ds.name, "mode": ds.mode, "sensitivity": label,
            "columns": [{"name": c.name, "dtype": c.dtype, "semantic_type": c.semantic_type,
                         "description": c.description} for c in ds.columns if c.name not in denied],
            "calculated_columns": [c.get("name") for c in (ds.calculated_columns or [])],
            "measures": [{"name": m.get("name"), "description": m.get("description")}
                         for m in (ds.measures or []) if isinstance(m, dict)],
        })
    return {"datasets": out}


@router.post("/query")
async def query(body: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """`{dataset_id, dimensions: [col...], measures: ["Named measure" | {"column", "agg"}],
    filters: [{column, op, value}], limit, format: "json"|"csv"}`."""
    from ..services.measure_eval import evaluate_measure, resolve_measure
    from ..services.widget_data import _apply_filters
    try:
        dataset_id = int(body.get("dataset_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "dataset_id is required")
    dims = body.get("dimensions") or []
    specs = body.get("measures") or []
    if not isinstance(dims, list) or not isinstance(specs, list) or not (dims or specs):
        raise HTTPException(400, "Ask for at least one dimension or measure")
    limit = max(1, min(int(body.get("limit") or MAX_GROUPS), MAX_GROUPS))
    ds, frame, measure_defs = await _governed(db, current_user, dataset_id)
    missing = [d for d in dims if d not in frame.columns]
    if missing:
        raise HTTPException(400, f"Column '{missing[0]}' is not available to you on this dataset")
    filters = body.get("filters") if isinstance(body.get("filters"), list) else []

    def run() -> pd.DataFrame:
        f = _apply_filters(frame, filters)
        pieces = []
        for spec in specs:
            if isinstance(spec, str):
                mdef = resolve_measure(spec, measure_defs)
                if mdef is None:
                    raise HTTPException(400, f"No measure named '{spec}' on this dataset")
                vals = evaluate_measure(mdef["expression"], f, list(dims))
                pieces.append((spec, vals))
            elif isinstance(spec, dict):
                col, agg = spec.get("column"), str(spec.get("agg") or "sum").lower()
                if agg not in AGGS:
                    raise HTTPException(400, f"agg must be one of {sorted(AGGS)}")
                if agg != "count" and col not in f.columns:
                    raise HTTPException(400, f"Column '{col}' is not available to you on this dataset")
                name = spec.get("as") or (f"{agg}_{col}" if col else "count")
                series = f[col] if col in f.columns else pd.Series(1, index=f.index)
                if agg not in ("count", "countd"):
                    series = pd.to_numeric(series, errors="coerce")
                vals = getattr(series.groupby([f[d] for d in dims]), AGGS[agg])() if dims else getattr(series, AGGS[agg])()
                pieces.append((name, vals))
            else:
                raise HTTPException(400, "each measure is a name or {column, agg}")
        if not dims:
            return pd.DataFrame([{n: (v if not isinstance(v, pd.Series) else v.iloc[0]) for n, v in pieces}])
        out = f.groupby(dims).size().rename("rows").to_frame()
        for n, v in pieces:
            out[n] = v if isinstance(v, pd.Series) else v
        return out.reset_index().head(limit)
    try:
        result = await asyncio.to_thread(run)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await audit(db, current_user, "semantic.query", "dataset", dataset_id,
                f"{', '.join(map(str, dims)) or '(total)'} × {len(specs)} measure(s)")
    await db.commit()
    return _respond(result, str(body.get("format") or "json"), f"{ds.name}-query",
                    {"dataset_id": dataset_id, "row_count": int(len(result))})


@router.get("/datasets/{dataset_id}/rows")
async def rows(dataset_id: int, offset: int = 0, limit: int = 10_000, columns: str | None = None,
               format: str = "json", db: AsyncSession = Depends(get_db),
               current_user: User = Depends(get_current_user)):
    """Secured row-level data, paged (at most 50,000 rows per call)."""
    limit = max(1, min(limit, MAX_ROWS_PAGE))
    ds, frame, _ = await _governed(db, current_user, dataset_id)
    if columns:
        wanted = [c.strip() for c in columns.split(",") if c.strip()]
        missing = [c for c in wanted if c not in frame.columns]
        if missing:
            raise HTTPException(400, f"Column '{missing[0]}' is not available to you on this dataset")
        frame = frame[wanted]
    total = int(len(frame))
    page = frame.iloc[max(0, offset): max(0, offset) + limit]
    await audit(db, current_user, "semantic.rows", "dataset", dataset_id, f"rows {offset}-{offset + len(page)} of {total}")
    await db.commit()
    return _respond(page, format, ds.name, {"dataset_id": dataset_id, "total_rows": total,
                                            "offset": offset, "row_count": int(len(page)),
                                            "next_offset": offset + len(page) if offset + len(page) < total else None})
