"""Batch authorization decisions with reasons (Phase 7.3).

One call answers up to 50 "may I …?" questions, each with the rule that
decided it, so a UI can grey out what the user cannot do AND say why --
instead of offering a button the server then refuses. The decisions are the
same functions every endpoint enforces with; this router only asks them.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import (can_read_dataset, explain_capability, max_dataset_capability,
                               rank as cap_rank)
from ..core.database import get_db
from ..dependencies import get_current_user
from ..models.models import Dataset, Report, User

router = APIRouter(prefix="/authz", tags=["authz"])

MAX_CHECKS = 50
REPORT_ACTIONS = {"view": "view", "edit": "edit", "data": "data"}


async def _report_decision(db, user, report_id: int, action: str) -> dict:
    from ..services.sensitivity import rank as s_rank, report_effective
    level, why = await explain_capability(db, user, report_id)
    if action in REPORT_ACTIONS:
        need = REPORT_ACTIONS[action]
        ok = cap_rank(level) >= cap_rank(need)
        return {"allowed": ok, "level": level,
                "reason": why + ("" if ok else f" That gives {level} access; this needs {need}.")}
    report = await db.get(Report, report_id)
    label, reasons = await report_effective(db, report) if report else (None, [])
    because = f" ({reasons[0]})" if reasons else ""
    if action == "share_link":
        if cap_rank(level) < cap_rank("edit"):
            return {"allowed": False, "level": level, "reason": why + " Sharing by link needs edit access."}
        if s_rank(label) >= s_rank("Restricted"):
            return {"allowed": False, "level": level, "sensitivity": label,
                    "reason": f"The report is Restricted{because}; share it with named people instead."}
        note = (" Anonymous readers will be asked to sign in, and personal-data columns are redacted."
                if s_rank(label) >= s_rank("Confidential") else "")
        return {"allowed": True, "level": level, "sensitivity": label, "reason": why + note}
    if action == "download":
        if cap_rank(level) < cap_rank("view"):
            return {"allowed": False, "level": level, "reason": why}
        if s_rank(label) >= s_rank("Restricted") and cap_rank(level) < cap_rank("data"):
            return {"allowed": False, "level": level, "sensitivity": label,
                    "reason": f"The report is Restricted{because}; only data-level access may download it."}
        note = " Personal-data columns are redacted from the file." if s_rank(label) >= s_rank("Confidential") else ""
        return {"allowed": True, "level": level, "sensitivity": label, "reason": why + note}
    raise HTTPException(400, f"Unknown report action '{action}'")


async def _dataset_decision(db, user, dataset_id: int, action: str, column: str | None) -> dict:
    from ..core.rls import resolve_denied_columns
    ds = await db.get(Dataset, dataset_id)
    if ds is None or ds.org_id != user.org_id or not await can_read_dataset(db, user, dataset_id):
        return {"allowed": False, "reason": "You have no access to this dataset: it is not yours, not shared "
                                            "with you, and no dashboard you can open uses it."}
    if action == "read":
        return {"allowed": True, "reason": "You can open a dashboard that uses it, or it is yours or shared with you."}
    if action in ("edit", "data"):
        level = await max_dataset_capability(db, user, dataset_id)
        ok = cap_rank(level) >= cap_rank(action)
        return {"allowed": ok, "level": level,
                "reason": ("Your role's access through the reports using it is " + level
                           + ("." if ok else f"; changing its model needs {action}."))}
    if action == "read_column":
        if not column:
            raise HTTPException(400, "read_column needs a column")
        denied = await resolve_denied_columns(db, user, dataset_id) or []
        if column in denied:
            return {"allowed": False, "reason": f"A column-security rule on your role hides '{column}'."}
        return {"allowed": True, "reason": f"No column-security rule hides '{column}' from your role."}
    raise HTTPException(400, f"Unknown dataset action '{action}'")


@router.post("/decisions")
async def decisions(body: dict, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """`{"checks": [{"resource": "report"|"dataset", "id": 5, "action": "edit", "column"?: "x"}]}`
    -> `{"decisions": [{...check, allowed, reason, level?, sensitivity?}]}` in the same order."""
    checks = body.get("checks")
    if not isinstance(checks, list) or not checks:
        raise HTTPException(400, "checks must be a non-empty list")
    if len(checks) > MAX_CHECKS:
        raise HTTPException(400, f"At most {MAX_CHECKS} checks per call")
    out = []
    for c in checks:
        if not isinstance(c, dict):
            raise HTTPException(400, "each check is an object")
        kind, action = c.get("resource"), str(c.get("action") or "")
        try:
            rid = int(c.get("id"))
        except (TypeError, ValueError):
            raise HTTPException(400, "each check needs a numeric id")
        if kind == "report":
            d = await _report_decision(db, current_user, rid, action)
        elif kind == "dataset":
            d = await _dataset_decision(db, current_user, rid, action, c.get("column"))
        else:
            raise HTTPException(400, "resource must be 'report' or 'dataset'")
        out.append({"resource": kind, "id": rid, "action": action,
                    **({"column": c.get("column")} if c.get("column") else {}), **d})
    return {"decisions": out}
