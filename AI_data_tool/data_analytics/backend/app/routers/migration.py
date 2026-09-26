"""E17: the migration inventory -- what the old estate has, what replaces each
piece, the evidence, and the owner's sign-off.

WHO DOES WHAT
-------------
Everyone in the org reads the inventory: it names old reports and who owns
them, which is what a migration has to be open about. A linked Datalytics
report is named only to readers who can open it (the same 404 discipline as
everywhere: a title is not leaked through the ledger).

An org admin runs the inventory: adds and imports items, names owners,
deletes. The named owner works their own items: links the report that
replaces one, records comparisons (from the widget's Reconcile dialog),
decides to retire it, and signs off. Only the owner signs off; that is what
a sign-off means. An admin can withdraw a sign-off (a sign-off given in
error) but cannot give one.

Status is derived, never stored (services/migration.py), and every change
is audited.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import effective_capabilities, effective_capability
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user, require_org_admin
from ..models.models import MigrationItem, Report, User
from ..services import migration as mig
from ..services.audit import record as audit
from ..services.sas_inventory import (FEATURES, KINDS, feature_row, fit_summary,
                                      read_inventory, scan_sas)

router = APIRouter(prefix="/migration", tags=["migration"])

_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_FILES = 200


def _is_admin(user: User) -> bool:
    return bool(user.role and user.role.is_org_admin)


def _can_edit(item: MigrationItem, user: User) -> bool:
    return _is_admin(user) or (item.owner_id is not None and item.owner_id == user.id)


class ItemIn(BaseModel):
    name: str | None = None
    kind: str | None = None
    source_system: str | None = None
    source_path: str | None = None
    owner_id: int | None = None
    report_id: int | None = None
    decision: str | None = None
    notes: str | None = None


class SignOffIn(BaseModel):
    note: str | None = None
    accept_differences: bool = False


async def _out_many(db: AsyncSession, user: User, items: list[MigrationItem]) -> list[dict]:
    owner_ids = {i.owner_id for i in items if i.owner_id}
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars()} \
        if owner_ids else {}
    report_ids = sorted({i.report_id for i in items if i.report_id})
    caps = await effective_capabilities(db, user, report_ids)
    reports = {r.id: r for r in (await db.execute(select(Report).where(Report.id.in_(report_ids)))).scalars()} \
        if report_ids else {}
    out = []
    for i in items:
        owner = owners.get(i.owner_id)
        rep = reports.get(i.report_id)
        visible = rep is not None and caps.get(rep.id, "none") != "none"
        so = i.sign_off or None
        recs = mig.current_reconciles(i)
        out.append({
            "id": i.id, "name": i.name, "kind": i.kind, "source_system": i.source_system,
            "source_path": i.source_path, "decision": i.decision, "notes": i.notes,
            "owner": {"id": owner.id, "email": owner.email} if owner else None,
            "report": ({"id": rep.id, "name": rep.name if visible else None, "can_open": visible}
                       if rep is not None else None),
            "features": i.features or None, "fit": fit_summary((i.features or {}).get("features")),
            "reconciles": [{"widget_key": k, **v} for k, v in sorted(recs.items(), key=lambda kv: kv[1].get("at", ""))],
            "sign_off": so,
            "report_changed_since_sign_off": bool(
                so and rep is not None and so.get("report_id") == rep.id
                and (rep.revision or 0) > (so.get("revision") or 0)),
            "status": mig.status_of(i),
            "can_edit": _can_edit(i, user),
            "can_sign_off": i.owner_id is not None and i.owner_id == user.id,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "updated_at": i.updated_at.isoformat() if i.updated_at else None,
        })
    return out


async def _load(db: AsyncSession, user: User, item_id: int) -> MigrationItem:
    item = await db.get(MigrationItem, item_id)
    check_org(item, user, "Item not found")
    return item


async def _check_owner(db: AsyncSession, user: User, owner_id: int | None) -> None:
    if owner_id is None:
        return
    owner = await db.get(User, owner_id)
    if owner is None or owner.org_id != user.org_id or not owner.is_active:
        raise HTTPException(400, "The owner must be an active user in your organization")


async def _check_report(db: AsyncSession, user: User, report_id: int | None) -> None:
    if report_id is not None and await effective_capability(db, user, report_id) == "none":
        raise HTTPException(404, "Report not found")


def _clean_kind(kind: str | None) -> str:
    kind = (kind or "report").strip().lower()
    if kind not in KINDS:
        raise HTTPException(400, f"kind is one of: {', '.join(KINDS)}")
    return kind


@router.get("/feature-map")
async def feature_map(current_user: User = Depends(get_current_user)):
    """The SAS-to-Datalytics feature mapping, as the scanner applies it."""
    return [{k: v for k, v in feature_row(key).items() if k != "count"} for key in FEATURES]


@router.get("/items")
async def list_items(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = (await db.execute(select(MigrationItem).where(MigrationItem.org_id == current_user.org_id)
                              .order_by(MigrationItem.name, MigrationItem.id))).scalars().all()
    out = await _out_many(db, current_user, list(items))
    summary = {s: 0 for s in mig.STATUSES}
    for o in out:
        summary[o["status"]] += 1
    return {"items": out, "summary": summary, "can_manage": _is_admin(current_user)}


@router.post("/items", status_code=201)
async def create_item(body: ItemIn, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_org_admin)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    await _check_owner(db, current_user, body.owner_id)
    await _check_report(db, current_user, body.report_id)
    item = MigrationItem(org_id=current_user.org_id, name=name[:300], kind=_clean_kind(body.kind),
                         source_system=(body.source_system or "SAS").strip()[:40] or "SAS",
                         source_path=(body.source_path or "").strip()[:1000] or None,
                         owner_id=body.owner_id, report_id=body.report_id,
                         notes=(body.notes or "").strip() or None, created_by=current_user.id)
    db.add(item)
    await db.flush()
    await audit(db, current_user, "migration.item_create", "migration_item", item.id, name[:200])
    await db.commit()
    return (await _out_many(db, current_user, [item]))[0]


@router.post("/items/import")
async def import_items(files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_org_admin)):
    """An inventory CSV (one row per item) and/or SAS programs (one item per
    .sas file, scanned). A program whose name is already listed has its scan
    updated rather than being listed twice; a CSV row whose name is already
    listed is skipped and said so."""
    if len(files) > _MAX_FILES:
        raise HTTPException(400, f"At most {_MAX_FILES} files at a time")
    existing = {i.name.lower(): i for i in (await db.execute(
        select(MigrationItem).where(MigrationItem.org_id == current_user.org_id))).scalars()}
    users = {u.email.lower(): u for u in (await db.execute(
        select(User).where(User.org_id == current_user.org_id, User.is_active.is_(True)))).scalars()}
    created, updated, warnings = 0, 0, []
    new_items: list[MigrationItem] = []
    for f in files:
        raw = await f.read(_MAX_FILE_BYTES + 1)
        fname = f.filename or "file"
        if len(raw) > _MAX_FILE_BYTES:
            warnings.append(f"{fname}: over 5 MB, skipped")
            continue
        text = raw.decode("utf-8", errors="replace") if raw[:3] != b"\xef\xbb\xbf" else raw[3:].decode("utf-8", "replace")
        lower = fname.lower()
        if lower.endswith(".sas"):
            name = fname.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:-4] or fname
            scan = scan_sas(text)
            scan["file"] = fname
            item = existing.get(name.lower())
            if item is not None:
                item.features = scan
                updated += 1
            else:
                item = MigrationItem(org_id=current_user.org_id, name=name[:300], kind="program",
                                     source_path=fname[:1000], features=scan, created_by=current_user.id)
                db.add(item)
                new_items.append(item)
                existing[name.lower()] = item
                created += 1
        elif lower.endswith((".csv", ".txt", ".tsv")):
            try:
                rows = read_inventory(text)
            except ValueError as e:
                warnings.append(f"{fname}: {e}")
                continue
            for n, row in enumerate(rows, start=2):
                if row["name"].lower() in existing:
                    warnings.append(f"{fname} row {n}: {row['name']} is already listed")
                    continue
                owner = users.get((row["owner"] or "").lower()) if row["owner"] else None
                if row["owner"] and owner is None:
                    warnings.append(f"{fname} row {n}: no active user {row['owner']}; owner left empty")
                item = MigrationItem(org_id=current_user.org_id, name=row["name"], kind=row["kind"],
                                     source_system=row["source_system"], source_path=row["source_path"],
                                     owner_id=owner.id if owner else None, notes=row["notes"],
                                     created_by=current_user.id)
                if row["report"]:
                    item.report_id = await _report_by_ref(db, current_user, row["report"])
                    if item.report_id is None:
                        warnings.append(f"{fname} row {n}: no report {row['report']} you can open; left unlinked")
                db.add(item)
                new_items.append(item)
                existing[row["name"].lower()] = item
                created += 1
        else:
            warnings.append(f"{fname}: not a .csv inventory or a .sas program, skipped")
    await db.flush()
    await audit(db, current_user, "migration.import", "migration_item", None,
                f"{created} added, {updated} rescanned from {len(files)} file(s)")
    await db.commit()
    return {"created": created, "updated": updated, "warnings": warnings[:200]}


async def _report_by_ref(db: AsyncSession, user: User, ref: str) -> int | None:
    """A report named in the inventory, by id or exact name, that the importer can open."""
    ref = ref.strip()
    q = select(Report.id).where(Report.org_id == user.org_id)
    q = q.where(Report.id == int(ref)) if ref.isdigit() else q.where(Report.name == ref)
    for rid in (await db.execute(q.order_by(Report.id))).scalars():
        if await effective_capability(db, user, rid) != "none":
            return rid
    return None


@router.post("/items/{item_id}/scan")
async def scan_item(item_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Attach the SAS program behind an item: its features, mapped."""
    item = await _load(db, current_user, item_id)
    if not _can_edit(item, current_user):
        raise HTTPException(403, "Only the item's owner or an admin can change it")
    raw = await file.read(_MAX_FILE_BYTES + 1)
    if len(raw) > _MAX_FILE_BYTES:
        raise HTTPException(400, "The program is over 5 MB")
    scan = scan_sas(raw.decode("utf-8", errors="replace").lstrip("﻿"))
    scan["file"] = file.filename
    item.features = scan
    await audit(db, current_user, "migration.scan", "migration_item", item.id,
                f"{file.filename}: {len(scan['features'])} features")
    await db.commit()
    return (await _out_many(db, current_user, [item]))[0]


@router.patch("/items/{item_id}")
async def update_item(item_id: int, body: ItemIn, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    item = await _load(db, current_user, item_id)
    if not _can_edit(item, current_user):
        raise HTTPException(403, "Only the item's owner or an admin can change it")
    sent = body.model_dump(exclude_unset=True)
    admin_only = {"name", "kind", "source_system", "source_path", "owner_id"} & sent.keys()
    if admin_only and not _is_admin(current_user):
        raise HTTPException(403, "Only an admin can rename an item or change its owner")
    changes = []
    if "name" in sent:
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        item.name = name[:300]
        changes.append("name")
    if "kind" in sent:
        item.kind = _clean_kind(body.kind)
        changes.append("kind")
    if "source_system" in sent:
        item.source_system = (body.source_system or "SAS").strip()[:40] or "SAS"
    if "source_path" in sent:
        item.source_path = (body.source_path or "").strip()[:1000] or None
    if "owner_id" in sent and body.owner_id != item.owner_id:
        await _check_owner(db, current_user, body.owner_id)
        item.owner_id = body.owner_id
        # A sign-off is the owner's; a new owner has not given one.
        if item.sign_off:
            item.sign_off = None
            changes.append("sign-off withdrawn (new owner)")
        changes.append(f"owner {body.owner_id}")
    if "report_id" in sent and body.report_id != item.report_id:
        await _check_report(db, current_user, body.report_id)
        item.report_id = body.report_id
        if item.sign_off:
            item.sign_off = None
            changes.append("sign-off withdrawn (another report)")
        changes.append(f"report {body.report_id}")
    if "decision" in sent:
        if body.decision not in ("migrate", "retire"):
            raise HTTPException(400, "decision is migrate or retire")
        if body.decision == "retire" and not ((body.notes if "notes" in sent else item.notes) or "").strip():
            raise HTTPException(400, "Say in the notes why it is retired")
        if body.decision != item.decision:
            item.decision = body.decision
            changes.append(f"decision {body.decision}")
    if "notes" in sent:
        item.notes = (body.notes or "").strip() or None
        changes.append("notes")
    await audit(db, current_user, "migration.item_update", "migration_item", item.id,
                f"{item.name[:120]}: {', '.join(changes) or 'no change'}")
    await db.commit()
    return (await _out_many(db, current_user, [item]))[0]


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_org_admin)):
    item = await _load(db, current_user, item_id)
    await audit(db, current_user, "migration.item_delete", "migration_item", item.id,
                f"{item.name[:200]} ({mig.status_of(item)})")
    await db.delete(item)
    await db.commit()


@router.post("/items/{item_id}/sign-off")
async def sign_off(item_id: int, body: SignOffIn, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    item = await _load(db, current_user, item_id)
    if item.owner_id != current_user.id:
        raise HTTPException(403, "Only the item's owner signs it off")
    try:
        basis = mig.sign_off_basis(item, body.note, body.accept_differences)
    except ValueError as e:
        raise HTTPException(400, str(e))
    report = await db.get(Report, item.report_id) if item.report_id else None
    item.sign_off = {"by": current_user.id, "by_email": current_user.email, "at": mig.now_iso(),
                     "basis": basis, "note": (body.note or "").strip() or None,
                     "report_id": item.report_id, "revision": report.revision if report else None,
                     "reconciles": mig.current_reconciles(item)}
    await audit(db, current_user, "migration.sign_off", "migration_item", item.id,
                f"{item.name[:150]}: {basis}" + (f" -- {body.note.strip()[:200]}" if body.note else ""))
    await db.commit()
    return (await _out_many(db, current_user, [item]))[0]


@router.delete("/items/{item_id}/sign-off")
async def withdraw_sign_off(item_id: int, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    item = await _load(db, current_user, item_id)
    if not _can_edit(item, current_user):
        raise HTTPException(403, "Only the item's owner or an admin can withdraw a sign-off")
    if not item.sign_off:
        raise HTTPException(400, "The item is not signed off")
    item.sign_off = None
    await audit(db, current_user, "migration.sign_off_withdrawn", "migration_item", item.id, item.name[:200])
    await db.commit()
    return (await _out_many(db, current_user, [item]))[0]
