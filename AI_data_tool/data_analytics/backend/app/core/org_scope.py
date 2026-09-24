from fastapi import HTTPException


def check_org(obj, current_user, message: str = "Not found") -> None:
    """Raise 404 if obj is missing or doesn't belong to current_user's org.

    Always 404, never 403 — a 403 would reveal that the object exists but isn't
    the caller's, which is itself information leakage. 404 keeps "doesn't exist"
    and "exists but isn't yours" indistinguishable, per the design spec.
    """
    if obj is None or obj.org_id != current_user.org_id:
        raise HTTPException(404, message)
