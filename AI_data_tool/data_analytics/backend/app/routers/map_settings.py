"""The org's basemap tile server: read by every map, set by an org admin.

Tiles are fetched by the viewer's BROWSER, never by this server, so there is no
server-side request to guard. What is guarded is where an admin may point
every map in the org: an XYZ template on http(s), and -- when the deployment
lists its tile hosts (`map_tile_hosts`, the air-gapped case) -- one of those.
"""
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..dependencies import get_current_user, require_org_admin
from ..models.models import OrgMapSettings, User

router = APIRouter(prefix="/map-settings", tags=["map-settings"])


def _out(row: OrgMapSettings | None) -> dict:
    return {"tile_url": row.tile_url if row else None,
            "attribution": row.attribution if row else None,
            "contrast_tile_url": row.contrast_tile_url if row else None}


def _check_template(url: str | None, label: str) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if len(url) > 500:
        raise HTTPException(400, f"The {label} is longer than 500 characters")
    parts = urlsplit(url.replace("{s}", "a"))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(400, f"The {label} must be an http(s) address")
    for token in ("{z}", "{x}", "{y}"):
        if token not in url:
            raise HTTPException(400, f"The {label} must contain {{z}}, {{x}} and {{y}} "
                                     f"(an XYZ tile template); {token} is missing")
    allowed = [h.strip().lower() for h in settings.map_tile_hosts.split(",") if h.strip()]
    if allowed and parts.hostname.lower() not in allowed:
        raise HTTPException(400, f"'{parts.hostname}' is not one of this deployment's tile hosts "
                                 f"({', '.join(allowed)})")
    return url


@router.get("")
async def get_map_settings(db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    row = (await db.execute(select(OrgMapSettings).where(
        OrgMapSettings.org_id == current_user.org_id))).scalars().first()
    return _out(row)


@router.put("")
async def set_map_settings(body: dict, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_org_admin)):
    tile_url = _check_template(body.get("tile_url"), "tile address")
    contrast = _check_template(body.get("contrast_tile_url"), "high-contrast tile address")
    attribution = (str(body.get("attribution") or "").strip()[:300]) or None
    if tile_url and not attribution:
        # Almost every tile licence requires it, and a map that drops the
        # credit is the one that gets a takedown letter.
        raise HTTPException(400, "Give the tiles' attribution (e.g. '© OpenStreetMap contributors')")
    row = (await db.execute(select(OrgMapSettings).where(
        OrgMapSettings.org_id == current_user.org_id))).scalars().first()
    if row is None:
        row = OrgMapSettings(org_id=current_user.org_id)
        db.add(row)
    row.tile_url, row.contrast_tile_url, row.attribution = tile_url, contrast, attribution
    row.updated_by = current_user.id
    await db.commit()
    await db.refresh(row)
    return _out(row)
