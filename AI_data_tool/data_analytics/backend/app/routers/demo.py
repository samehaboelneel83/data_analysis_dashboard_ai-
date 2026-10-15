"""Load (and unload) the demo content for the calling user's organization.

Everything here writes into `current_user.org_id` and nothing else. The seeders
themselves flush rather than commit, so this router owns the transaction: either the
whole demo lands or none of it does. That matters because the four passes are not
independent -- reports reference datasets, and the feature pass patches widgets the
report pass created -- so a partial success would leave a demo that loads and looks
fine while being quietly wrong.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..dependencies import require_org_admin
from ..models.models import Report, ReportPage, ReportWidget, User
from ..services.demo_content import (
    remove_demo_content,
    seed_demo_datasets,
    seed_demo_directquery,
    seed_demo_features,
    seed_demo_reports,
    seed_demo_ux_showcase,
)
from ..services.demo_use_cases import seed_demo_use_cases, seed_demo_workspace

router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger(__name__)


async def _start_demo_sync(db: AsyncSession, org_id: int, source) -> int | None:
    """B-26: read the demo connection's catalog right away (a local SQLite
    file: seconds), so its review page, tables and glossary links are filled
    for every new user instead of "never synced". The model is not used.

    After the demo's own commit, and never able to fail the seed: a sync that
    cannot start leaves the connection unsynced, exactly as before, with "Run
    sync" on its review page. Re-seeding deletes the source, and its runs with
    it (ON DELETE CASCADE), so this stays idempotent."""
    from ..core.config import settings
    if source is None or not settings.demo_sync_on_seed:
        return None
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from ..models.models import SyncRun
    from ..services.metadata import cache as cache_module
    from ..services.metadata import sync
    try:
        cache = cache_module.get_cache()
        run = SyncRun(data_source_id=source.id, org_id=org_id, trigger="demo_seed",
                      status="running", stages=[])
        db.add(run)
        await db.commit()
        cfg = dict(source.config or {})
        cfg["type"] = source.type
        # On the request's own engine: the app's pool (a test's database).
        factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
        asyncio.create_task(sync.run_sync_background(
            factory, run.id, source.id, org_id,
            cache=cache, llm_client=None, allow_llm=False, source_config=cfg))
        return run.id
    except Exception:                                       # noqa: BLE001 -- never fails the seed
        logger.exception("demo: could not start the sync of the demo connection")
        try:
            await db.rollback()
        except Exception:                                   # noqa: BLE001
            pass
        return None


@router.post("/seed")
async def seed_demo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
) -> dict:
    """Fill the caller's org with the demo datasets and reports.

    Org admins only (QA E-08 follow-up): it writes org-wide datasets, a
    connection and dashboards, and DELETE removes them for everyone.

    Idempotent: each pass removes its own previously seeded content first, so calling
    this twice leaves one demo, and content the user made themselves is untouched --
    demo rows are identified by a marker, never by name.
    """
    org_id = current_user.org_id

    # Order is a hard dependency, not a preference: reports need the datasets, and the
    # feature pass patches the widgets the report pass created. seed_demo_features is
    # easy to leave out -- the demo still loads and looks complete without it, just
    # with none of the display rules, formats, calculated column or interactions that
    # are half the point. test_demo_endpoint asserts an observable artefact of it.
    datasets = await seed_demo_datasets(db, org_id)
    reports = await seed_demo_reports(db, org_id, datasets)
    await seed_demo_features(db, org_id, datasets, reports)
    # The UX showcase needs the drill hierarchy seed_demo_features just built, so it
    # runs after that pass, not alongside seed_demo_reports.
    await seed_demo_ux_showcase(db, org_id, datasets)
    # The insight-led use-case layer: additive, and independent of the showcase
    # above. It needs only the datasets, so ordering against the feature pass is
    # not load-bearing -- it runs here so a failure surfaces with the rest.
    await seed_demo_use_cases(db, org_id, datasets)
    # After every report-creating pass: the tree files what exists, so anything
    # seeded later would land in "Unfiled".
    await seed_demo_workspace(db, org_id)
    direct = await seed_demo_directquery(db, org_id)

    # Counted with an explicit query rather than by walking report.pages: those are
    # lazy relationships, and touching them outside an await raises MissingGreenlet
    # under async SQLAlchemy. Runs before the commit, while the rows are still ours.
    widget_count = (await db.execute(
        select(func.count(ReportWidget.id))
        .join(ReportPage, ReportWidget.page_id == ReportPage.id)
        .join(Report, ReportPage.report_id == Report.id)
        .where(Report.org_id == org_id)
    )).scalar_one()

    await db.commit()
    await _start_demo_sync(db, org_id, direct.get("source"))

    return {
        "datasets": len(datasets) + 1,          # + the DirectQuery one
        "reports": len(reports) + 1 + (1 if direct.get("report") else 0),  # + the showcase
        "widgets": widget_count,
    }


@router.delete("/seed")
async def unseed_demo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
) -> dict:
    """Remove the demo content from the caller's org, leaving their own data alone."""
    removed = await remove_demo_content(db, current_user.org_id)
    await db.commit()
    return removed
