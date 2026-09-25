"""SAML 2.0 SP-initiated Web SSO, driven against a mocked IdP.

A real self-signed certificate signs real SAML assertions with signxml; the SP verification
path runs for real (signature, conditions, audience, recipient, InResponseTo one-time use).
Includes an XML Signature Wrapping (XSW) case: an unsigned attacker assertion injected beside
the signed one must be ignored, because identity is read only from the verified subtree.
"""
import base64
import uuid
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner, methods

from app.core.security import decode_access_token
from app.models.models import OrgIdp, SamlAuthnRequest

SAMLP = "urn:oasis:names:tc:SAML:2.0:protocol"
SAML = "urn:oasis:names:tc:SAML:2.0:assertion"
SP_ENTITY = "http://test/api/v1/auth/sso/saml/metadata"
ACS = "http://test/api/v1/auth/sso/saml/acs"
IDP_ENTITY = "https://idp.saml.test"
SSO_URL = "https://idp.saml.test/sso"
EMAIL_FMT = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"


def _key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.saml.test")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.TraditionalOpenSSL,
                               serialization.NoEncryption())
    return key_pem, cert.public_bytes(serialization.Encoding.PEM)


_KEY_PEM, _CERT_PEM = _key_and_cert()
_WRONG_KEY_PEM, _WRONG_CERT_PEM = _key_and_cert()      # a different signer, for bad-signature tests


def _iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _assertion(request_id, email, *, audience=SP_ENTITY, recipient=ACS,
               nb_delta=-60, noa_delta=300, issuer=IDP_ENTITY):
    now = datetime.now(timezone.utc)
    aid = "_a" + uuid.uuid4().hex
    nb, noa = _iso(now + timedelta(seconds=nb_delta)), _iso(now + timedelta(seconds=noa_delta))
    xml = (
        f'<saml:Assertion xmlns:saml="{SAML}" ID="{aid}" Version="2.0" IssueInstant="{_iso(now)}">'
        f'<saml:Issuer>{issuer}</saml:Issuer>'
        f'<saml:Subject><saml:NameID Format="{EMAIL_FMT}">{email}</saml:NameID>'
        f'<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData InResponseTo="{request_id}" Recipient="{recipient}" NotOnOrAfter="{noa}"/>'
        f'</saml:SubjectConfirmation></saml:Subject>'
        f'<saml:Conditions NotBefore="{nb}" NotOnOrAfter="{noa}">'
        f'<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>'
        f'</saml:Conditions>'
        f'<saml:AuthnStatement AuthnInstant="{_iso(now)}"><saml:AuthnContext>'
        f'<saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef>'
        f'</saml:AuthnContext></saml:AuthnStatement></saml:Assertion>'
    )
    return etree.fromstring(xml.encode())


def _response_b64(request_id, email, *, key_pem=_KEY_PEM, cert_pem=_CERT_PEM,
                  evil_emails=(), **assertion_kwargs):
    """A base64 SAMLResponse whose assertion is signed IN PLACE within the response (the
    real IdP pattern; the whole tree is serialized once, so the signature survives). Extra
    `evil_emails` add UNSIGNED sibling assertions for the XSW test."""
    resp = etree.Element(f"{{{SAMLP}}}Response", nsmap={"samlp": SAMLP},
                         ID="_r" + uuid.uuid4().hex, Version="2.0",
                         IssueInstant=_iso(datetime.now(timezone.utc)),
                         InResponseTo=request_id, Destination=ACS)
    status = etree.SubElement(resp, f"{{{SAMLP}}}Status")
    etree.SubElement(status, f"{{{SAMLP}}}StatusCode").set(
        "Value", "urn:oasis:names:tc:SAML:2.0:status:Success")
    good = _assertion(request_id, email, **assertion_kwargs)
    resp.append(good)
    signed = XMLSigner(method=methods.enveloped, signature_algorithm="rsa-sha256",
                       digest_algorithm="sha256").sign(good, key=key_pem, cert=cert_pem)
    resp.replace(good, signed)
    for evil in evil_emails:
        resp.append(_assertion(request_id, evil))          # unsigned — must be ignored
    return base64.b64encode(etree.tostring(resp)).decode()


async def _make_saml_idp(db, org_id, *, domain="example.com", cert=None):
    idp = OrgIdp(org_id=org_id, protocol="saml", enabled=True, email_domain=domain,
                 issuer=IDP_ENTITY, client_id="", client_secret="",
                 config={"sso_url": SSO_URL, "x509_cert": (cert or _CERT_PEM).decode()})
    db.add(idp)
    await db.commit()
    return idp


async def _pending(db, request_id, org_id):
    db.add(SamlAuthnRequest(id=request_id, org_id=org_id, acs_url=ACS))
    await db.commit()


async def _post_acs(client, b64):
    return await client.post("/api/v1/auth/sso/saml/acs",
                             data={"SAMLResponse": b64, "RelayState": "x"}, follow_redirects=False)


# ── config + discovery ───────────────────────────────────────────────────────────
async def test_saml_config_put_get_and_discover(client, db_session, two_orgs, auth_headers):
    body = {"protocol": "saml", "enabled": True, "email_domain": "example.com",
            "issuer": IDP_ENTITY, "config": {"sso_url": SSO_URL, "x509_cert": _CERT_PEM.decode()}}
    r = await client.put("/api/v1/auth/sso/config", json=body, headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["protocol"] == "saml"
    assert r.json()["config"]["sso_url"] == SSO_URL and "BEGIN CERTIFICATE" in r.json()["config"]["x509_cert"]

    d = await client.post("/api/v1/auth/sso/discover", json={"email": "user@example.com"})
    assert d.json() == {"sso": True, "protocol": "saml"}


async def test_saml_config_rejects_missing_fields(client, auth_headers):
    r = await client.put("/api/v1/auth/sso/config",
                         json={"protocol": "saml", "email_domain": "example.com", "issuer": IDP_ENTITY},
                         headers=auth_headers["a"])
    assert r.status_code == 400


# ── login initiation ─────────────────────────────────────────────────────────────
async def test_saml_login_redirects_and_records_request(client, db_session, two_orgs):
    await _make_saml_idp(db_session, two_orgs["a"]["org"].id)
    r = await client.get("/api/v1/auth/sso/saml/login",
                         params={"email": "admin-a@example.com"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith(SSO_URL) and "SAMLRequest=" in r.headers["location"]
    from sqlalchemy import select
    rows = (await db_session.execute(select(SamlAuthnRequest))).scalars().all()
    assert len(rows) == 1 and rows[0].org_id == two_orgs["a"]["org"].id


# ── ACS: the security-critical path ──────────────────────────────────────────────
async def test_saml_acs_happy_path_mints_token(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "admin-a@example.com")
    r = await _post_acs(client, b64)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert "/sso/callback#token=" in loc
    payload = decode_access_token(loc.split("#token=", 1)[1])
    assert payload is not None and int(payload["sub"]) == two_orgs["a"]["user"].id


async def test_saml_acs_bad_signature_rejected(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)             # configured with _CERT_PEM
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    # Signed by the WRONG key → signature does not match the configured certificate.
    b64 = _response_b64(rid, "admin-a@example.com", key_pem=_WRONG_KEY_PEM, cert_pem=_WRONG_CERT_PEM)
    r = await _post_acs(client, b64)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_saml_acs_expired_assertion_rejected(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "admin-a@example.com", noa_delta=-300)
    r = await _post_acs(client, b64)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_saml_acs_wrong_audience_rejected(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "admin-a@example.com", audience="urn:someone-else")
    r = await _post_acs(client, b64)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_saml_acs_wrong_recipient_rejected(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "admin-a@example.com", recipient="https://evil.test/acs")
    r = await _post_acs(client, b64)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_saml_acs_unknown_inresponseto_rejected(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex                          # never recorded as pending
    b64 = _response_b64(rid, "admin-a@example.com")
    r = await _post_acs(client, b64)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_saml_acs_response_is_one_time_use(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "admin-a@example.com")
    first = await _post_acs(client, b64)
    assert "/sso/callback#token=" in first.headers["location"]
    replay = await _post_acs(client, b64)                 # request already consumed
    assert "sso_error=validation_failed" in replay.headers["location"]


async def test_saml_acs_unknown_email_refused(client, db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "stranger@example.com")
    r = await _post_acs(client, b64)
    assert r.status_code == 303 and "sso_error=no_account" in r.headers["location"]


async def test_saml_acs_ignores_xsw_injected_unsigned_assertion(client, db_session, two_orgs):
    """XSW: an unsigned attacker assertion placed beside the signed one must be ignored —
    identity is read only from the signxml-verified subtree."""
    org_id = two_orgs["a"]["org"].id
    await _make_saml_idp(db_session, org_id)
    rid = "_" + uuid.uuid4().hex
    await _pending(db_session, rid, org_id)
    b64 = _response_b64(rid, "admin-a@example.com", evil_emails=("attacker@example.com",))
    r = await _post_acs(client, b64)
    # The signed (real) identity wins; the attacker email is never trusted.
    assert "/sso/callback#token=" in r.headers["location"]
    payload = decode_access_token(r.headers["location"].split("#token=", 1)[1])
    assert int(payload["sub"]) == two_orgs["a"]["user"].id
