from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .core.api_keys import looks_like_api_key, prefix_of, verify
from .core.database import get_db
from .core.security import (CSRF_HEADER, SESSION_COOKIE, decode_access_token,
                            issued_before_cutoff)
from .models.models import ApiKey, User

# auto_error=False on both: the token may instead ride in the session cookie
# (T6), so a missing header is not yet a failure -- `_request_token` decides.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
# A guest/share-link route wants to know WHETHER a valid session rides along
# without ever failing the request over it -- a missing, stale or foreign-org
# credential just falls back to anonymous, it never 401s.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_CREDS_ERROR = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _request_token(request: Request, header_token: str | None) -> str | None:
    """The Authorization header if present, else the browser session cookie.

    A cookie is sent by the browser on its own, which is what makes CSRF
    possible, so a cookie-authenticated WRITE must also carry the custom
    header (CSRF_HEADER): a cross-site form cannot set one, and a cross-origin
    fetch cannot without a CORS preflight only our origins pass. Missing it,
    the cookie is simply not used -- the request is anonymous, not an error
    of its own. A header token needs no such check: nothing attaches it
    automatically."""
    if header_token:
        return header_token
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    if request.method.upper() not in _SAFE_METHODS and not request.headers.get(CSRF_HEADER):
        return None
    return cookie


async def _load_active_user(db: AsyncSession, user_id: int, payload: dict | None = None) -> User:
    user = (await db.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization))
        .where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _CREDS_ERROR
    # A login token minted before the user's password was reset is dead, even
    # with days left on it. API keys pass no payload: they are revoked on their
    # own row, not by a password change.
    if payload is not None and issued_before_cutoff(payload, user.tokens_valid_after):
        raise _CREDS_ERROR
    return user


async def _user_from_api_key(db: AsyncSession, token: str) -> User:
    """Resolve a `dk_…` machine key to its user. Looked up by prefix, then the full key
    is hash-verified in constant time; the key acts as its owning user, so every
    downstream control (org scope, RLS, capabilities) applies unchanged."""
    pfx = prefix_of(token)
    if not pfx:
        raise _CREDS_ERROR
    row = (await db.execute(select(ApiKey).where(ApiKey.prefix == pfx))).scalar_one_or_none()
    if row is None or not verify(token, row.key_hash):
        raise _CREDS_ERROR
    # A platform super-admin can switch MCP / machine access off for a whole org; when
    # off, every one of its API keys stops authenticating, in one place.
    from .services.org_access import mcp_enabled
    if not await mcp_enabled(db, row.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "MCP / API-key access is disabled for this organization")
    return await _load_active_user(db, row.user_id)


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _request_token(request, token)
    if not token:
        raise _CREDS_ERROR
    # A bearer credential is either a machine API key (dk_…) or a login JWT. Machine
    # keys let agents (the MCP server) authenticate durably without a login round-trip.
    if looks_like_api_key(token):
        return await _user_from_api_key(db, token)
    payload = decode_access_token(token)
    if payload is None:
        raise _CREDS_ERROR
    user_id = payload.get("sub")
    if user_id is None:
        raise _CREDS_ERROR
    return await _load_active_user(db, int(user_id), payload)


async def get_current_user_optional(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Same resolution as `get_current_user`, but never raises: no token, a
    stale/invalid one, an inactive user, or a disabled-MCP API key all resolve
    to None (anonymous) rather than a 401. Built for share-link routes, which
    have NO auth requirement of their own and must keep working for a truly
    anonymous caller -- this only upgrades identity when a valid session is
    actually present, it never gates access on one."""
    token = _request_token(request, token)
    if not token:
        return None
    try:
        if looks_like_api_key(token):
            return await _user_from_api_key(db, token)
        payload = decode_access_token(token)
        if payload is None:
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return await _load_active_user(db, int(user_id), payload)
    except HTTPException:
        return None


async def require_org_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.role.is_org_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return current_user


def is_super_admin(user: User | None) -> bool:
    """A platform super-admin, from the config email allowlist. Read dynamically so the
    allowlist can change (and tests can set it) without a restart."""
    from .core.config import settings
    allow = {e.strip().lower() for e in (settings.super_admin_emails or "").split(",") if e.strip()}
    return bool(user and user.email and user.email.lower() in allow)


async def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_super_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform super-admin privileges required")
    return current_user
