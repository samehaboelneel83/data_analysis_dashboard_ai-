"""Report quality as CI (Phase 7.4): server-side review, performance
evaluation and the org's optional publish gate."""
import asyncio
import statistics
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.capability import require_capability
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user, require_org_admin
from ..models.models import OrgReviewSettings, QueryRun, Report, ReportPage, User
from ..services.audit import record as audit
from ..services.report_review import high_findings

router = APIRouter(tags=["review"])

#: A widget slower than this is named; the builder's pane uses the same line.
SLOW_MS = 2000


async def gate_on(db: AsyncSession, org_id: int) -> bool:
    row = (await db.execute(select(OrgReviewSettings).where(OrgReviewSettings.org_id == org_id))).scalar_one_or_none()
    return bool(row and row.publish_gate)


async def report_pages(db: AsyncSession, report_id: int) -> list[dict]:
    pages = (await db.execute(select(ReportPage).options(selectinload(ReportPage.widgets))
                              .where(ReportPage.report_id == report_id)
                              .order_by(ReportPage.position))).scalars().all()
    return [{"id": p.id, "name": p.name,
             "widgets": [{"id": w.id, "widget_type": w.widget_type, "title": w.title,
                          "config": w.config or {}} for w in p.widgets]} for p in pages]


@router.get("/reports/{report_id}/review")
async def review_report(report_id: int, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "view")
    return {"findings": high_findings(await report_pages(db, report_id)),
            "publish_gate": await gate_on(db, report.org_id)}


@router.post("/reports/{report_id}/evaluate-performance")
async def evaluate_performance(report_id: int, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    """Evaluate Performance: every data widget run NOW, uncached, as the caller
    (so the timing is a real reader's), ranked by cost -- plus each dataset's
    recorded history from the monitoring table (runs, median and p95 over the
    last 7 days, cache-hit share), and a sentence of advice per slow widget."""
    from ..schemas.schemas import WidgetDataRequest
    from .widget_data import _resolve_widget_data

    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    pages = await report_pages(db, report_id)
    rows = []
    for p in pages:
        for w in p["widgets"]:
            if w["widget_type"] in ("text", "button", "image", "shape", "container", "web_content", "slicer"):
                continue
            ds_id = w["config"].get("dataset_id") or report.dataset_id
            if not ds_id:
                continue
            cfg = {**w["config"], "__perf_probe__": time.time()}   # a fresh key: never a cache hit
            start = time.monotonic()
            error = None
            n = None
            try:
                res = await _resolve_widget_data(int(ds_id), WidgetDataRequest(
                    widget_type=w["widget_type"], config=cfg, report_id=report_id), db, current_user,
                    via_report_id=report_id)
                n = len(res.get("rows") or []) if isinstance(res, dict) else None
            except HTTPException as e:
                error = str(e.detail)
            except Exception as e:  # noqa: BLE001 -- one widget must not sink the evaluation
                error = str(e)[:200]
            ms = int((time.monotonic() - start) * 1000)
            advice = []
            if ms > SLOW_MS:
                advice.append("Slow for every reader: filter it to fewer rows, aggregate before charting "
                              "(a prep aggregate step), or pre-compute it as a materialized dataset.")
            if n is not None and n > 500:
                advice.append(f"Draws {n:,} marks — more than a reader can see; add a Top N or a row limit.")
            rows.append({"widget_id": w["id"], "title": w["title"] or w["widget_type"], "page": p["name"],
                         "widget_type": w["widget_type"], "dataset_id": int(ds_id), "ms": ms,
                         "rows": n, "error": error, "advice": advice})
    rows.sort(key=lambda r: r["ms"], reverse=True)

    since = datetime.utcnow() - timedelta(days=7)
    history = {}
    for ds_id in sorted({r["dataset_id"] for r in rows}):
        runs = (await db.execute(select(QueryRun.duration_ms, QueryRun.cache_hit)
                                 .where(QueryRun.dataset_id == ds_id, QueryRun.org_id == report.org_id,
                                        QueryRun.created_at >= since))).all()
        durations = sorted(int(d) for d, _ in runs)
        history[str(ds_id)] = {
            "runs": len(runs),
            "median_ms": int(statistics.median(durations)) if durations else None,
            "p95_ms": durations[int(0.95 * (len(durations) - 1))] if durations else None,
            "cache_hit_share": round(sum(1 for _, c in runs if c) / len(runs), 3) if runs else None,
        }
    total = sum(r["ms"] for r in rows)
    return {"widgets": rows, "total_ms": total, "slow_ms": SLOW_MS,
            "slow": sum(1 for r in rows if r["ms"] > SLOW_MS), "history": history,
            "measured_at": datetime.utcnow().isoformat()}


@router.get("/review-settings")
async def get_review_settings(db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    return {"publish_gate": await gate_on(db, current_user.org_id)}


@router.put("/review-settings")
async def put_review_settings(body: dict, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_org_admin)):
    row = (await db.execute(select(OrgReviewSettings)
                            .where(OrgReviewSettings.org_id == current_user.org_id))).scalar_one_or_none()
    if row is None:
        row = OrgReviewSettings(org_id=current_user.org_id)
        db.add(row)
    row.publish_gate = bool(body.get("publish_gate"))
    row.updated_by = current_user.id
    await audit(db, current_user, "org.review_gate", "org", current_user.org_id,
                "on" if row.publish_gate else "off")
    await db.commit()
    return {"publish_gate": row.publish_gate}
