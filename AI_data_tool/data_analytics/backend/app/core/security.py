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
ACCESS_TOKEN_EXPIRE_DAYS = 7


def create_access_token(user_id: int, org_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "org_id": org_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


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
