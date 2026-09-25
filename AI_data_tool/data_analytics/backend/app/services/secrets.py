"""At-rest encryption for connection secrets stored in DataSource.config.

Passwords, tokens and API keys used to sit in the config JSON as plaintext. Here they
are encrypted with Fernet (AES-128-CBC + HMAC) before storage and decrypted only at the
point a connection is actually built. Three properties make this safe to switch on over
a live database:

  * Backward compatible. An encrypted value carries a marker prefix; `decrypt_value`
    returns anything without it unchanged, so rows written before this shipped keep
    working and re-encrypt the next time they are saved.
  * Always on, zero config. The key derives from the app `secret_key` when
    `connector_secret_key` is unset, so nothing has to be provisioned to get encryption
    — production pins a dedicated key.
  * Idempotent. `encrypt_value` never double-wraps an already-encrypted value.

The API redacts secret fields (`redact_config`) so ciphertext never leaves the server;
an update that sends the redaction sentinel back means "unchanged", handled by the router.

ENVELOPE ENCRYPTION (enc:v2:, ARCHITECTURE.md stage 0.3)
---------------------------------------------------------
v1 encrypts every secret directly under one key derived from the app secret. That
works, but rotating the key makes every stored secret undecryptable at once, so a
rotation is an outage until every row is re-saved by hand.

v2 gives each secret its OWN random data key and wraps only that data key with the
master. Rotating then means re-wrapping a handful of short data keys
(`rewrap_value`) and never touching the ciphertext. Blast radius shrinks too: one
leaked data key exposes one secret rather than all of them. As a side effect, two
connections sharing a password no longer produce identical ciphertext, so the
stored rows stop revealing that they match.

Both versions coexist deliberately. A live database is full of v1 values and they
keep decrypting forever; new writes are v2, so rows upgrade as they are saved.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings

logger = logging.getLogger(__name__)

_MARKER = "enc:v1:"
_MARKER_V2 = "enc:v2:"
# What the API shows instead of a stored secret, and the sentinel an update sends back
# to mean "leave this secret unchanged". Masked as dots in the UI's password field, so
# its exact text is never seen; a real secret equal to it is vanishingly unlikely.
REDACTED = "__SECRET_UNCHANGED__"


def _master_fernet(master: str | None = None) -> Fernet:
    """The key-encrypting key. Wraps data keys in v2, and encrypts secrets directly
    in v1. `master` overrides the configured secret, which is what makes rotation
    testable and lets a rotation script hold both keys at once."""
    if master is not None:
        digest = hashlib.sha256(("datasource-config-v1:" + master).encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))
    raw = (settings.connector_secret_key or "").strip()
    if raw:
        key = raw.encode()
    else:
        # A stable Fernet key derived from secret_key in a distinct domain, so it is not
        # the JWT-signing key even though it follows the same secret.
        digest = hashlib.sha256(("datasource-config-v1:" + settings.secret_key).encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


# Kept under the original name so nothing that imported it breaks.
_fernet = _master_fernet


def is_encrypted(value) -> bool:
    """True for either scheme. Callers branch on "is this a secret", never on which
    version encrypted it."""
    return isinstance(value, str) and (value.startswith(_MARKER) or value.startswith(_MARKER_V2))


def encrypt_value_v1(value):
    """The original single-key scheme. Retained so the v1 decrypt path stays
    exercised by tests long after new writes stopped producing it."""
    if not isinstance(value, str) or value == "" or is_encrypted(value):
        return value
    return _MARKER + _master_fernet().encrypt(value.encode()).decode()


def encrypt_value(value):
    """Encrypt a string secret with a fresh per-secret data key (v2).

    Passes through non-strings, empties and already-encrypted values unchanged, so
    encrypt is idempotent and never wraps a placeholder — or an existing v1 value —
    as though it were plaintext.
    """
    if not isinstance(value, str) or value == "" or is_encrypted(value):
        return value

    data_key = Fernet.generate_key()
    ciphertext = Fernet(data_key).encrypt(value.encode()).decode()
    wrapped = _master_fernet().encrypt(data_key).decode()
    return f"{_MARKER_V2}{wrapped}:{ciphertext}"


def decrypt_value(value, master: str | None = None):
    """Decrypt a marked value of either version; return anything else (plaintext,
    non-string) unchanged.

    A value that carries a marker but cannot be decrypted raises, because silently
    handing ciphertext back as a password fails far more obscurely later — at
    connect time, against a real database, with an error that names none of this.
    """
    if not is_encrypted(value):
        return value

    try:
        if value.startswith(_MARKER_V2):
            wrapped, _, ciphertext = value[len(_MARKER_V2):].partition(":")
            if not ciphertext:
                raise InvalidToken("malformed envelope")
            data_key = _master_fernet(master).decrypt(wrapped.encode())
            return Fernet(data_key).decrypt(ciphertext.encode()).decode()
        return _master_fernet(master).decrypt(value[len(_MARKER):].encode()).decode()
    except (InvalidToken, ValueError, TypeError) as e:
        raise ValueError("A stored connection secret could not be decrypted "
                         "(the encryption key changed since it was saved)") from e


def rewrap_value(value, *, new_master: str, master: str | None = None):
    """Re-wrap a v2 secret's data key under a new master, leaving the ciphertext
    untouched. This is the whole point of the envelope: rotating the master is a
    cheap operation over short data keys instead of a decrypt-and-re-encrypt pass
    over every secret in the database.

    Refuses a v1 value rather than silently doing nothing — v1 has no separable
    data key, so a caller that quietly skipped it would believe a secret had been
    rotated when it is still sitting under the old master.
    """
    if not isinstance(value, str) or not value.startswith(_MARKER_V2):
        raise ValueError("rewrap_value requires an enc:v2: envelope value")

    wrapped, _, ciphertext = value[len(_MARKER_V2):].partition(":")
    try:
        data_key = _master_fernet(master).decrypt(wrapped.encode())
    except InvalidToken as e:
        raise ValueError("Could not unwrap the data key with the current master") from e

    rewrapped = _master_fernet(new_master).encrypt(data_key).decode()
    return f"{_MARKER_V2}{rewrapped}:{ciphertext}"


def encrypt_config(config: dict, secret_fields) -> dict:
    """A copy of config with the named secret fields encrypted."""
    fields = set(secret_fields)
    return {k: (encrypt_value(v) if k in fields else v) for k, v in (config or {}).items()}


def decrypt_config(config: dict, secret_fields) -> dict:
    """A copy of config with the named secret fields decrypted for use."""
    fields = set(secret_fields)
    return {k: (decrypt_value(v) if k in fields else v) for k, v in (config or {}).items()}


def redact_config(config: dict, secret_fields) -> dict:
    """A copy of config safe to return over the API: every non-empty secret field is
    replaced with the redaction sentinel so ciphertext (or plaintext) never leaves."""
    fields = set(secret_fields)
    return {k: (REDACTED if (k in fields and v) else v) for k, v in (config or {}).items()}


async def migrate_v1_to_v2(session: AsyncSession) -> int:
    """S5 startup task: re-encrypt every `enc:v1:` secret in DataSource.config to
    v2, in place. Idempotent -- a v2 value never matches the v1 marker, so running
    this twice (or on every boot) touches nothing the second time and every count
    it logs afterwards is 0. A value that carries the v1 marker but cannot be
    decrypted (wrong key, truncated row) is left exactly as it was, with a
    warning: silently dropping or blanking a secret this app cannot recover is a
    worse outcome than leaving it in v1 for a human to investigate.

    Returns the number of data sources that had at least one field upgraded.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from ..models.models import DataSource
    from . import connectors

    rows = (await session.execute(select(DataSource))).scalars().all()
    migrated = 0
    for ds in rows:
        cfg = ds.config or {}
        fields = connectors.secret_field_names(ds.type)
        new_cfg = None
        for field in fields:
            value = cfg.get(field)
            if not (isinstance(value, str) and value.startswith(_MARKER)):
                continue   # not a v1 value: plaintext, v2, or absent -- leave it
            try:
                plaintext = decrypt_value(value)
            except ValueError:
                logger.warning(
                    "enc:v1->v2 migration: could not decrypt data source %s field %r "
                    "(left as v1, unmigrated)", ds.id, field,
                )
                continue
            if new_cfg is None:
                new_cfg = dict(cfg)
            new_cfg[field] = encrypt_value(plaintext)
        if new_cfg is not None:
            ds.config = new_cfg
            flag_modified(ds, "config")
            migrated += 1
    if migrated:
        await session.commit()
    logger.info("enc:v1->v2 migration: upgraded %d data source(s)", migrated)
    return migrated
