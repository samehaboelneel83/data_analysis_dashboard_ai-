"""Generation and hashing of machine API keys.

Format:  dk_<prefix>.<secret>
  - prefix  a short, non-secret lookup handle (stored, indexed)
  - secret  high-entropy random; only the SHA-256 of the WHOLE key is stored
The "." separator is safe because url-safe base64 never contains it, so the prefix
is unambiguous. The key is shown once at creation and cannot be recovered.
"""
import hashlib
import hmac
import secrets

_SCHEME = "dk_"


def looks_like_api_key(token: str) -> bool:
    return isinstance(token, str) and token.startswith(_SCHEME)


def prefix_of(token: str) -> str | None:
    if not looks_like_api_key(token):
        return None
    rest = token[len(_SCHEME):]
    return rest.split(".", 1)[0] if "." in rest else None


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_key(token), stored_hash)   # constant-time


def generate() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash). Persist prefix + key_hash; show full_key once."""
    prefix = secrets.token_urlsafe(6)
    secret = secrets.token_urlsafe(32)
    full = f"{_SCHEME}{prefix}.{secret}"
    return full, prefix, hash_key(full)
