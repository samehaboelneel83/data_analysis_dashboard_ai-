"""At-rest encryption of connection secrets (services/secrets.py)."""
from app.services import connectors, secrets
from app.services import secrets


def test_encrypt_then_decrypt_round_trips():
    enc = secrets.encrypt_value("hunter2")
    assert secrets.is_encrypted(enc) and enc != "hunter2"
    assert secrets.decrypt_value(enc) == "hunter2"


def test_encrypt_is_idempotent_and_skips_empties():
    once = secrets.encrypt_value("pw")
    assert secrets.encrypt_value(once) == once      # never double-wraps
    assert secrets.encrypt_value("") == ""          # empty stays empty
    assert secrets.encrypt_value(None) is None


def test_decrypt_passes_plaintext_through_for_backward_compatibility():
    # A value written before encryption shipped has no marker and is returned as-is.
    assert secrets.decrypt_value("legacy-plaintext") == "legacy-plaintext"


def test_config_helpers_touch_only_secret_fields():
    cfg = {"host": "h", "username": "u", "password": "p"}
    enc = secrets.encrypt_config(cfg, {"password"})
    assert enc["host"] == "h" and enc["username"] == "u"
    assert secrets.is_encrypted(enc["password"])
    assert secrets.decrypt_config(enc, {"password"})["password"] == "p"
    red = secrets.redact_config(enc, {"password"})
    assert red["password"] == secrets.REDACTED and red["host"] == "h"


def test_build_url_decrypts_the_stored_password():
    enc = secrets.encrypt_config(
        {"type": "postgresql", "host": "localhost", "database": "d", "username": "u", "password": "s3cretpw"},
        connectors.secret_field_names("postgresql"))
    url = connectors.build_url(enc)
    assert "s3cretpw" in url and not secrets.is_encrypted(url) and "enc:v" not in url   # the live URL carries the plaintext


def test_build_url_still_works_with_a_legacy_plaintext_password():
    url = connectors.build_url(
        {"type": "postgresql", "host": "localhost", "database": "d", "username": "u", "password": "plainpw"})
    assert "plainpw" in url


def test_secret_field_names_come_from_the_connector_spec():
    assert connectors.secret_field_names("postgresql") == {"password"}
    assert connectors.secret_field_names("api") == {"token", "api_key", "password"}
