"""Task E1: embedded reports, secured with HOST-SIGNED JWTs -- "never trust the
browser with scope" (ARCHITECTURE.md D7.1).

Two surfaces:
  * Admin CRUD (`/reports/{report_id}/embed-configs`, authenticated, gated
    like guest-link management via `require_capability(..., "edit")`): mint,
    list, enable/disable and delete embed configs. The secret is returned
    exactly ONCE, at creation -- only its enc:v2 ciphertext is ever stored,
    mirroring `core/api_keys.py`'s secret-shown-once pattern.
  * Public embed surface (`GET /embed/report`, `POST
    /embed/widget-data/{widget_id}`), reached with NO login of any kind. The
    caller instead holds a JWT that the HOST APPLICATION signed itself with
    the config's secret; that signature is the entire proof of authorization.
    Trust boundary, spelled out: everything inside a verified token's claims
    (`filters`, `viewer_email`, `viewer_org`) is trusted as the HOST'S
    assertion about its own viewer -- the browser never gets a vote. Every
    other input from the browser (query params, request bodies, the
    `Authorization` header's own claims once re-decoded) is either ignored
    outright or re-derived server-side from the config/report, never trusted
    for scope.

Identity model: EXACTLY ShareLink's guest parity (routers/shared.py
`_resolve_identity`), not "unrestricted". An embed config has a CREATOR
(`created_by`, the admin who minted it), and row-level security + denied
columns always resolve as THAT user -- an embed can never expose more than
its own creator's slice, no matter what the host's JWT claims. The verified
token's `filters` still composes ON TOP of that creator-scoped result
(narrowing further, never widening it), and `viewer_email`/`viewer_org`
still override USEREMAIL()/ORGID() expansion inside a dataset's OWN author
expressions (default_filter_expr, calculated columns) via the
`email_override`/`org_id_override` params already threaded through
`_resolve_widget_data` -- but never substitute for the creator's role in
RLS/column-security resolution, and never for tenancy, which always keys on
the config's real `org_id` (see that param's docstring in widget_data.py).

Enumeration resistance: every failure short of a fully valid, correctly-
signed, non-expired, in-allowlist token collapses to 404 ("this embed link
is invalid") EXCEPT expiry, which is reported as 401 so a host can tell
"mint me a fresh token" apart from "this integration is broken" -- a
distinction only available to someone who already holds a validly-signed
token in the first place, so it leaks nothing to a prober who doesn't.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.capability import require_capability
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.security import ALGORITHM, create_embed_session_token, decode_embed_session_token
from ..dependencies import get_current_user
from ..models.models import EmbedConfig, Report, User
from ..schemas.schemas import WidgetDataRequest
from ..services.audit import record as audit
from ..services.secrets import decrypt_value, encrypt_value

router = APIRouter(tags=["embed"])

# Token contract (plan E1): exp is required and may not sit more than 24h
# ahead of the moment it's checked -- a small leeway absorbs clock skew
# between the host that minted the token and this server.
_MAX_TOKEN_TTL = timedelta(hours=24)
_CLOCK_SKEW_LEEWAY = timedelta(minutes=5)
_INVALID = "This embed link is invalid"


def _origin_of(value: str) -> str | None:
    try:
        p = urlparse(value)
    except ValueError:
        return None
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def _origin_allowed(request: Request, allowed_origins: list) -> bool:
    """Empty allowlist = no origin restriction -- a deliberate tradeoff
    (documented in EmbedConfig's docstring): some hosts embed from contexts
    that send no Origin/Referer at all. A caller that sends NEITHER header is
    likewise let through -- there is nothing to check, and this mirrors the
    "no signal available" branch, not a bypass of one that's present."""
    if not allowed_origins:
        return True
    origin = request.headers.get("origin") or request.headers.get("referer")
    if not origin:
        return True
    host = _origin_of(origin)
    return host is not None and host in allowed_origins


async def _load_config_or_404(db: AsyncSession, cfg_id) -> EmbedConfig:
    cfg = await db.get(EmbedConfig, cfg_id) if isinstance(cfg_id, int) else None
    if cfg is None or not cfg.enabled:
        raise HTTPException(404, _INVALID)
    return cfg


async def _load_creator_or_404(db: AsyncSession, cfg: EmbedConfig) -> User:
    """The user whose RLS/column-security slice an embed always resolves as --
    see the module docstring. Role rides along eagerly: resolve_rls_expr reads
    creator.role.is_org_admin synchronously, same reason shared.py._resolve_link
    does this."""
    creator = (await db.execute(
        select(User).options(selectinload(User.role)).where(User.id == cfg.created_by)
    )).scalar_one_or_none()
    if creator is None or not creator.is_active or creator.org_id != cfg.org_id:
        raise HTTPException(404, _INVALID)
    return creator


async def _visible_widget(db: AsyncSession, report: Report, creator: User, widget_id: int) -> dict | None:
    """Only a widget on one of the pages `creator` may see resolves, as a
    shaped dict off `shared.py`'s `visible_pages_for_creator` -- the SAME
    rules a guest link gets (ordinary page_type only, PageRoleVisibility
    honoured for the creator's role), so an embed can't be used to fish for a
    hidden/popup/tooltip/drillthrough OR role-restricted page's widget by
    guessing its id."""
    from .shared import visible_pages_for_creator

    for p in await visible_pages_for_creator(db, report, creator):
        for w in p["widgets"]:
            if w["id"] == widget_id:
                return w
    return None


# ── Admin CRUD: create/list/enable-disable/delete ──────────────────────────

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


@router.post("/reports/{report_id}/embed-configs", status_code=201)
async def create_embed_config(report_id: int, body: dict, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Mint an embed config, recorded as created by THIS user -- the embed's
    entire data-access ceiling from here on. The plaintext secret is returned
    exactly ONCE; only its enc:v2 ciphertext is stored -- see
    `core/api_keys.py`'s secret-shown-once pattern, which this mirrors."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")

    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    allowed_origins = body.get("allowed_origins") or []
    if not isinstance(allowed_origins, list) or not all(isinstance(o, str) for o in allowed_origins):
        raise HTTPException(400, "allowed_origins must be a list of origin strings")

    existing = (await db.execute(
        select(EmbedConfig).where(EmbedConfig.report_id == report_id, EmbedConfig.name == name)
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "An embed config with this name already exists for this report")

    secret = secrets.token_urlsafe(32)
    cfg = EmbedConfig(org_id=current_user.org_id, report_id=report_id, created_by=current_user.id, name=name,
                      secret_encrypted=encrypt_value(secret), allowed_origins=allowed_origins, enabled=True)
    db.add(cfg)
    await audit(db, current_user, "report.embed_config_created", "report", report_id, name)
    await db.commit()
    await db.refresh(cfg)
    return {"id": cfg.id, "name": cfg.name, "secret": secret, "allowed_origins": cfg.allowed_origins,
            "enabled": cfg.enabled, "created_at": cfg.created_at,
            "note": "Copy this secret now -- it is shown only once and cannot be recovered."}


@router.get("/reports/{report_id}/embed-configs")
async def list_embed_configs(report_id: int, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(EmbedConfig).where(EmbedConfig.report_id == report_id).order_by(EmbedConfig.created_at.desc())
    )).scalars().all()
    return [{"id": c.id, "name": c.name, "allowed_origins": c.allowed_origins, "enabled": c.enabled,
             "created_at": c.created_at, "last_used_at": c.last_used_at} for c in rows]


@router.patch("/reports/{report_id}/embed-configs/{config_id}")
async def update_embed_config(report_id: int, config_id: int, body: dict, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Enable/disable (revoke) an embed config. Revocation, not deletion --
    mirrors ShareLink: the row (and its audit trail) stays."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    cfg = await db.get(EmbedConfig, config_id)
    if cfg is None or cfg.report_id != report_id:
        raise HTTPException(404, "Embed config not found")
    if "enabled" in body:
        cfg.enabled = bool(body["enabled"])
    if "allowed_origins" in body:
        allowed_origins = body["allowed_origins"] or []
        if not isinstance(allowed_origins, list) or not all(isinstance(o, str) for o in allowed_origins):
            raise HTTPException(400, "allowed_origins must be a list of origin strings")
        cfg.allowed_origins = allowed_origins
    await audit(db, current_user, "report.embed_config_updated", "report", report_id, cfg.name)
    await db.commit()
    return {"id": cfg.id, "name": cfg.name, "allowed_origins": cfg.allowed_origins, "enabled": cfg.enabled}


@router.delete("/reports/{report_id}/embed-configs/{config_id}", status_code=204)
async def delete_embed_config(report_id: int, config_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    cfg = await db.get(EmbedConfig, config_id)
    if cfg is None or cfg.report_id != report_id:
        raise HTTPException(404, "Embed config not found")
    await audit(db, current_user, "report.embed_config_deleted", "report", report_id, cfg.name)
    await db.delete(cfg)
    await db.commit()


# ── Public embed surface ────────────────────────────────────────────────────

@router.get("/embed/report")
async def embed_report(token: str, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Decode UNVERIFIED header -> cfg id -> load config (else 404) -> verify
    signature with the config's decrypted secret -> origin check -> return the
    report structure plus a short-lived internal session token for widget-data
    calls. Every step here is described, in this order, by the plan's
    "Endpoint flow" -- see the module docstring for the trust model."""
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError:
        raise HTTPException(404, _INVALID)
    cfg = await _load_config_or_404(db, unverified.get("cfg"))

    try:
        secret = decrypt_value(cfg.secret_encrypted)
    except ValueError:
        raise HTTPException(404, _INVALID)

    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require_exp": True})
    except ExpiredSignatureError:
        raise HTTPException(401, "This embed token has expired")
    except (JWTClaimsError, JWTError):
        # Bad signature, tampered payload, missing/malformed exp -- collapsed
        # into the SAME 404 a nonexistent config gets, so a prober watching
        # status codes can't use "401 vs 404" as an oracle for "this cfg id
        # exists but I don't hold its secret" vs "this cfg id doesn't exist".
        raise HTTPException(404, _INVALID)

    exp = datetime.fromtimestamp(float(claims["exp"]), tz=timezone.utc)
    if exp - datetime.now(timezone.utc) > _MAX_TOKEN_TTL + _CLOCK_SKEW_LEEWAY:
        raise HTTPException(401, "Embed token expiry is too far in the future (max 24h)")

    if not _origin_allowed(request, cfg.allowed_origins or []):
        raise HTTPException(403, "This origin is not allowed to embed this report")

    report = await db.get(Report, cfg.report_id)
    if report is None or report.org_id != cfg.org_id:
        raise HTTPException(404, _INVALID)
    creator = await _load_creator_or_404(db, cfg)
    await _embed_sensitivity(db, report)

    from ..models.models import CommonFilter, Dataset, ReportClassification
    from .shared import published_relationships, visible_pages_for_creator

    pages = await visible_pages_for_creator(db, report, creator)
    ds = await db.get(Dataset, report.dataset_id) if report.dataset_id else None
    classif = (await db.execute(
        select(ReportClassification).where(ReportClassification.report_id == report.id)
    )).scalar_one_or_none()
    common_filters = (await db.execute(
        select(CommonFilter).where(CommonFilter.report_id == report.id)
        .order_by(CommonFilter.position, CommonFilter.id)
    )).scalars().all()

    filters = claims.get("filters") or []
    viewer_email = claims.get("viewer_email")
    viewer_org = claims.get("viewer_org")
    session_token = create_embed_session_token(
        cfg.id, filters=filters if isinstance(filters, list) else [],
        viewer_email=viewer_email if isinstance(viewer_email, str) else None,
        viewer_org=viewer_org if isinstance(viewer_org, int) else None,
    )

    cfg.last_used_at = datetime.utcnow()
    await db.commit()

    if cfg.allowed_origins:
        # Where the plan's CSP note belongs: this API response is what the SPA's
        # /embed route ultimately renders behind, so this is the header's home
        # in this stack. Empty allowlist = no origin restriction (see
        # `_origin_allowed`), so no frame-ancestors is set either -- consistent,
        # not a gap: a config with no allowlist places no framing restriction.
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors " + " ".join(cfg.allowed_origins))

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
        "embed_session_token": session_token,
        **(await published_relationships(db, report, pages, creator)),
    }


async def _embed_sensitivity(db: AsyncSession, report: Report) -> str | None:
    """Phase 7.3 on the embed surface: a Restricted report is never embedded;
    a Confidential one is (the host authenticated its user) with personal-data
    columns redacted from every widget."""
    from ..services.sensitivity import rank, report_effective
    label, reasons = await report_effective(db, report)
    if rank(label) >= rank("Restricted"):
        why = f" ({reasons[0]})" if reasons else ""
        raise HTTPException(403, f"This report is Restricted{why}; it cannot be embedded.")
    return label


@router.post("/embed/widget-data/{widget_id}")
async def embed_widget_data(widget_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """One widget's data for an embedded report. The embed SESSION token (from
    `GET /embed/report`, 15 min TTL) is the only credential accepted here --
    it carries the cfg id plus the ORIGINAL host JWT's filters/viewer_email/
    viewer_org, baked in at mint time. The request body/query string are never
    parsed for scope at all: filters come ONLY from the token, full stop.

    Row-level security and denied columns resolve as the config's CREATOR
    (`_load_creator_or_404`) -- the same creator-scoping a ShareLink guest
    gets -- never as an unrestricted identity; the token's own `filters`
    narrow that creator-scoped result further, they never widen it."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing embed session token")
    claims = decode_embed_session_token(auth[7:])
    if claims is None:
        raise HTTPException(401, "Invalid or expired embed session")

    cfg = await _load_config_or_404(db, claims.get("cfg"))
    report = await db.get(Report, cfg.report_id)
    if report is None or report.org_id != cfg.org_id:
        raise HTTPException(404, _INVALID)
    creator = await _load_creator_or_404(db, cfg)
    label = await _embed_sensitivity(db, report)
    widget = await _visible_widget(db, report, creator, widget_id)
    if widget is None:
        raise HTTPException(404, "Widget not found")

    dataset_id = (widget["config"] or {}).get("dataset_id") or report.dataset_id
    if not dataset_id:
        raise HTTPException(404, "Widget has no dataset")

    config = dict(widget["config"] or {})
    token_filters = claims.get("filters") or []
    if token_filters:
        # ALWAYS merged server-side, on top of whatever the saved widget
        # already filters by -- never replaced by, and never read from,
        # anything the browser sent on this request.
        config["filters"] = list(config.get("filters") or []) + list(token_filters)

    req = WidgetDataRequest(widget_type=widget["widget_type"], config=config)
    viewer_email = claims.get("viewer_email")
    viewer_org = claims.get("viewer_org")

    from ..services.sensitivity import redacted_columns
    from .widget_data import _resolve_widget_data

    result = await _resolve_widget_data(
        dataset_id, req, db, creator,
        email_override=viewer_email if isinstance(viewer_email, str) else None,
        org_id_override=viewer_org if isinstance(viewer_org, int) else None,
        via_report_id=report.id,
        redact_columns=await redacted_columns(db, int(dataset_id), label),
    )
    cfg.last_used_at = datetime.utcnow()
    await db.commit()
    return result
