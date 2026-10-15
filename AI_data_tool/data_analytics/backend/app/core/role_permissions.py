"""What a role may do, beyond seeing data (QA E-08).

A role was a name plus "Org admin". Nothing could stop a role from uploading
files, adding connections or creating dashboards. Each role now carries a
small, fixed set of capabilities, each enforced at ONE server choke point:

  upload_data        POST /datasets, POST /datasets/batch (file uploads)
  create_connection  POST /data-sources
  create_dashboard   POST /reports, duplicate, create from a template
  use_ai             every model call made for the person (services/llm.py
                     refuses it; Ask AI and the page copilot answer 403)
  export             routers/shared.download_gate (every dashboard, widget and
                     semantic download), the dataset export and Ask AI's
                     result export

Stored on `roles.permissions` (JSON) as {capability: bool}. Backward
compatible by construction: NULL -- every role that existed before revision
0072_role_capabilities -- and any capability missing from the dict (one added
later) mean ALLOWED, so nobody loses a right on upgrade. An org-admin role
always has every capability, whatever is stored.

These capabilities only take rights away from a role; they never grant data
access. Org scope, row/column security, dataset shares and dashboard grants
are checked exactly as before.
"""
from __future__ import annotations

from fastapi import HTTPException, status

CAPABILITIES: tuple[str, ...] = (
    "upload_data", "create_connection", "create_dashboard", "use_ai", "export",
)

#: What the person was trying to do, for the 403 text.
_ACTION = {
    "upload_data": "upload data",
    "create_connection": "add connections",
    "create_dashboard": "create dashboards",
    "use_ai": "use AI features",
    "export": "download or export data",
}


def effective(role) -> dict[str, bool]:
    """The role's capabilities with the defaults applied. No role: nothing."""
    if role is None:
        return {c: False for c in CAPABILITIES}
    if getattr(role, "is_org_admin", False):
        return {c: True for c in CAPABILITIES}
    stored = getattr(role, "permissions_raw", None) or {}
    if not isinstance(stored, dict):
        stored = {}
    return {c: bool(stored.get(c, True)) for c in CAPABILITIES}


def normalise(changes: dict | None, current: dict | None = None) -> dict[str, bool]:
    """`current` with `changes` applied, every capability spelled out. Raises
    422 on a name that is not a capability or a value that is not a boolean."""
    out = {c: bool((current or {}).get(c, True)) for c in CAPABILITIES}
    for key, value in (changes or {}).items():
        if key not in CAPABILITIES:
            raise HTTPException(422, f"Unknown permission '{key}'. Known: {', '.join(CAPABILITIES)}")
        if not isinstance(value, bool):
            raise HTTPException(422, f"Permission '{key}' must be true or false")
        out[key] = value
    return out


def refusal(role, capability: str) -> str | None:
    """Why this role may not use `capability`, or None when it may."""
    if effective(role).get(capability, False):
        return None
    name = getattr(role, "name", None) or "your role"
    return (f"Your role ({name}) is not allowed to {_ACTION.get(capability, capability)}. "
            f"Ask an organization admin to change the role's permissions.")


def check(user, capability: str) -> None:
    """403 with a readable reason when the user's role lacks `capability`."""
    why = refusal(getattr(user, "role", None), capability)
    if why:
        raise HTTPException(status.HTTP_403_FORBIDDEN, why)


async def user_may(db, user_id: int | None, capability: str) -> str | None:
    """`refusal` for a user known only by id (a background run, an
    automation): None when allowed or when there is no person behind the
    work. Reads the role in one query; never touches a lazy relationship."""
    if user_id is None:
        return None
    from sqlalchemy import select
    from ..models.models import Role, User
    role = (await db.execute(select(Role).join(User, User.role_id == Role.id)
                             .where(User.id == user_id))).scalar_one_or_none()
    if role is None:
        return None
    return refusal(role, capability)

