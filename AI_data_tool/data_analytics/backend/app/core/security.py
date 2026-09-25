from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


ALGORITHM = "HS256"


def create_access_token(user_id: int, org_id: int) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.access_token_expire_hours)
    # `iat` is what lets a password reset end this session early: the
    # dependency refuses a token issued before User.tokens_valid_after.
    payload = {"sub": str(user_id), "org_id": org_id, "exp": expire,
               "iat": int(now.timestamp())}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


# ── T6: the browser session rides in an httpOnly cookie ──────────────────────
# The login JWT used to live in localStorage, where any script injected into
# the page could read it and carry it off. As an httpOnly cookie no script can
# read it; SameSite=Lax keeps it off cross-site subrequests, and the dependency
# additionally demands a custom header on a cookie-authenticated write (CSRF).
# The Authorization header still works for API keys, embeds and scripts.
SESSION_COOKIE = "datalytics_session"
# A header a cross-site <form> cannot send and a cross-origin fetch cannot send
# without a CORS preflight, which only the configured origins pass.
CSRF_HEADER = "x-requested-with"


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=settings.access_token_expire_hours * 3600,
        httponly=True, secure=settings.is_production(), samesite="lax", path="/api",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api", httponly=True,
                           secure=settings.is_production(), samesite="lax")


def issued_before_cutoff(payload: dict, cutoff: datetime | None) -> bool:
    """True when this token predates the user's revocation cut-off.

    Whole seconds on both sides (`iat` is an integer), so a token minted in the
    same second as the reset -- the fresh login right after it -- survives. A
    token with no `iat` was minted before revocation existed and is refused
    once any cut-off is set."""
    if cutoff is None:
        return False
    if cutoff.tzinfo is None:          # SQLite hands back naive UTC
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    iat = payload.get("iat")
    if not isinstance(iat, (int, float)):
        return True
    return int(iat) < int(cutoff.timestamp())


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


# Task E1: the internal, short-lived token an embedded report's browser session
# uses for widget-data calls. Deliberately NOT `create_access_token` -- it must
# never open any endpoint besides the embed widget-data route. Two things
# enforce that isolation, both directions:
#   * `aud="embed"` -- decode_access_token() never passes `audience=`, so
#     python-jose refuses ANY token carrying an `aud` claim there (a security
#     default, not an oversight): this token can't authenticate as a user.
#   * decode_embed_session_token() always passes `audience=EMBED_AUDIENCE`, so
#     jose equally refuses an ordinary login JWT (no `aud` claim at all) here.
# It carries the embed config id plus everything the host's original JWT
# declared (filters/viewer_email/viewer_org) baked in at mint time, so the
# widget-data route never has to re-trust anything the browser sends.
EMBED_AUDIENCE = "embed"
EMBED_SESSION_TTL_MINUTES = 15


def create_embed_session_token(
    cfg_id: int, *, filters: list | None = None,
    viewer_email: str | None = None, viewer_org: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=EMBED_SESSION_TTL_MINUTES)
    payload = {
        "aud": EMBED_AUDIENCE, "cfg": int(cfg_id), "exp": expire,
        "filters": filters or [], "viewer_email": viewer_email, "viewer_org": viewer_org,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_embed_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM], audience=EMBED_AUDIENCE)
    except JWTError:
        return None
