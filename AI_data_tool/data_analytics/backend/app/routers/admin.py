import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.security import hash_password
from ..dependencies import get_current_user, require_org_admin
from ..models.models import AuditLogEntry, ColumnSecurityRule, Dataset, Role, RowSecurityRule, User
from ..schemas.schemas import (
    RoleCreate, RoleUpdate, RoleOut,
    UserCreate, UserUpdate, UserOut, BulkUserCreate,
    RowSecurityRuleCreate, RowSecurityRuleUpdate, RowSecurityRuleOut,
    RlsAutoGenerateRequest,
)
from ..services import admin_audit
from ..services.analytics import load_file
from ..services.sql_expr import ExpressionTranslationError, expression_columns, translate_filter_expr
from ..services.widget_data import apply_filter_expr

from ..services.refresh_scheduler import calendar_spec
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Roles ────────────────────────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(select(Role).where(Role.org_id == current_user.org_id))
    return result.scalars().all()


@router.post("/roles", response_model=RoleOut)
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = Role(org_id=current_user.org_id, name=body.name, is_org_admin=body.is_org_admin)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(role_id: int, body: RoleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, role_id)
    check_org(role, current_user, "Role not found")
    if body.name is not None:
        role.name = body.name
    if body.is_org_admin is not None:
        role.is_org_admin = body.is_org_admin
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, role_id)
    check_org(role, current_user, "Role not found")
    result = await db.execute(select(User).where(User.role_id == role_id).limit(1))
    if result.scalars().first() is not None:
        raise HTTPException(400, "Cannot delete a role that still has users assigned")
    await db.delete(role)
    await db.commit()


# ── Users ────────────────────────────────────────────────────────────────────

async def _load_user_out(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization)).where(User.id == user_id)
    )
    return result.scalar_one()


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    result = await db.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization))
        .where(User.org_id == current_user.org_id)
    )
    return result.scalars().all()


@router.post("/users", response_model=UserOut)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, body.role_id)
    check_org(role, current_user, "Role not found")
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(400, "Email already in use")
    user = User(
        org_id=current_user.org_id, role_id=body.role_id,
        email=body.email, password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    return await _load_user_out(db, user.id)


@router.post("/users/bulk")
async def bulk_create_users(body: BulkUserCreate, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_org_admin)):
    """Provision many users at once (CSV import from the admin UI). Partial success:
    every valid row is created and every invalid one is reported with its reason, so
    one bad line never sinks the whole upload. Roles are matched by name within the
    admin's org. bcrypt hashing runs on a worker thread so a large batch does not
    block the event loop."""
    roles = (await db.execute(select(Role).where(Role.org_id == current_user.org_id))).scalars().all()
    role_by_name = {}
    for r in roles:
        role_by_name.setdefault((r.name or "").strip().lower(), r)   # first wins on a name clash

    wanted = [(u.email or "").strip() for u in body.users if (u.email or "").strip()]
    taken = set()
    if wanted:
        taken = set((await db.execute(select(User.email).where(User.email.in_(wanted)))).scalars().all())

    errors: list[dict] = []
    valid: list[tuple[str, int, str]] = []   # (email, role_id, password)
    seen: set[str] = set()
    for i, u in enumerate(body.users):
        row = i + 1                           # 1-based, matches a spreadsheet
        email = (u.email or "").strip()
        if not email or "@" not in email:
            errors.append({"row": row, "email": email, "error": "invalid email"}); continue
        if email in seen:
            errors.append({"row": row, "email": email, "error": "duplicate email in this upload"}); continue
        if email in taken:
            errors.append({"row": row, "email": email, "error": "email already in use"}); continue
        if not (u.password or "").strip():
            errors.append({"row": row, "email": email, "error": "password required"}); continue
        role = role_by_name.get((u.role or "").strip().lower())
        if role is None:
            errors.append({"row": row, "email": email, "error": f"unknown role '{u.role}'"}); continue
        seen.add(email)
        valid.append((email, role.id, u.password))

    # Hash every accepted password off the event loop — bcrypt is ~100ms each.
    hashed = await asyncio.to_thread(
        lambda rows: [(e, rid, hash_password(pw)) for e, rid, pw in rows], valid)
    for email, role_id, pw_hash in hashed:
        db.add(User(org_id=current_user.org_id, role_id=role_id, email=email, password_hash=pw_hash))
    if hashed:
        await db.commit()
    return {"created_count": len(hashed), "created": [e for e, _, _ in hashed], "errors": errors}


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    user = await db.get(User, user_id)
    check_org(user, current_user, "User not found")
    if body.email is not None:
        existing = await db.execute(select(User).where(User.email == body.email, User.id != user_id))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(400, "Email already in use")
        user.email = body.email
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        # A reset is the moment a revocation is certainly wanted (a leaked or
        # shared password): every login token issued before now stops working.
        from datetime import datetime, timezone
        user.tokens_valid_after = datetime.now(timezone.utc)
    if body.role_id is not None:
        role = await db.get(Role, body.role_id)
        check_org(role, current_user, "Role not found")
        user.role_id = body.role_id
    if body.is_active is not None:
        user.is_active = body.is_active
    await db.commit()
    return await _load_user_out(db, user.id)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    user = await db.get(User, user_id)
    check_org(user, current_user, "User not found")
    if user.id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    await db.delete(user)
    await db.commit()


# ── Row Security Rules ─────────────────────────────────────────────────────

def _refuse_if_aggregate(dataset: Dataset) -> None:
    """A rule saved directly on an aggregate dataset would sit there, inert,
    forever: both RLS resolvers (core/rls.py) redirect past the aggregate to
    its source before ever looking a rule up, so the rule would list in the
    admin UI as if it applied and never be read -- a control that looks
    enabled and is not. Refuse at creation, where the mistake is made, naming
    the dataset it actually belongs on."""
    if dataset.aggregate_of_dataset_id is not None:
        raise HTTPException(
            400, f"Dataset {dataset.id} is an aggregate of dataset "
                 f"{dataset.aggregate_of_dataset_id}; security rules belong "
                 f"on the source dataset, not the aggregate.")


async def _validate_filter_expr(dataset: Dataset, filter_expr: str) -> None:
    # Resolve any USEREMAIL()/USER()/USERID() tokens against a placeholder identity so
    # the rule validates as the concrete expression it becomes at query time — the
    # column references and grammar are what we are checking here, not a real user.
    from ..core.rls import apply_user_context
    filter_expr = apply_user_context(
        filter_expr, email="validator@example.com", user_id=0,
        org_id=0, org_name="validator-org",
    ) or filter_expr
    if dataset.mode == "directquery":
        # No file to sample against -- validate the same way DirectQuery pushdown
        # itself will: does this expression translate to SQL against the dataset's
        # known columns? This is what makes an untranslatable rule surface to the
        # admin authoring it, rather than to a viewer's dashboard at query time.
        known_columns = {c.name for c in dataset.columns}
        try:
            translate_filter_expr(filter_expr, known_columns)
        except ExpressionTranslationError as e:
            raise HTTPException(400, f"Invalid filter expression: {e}")
        return
    if not dataset.filename:
        raise HTTPException(400, "Dataset has no data file to validate the expression against")
    try:
        df = await asyncio.to_thread(load_file, dataset.filename)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, f"Could not load dataset file to validate the expression: {e}")
    try:
        apply_filter_expr(df, filter_expr, silent=False)
    except Exception as e:
        raise HTTPException(400, f"Invalid filter expression: {e}")


@router.get("/row-security-rules", response_model=list[RowSecurityRuleOut])
async def list_rules(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    # Role AND dataset in this org: a rule is this org's only when both ends are.
    # A seeder once bound org 1's role to org 4's dataset; scoped by role alone,
    # org 1's admin listed (and could edit) a rule on data it cannot see.
    result = await db.execute(
        select(RowSecurityRule).join(Role, RowSecurityRule.role_id == Role.id)
        .join(Dataset, RowSecurityRule.dataset_id == Dataset.id)
        .where(Role.org_id == current_user.org_id, Dataset.org_id == current_user.org_id)
    )
    return result.scalars().all()


@router.post("/row-security-rules", response_model=RowSecurityRuleOut)
async def create_rule(body: RowSecurityRuleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    role = await db.get(Role, body.role_id)
    check_org(role, current_user, "Role not found")
    ds_result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == body.dataset_id)
    )
    dataset = ds_result.scalar_one_or_none()
    check_org(dataset, current_user, "Dataset not found")
    _refuse_if_aggregate(dataset)
    await _validate_filter_expr(dataset, body.filter_expr)

    existing = await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == body.role_id, RowSecurityRule.dataset_id == body.dataset_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(400, "A rule for this role and dataset already exists")

    rule = RowSecurityRule(role_id=body.role_id, dataset_id=body.dataset_id, filter_expr=body.filter_expr)
    db.add(rule)
    await admin_audit.record(db, current_user, "row_security_rule.create",
                              f"dataset:{body.dataset_id}", body.filter_expr)
    await db.commit()
    await db.refresh(rule)
    return rule


# S0c: same "looks like a user/owner column" heuristic as the frontend's codeless
# builder (AdminRowSecurityRules.tsx isUserishColumn), plus an org-ish match. Kept
# here rather than imported from the frontend since this runs server-side against
# DatasetColumn rows, not the Dataset payload the UI already has in hand.
_EMAILISH_COL = re.compile(r"user|email|owner", re.IGNORECASE)
_ORGISH_COL = re.compile(r"org|tenant|company", re.IGNORECASE)


def _propose_rls_rules(columns) -> list[dict]:
    """One proposal per qualifying column, independent of role -- USEREMAIL()/
    ORGID()/ORGNAME() expand to the VIEWING user at query time, so the same
    expression text is correct for every role it gets applied to."""
    proposals: list[dict] = []
    for col in columns:
        if col.semantic_type == "email" or _EMAILISH_COL.search(col.name or ""):
            proposals.append({
                "column": col.name, "kind": "user_email",
                "expression": f"`{col.name}` == USEREMAIL()",
            })
        elif _ORGISH_COL.search(col.name or ""):
            if col.dtype == "numeric":
                proposals.append({
                    "column": col.name, "kind": "org_id",
                    "expression": f"`{col.name}` == ORGID()",
                })
            else:
                proposals.append({
                    "column": col.name, "kind": "org_name",
                    "expression": f"`{col.name}` == ORGNAME()",
                })
    return proposals


@router.post("/rls-rules/auto-generate")
async def auto_generate_rls_rules(
    body: RlsAutoGenerateRequest, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    """Propose (and optionally create) row-security rules from column semantics/
    naming (S0c). Proposing needs only a dataset; applying needs a role too, since
    a RowSecurityRule is always (role, dataset). Checked proposals for the SAME
    role+dataset are AND-combined into one filter_expr -- the (role_id, dataset_id)
    unique constraint allows only one rule per pair. Idempotent: re-running never
    duplicates a column already covered by the existing filter_expr text, and never
    touches a rule an admin has since hand-edited (auto_generated cleared)."""
    ds_result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == body.dataset_id)
    )
    dataset = ds_result.scalar_one_or_none()
    check_org(dataset, current_user, "Dataset not found")
    _refuse_if_aggregate(dataset)

    proposals = _propose_rls_rules(dataset.columns)

    if not body.apply:
        return {"proposals": proposals}

    if body.role_id is None:
        raise HTTPException(400, "role_id is required to apply auto-generated rules")
    role = await db.get(Role, body.role_id)
    check_org(role, current_user, "Role not found")

    selected = [p for p in proposals if body.columns is None or p["column"] in body.columns]

    existing = (await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == body.role_id, RowSecurityRule.dataset_id == body.dataset_id,
        )
    )).scalar_one_or_none()

    if existing is not None and not existing.auto_generated:
        return {
            "proposals": proposals, "created": None,
            "skipped": [p["column"] for p in selected],
            "reason": "a rule already exists for this role and dataset and was hand-edited",
        }

    base_expr = existing.filter_expr if existing is not None else ""
    new_clauses, skipped = [], []
    for p in selected:
        if f"`{p['column']}`" in base_expr:
            skipped.append(p["column"])
            continue
        new_clauses.append(p["expression"])

    if not new_clauses:
        return {
            "proposals": proposals,
            "created": RowSecurityRuleOut.model_validate(existing) if existing else None,
            "skipped": skipped,
        }

    combined = " and ".join(([base_expr] if base_expr else []) + new_clauses)
    await _validate_filter_expr(dataset, combined)

    if existing is not None:
        existing.filter_expr = combined
        existing.auto_generated = True
        rule = existing
    else:
        rule = RowSecurityRule(role_id=body.role_id, dataset_id=body.dataset_id,
                                filter_expr=combined, auto_generated=True)
        db.add(rule)
    await admin_audit.record(db, current_user, "row_security_rule.auto_generate",
                              f"dataset:{body.dataset_id}", combined)
    await db.commit()
    await db.refresh(rule)
    return {"proposals": proposals, "created": RowSecurityRuleOut.model_validate(rule), "skipped": skipped}


@router.get("/row-security-rules/preflight")
async def rule_preflight(
    role_id: int, dataset_id: int, filter_expr: str,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin),
):
    """What a rule reads, and which of those columns the role cannot see.

    Informational: the row rule is still evaluated over every column and the
    role receives the rows it selects, never the column itself (widget_data
    applies RLS before column security). This tells the admin that at the
    moment they type it. Names what the SQL translator can read. An
    import-mode expression the pandas evaluator accepts but the translator
    rejects (function calls, %, **, chained compares) reports no columns --
    see the spec's follow-up list, item 12."""
    from ..core.rls import apply_user_context
    role = await db.get(Role, role_id)
    check_org(role, current_user, "Role not found")
    dataset = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                                .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(dataset, current_user, "Dataset not found")
    expr = apply_user_context(filter_expr, email="validator@example.com", user_id=0,
                              org_id=0, org_name="validator-org") or filter_expr
    known = {c.name for c in dataset.columns}
    try:
        columns = sorted(expression_columns(expr, known))
    except Exception:  # noqa: BLE001 -- an unparsable draft reads nothing yet
        columns = []
    rule = (await db.execute(select(ColumnSecurityRule).where(
        ColumnSecurityRule.role_id == role_id, ColumnSecurityRule.dataset_id == dataset_id))).scalar_one_or_none()
    denied = set(rule.denied_columns or []) if rule else set()
    return {"columns": columns, "denied": sorted(c for c in columns if c in denied)}


async def _get_rule_in_org(db: AsyncSession, rule_id: int, current_user: User) -> RowSecurityRule:
    result = await db.execute(
        select(RowSecurityRule).options(selectinload(RowSecurityRule.role)).where(RowSecurityRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None or rule.role.org_id != current_user.org_id:
        raise HTTPException(404, "Rule not found")
    ds = await db.get(Dataset, rule.dataset_id)
    if ds is None or ds.org_id != current_user.org_id:    # see list_rules
        raise HTTPException(404, "Rule not found")
    return rule


@router.patch("/row-security-rules/{rule_id}", response_model=RowSecurityRuleOut)
async def update_rule(rule_id: int, body: RowSecurityRuleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    rule = await _get_rule_in_org(db, rule_id, current_user)
    ds_result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == rule.dataset_id)
    )
    dataset = ds_result.scalar_one_or_none()
    await _validate_filter_expr(dataset, body.filter_expr)
    rule.filter_expr = body.filter_expr
    # S0c: an admin editing the expression is a deliberate override -- clear the
    # auto-generated flag so a later auto-generate run never overwrites it again.
    rule.auto_generated = False
    await admin_audit.record(db, current_user, "row_security_rule.update",
                              f"dataset:{rule.dataset_id}", body.filter_expr)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/row-security-rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    rule = await _get_rule_in_org(db, rule_id, current_user)
    await admin_audit.record(db, current_user, "row_security_rule.delete",
                              f"dataset:{rule.dataset_id}", None)
    await db.delete(rule)
    await db.commit()


@router.get("/audit-log")
async def list_audit_log(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_org_admin),
):
    """The org's audit trail, newest first. Admin-only and org-scoped: the log records
    an org's own actions and is readable by that org's admins alone."""
    limit = max(1, min(limit, 1000))
    rows = (await db.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.org_id == admin.org_id)
        .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {"id": r.id, "user_email": r.user_email, "action": r.action, "entity": r.entity,
         "entity_id": r.entity_id, "detail": r.detail, "created_at": r.created_at}
        for r in rows
    ]


# ── Column-level security ─────────────────────────────────────────────────────
@router.get("/column-security-rules")
async def list_column_rules(db: AsyncSession = Depends(get_db), admin: User = Depends(require_org_admin)):
    role_ids = [r.id for r in (await db.execute(
        select(Role).where(Role.org_id == admin.org_id))).scalars().all()]
    rows = (await db.execute(
        select(ColumnSecurityRule).join(Dataset, ColumnSecurityRule.dataset_id == Dataset.id)
        .where(ColumnSecurityRule.role_id.in_(role_ids), Dataset.org_id == admin.org_id)  # see list_rules
    )).scalars().all() if role_ids else []
    return [{"id": r.id, "role_id": r.role_id, "dataset_id": r.dataset_id,
             "denied_columns": r.denied_columns} for r in rows]


@router.post("/column-security-rules", status_code=201)
async def create_column_rule(body: dict, db: AsyncSession = Depends(get_db), admin: User = Depends(require_org_admin)):
    role = await db.get(Role, int(body.get("role_id") or 0))
    check_org(role, admin, "Role not found")
    ds = await db.get(Dataset, int(body.get("dataset_id") or 0))
    check_org(ds, admin, "Dataset not found")
    _refuse_if_aggregate(ds)
    denied = [str(c) for c in (body.get("denied_columns") or []) if str(c).strip()]
    if not denied:
        raise HTTPException(400, "denied_columns must name at least one column")
    rule = ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=denied)
    db.add(rule)
    await admin_audit.record(db, admin, "column_security_rule.create",
                              f"dataset:{ds.id}", ", ".join(denied))
    await db.commit()
    return {"id": rule.id}


@router.delete("/column-security-rules/{rule_id}", status_code=204)
async def delete_column_rule(rule_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_org_admin)):
    rule = await db.get(ColumnSecurityRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    role = await db.get(Role, rule.role_id)
    check_org(role, admin, "Rule not found")
    check_org(await db.get(Dataset, rule.dataset_id), admin, "Rule not found")    # see list_rules
    await admin_audit.record(db, admin, "column_security_rule.delete",
                              f"dataset:{rule.dataset_id}", None)
    await db.delete(rule)
    await db.commit()


# ── Admin audit trail (S5) ────────────────────────────────────────────────────
@router.get("/admin-audit")
async def list_admin_audit(
    limit: int = 200,
    action: str | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_org_admin),
):
    """Read-only trail of security-relevant admin mutations, newest first.
    Org-scoped and admin-only, same as `/audit-log`; `action` filters by exact
    action name, `q` by a case-insensitive substring of the target."""
    from ..models.models import AdminAudit
    limit = max(1, min(limit, 1000))
    stmt = select(AdminAudit).where(AdminAudit.org_id == admin.org_id)
    if action:
        stmt = stmt.where(AdminAudit.action == action)
    if q:
        stmt = stmt.where(AdminAudit.target.ilike(f"%{q}%"))
    rows = (await db.execute(
        stmt.order_by(AdminAudit.created_at.desc(), AdminAudit.id.desc()).limit(limit)
    )).scalars().all()
    return [
        {"id": r.id, "actor_email": r.actor_email, "action": r.action,
         "target": r.target, "detail": r.detail, "created_at": r.created_at}
        for r in rows
    ]


# ── Monitoring ────────────────────────────────────────────────────────────────
# Read-only, org-scoped, admin-only. Everything below is an AGGREGATION of
# state other features already record -- schedules, refresh timestamps, the
# delivery log. The one thing each endpoint adds is the cross-object view:
# "what runs in this org, and when did it last work" was previously answerable
# only by opening every report and every dataset one at a time.

@router.get("/monitoring/jobs")
async def list_monitoring_jobs(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_org_admin),
):
    """Every scheduled thing in the org, one uniform row shape per kind.

    Four kinds exist today -- dataset refreshes, dataflow runs, report
    schedules, data alerts -- and each stores its own last-run bookkeeping
    with its own field names. Normalising here (kind, name, interval,
    last_run_at, status, error) is what lets ONE page answer the question;
    a per-kind payload would just move the joins into the frontend.
    """
    from ..models.models import DataAlert, Dataflow, Report, ReportSchedule

    jobs: list[dict] = []

    ds_rows = (await db.execute(
        select(Dataset).where(Dataset.org_id == admin.org_id,
                              Dataset.refresh_interval_minutes.isnot(None))
    )).scalars().all()
    for d in ds_rows:
        jobs.append({"kind": "dataset_refresh", "id": d.id, "name": d.name,
                     "interval_minutes": d.refresh_interval_minutes,
                     "last_run_at": d.last_refreshed_at,
                     # The refresh loop advances last_refreshed_at on failure too
                     # (retry on schedule, not every tick) and keeps no status
                     # column -- so none is invented here.
                     "status": None, "error": None})

    df_rows = (await db.execute(
        select(Dataflow).where(Dataflow.org_id == admin.org_id,
                               Dataflow.refresh_interval_minutes.isnot(None))
    )).scalars().all()
    for f in df_rows:
        jobs.append({"kind": "dataflow", "id": f.id, "name": f.name,
                     "interval_minutes": f.refresh_interval_minutes,
                     "last_run_at": f.last_run_at,
                     "status": f.last_run_status, "error": f.last_run_error})

    sched_rows = (await db.execute(
        select(ReportSchedule, Report.name)
        .join(Report, Report.id == ReportSchedule.report_id)
        .where(ReportSchedule.org_id == admin.org_id)
    )).all()
    for s, report_name in sched_rows:
        jobs.append({"kind": "report_schedule", "id": s.id,
                     "name": s.subject or report_name,
                     "interval_minutes": s.interval_minutes,
                     # A calendar schedule ("weekly on Monday at 09:00") keeps
                     # its spec beside the recipients; without it the jobs page
                     # printed "—" for a schedule that very much runs.
                     "calendar": calendar_spec(s.recipients),
                     "timezone": s.timezone,
                     "last_run_at": s.last_run_at,
                     "status": s.last_status, "error": None,
                     "report_id": s.report_id})

    alert_rows = (await db.execute(
        select(DataAlert).where(DataAlert.org_id == admin.org_id)
    )).scalars().all()
    for a in alert_rows:
        jobs.append({"kind": "alert", "id": a.id, "name": a.name,
                     "dataset_id": a.dataset_id,
                     "interval_minutes": a.interval_minutes,
                     "last_run_at": a.last_checked_at,
                     "status": a.last_state, "error": a.last_status})

    # Most-recently-run first; never-run rows sink to the end in a stable
    # order, so a fresh org reads as a plain list, not a shuffle.
    jobs.sort(key=lambda j: (j["last_run_at"] is None,
                             -(j["last_run_at"].timestamp() if j["last_run_at"] else 0)))
    return jobs


@router.get("/monitoring/deliveries")
async def list_monitoring_deliveries(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_org_admin),
):
    """The org's delivery log across every report and alert, newest first --
    the per-report `GET /reports/{id}/deliveries` view unscoped from one
    report. Report names come back joined because a bare report_id would
    force the page into N follow-up fetches to be legible."""
    from ..models.models import Delivery, Report
    limit = max(1, min(limit, 1000))
    rows = (await db.execute(
        select(Delivery, Report.name)
        .join(Report, Report.id == Delivery.report_id, isouter=True)
        .where(Delivery.org_id == admin.org_id)
        .order_by(Delivery.created_at.desc(), Delivery.id.desc())
        .limit(limit)
    )).all()
    return [
        {"id": d.id, "kind": d.kind, "status": d.status, "error": d.error,
         "artifact_kind": d.artifact_kind, "duration_ms": d.duration_ms,
         "created_at": d.created_at, "report_id": d.report_id,
         "report_name": report_name, "schedule_id": d.schedule_id}
        for d, report_name in rows
    ]


# ── Organization hierarchy (hierarchical RLS) ────────────────────────────────
# The org's own chart, and who sits where. A rule written once as
# `branch in MYSCOPE()` then scopes every user to their own subtree -- see
# core/rls.py for the expansion, which is where the security lives. These
# endpoints only author the tree; they never decide access.

def _unit_out(u, child_count: int = 0) -> dict:
    return {"id": u.id, "parent_id": u.parent_id, "name": u.name,
            "level_name": u.level_name, "match_value": u.match_value,
            "position": u.position, "child_count": child_count}


@router.get("/org-units")
async def list_org_units(db: AsyncSession = Depends(get_db),
                         admin: User = Depends(require_org_admin)):
    """The whole tree, flat. The client nests it -- one query beats N."""
    from ..models.models import OrgUnit
    rows = (await db.execute(
        select(OrgUnit).where(OrgUnit.org_id == admin.org_id)
        .order_by(OrgUnit.position, OrgUnit.id)
    )).scalars().all()
    counts: dict[int, int] = {}
    for u in rows:
        if u.parent_id is not None:
            counts[u.parent_id] = counts.get(u.parent_id, 0) + 1
    return [_unit_out(u, counts.get(u.id, 0)) for u in rows]


@router.post("/org-units", status_code=201)
async def create_org_unit(body: dict, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(require_org_admin)):
    from ..models.models import OrgUnit
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    parent_id = body.get("parent_id")
    if parent_id is not None:
        parent = await db.get(OrgUnit, int(parent_id))
        if parent is None or parent.org_id != admin.org_id:
            raise HTTPException(404, "Parent unit not found")
    unit = OrgUnit(
        org_id=admin.org_id, parent_id=parent_id, name=name,
        level_name=(str(body.get("level_name")).strip() or None
                    if body.get("level_name") else None),
        # The value as it appears in the DATA defaults to the name: the common
        # case is that they agree, and making an author retype it invites a
        # typo that silently scopes somebody to nothing.
        match_value=str(body.get("match_value") or name).strip(),
        position=int(body.get("position") or 0),
    )
    db.add(unit)
    await admin_audit.record(db, admin, "org_unit.create", f"unit:{name}",
                             unit.level_name)
    await db.commit()
    await db.refresh(unit)
    return _unit_out(unit)


@router.patch("/org-units/{unit_id}")
async def update_org_unit(unit_id: int, body: dict, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(require_org_admin)):
    from ..models.models import OrgUnit
    unit = await db.get(OrgUnit, unit_id)
    if unit is None or unit.org_id != admin.org_id:
        raise HTTPException(404, "Unit not found")

    if "parent_id" in body:
        new_parent = body["parent_id"]
        if new_parent is not None:
            new_parent = int(new_parent)
            if new_parent == unit_id:
                raise HTTPException(400, "a unit cannot be its own parent")
            parent = await db.get(OrgUnit, new_parent)
            if parent is None or parent.org_id != admin.org_id:
                raise HTTPException(404, "Parent unit not found")
            # A move into the node's OWN subtree would orphan that subtree from
            # the root and make the descendant walk in `scope_values_for` spin
            # -- refused here, the same stance the workspace tree takes.
            rows = (await db.execute(
                select(OrgUnit.id, OrgUnit.parent_id)
                .where(OrgUnit.org_id == admin.org_id))).all()
            parents = {i: p for i, p in rows}
            seen, cur = set(), new_parent
            while cur is not None and cur not in seen:
                if cur == unit_id:
                    raise HTTPException(400, "a unit cannot be moved inside itself")
                seen.add(cur)
                cur = parents.get(cur)
        unit.parent_id = new_parent

    if "name" in body:
        name = str(body["name"] or "").strip()
        if not name:
            raise HTTPException(400, "name cannot be empty")
        unit.name = name
    if "level_name" in body:
        unit.level_name = str(body["level_name"]).strip() or None
    if "match_value" in body:
        mv = str(body["match_value"] or "").strip()
        if not mv:
            raise HTTPException(400, "match_value cannot be empty")
        unit.match_value = mv
    if "position" in body:
        unit.position = int(body["position"] or 0)

    await admin_audit.record(db, admin, "org_unit.update", f"unit:{unit.name}", None)
    await db.commit()
    await db.refresh(unit)
    return _unit_out(unit)


@router.delete("/org-units/{unit_id}", status_code=204)
async def delete_org_unit(unit_id: int, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(require_org_admin)):
    """Deleting a unit deletes its subtree (FK cascade) and every placement in
    it. Said plainly in the UI confirmation, because it is not recoverable."""
    from ..models.models import OrgUnit
    unit = await db.get(OrgUnit, unit_id)
    if unit is None or unit.org_id != admin.org_id:
        raise HTTPException(404, "Unit not found")
    await admin_audit.record(db, admin, "org_unit.delete", f"unit:{unit.name}", None)
    await db.delete(unit)
    await db.commit()


@router.get("/users/{user_id}/org-units")
async def list_user_org_units(user_id: int, db: AsyncSession = Depends(get_db),
                              admin: User = Depends(require_org_admin)):
    from ..models.models import OrgUnit, UserOrgUnit
    target = await db.get(User, user_id)
    check_org(target, admin, "User not found")
    rows = (await db.execute(
        select(UserOrgUnit, OrgUnit)
        .join(OrgUnit, OrgUnit.id == UserOrgUnit.org_unit_id)
        .where(UserOrgUnit.user_id == user_id, OrgUnit.org_id == admin.org_id)
    )).all()
    return [{"id": p.id, "org_unit_id": u.id, "name": u.name,
             "level_name": u.level_name, "match_value": u.match_value}
            for p, u in rows]


@router.put("/users/{user_id}/org-units")
async def set_user_org_units(user_id: int, body: dict, db: AsyncSession = Depends(get_db),
                             admin: User = Depends(require_org_admin)):
    """Replace this user's placements wholesale. An empty list clears them,
    which means MYSCOPE() no longer resolves for that user and any rule using
    it fails closed -- they see nothing rather than everything."""
    from ..models.models import OrgUnit, UserOrgUnit
    target = await db.get(User, user_id)
    check_org(target, admin, "User not found")
    ids = [int(i) for i in (body.get("org_unit_ids") or [])]
    if ids:
        valid = (await db.execute(
            select(OrgUnit.id).where(OrgUnit.id.in_(ids),
                                     OrgUnit.org_id == admin.org_id)
        )).scalars().all()
        missing = set(ids) - set(valid)
        if missing:
            raise HTTPException(404, f"unit(s) not in your organization: {sorted(missing)}")

    existing = (await db.execute(
        select(UserOrgUnit).where(UserOrgUnit.user_id == user_id)
    )).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()
    for unit_id in dict.fromkeys(ids):
        db.add(UserOrgUnit(user_id=user_id, org_unit_id=unit_id))
    await admin_audit.record(db, admin, "user.org_units", f"user:{target.email}",
                             ", ".join(str(i) for i in ids) or "(cleared)")
    await db.commit()
    return {"org_unit_ids": ids}


