"""Envelope encryption for connection secrets (ARCHITECTURE.md stage 0.3).

The existing scheme encrypts every secret directly under one key derived from
the app secret. It works, but it has one operationally nasty property: rotating
the key makes every stored secret undecryptable at once, and `decrypt_value`
raises rather than guessing — so a rotation is an outage until every row is
re-saved by hand.

Envelope encryption fixes exactly that. Each secret gets its own random data
key; the data key is what gets wrapped by the master key. Rotating the master
then means re-wrapping a few short data keys, never touching the ciphertext.
Blast radius also shrinks: one leaked data key exposes one secret, not all of
them.

This ships as `enc:v2:` alongside the existing `enc:v1:`. v1 values keep
decrypting forever — a live database full of them must not break — and get
upgraded to v2 the next time they are written.
"""
import pytest

from app.services import secrets


class TestRoundTrip:
    def test_encrypts_and_decrypts(self):
        token = secrets.encrypt_value("hunter2")
        assert secrets.decrypt_value(token) == "hunter2"

    def test_ciphertext_never_contains_the_plaintext(self):
        token = secrets.encrypt_value("hunter2")
        assert "hunter2" not in token

    def test_new_writes_use_the_envelope_scheme(self):
        assert secrets.encrypt_value("hunter2").startswith("enc:v2:")

    def test_each_secret_gets_its_own_data_key(self):
        """Two identical plaintexts must not produce identical ciphertext, or an
        attacker could tell which connections share a password."""
        a = secrets.encrypt_value("same-password")
        b = secrets.encrypt_value("same-password")
        assert a != b
        assert secrets.decrypt_value(a) == secrets.decrypt_value(b) == "same-password"


class TestBackwardCompatibility:
    """A live database is full of v1 values. They must keep working."""

    def test_v1_values_still_decrypt(self):
        legacy = secrets.encrypt_value_v1("legacy-password")
        assert legacy.startswith("enc:v1:")
        assert secrets.decrypt_value(legacy) == "legacy-password"

    def test_plaintext_passes_through_unchanged(self):
        """Rows written before any encryption shipped."""
        assert secrets.decrypt_value("bare-plaintext") == "bare-plaintext"

    def test_encrypt_is_idempotent_across_both_versions(self):
        v2 = secrets.encrypt_value("x")
        assert secrets.encrypt_value(v2) == v2
        v1 = secrets.encrypt_value_v1("y")
        assert secrets.encrypt_value(v1) == v1, "must not re-wrap a v1 value as v2 data"

    def test_is_encrypted_recognises_both_markers(self):
        assert secrets.is_encrypted(secrets.encrypt_value("x")) is True
        assert secrets.is_encrypted(secrets.encrypt_value_v1("x")) is True
        assert secrets.is_encrypted("plain") is False


class TestRotation:
    """The reason envelope encryption is worth the extra indirection."""

    def test_rewrap_changes_the_master_without_touching_the_ciphertext(self):
        token = secrets.encrypt_value("hunter2")
        rotated = secrets.rewrap_value(token, new_master="a-brand-new-master-secret")

        assert rotated != token
        assert secrets.decrypt_value(rotated, master="a-brand-new-master-secret") == "hunter2"

    def test_the_old_master_no_longer_opens_a_rotated_secret(self):
        token = secrets.encrypt_value("hunter2")
        rotated = secrets.rewrap_value(token, new_master="a-brand-new-master-secret")
        with pytest.raises(ValueError):
            secrets.decrypt_value(rotated)

    def test_rewrap_refuses_a_v1_value(self):
        """v1 has no separable data key, so there is nothing to re-wrap. Failing
        loudly is better than silently leaving a secret on the old master."""
        legacy = secrets.encrypt_value_v1("x")
        with pytest.raises(ValueError):
            secrets.rewrap_value(legacy, new_master="new")


class TestFailureModes:
    def test_a_corrupt_token_raises_rather_than_returning_ciphertext(self):
        """Handing ciphertext back as a password would fail far more obscurely at
        connect time, against a real database, with a useless error message."""
        with pytest.raises(ValueError):
            secrets.decrypt_value("enc:v2:not-valid-at-all")

    def test_empty_and_non_string_values_pass_through(self):
        assert secrets.encrypt_value("") == ""
        assert secrets.encrypt_value(None) is None
        assert secrets.encrypt_value(42) == 42


class TestConfigHelpers:
    """The existing public API must behave identically on top of v2."""

    def test_encrypt_config_only_touches_named_fields(self):
        cfg = {"host": "db.internal", "password": "hunter2"}
        out = secrets.encrypt_config(cfg, ["password"])
        assert out["host"] == "db.internal"
        assert out["password"].startswith("enc:v2:")

    def test_decrypt_config_round_trips(self):
        cfg = {"host": "db.internal", "password": "hunter2"}
        enc = secrets.encrypt_config(cfg, ["password"])
        assert secrets.decrypt_config(enc, ["password"]) == cfg

    def test_redact_config_never_leaks_ciphertext(self):
        cfg = secrets.encrypt_config({"password": "hunter2"}, ["password"])
        out = secrets.redact_config(cfg, ["password"])
        assert out["password"] == secrets.REDACTED
        assert "enc:v2:" not in str(out)
