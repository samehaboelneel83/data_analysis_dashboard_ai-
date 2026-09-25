"""SSO endpoints: the public OIDC login/callback flow, and per-org IdP configuration.

Config is managed by an org admin for their own org (a super-admin can manage any org via
the platform surface). The login/callback endpoints are unauthenticated by design — they
ARE the authentication — and hand the browser a normal datalytics token at the end, so the
rest of the app is unchanged.
"""
from __future__ import annotations

import secrets as rand
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db
from ..core.security import create_access_token, set_session_cookie
from ..dependencies import require_org_admin
from ..models.models import OrgIdp, SamlAuthnRequest, User
from ..services import saml, sso

router = APIRouter(prefix="/auth/sso", tags=["sso"])

_FLOW_COOKIE = "sso_flow"


def _cookie_secure() -> bool:
    return (settings.env or "").lower() not in ("development", "dev", "test")


def _frontend(path: str) -> str:
    return settings.public_base_url.rstrip("/") + path


# ── public: discovery for the login page ─────────────────────────────────────────
class DiscoverIn(BaseModel):
    # A plain string, not EmailStr: we only need the domain, and internal IdP domains
    # (…​.local, …​.internal) that EmailStr rejects as reserved must still resolve — the
    # login endpoint accepts them too, so discover must agree.
    email: str = Field(min_length=1, max_length=320)


@router.post("/discover")
async def discover(body: DiscoverIn, db: AsyncSession = Depends(get_db)):
    """Tell the login UI whether an email's domain has SSO configured, so it can show a
    'Sign in with SSO' button. No secrets, no user existence leaked."""
    idp = await sso.idp_for_domain(db, body.email)
    return {"sso": idp is not None, "protocol": idp.protocol if idp else None}


# ── public: OIDC login initiation ────────────────────────────────────────────────
@router.get("/oidc/login")
async def oidc_login(request: Request, email: str, db: AsyncSession = Depends(get_db)):
    idp = await sso.idp_for_domain(db, email)
    if idp is None or idp.protocol != "oidc":
        return RedirectResponse(_frontend("/login?sso_error=not_configured"), status_code=303)
    try:
        disco = await sso.fetch_discovery(idp.issuer)
        redirect_uri = str(request.url_for("sso_oidc_callback"))
        state, nonce = rand.token_urlsafe(24), rand.token_urlsafe(24)
        verifier, challenge = sso.make_pkce()
        url = sso.build_authorize_url(disco, idp, redirect_uri, state, nonce, challenge)
    except sso.SsoError:
        return RedirectResponse(_frontend("/login?sso_error=provider_unreachable"), status_code=303)
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(
        _FLOW_COOKIE, sso.seal_flow(idp.org_id, state, nonce, verifier, redirect_uri),
        max_age=600, httponly=True, secure=_cookie_secure(), samesite="lax", path="/",
    )
    return resp


# ── public: OIDC callback ────────────────────────────────────────────────────────
@router.get("/oidc/callback", name="sso_oidc_callback")
async def oidc_callback(request: Request, db: AsyncSession = Depends(get_db),
                        code: str | None = None, state: str | None = None,
                        error: str | None = None):
    def fail(reason: str) -> RedirectResponse:
        r = RedirectResponse(_frontend(f"/login?sso_error={reason}"), status_code=303)
        r.delete_cookie(_FLOW_COOKIE, path="/")
        return r

    if error or not code:
        return fail("denied")
    try:
        flow = sso.open_flow(request.cookies.get(_FLOW_COOKIE), state)
        idp = await sso.idp_for_org(db, int(flow["org_id"]))
        if idp is None or idp.protocol != "oidc":
            return fail("not_configured")
        disco = await sso.fetch_discovery(idp.issuer)
        tokens = await sso.exchange_code(disco, idp, code, flow["ru"], flow["cv"])
        id_token = tokens.get("id_token")
        if not id_token:
            return fail("no_id_token")
        jwks = await sso.fetch_jwks(disco["jwks_uri"])
        claims = sso.validate_id_token(id_token, idp, disco, jwks, flow["nonce"])
    except sso.SsoError:
        return fail("validation_failed")

    email = claims.get("email") or ""
    # OIDC: only trust the email when the provider marks it verified (absent = trust, since
    # many enterprise IdPs omit the claim for their own managed accounts).
    if claims.get("email_verified") is False:
        return fail("email_unverified")
    user = await sso.match_user(db, idp.org_id, email)
    if user is None:
        # Match-existing only: authenticated at the IdP, but no account here to log into.
        return fail("no_account")

    token = create_access_token(user.id, user.org_id)
    # T6: the session is the httpOnly cookie; the token no longer rides in the
    # URL, where it sat in browser history and any Referer the page sent.
    resp = RedirectResponse(_frontend("/sso/callback"), status_code=303)
    set_session_cookie(resp, token)
    resp.delete_cookie(_FLOW_COOKIE, path="/")
    return resp


# ── public: SAML 2.0 (SP-initiated Web SSO) ──────────────────────────────────────
def _saml_urls(request: Request) -> tuple[str, str]:
    """(sp_entity_id, acs_url) — our SP entityID is the metadata URL, per convention."""
    return str(request.url_for("saml_metadata")), str(request.url_for("saml_acs"))


@router.get("/saml/metadata", name="saml_metadata")
async def saml_metadata(request: Request, db: AsyncSession = Depends(get_db)):
    sp_entity_id, acs_url = _saml_urls(request)
    xml = (
        f'<?xml version="1.0"?>'
        f'<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{sp_entity_id}">'
        f'<SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" '
        f'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        f'<AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs_url}" index="0" isDefault="true"/>'
        f'</SPSSODescriptor></EntityDescriptor>'
    )
    return Response(content=xml, media_type="application/samlmetadata+xml")


@router.get("/saml/login")
async def saml_login(request: Request, email: str, db: AsyncSession = Depends(get_db)):
    idp = await sso.idp_for_domain(db, email)
    if idp is None or idp.protocol != "saml":
        return RedirectResponse(_frontend("/login?sso_error=not_configured"), status_code=303)
    sso_url = str((idp.config or {}).get("sso_url", "")).strip()
    if not sso_url:
        return RedirectResponse(_frontend("/login?sso_error=not_configured"), status_code=303)
    _, acs_url = _saml_urls(request)
    redirect_url, request_id = saml.build_authn_request(str(request.url_for("saml_metadata")),
                                                        acs_url, sso_url)
    # Sweep stale pending requests, then record this one so the reply can be bound to it.
    await db.execute(delete(SamlAuthnRequest).where(
        SamlAuthnRequest.created_at < datetime.now(timezone.utc) - timedelta(minutes=15)))
    db.add(SamlAuthnRequest(id=request_id, org_id=idp.org_id, acs_url=acs_url))
    await db.commit()
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/saml/acs", name="saml_acs")
async def saml_acs(request: Request, db: AsyncSession = Depends(get_db),
                   SAMLResponse: str = Form(...), RelayState: str | None = Form(None)):
    def fail(reason: str) -> RedirectResponse:
        return RedirectResponse(_frontend(f"/login?sso_error={reason}"), status_code=303)

    try:
        xml_bytes = saml.decode_response(SAMLResponse)
        _, in_response_to = saml.peek_ids(xml_bytes)
    except saml.SamlError:
        return fail("validation_failed")
    if not in_response_to:
        return fail("validation_failed")

    # Bind to a request we issued (authoritative org source) and consume it once.
    pending = (await db.execute(
        select(SamlAuthnRequest).where(SamlAuthnRequest.id == in_response_to))).scalar_one_or_none()
    if pending is None:
        return fail("validation_failed")
    org_id, stored_acs = pending.org_id, pending.acs_url
    await db.delete(pending)
    await db.commit()

    idp = await sso.idp_for_org(db, org_id)
    if idp is None or idp.protocol != "saml":
        return fail("not_configured")
    sp_entity_id = str(request.url_for("saml_metadata"))
    try:
        claims = saml.validate_response(
            xml_bytes, str((idp.config or {}).get("x509_cert", "")),
            sp_entity_id, stored_acs, in_response_to)
    except saml.SamlError:
        return fail("validation_failed")

    user = await sso.match_user(db, org_id, claims.get("email") or "")
    if user is None:
        return fail("no_account")
    token = create_access_token(user.id, user.org_id)
    resp = RedirectResponse(_frontend("/sso/callback"), status_code=303)
    set_session_cookie(resp, token)     # T6: see the OIDC callback
    return resp


# ── admin: per-org IdP configuration ─────────────────────────────────────────────
class IdpConfigIn(BaseModel):
    protocol: str = "oidc"
    enabled: bool = True
    email_domain: str = Field(min_length=1, max_length=255)
    issuer: str = Field(default="", max_length=500)
    client_id: str = Field(default="", max_length=255)
    client_secret: str | None = None          # omitted/sentinel = keep stored
    config: dict = Field(default_factory=dict)


@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db),
                     current: User = Depends(require_org_admin)):
    idp = await sso.idp_for_org(db, current.org_id)
    if idp is None:
        return {"configured": False}
    return {"configured": True, **sso.config_out(idp)}


@router.put("/config")
async def put_config(body: IdpConfigIn, db: AsyncSession = Depends(get_db),
                     current: User = Depends(require_org_admin)):
    if body.protocol not in ("oidc", "saml"):
        raise HTTPException(400, "Protocol must be 'oidc' or 'saml'.")
    domain = body.email_domain.strip().lower()
    cfg = dict(body.config or {})
    if body.protocol == "oidc":
        if not body.issuer.strip() or not body.client_id.strip():
            raise HTTPException(400, "OIDC requires an issuer URL and a client ID.")
    else:  # saml — issuer holds the IdP entityID; SSO URL and signing cert live in config
        if not body.issuer.strip() or not str(cfg.get("sso_url", "")).strip() \
                or not str(cfg.get("x509_cert", "")).strip():
            raise HTTPException(400, "SAML requires the IdP entity ID, an SSO URL and a signing certificate.")
    if await sso.domain_claimed_by_other(db, domain, current.org_id):
        raise HTTPException(409, f"The domain '{domain}' is already configured for another organization.")

    idp = await sso.idp_for_org(db, current.org_id)
    if idp is None:
        idp = OrgIdp(org_id=current.org_id)
        db.add(idp)
    idp.protocol = body.protocol
    idp.enabled = body.enabled
    idp.email_domain = domain
    idp.issuer = body.issuer.strip()
    if body.protocol == "oidc":
        idp.client_id = body.client_id.strip()
        idp.config = cfg
        sso.apply_secret_update(idp, body.client_secret)
    else:
        idp.client_id = ""
        idp.config = {"sso_url": str(cfg["sso_url"]).strip(),
                      "x509_cert": str(cfg["x509_cert"]).strip()}
    await db.commit()
    await db.refresh(idp)
    return {"configured": True, **sso.config_out(idp)}


@router.delete("/config", status_code=204)
async def delete_config(db: AsyncSession = Depends(get_db),
                        current: User = Depends(require_org_admin)):
    idp = await sso.idp_for_org(db, current.org_id)
    if idp is not None:
        await db.delete(idp)
        await db.commit()
