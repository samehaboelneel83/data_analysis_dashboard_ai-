from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core import api_keys
from ..core.database import get_db
from ..core.security import (clear_session_cookie, create_access_token, hash_password,
                             set_session_cookie, verify_password)
from ..dependencies import get_current_user
from ..models.models import ApiKey, User
from ..schemas.schemas import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# A hash of a password nobody will ever type, computed once at import time.
# Used to pay bcrypt's cost when there's no real user to check against, so an
# unknown-email login takes the same time as a wrong-password one and the two
# can't be told apart by response time.
_DUMMY_HASH = hash_password("timing-attack-mitigation")


@router.post("/login", response_model=TokenOut)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, "Invalid email or password")
    # Compute this unconditionally (not inside an `or` short-circuit) so an
    # inactive user's login attempt pays the same bcrypt cost as a wrong
    # password, keeping unknown-email/inactive-user/wrong-password
    # indistinguishable by timing as well as by response body.
    password_ok = verify_password(body.password, user.password_hash)
    if not user.is_active or not password_ok:
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(user.id, user.org_id)
    # T6: the browser keeps the session in an httpOnly cookie it cannot read
    # from script. The body still carries the token for API clients.
    set_session_cookie(response, token)
    return TokenOut(access_token=token)


@router.post("/session", status_code=204)
async def adopt_session(request: Request, response: Response,
                        current_user: User = Depends(get_current_user)):
    """Move a browser session from the old localStorage token into the cookie.

    Before T6 the frontend stored the login JWT in localStorage; on its first
    load after the change it sends that token here once, as a header, gets the
    cookie, and deletes its copy -- so nobody is logged out by the upgrade.
    Only a login JWT is accepted: a machine API key must never become a
    browser cookie."""
    auth = request.headers.get("authorization") or ""
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not token or api_keys.looks_like_api_key(token):
        raise HTTPException(400, "Send the login token as a Bearer header")
    set_session_cookie(response, token)


@router.post("/logout", status_code=204)
async def logout(response: Response):
    """End the browser session: the cookie is httpOnly, so only the server can
    remove it. (The JWT itself stays valid until it expires, as before; a
    password reset still revokes every session at once.)"""
    clear_session_cookie(response)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    from ..dependencies import is_super_admin
    current_user.is_super_admin = is_super_admin(current_user)
    return current_user


# ── Machine API keys ──────────────────────────────────────────────────────────
# A user issues durable keys for agents (e.g. the MCP server) that act as them. The
# full key is returned once at creation; only its hash is stored. A key works anywhere
# a login token does, so an agent authenticates with it as a plain bearer token.

class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _key_out(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix,
            "created_at": k.created_at, "last_used_at": k.last_used_at}


@router.get("/api-keys")
async def list_api_keys(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    )).scalars().all()
    return [_key_out(k) for k in rows]


@router.post("/api-keys", status_code=201)
async def create_api_key(body: ApiKeyCreate, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Issue a key. The `key` in the response is shown ONCE and cannot be recovered —
    store it now. It authenticates as this user until revoked."""
    full, prefix, key_hash = api_keys.generate()
    row = ApiKey(org_id=current_user.org_id, user_id=current_user.id,
                 name=body.name.strip(), prefix=prefix, key_hash=key_hash)
    db.add(row)
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "api_key.create", f"prefix:{prefix}", body.name.strip())
    await db.commit()
    await db.refresh(row)
    return {**_key_out(row), "key": full}


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: int, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    row = await db.get(ApiKey, key_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(404, "API key not found")   # scoped to the owner
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "api_key.revoke", f"prefix:{row.prefix}", None)
    await db.delete(row)
    await db.commit()


@router.get("/my-scope")
async def my_scope(db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """What MYSCOPE() resolves to for the CALLER: their org-unit placements
    expanded to every descendant.

    Lives under /auth rather than /admin because it is deliberately open to any
    signed-in user, and an endpoint that is not admin-only has no business
    sitting behind the admin prefix -- the parametric admin sweep in
    test_admin_endpoints_require_admin.py caught exactly that mismatch.

    Answering "why does my dashboard show these rows" without filing a ticket
    is the point. It reveals only the caller's own access, which they can
    already infer from the data they can read.
    """
    from ..core.rls import scope_values_for
    values = await scope_values_for(db, current_user)
    return {
        "placed": values is not None,
        "values": values or [],
        "is_org_admin": bool(current_user.role and current_user.role.is_org_admin),
    }
