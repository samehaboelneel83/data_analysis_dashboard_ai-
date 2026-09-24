"""Customer-supplied map boundaries: governorates, states, districts.

A JSON body rather than a multipart upload, deliberately. There is no
non-dataset file-upload endpoint in this codebase to follow, and inventing one
buys nothing: the browser must parse the file anyway to convert TopoJSON to
GeoJSON before sending, so by the time it reaches the wire it is already a JSON
document. This follows `custom_connectors` — an org-owned, named reference
artifact — not `datasets`.

Read is org-wide, write is not. A boundary set is reference data: a colleague
opening a dashboard that draws against it must be able to fetch the geometry,
or the map is blank for everyone but its author. Deleting one is different —
it may sit behind widgets on dashboards the deleter has never seen — so that
stays with the creator or an org admin, the same rule connections use.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import BoundarySet, User, Dataset
from ..services.boundary_sets import BoundarySetError, list_packs, load_pack, validate_boundaries

router = APIRouter(prefix="/boundary-sets", tags=["boundary-sets"])


def _summary(bs: BoundarySet) -> dict:
    """Everything except the geometry.

    A boundary file is megabytes. A picker that fetched all of them to draw a
    dropdown would download the lot to show three words.
    """
    features = (bs.geometry or {}).get("features") or []
    keys = bs.key_properties or []
    first = keys[0] if keys else None
    sample = []
    if first:
        for f in features[:12]:
            value = (f.get("properties") or {}).get(first)
            if isinstance(value, str):
                sample.append(value)
    return {
        "id": bs.id,
        "name": bs.name,
        "feature_count": bs.feature_count,
        "key_properties": keys,
        "sample_names": sample,
        "created_by": bs.created_by,
        "created_at": bs.created_at,
    }


async def _readable(db: AsyncSession, set_id: int, user: User) -> BoundarySet:
    bs = await db.get(BoundarySet, set_id)
    # 404 rather than 403 across orgs: a 403 on an id from another org confirms
    # it exists.
    check_org(bs, user, "Boundary set not found")
    return bs


@router.get("")
async def list_boundary_sets(db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(BoundarySet).where(BoundarySet.org_id == current_user.org_id)
        .order_by(BoundarySet.name)
    )).scalars().all()
    return [_summary(bs) for bs in rows]


@router.get("/packs")
async def list_boundary_packs(current_user: User = Depends(get_current_user)):
    """Starter packs this deployment ships (Egypt governorates, US states...).
    Metadata only; the geometry is read when a pack is installed."""
    return list_packs()


@router.post("/packs/{pack_id}/install", status_code=201)
async def install_boundary_pack(pack_id: str, body: dict | None = None,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """Install a pack as an ordinary boundary set of the caller's org.

    The same row an upload creates, so everything downstream (classification,
    maps, share links) is unchanged. Installing twice is refused by name, as
    uploading twice is -- the existing set is what the author wants anyway."""
    try:
        entry, checked = load_pack(pack_id)
    except BoundarySetError as e:
        raise HTTPException(404, str(e))
    # A pack under non-public-domain terms (eu-nuts1) installs only when the
    # admin has read and accepted them, and its credit rides on the geometry
    # so every map drawn with it can show it -- the terms require that.
    if entry.get("requires_acceptance") and not (body or {}).get("accept_terms"):
        raise HTTPException(400, f"Installing '{entry['name']}' needs its terms accepted: {entry.get('terms') or entry.get('license')}")
    if entry.get("attribution"):
        checked["geometry"] = {**checked["geometry"], "x_attribution": entry["attribution"]}
    name = str(entry["name"])[:200]
    clash = (await db.execute(select(BoundarySet).where(
        BoundarySet.org_id == current_user.org_id, BoundarySet.name == name)
    )).scalars().first()
    if clash is not None:
        raise HTTPException(409, f"'{name}' is already installed")
    bs = BoundarySet(org_id=current_user.org_id, name=name,
                     geometry=checked["geometry"],
                     key_properties=checked["key_properties"],
                     feature_count=checked["feature_count"],
                     created_by=current_user.id)
    db.add(bs)
    if entry.get("requires_acceptance"):
        from ..services.audit import record as audit
        await audit(db, current_user, "boundary_pack.accept_terms", "boundary_pack", 0,
                    f"{pack_id}: {str(entry.get('license'))[:150]}")
    await db.commit()
    await db.refresh(bs)
    return {**_summary(bs), "sample_names": checked["sample_names"]}


@router.get("/{set_id}")
async def get_boundary_set(set_id: int, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """The geometry, verbatim. This is what the browser draws."""
    bs = await _readable(db, set_id, current_user)
    return {**_summary(bs), "geometry": bs.geometry}


@router.post("", status_code=201)
async def create_boundary_set(body: dict, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    name = str(body.get("name") or "").strip()[:200]
    if not name:
        raise HTTPException(400, "A name is required")
    try:
        checked = validate_boundaries(body.get("geometry"))
    except BoundarySetError as e:
        raise HTTPException(400, str(e))

    # Checked before insert rather than caught as an IntegrityError: the name is
    # how an author picks a set in the widget config, and two the same is a coin
    # flip every time one is chosen.
    clash = (await db.execute(select(BoundarySet).where(
        BoundarySet.org_id == current_user.org_id, BoundarySet.name == name)
    )).scalars().first()
    if clash is not None:
        raise HTTPException(409, f"A boundary set named '{name}' already exists")

    bs = BoundarySet(org_id=current_user.org_id, name=name,
                     geometry=checked["geometry"],
                     key_properties=checked["key_properties"],
                     feature_count=checked["feature_count"],
                     created_by=current_user.id)
    db.add(bs)
    await db.commit()
    await db.refresh(bs)
    return {**_summary(bs), "sample_names": checked["sample_names"]}


async def _clear_classifications_using(db: AsyncSession, org_id: int, set_id: int) -> None:
    """Drop every column classification that pointed at a set being deleted.

    `column_meta[col].boundary_set_id` is how a column says which shapes it
    draws with. Left behind, it points at nothing: the map silently falls back
    to countries and the column still calls itself geography, so the author
    sees a setting that is enabled and does nothing. The `role` goes with the
    id -- geography with no shapes to draw is the same lie in a different key.

    Pruned HERE because deletion is the only place that knows it happened,
    exactly as per-pair actions are pruned when their target widget is deleted.
    """
    rows = (await db.execute(
        select(Dataset).where(Dataset.org_id == org_id))).scalars().all()
    for ds in rows:
        meta = ds.column_meta or {}
        if not isinstance(meta, dict):
            continue
        changed = False
        updated: dict = {}
        for column, entry in meta.items():
            if (isinstance(entry, dict)
                    and entry.get("boundary_set_id") == set_id):
                trimmed = {k: v for k, v in entry.items()
                           if k not in ("boundary_set_id", "role")}
                updated[column] = trimmed
                changed = True
            else:
                updated[column] = entry
        if changed:
            # Rebuilt, not mutated: SQLAlchemy does not track edits made
            # inside a JSON column, so an in-place change is never written.
            ds.column_meta = updated


@router.delete("/{set_id}", status_code=204)
async def delete_boundary_set(set_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    bs = await _readable(db, set_id, current_user)
    is_admin = bool(current_user.role and current_user.role.is_org_admin)
    if not is_admin and bs.created_by != current_user.id:
        # Visible but not yours -> 403. The set is legitimately visible to the
        # whole org (see the module docstring), so hiding its existence here
        # would contradict the listing they can already see.
        raise HTTPException(403, "Only the creator or an org admin can delete a boundary set")
    await _clear_classifications_using(db, current_user.org_id, set_id)
    await db.delete(bs)
    await db.commit()


#: Manual pins are for the handful of spellings a file does not carry
#: ("England" -> United Kingdom), not a second boundary file.
MAX_PINS = 2000


@router.put("/{set_id}/pins")
async def set_boundary_pins(set_id: int, body: dict, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Pin data values to regions: `{"pins": {"England": 12, ...}}`, value ->
    feature index. Replaces the set's pins wholesale.

    Stored ON the set (a GeoJSON foreign member, `x_pins`), so every map that
    draws the set -- in the builder, a share link, an embed -- resolves the
    pinned spellings the same way, with nothing extra to plumb through. The
    match stays exact: a pin is one more exact lookup, chosen by a person.

    Same rights as deleting: a pin changes what every map in the org draws."""
    bs = await _readable(db, set_id, current_user)
    is_admin = bool(current_user.role and current_user.role.is_org_admin)
    if not is_admin and bs.created_by != current_user.id:
        raise HTTPException(403, "Only the creator of this boundary set or an org admin can pin values to it")
    pins = body.get("pins")
    if not isinstance(pins, dict):
        raise HTTPException(400, "pins must be an object of value -> region index")
    if len(pins) > MAX_PINS:
        raise HTTPException(400, f"At most {MAX_PINS} pinned values")
    n = len((bs.geometry or {}).get("features") or [])
    clean: dict[str, int] = {}
    for value, index in pins.items():
        text = str(value).strip()
        if not text:
            continue
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < n:
            raise HTTPException(400, f"'{text}' is pinned to region {index!r}, which this set does not have")
        clean[text] = index
    geometry = dict(bs.geometry or {})
    if clean:
        geometry["x_pins"] = clean
    else:
        geometry.pop("x_pins", None)
    bs.geometry = geometry
    flag_modified(bs, "geometry")
    await db.commit()
    return {"id": bs.id, "pins": clean}
