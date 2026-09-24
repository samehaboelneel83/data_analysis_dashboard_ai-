"""OpenID Connect (Authorization Code + PKCE) single sign-on, per organization.

datalytics acts as an OIDC *relying party*. Each org configures one IdP (models.OrgIdp),
resolved at login by the user's email domain. The flow, split across two HTTP requests:

  1. /auth/sso/oidc/login?email=…  → resolve the org's IdP, fetch its discovery document,
     build the authorize URL with `state` (CSRF), `nonce` (replay) and PKCE, stash the
     one-time flow secrets in a signed, HttpOnly, short-lived cookie, and 302 to the IdP.
  2. /auth/sso/oidc/callback       → verify the cookie + `state`, exchange the code for
     tokens (sending the PKCE verifier), fully validate the id_token (JWKS signature,
     `iss`, `aud`, `exp`, `nonce`), read the email, and match it to an EXISTING active
     user in that org. A successful login whose email has no user is refused, never
     provisioned — SSO authenticates, it does not create accounts.

The IdP client secret is stored encrypted (services/secrets.py) like any other credential.
No server-side session store is needed: the flow secrets live in the signed cookie, so this
works unchanged across multiple backend workers.
"""
from __future__ import annotations

import base64
import hashlib
import secrets as rand           # stdlib CSPRNG (absolute import; not app.services.secrets)
import time
from typing import Any

import httpx
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.models import OrgIdp, User
from .secrets import decrypt_value, encrypt_value, REDACTED

# The one secret field on an IdP config, encrypted at rest and redacted over the API.
SECRET_FIELDS = ("client_secret",)

_FLOW_ALG = "HS256"          # signs the short-lived flow cookie with the app secret
_FLOW_TTL = 600              # 10 minutes to complete the round-trip to the IdP
_HTTP_TIMEOUT = 10.0

# ── discovery / JWKS caches (issuer/uri → (fetched_at, doc)) ────────────────────
_DISCO_TTL = 3600
_disco_cache: dict[str, tuple[float, dict]] = {}
_jwks_cache: dict[str, tuple[float, dict]] = {}


class SsoError(Exception):
    """A recoverable SSO failure surfaced to the user as a login error (never leaks
    IdP internals)."""


# ── config helpers ──────────────────────────────────────────────────────────────
def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if email and "@" in email else ""


async def idp_for_domain(db: AsyncSession, email: str) -> OrgIdp | None:
    """The enabled IdP that claims this email's domain, or None. If two orgs claim the
    same domain (a misconfiguration) we resolve to none rather than guess an org."""
    dom = domain_of(email)
    if not dom:
        return None
    rows = (await db.execute(
        select(OrgIdp).where(OrgIdp.email_domain == dom, OrgIdp.enabled == True)  # noqa: E712
    )).scalars().all()
    return rows[0] if len(rows) == 1 else None


async def idp_for_org(db: AsyncSession, org_id: int) -> OrgIdp | None:
    return (await db.execute(
        select(OrgIdp).where(OrgIdp.org_id == org_id))).scalar_one_or_none()


async def domain_claimed_by_other(db: AsyncSession, domain: str, org_id: int) -> bool:
    """True if another org already claims this email domain — enforced at config time so
    domain→org resolution stays unambiguous."""
    dom = (domain or "").strip().lower()
    rows = (await db.execute(select(OrgIdp).where(OrgIdp.email_domain == dom))).scalars().all()
    return any(r.org_id != org_id for r in rows)


def config_out(idp: OrgIdp) -> dict:
    """IdP config safe to return over the API — the client secret is redacted."""
    return {
        "protocol": idp.protocol,
        "enabled": idp.enabled,
        "email_domain": idp.email_domain,
        "issuer": idp.issuer,
        "client_id": idp.client_id,
        "client_secret": REDACTED if idp.client_secret else "",
        "config": idp.config or {},
    }


# ── OIDC network calls (discovery, JWKS, token exchange) ─────────────────────────
async def _get_json(url: str) -> dict:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def fetch_discovery(issuer: str) -> dict:
    """The IdP's OIDC discovery document (authorization/token endpoints, jwks_uri),
    cached for an hour."""
    key = issuer.rstrip("/")
    hit = _disco_cache.get(key)
    if hit and time.time() - hit[0] < _DISCO_TTL:
        return hit[1]
    try:
        doc = await _get_json(key + "/.well-known/openid-configuration")
    except Exception as e:                                   # noqa: BLE001
        raise SsoError("Could not reach the identity provider") from e
    _disco_cache[key] = (time.time(), doc)
    return doc


async def fetch_jwks(jwks_uri: str) -> dict:
    hit = _jwks_cache.get(jwks_uri)
    if hit and time.time() - hit[0] < _DISCO_TTL:
        return hit[1]
    try:
        doc = await _get_json(jwks_uri)
    except Exception as e:                                   # noqa: BLE001
        raise SsoError("Could not fetch the identity provider's signing keys") from e
    _jwks_cache[jwks_uri] = (time.time(), doc)
    return doc


async def exchange_code(disco: dict, idp: OrgIdp, code: str, redirect_uri: str,
                        code_verifier: str) -> dict:
    """Swap the authorization code for tokens at the IdP's token endpoint, proving
    possession of the PKCE verifier. Returns the token response (must contain id_token)."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": idp.client_id,
        "client_secret": decrypt_value(idp.client_secret) if idp.client_secret else "",
        "code_verifier": code_verifier,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(disco["token_endpoint"], data=data,
                                     headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:                                   # noqa: BLE001
        raise SsoError("The identity provider rejected the login") from e


# ── PKCE + flow-state cookie ─────────────────────────────────────────────────────
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge) for PKCE S256."""
    verifier = _b64url(rand.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def build_authorize_url(disco: dict, idp: OrgIdp, redirect_uri: str,
                        state: str, nonce: str, code_challenge: str) -> str:
    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": idp.client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return disco["authorization_endpoint"] + "?" + urlencode(params)


def seal_flow(org_id: int, state: str, nonce: str, code_verifier: str,
              redirect_uri: str) -> str:
    """Sign the one-time flow secrets into a short-lived token for the HttpOnly cookie."""
    payload = {"org_id": org_id, "st": state, "nonce": nonce, "cv": code_verifier,
               "ru": redirect_uri, "exp": int(time.time()) + _FLOW_TTL}
    return jwt.encode(payload, settings.secret_key, algorithm=_FLOW_ALG)


def open_flow(cookie: str | None, state_param: str | None) -> dict:
    """Verify the flow cookie and that the returned `state` matches the one we issued
    (CSRF). Raises SsoError on any tampering, expiry, or mismatch."""
    if not cookie or not state_param:
        raise SsoError("The login session expired or is invalid. Please try again.")
    try:
        flow = jwt.decode(cookie, settings.secret_key, algorithms=[_FLOW_ALG])
    except JWTError as e:
        raise SsoError("The login session is invalid. Please try again.") from e
    if not rand.compare_digest(str(flow.get("st", "")), state_param):
        raise SsoError("The login request could not be verified. Please try again.")
    return flow


# ── id_token validation ──────────────────────────────────────────────────────────
def validate_id_token(id_token: str, idp: OrgIdp, disco: dict, jwks: dict,
                      nonce: str) -> dict:
    """Fully validate the id_token and return its claims. Verifies the RS/ES signature
    against the JWKS key named by the token's `kid`, plus `aud` (== client_id), `iss`
    (== discovery issuer), `exp`, and the `nonce` we sent. Raises SsoError otherwise."""
    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as e:
        raise SsoError("The identity provider returned an unreadable token") from e
    kid = header.get("kid")
    keys = jwks.get("keys", [])
    key = next((k for k in keys if k.get("kid") == kid), keys[0] if keys else None)
    if key is None:
        raise SsoError("The identity provider's signing key was not found")
    alg = key.get("alg") or header.get("alg") or "RS256"
    try:
        claims = jwt.decode(
            id_token, key, algorithms=[alg],
            audience=idp.client_id, issuer=disco.get("issuer"),
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise SsoError("The login token failed validation") from e
    if not rand.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("The login token failed a replay check")
    return claims


async def match_user(db: AsyncSession, org_id: int, email: str) -> User | None:
    """The active user in this org with this email, or None. SSO matches existing users
    only — it never provisions. Email match is case-insensitive."""
    if not email:
        return None
    from sqlalchemy import func
    return (await db.execute(
        select(User).where(User.org_id == org_id,
                           func.lower(User.email) == email.strip().lower(),
                           User.is_active == True)  # noqa: E712
    )).scalar_one_or_none()


def apply_secret_update(idp: OrgIdp, new_secret: str | None) -> None:
    """Set the client secret from an admin update: the redaction sentinel means 'keep the
    stored one'; any other non-empty value is encrypted and stored."""
    if new_secret is None or new_secret == REDACTED:
        return
    idp.client_secret = encrypt_value(new_secret) if new_secret else ""
