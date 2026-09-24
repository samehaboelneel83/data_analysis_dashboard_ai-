"""SAML 2.0 Web Browser SSO (SP-initiated), per organization — Phase 2 of SSO.

datalytics is the Service Provider. The flow:

  1. /auth/sso/saml/login  → build an AuthnRequest, record its ID (models.SamlAuthnRequest)
     so the reply can be bound to it, deflate+base64 it (HTTP-Redirect binding) and send the
     browser to the IdP.
  2. /auth/sso/saml/acs    → the IdP POSTs a signed SAMLResponse. We verify the XML signature
     against the org's configured IdP certificate with signxml, and — critically — read the
     subject and attributes ONLY from the element signxml returns as verified. That defeats
     XML Signature Wrapping (XSW): an attacker who injects an unsigned assertion cannot get us
     to read it, because we never touch the raw parse for identity, only the verified subtree.

Plus the SAML condition checks: NotBefore/NotOnOrAfter (with small skew), AudienceRestriction
== our SP entityID, SubjectConfirmationData Recipient == our ACS URL, and InResponseTo bound
to a pending request we issued (one-time use → the same response can't be replayed).

SAML config is stored on the shared OrgIdp row (protocol='saml'): `issuer` holds the IdP
entityID and `config` holds {sso_url, x509_cert}. The certificate is public, so it is stored
in the clear (unlike the OIDC client secret).
"""
from __future__ import annotations

import base64
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from lxml import etree
from signxml import XMLVerifier

SAML_ASSERTION = "urn:oasis:names:tc:SAML:2.0:assertion"
SAML_PROTOCOL = "urn:oasis:names:tc:SAML:2.0:protocol"
NS = {"saml": SAML_ASSERTION, "samlp": SAML_PROTOCOL}
_SKEW = timedelta(seconds=120)
_NAMEID_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
# Attribute names IdPs commonly use for the email address.
_EMAIL_ATTRS = {"email", "mail", "emailaddress",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"}


class SamlError(Exception):
    """A recoverable SAML failure surfaced to the user as a generic login error."""


# ── certificate + XML parsing helpers ────────────────────────────────────────────
def wrap_pem(cert: str) -> str:
    """Normalize an IdP certificate to PEM. IdP metadata often gives bare base64 (the
    <ds:X509Certificate> body); wrap it with PEM headers and 64-col lines if needed."""
    c = (cert or "").strip()
    if "BEGIN CERTIFICATE" in c:
        return c
    body = "".join(c.split())
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN CERTIFICATE-----\n{lines}\n-----END CERTIFICATE-----\n"


def _parse_hardened(xml_bytes: bytes):
    """Parse untrusted XML with entity resolution and network access OFF (XXE defense)."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True,
                             load_dtd=False, dtd_validation=False, huge_tree=False)
    try:
        return etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as e:
        raise SamlError("The identity provider returned malformed XML") from e


def decode_response(saml_response_b64: str) -> bytes:
    try:
        return base64.b64decode(saml_response_b64)
    except Exception as e:                                   # noqa: BLE001
        raise SamlError("The SAML response could not be decoded") from e


def peek_ids(xml_bytes: bytes) -> tuple[str | None, str | None]:
    """Read (Issuer, InResponseTo) from the UNVERIFIED response, only to look up which org's
    certificate to verify with. Trust nothing here — the signature check comes next."""
    doc = _parse_hardened(xml_bytes)
    issuer = doc.findtext("saml:Issuer", namespaces=NS) or doc.findtext(".//saml:Issuer", namespaces=NS)
    in_response_to = doc.get("InResponseTo")
    return (issuer.strip() if issuer else None), in_response_to


# ── AuthnRequest (SP → IdP) ──────────────────────────────────────────────────────
def build_authn_request(sp_entity_id: str, acs_url: str, idp_sso_url: str) -> tuple[str, str]:
    """Return (redirect_url, request_id) for the HTTP-Redirect binding. The request is not
    SP-signed (v1); IdPs that require signed requests are a later addition."""
    request_id = "_" + uuid.uuid4().hex
    issued = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{SAML_PROTOCOL}" xmlns:saml="{SAML_ASSERTION}" '
        f'ID="{request_id}" Version="2.0" IssueInstant="{issued}" '
        f'Destination="{idp_sso_url}" AssertionConsumerServiceURL="{acs_url}" '
        f'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
        f'<saml:Issuer>{sp_entity_id}</saml:Issuer>'
        f'<samlp:NameIDPolicy Format="{_NAMEID_EMAIL}" AllowCreate="true"/>'
        f'</samlp:AuthnRequest>'
    ).encode()
    # HTTP-Redirect binding: raw DEFLATE (strip zlib's 2-byte header and 4-byte checksum).
    deflated = zlib.compress(xml)[2:-4]
    saml_request = quote(base64.b64encode(deflated).decode())
    sep = "&" if "?" in idp_sso_url else "?"
    return f"{idp_sso_url}{sep}SAMLRequest={saml_request}", request_id


# ── SAMLResponse validation (IdP → SP) ───────────────────────────────────────────
def _parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _verified_assertion(xml_bytes: bytes, idp_cert_pem: str):
    """Verify the signature and return the single Assertion inside the VERIFIED subtree.
    Reading identity only from here is the XSW defense."""
    try:
        result = XMLVerifier().verify(xml_bytes, x509_cert=idp_cert_pem)
    except Exception as e:                                   # noqa: BLE001 (signxml raises many)
        raise SamlError("The SAML response signature is invalid") from e
    signed = result.signed_xml
    if signed is None:
        raise SamlError("The SAML response was not signed")
    local = etree.QName(signed).localname
    if local == "Assertion":
        return signed
    assertions = signed.findall(".//saml:Assertion", NS)
    if len(assertions) != 1:
        raise SamlError("The SAML response did not contain exactly one signed assertion")
    return assertions[0]


def _check_conditions(assertion, sp_entity_id: str, acs_url: str, expected_request_id: str) -> None:
    now = datetime.now(timezone.utc)
    cond = assertion.find("saml:Conditions", NS)
    if cond is not None:
        nb, noa = cond.get("NotBefore"), cond.get("NotOnOrAfter")
        if nb and now + _SKEW < _parse_instant(nb):
            raise SamlError("The SAML assertion is not yet valid")
        if noa and now - _SKEW >= _parse_instant(noa):
            raise SamlError("The SAML assertion has expired")
        audiences = [a.text for a in cond.findall(".//saml:Audience", NS)]
        if audiences and sp_entity_id not in audiences:
            raise SamlError("The SAML assertion was issued for a different audience")

    # SubjectConfirmationData: bind to our ACS and to the request we actually issued.
    scd = assertion.find(".//saml:SubjectConfirmationData", NS)
    if scd is None:
        raise SamlError("The SAML assertion has no subject confirmation")
    if scd.get("Recipient") and scd.get("Recipient") != acs_url:
        raise SamlError("The SAML assertion was addressed to a different recipient")
    if scd.get("NotOnOrAfter") and now - _SKEW >= _parse_instant(scd.get("NotOnOrAfter")):
        raise SamlError("The SAML assertion confirmation has expired")
    if scd.get("InResponseTo") != expected_request_id:
        raise SamlError("The SAML assertion does not match the login request")


def _extract_email(assertion) -> str:
    name_id = assertion.find(".//saml:Subject/saml:NameID", NS)
    if name_id is not None:
        fmt, text = name_id.get("Format"), (name_id.text or "").strip()
        if text and (fmt == _NAMEID_EMAIL or "@" in text):
            return text
    for attr in assertion.findall(".//saml:Attribute", NS):
        name = (attr.get("Name") or attr.get("FriendlyName") or "").strip().lower()
        if name in _EMAIL_ATTRS:
            val = attr.findtext("saml:AttributeValue", namespaces=NS)
            if val and val.strip():
                return val.strip()
    raise SamlError("The SAML assertion did not include an email address")


def validate_response(xml_bytes: bytes, idp_cert_pem: str, sp_entity_id: str,
                      acs_url: str, expected_request_id: str) -> dict:
    """Verify signature + conditions and return {'email': …}. Identity is read only from the
    signxml-verified assertion subtree."""
    assertion = _verified_assertion(xml_bytes, wrap_pem(idp_cert_pem))
    _check_conditions(assertion, sp_entity_id, acs_url, expected_request_id)
    return {"email": _extract_email(assertion)}
