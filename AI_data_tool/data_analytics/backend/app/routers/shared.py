"""Guest access: the public face of a share link. NO auth dependency here --
the token in the path IS the credential, and everything else in the API keeps
requiring a JWT, so a share token grants exactly these two read-only routes
and nothing besides.

Resolution identity: a truly anonymous caller, or an authenticated caller
from a DIFFERENT org (or an inactive/foreign session), resolves RLS + author
expressions as the LINK'S CREATOR (the schedule rule -- the sharer knowingly
exposes their own slice to anyone holding the URL, never more). An
AUTHENTICATED IN-ORG viewer -- someone who followed the link while already
logged into the same org -- resolves as THEMSELVES instead (S3): the link is
a distribution mechanism, not a way to borrow someone else's row-security
slice inside your own organisation. See `_resolve_identity` below. Page
VISIBILITY (which pages exist in the payload at all) still follows the
creator's role either way -- unchanged, see `_visible_pages`.

A vanished creator, an expired or revoked link, or a deleted report all 404
identically -- a probe learns nothing about which failed.
"""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..dependencies import get_current_user_optional
from ..models.models import (
    CommonFilter, Dataset, PageRoleVisibility, Report, ReportClassification, ReportPage, ShareLink, User,
)
from ..schemas.schemas import WidgetDataRequest

router = APIRouter(prefix="/shared", tags=["shared"])


def _expired(expires_at: datetime) -> bool:
    # Postgres hands back timezone-AWARE datetimes for timezone=True columns,
    # SQLite naive ones -- so the unit suite cannot catch a naive/aware mixup
    # here, and the first live drive of this route did. Normalise both sides.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _shape_widget(w) -> dict:
    """Normalise a widget to one dict shape whether it came from a live
    ReportWidget row or a stored PageOut/WidgetOut snapshot dict."""
    if isinstance(w, dict):
        return {"id": w["id"], "page_id": w["page_id"], "widget_type": w["widget_type"],
                "title": w.get("title"), "config": w.get("config") or {}, "layout": w.get("layout") or {}}
    return {"id": w.id, "page_id": w.page_id, "widget_type": w.widget_type,
            "title": w.title, "config": w.config or {}, "layout": w.layout or {}}


def _interaction_mode(ml) -> str:
    """The page's authored automatic-action mode, published as its own field.

    Viewers used to get no mode at all, so the provider fell back to "manual"
    and a page the author set to linked/oneway/twoway behaved as neither --
    the setting worked in the builder and silently died on publication.

    Only the four known modes pass: `mobile_layout` is author-written JSON,
    and an unrecognised string reaching the frontend union would be a filter
    rule nothing implements rather than an error anyone sees.
    """
    mode = (ml or {}).get("interaction_mode") if isinstance(ml, dict) else None
    return mode if mode in {"manual", "linked", "oneway", "twoway"} else "manual"


def _shape_page(p) -> dict:
    """Normalise a page (live ReportPage or snapshot dict) to one shape."""
    if isinstance(p, dict):
        return {"id": p["id"], "name": p["name"], "page_type": p.get("page_type", "normal"),
                "position": p.get("position", 0),
                "interaction_mode": _interaction_mode(p.get("mobile_layout")),
                "widgets": [_shape_widget(w) for w in p.get("widgets", [])]}
    return {"id": p.id, "name": p.name, "page_type": p.page_type, "position": p.position,
            "interaction_mode": _interaction_mode(p.mobile_layout),
            "widgets": [_shape_widget(w) for w in p.widgets]}


def _role_visible(p: dict, allowed_by_page: dict[int, set[int]], creator: User) -> bool:
    # Guest/embed views show ONLY ordinary pages: 'hidden' pages hold working
    # notes by convention, and 'popup'/'tooltip'/'drillthrough' pages are
    # reached by button/hover navigation neither surface wires up (no
    # onNavigateToPage) -- so serving their content here would ship it to a
    # viewer with no way to reach it through the UI and no way to hide it
    # again. Matches the authenticated builder's own view-mode tab strip,
    # which applies the same restriction.
    if p["page_type"] != "normal":
        return False
    allowed = allowed_by_page.get(p["id"])
    if allowed is None or creator.role.is_org_admin:
        return True
    return creator.role_id in allowed


async def visible_pages_for_creator(db: AsyncSession, report: Report, creator: User) -> list[dict]:
    """Pages a viewer resolving AS `creator` may see, read LIVE from the
    report -- role-restricted pages (PageRoleVisibility) are absent from the
    payload entirely, exactly as they'd be absent from the creator's own
    builder session. Shared by every surface that renders a report as a
    fixed creator identity with no snapshot of its own: the live branch of
    the guest share-link route below, and the embed route
    (routers/embed.py), which has no pinning/snapshot concept at all."""
    rows = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.report_id == report.id).order_by(ReportPage.position)
    )).scalars().all()
    raw = [_shape_page(p) for p in rows]

    restricted = (await db.execute(
        select(PageRoleVisibility).where(
            PageRoleVisibility.page_id.in_([p["id"] for p in raw] or [0]))
    )).scalars().all()
    allowed_by_page: dict[int, set[int]] = {}
    for r in restricted:
        allowed_by_page.setdefault(r.page_id, set()).add(r.role_id)

    return [p for p in raw if _role_visible(p, allowed_by_page, creator)]


async def _visible_pages(db: AsyncSession, link: ShareLink, report: Report, creator: User) -> list[dict]:
    """Pages a guest holding this link may see, served from the link's frozen
    `snapshot` when it has one (pinned link) or live from the report otherwise
    -- data stays live either way, this only decides which PAGES/WIDGETS exist.
    Shared by both the report-shape route and the per-widget-data route, so a
    widget on a page the guest can't see can never be fetched by guessing its id."""
    if link.snapshot is None:
        return await visible_pages_for_creator(db, report, creator)

    raw = [_shape_page(p) for p in link.snapshot]
    # Role visibility is read from the SNAPSHOT itself, frozen at pin time,
    # never live -- a page role-restricted when the link was pinned must
    # stay restricted even after the live page (and its cascade-deleted
    # PageRoleVisibility rows) is gone. A live lookup keyed on these
    # (possibly stale/nonexistent) page ids would silently find nothing
    # and treat the page as unrestricted -- the exact edge case this
    # guards against. See `_report_snapshot` in routers/reports.py.
    allowed_by_page: dict[int, set[int]] = {
        p["id"]: set(p.get("role_visibility") or [])
        for p in link.snapshot if p.get("role_visibility")
    }
    return [p for p in raw if _role_visible(p, allowed_by_page, creator)]


async def _resolve_link(db: AsyncSession, token: str) -> tuple[ShareLink, Report, User]:
    link = (await db.execute(
        select(ShareLink).where(ShareLink.token_hash == hash_token(token))
    )).scalar_one_or_none()
    if link is None or link.revoked_at is not None or _expired(link.expires_at):
        raise HTTPException(404, "This link does not exist or has expired")
    report = await db.get(Report, link.report_id)
    # Role rides along eagerly: resolve_rls_expr reads creator.role.is_org_admin
    # synchronously, and a lazy load there raises MissingGreenlet under async.
    creator = (await db.execute(
        select(User).options(selectinload(User.role)).where(User.id == link.creator_user_id)
    )).scalar_one_or_none()
    if report is None or creator is None or report.org_id != link.org_id:
        raise HTTPException(404, "This link does not exist or has expired")
    return link, report, creator


def _resolve_identity(link: ShareLink, creator: User, viewer: User | None) -> User:
    """S3: an authenticated caller from the link's OWN org resolves RLS +
    author-expression tokens as THEMSELVES; anyone else (anonymous, a
    different org, an inactive session) keeps the creator's slice -- the
    documented guest/anonymous semantics. `viewer` is whatever
    `get_current_user_optional` resolved from the request's own bearer
    token, if any; it has nothing to do with the token in the URL path."""
    if viewer is not None and viewer.is_active and viewer.org_id == link.org_id:
        return viewer
    return creator


def _log_access(link: ShareLink, viewer: User | None, request: Request) -> None:
    """Fire-and-forget access-log row for this guest render. Never allowed to
    fail or slow the response -- see log_share_access_sync."""
    from ..services.query_log import log_share_access_sync

    ip = request.client.host if request.client else None
    ua = (request.headers.get("user-agent") or "")[:200]
    log_share_access_sync(
        share_link_id=link.id,
        viewer_user_id=viewer.id if viewer is not None else None,
        ip_hash=hashlib.sha256(ip.encode()).hexdigest() if ip else None,
        user_agent=ua or None,
    )


def _published_geography(ds) -> dict:
    """Columns classified as geography, and the boundary set each draws with.

    A DERIVED subset of `column_meta`, never the blob: that also holds
    `__prep_steps__` and `__derived_from__` -- the recipe -- and an anonymous
    surface has no business with either. Same rule as `interaction_mode`:
    publish the one thing a viewer needs, shaped for them.

    Without this a shared link drew a world map for a column the author had
    already told the product was governorates: the classification lives on the
    DATASET, and a viewer never sees the dataset.
    """
    out: dict[str, int] = {}
    for column, meta in (getattr(ds, "column_meta", None) or {}).items():
        if column.startswith("__") or not isinstance(meta, dict):
            continue
        if meta.get("role") != "geography":
            continue
        set_id = meta.get("boundary_set_id")
        if isinstance(set_id, int):
            out[column] = set_id
    return out


async def sensitivity_gate(db: AsyncSession, report: Report, viewer: User | None,
                           *, surface: str = "share link") -> str | None:
    """Enforce the report's EFFECTIVE sensitivity on a publication surface
    (Phase 7.3). Restricted: no share links or embeds at all. Confidential:
    no anonymous or cross-org readers -- a signed-in member of the report's
    org still opens it as themselves. Returns the label, for redaction."""
    from ..services.sensitivity import rank, report_effective
    label, reasons = await report_effective(db, report)
    why = f" ({reasons[0]})" if reasons else ""
    if rank(label) >= rank("Restricted"):
        raise HTTPException(403, f"This report is Restricted{why}; it cannot be opened through a {surface}.")
    if rank(label) >= rank("Confidential") and (viewer is None or viewer.org_id != report.org_id):
        raise HTTPException(403, f"This report is Confidential{why}; sign in as a member of the organisation to open it.")
    return label


async def download_gate(db, user, *, report=None, dataset_id: int | None = None) -> str | None:
    """Downloads (CSV/Excel, PDF, offline package) under the effective label.

    Restricted: only a reader with DATA-level access may take the rows away
    (they could query the dataset anyway); everyone else gets a 403 naming
    why. Returns the label so the caller can redact personal data from what
    it hands out (Confidential and above)."""
    from ..core.capability import effective_capability, max_dataset_capability, rank as cap_rank
    from ..services.sensitivity import dataset_effective, rank, report_effective
    label, reasons = (await report_effective(db, report)) if report is not None else (None, [])
    if dataset_id is not None:
        ds_label, ds_reasons = await dataset_effective(db, dataset_id)
        if rank(ds_label) > rank(label):
            label, reasons = ds_label, ds_reasons
    if rank(label) >= rank("Restricted"):
        level = (await effective_capability(db, user, report.id)) if report is not None \
            else (await max_dataset_capability(db, user, dataset_id))
        if cap_rank(level) < cap_rank("data"):
            why = f" ({reasons[0]})" if reasons else ""
            raise HTTPException(403, f"This is Restricted{why}; only people with data-level access may download it.")
    return label


async def published_relationships(db: AsyncSession, report: Report, pages: list[dict],
                                  identity: User) -> dict:
    """The cross-source mappings a published report needs, and nothing more.

    Without these a click on a Sales chart filtered Sales widgets only on a
    shared link or an embed -- the builder translated "country" to
    "cust_country" through the org's relationships, the published viewer never
    received them, so cross-dataset filtering died at publication.

    Published: the relationships whose BOTH ends are datasets this report's
    visible widgets draw on, and for each such dataset only the names of its
    columns that appear in one of those relationships (what the client needs
    to decide whether to translate a column) -- minus columns the identity's
    column security denies. No other column names, no data.
    """
    from ..core.rls import resolve_denied_columns
    from ..models.models import Relationship

    ids: set[int] = set()
    if report.dataset_id:
        ids.add(int(report.dataset_id))
    for extra in (report.additional_dataset_ids or []):
        if isinstance(extra, int):
            ids.add(extra)
    for p in pages:
        for w in p.get("widgets") or []:
            did = (w.get("config") or {}).get("dataset_id")
            if isinstance(did, int):
                ids.add(did)
    if len(ids) < 2:
        return {"relationships": [], "datasets": {}}
    rels = (await db.execute(select(Relationship).where(
        Relationship.org_id == report.org_id,
        Relationship.from_dataset_id.in_(ids), Relationship.to_dataset_id.in_(ids)))).scalars().all()
    if not rels:
        return {"relationships": [], "datasets": {}}
    names = {r.from_column for r in rels} | {r.to_column for r in rels}
    columns: dict[int, list[str]] = {}
    for did in ids:
        ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                               .where(Dataset.id == did))).scalar_one_or_none()
        if ds is None or ds.org_id != report.org_id:
            continue
        denied = set(await resolve_denied_columns(db, identity, did) or [])
        columns[did] = sorted(c.name for c in ds.columns if c.name in names and c.name not in denied)
    out = [{"from_dataset_id": r.from_dataset_id, "from_column": r.from_column,
            "to_dataset_id": r.to_dataset_id, "to_column": r.to_column}
           for r in rels
           if r.from_column in columns.get(r.from_dataset_id, [])
           and r.to_column in columns.get(r.to_dataset_id, [])]
    return {"relationships": out,
            "datasets": {str(k): {"columns": [{"name": n} for n in v]} for k, v in columns.items()}}


@router.get("/{token}")
async def shared_report(token: str, request: Request, db: AsyncSession = Depends(get_db),
                        viewer: User | None = Depends(get_current_user_optional)):
    """The report's structure plus the rendering context (formats, calc column
    definitions) -- data itself comes per widget from the sibling route."""
    link, report, creator = await _resolve_link(db, token)
    await sensitivity_gate(db, report, viewer)
    pages = await _visible_pages(db, link, report, creator)
    _log_access(link, viewer, request)

    ds = await db.get(Dataset, report.dataset_id) if report.dataset_id else None
    classif = (await db.execute(
        select(ReportClassification).where(ReportClassification.report_id == report.id)
    )).scalar_one_or_none()
    common_filters = (await db.execute(
        select(CommonFilter).where(CommonFilter.report_id == report.id)
        .order_by(CommonFilter.position, CommonFilter.id)
    )).scalars().all()
    return {
        "name": report.name,
        "theme": report.theme,
        "classification": classif.label if classif else None,
        "common_filters": [{"id": f.id, "column": f.column, "op": f.op, "value": f.value} for f in common_filters],
        "dataset_id": report.dataset_id,
        "column_formats": (ds.column_formats or {}) if ds else {},
        "geography": _published_geography(ds) if ds else {},
        "calculated_columns": (ds.calculated_columns or []) if ds else [],
        "pages": pages,
        "pinned": link.pinned,
        **(await published_relationships(db, report, pages, _resolve_identity(link, creator, viewer))),
    }


@router.post("/{token}/widget-data/{widget_id}")
async def shared_widget_data(token: str, widget_id: int, db: AsyncSession = Depends(get_db),
                             viewer: User | None = Depends(get_current_user_optional)):
    """One widget's data, resolved from its SAVED config as the effective
    viewer (S3: the requester's own identity when they're an authenticated
    in-org user, the creator's otherwise -- see `_resolve_identity`).

    Only saved widget ids resolve, and only if the widget's page is one the
    guest can see (same rule the report-shape route applies) -- the route
    never accepts a config from the anonymous caller and never resolves a
    widget parked on a hidden/restricted page, so a share token can only
    re-read what the report's VISIBLE pages already show. Page VISIBILITY
    itself still follows the creator's role (see `_visible_pages`) -- only
    the data resolution (RLS, author-expression tokens) switches identity.
    """
    from .widget_data import _resolve_widget_data

    link, report, creator = await _resolve_link(db, token)
    label = await sensitivity_gate(db, report, viewer)
    widget = None
    for p in await _visible_pages(db, link, report, creator):
        for w in p["widgets"]:
            if w["id"] == widget_id:
                widget = w
                break
    if widget is None:
        raise HTTPException(404, "Widget not found")

    cfg = dict(widget["config"] or {})
    dataset_id = cfg.get("dataset_id") or report.dataset_id
    if not dataset_id:
        raise HTTPException(404, "Widget has no dataset")
    req = WidgetDataRequest(widget_type=widget["widget_type"], config=cfg)
    identity = _resolve_identity(link, creator, viewer)
    # The link names the report, so a same-org viewer resolved as THEMSELVES
    # still reads this widget's data: the dataset gate accepts "a dashboard
    # you can open". Without this the new gate would 404 a guest link for the
    # one class of viewer it resolves as a real user.
    from ..services.sensitivity import redacted_columns
    return await _resolve_widget_data(dataset_id, req, db, identity,
                                      via_report_id=report.id,
                                      redact_columns=await redacted_columns(db, int(dataset_id), label))
