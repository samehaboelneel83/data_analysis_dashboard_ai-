from datetime import timedelta
from freezegun import freeze_time
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_hash_password_does_not_return_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert len(hashed) > 20


def test_verify_password_accepts_the_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_the_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hashing_the_same_password_twice_produces_different_hashes():
    """bcrypt salts each hash — this guards against someone 'optimizing' by
    caching or reusing a hash, which would defeat the salt's purpose."""
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a) is True
    assert verify_password("same password", b) is True


def test_create_and_decode_access_token_round_trips():
    token = create_access_token(user_id=42, org_id=7)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["org_id"] == 7


def test_decode_access_token_rejects_garbage():
    assert decode_access_token("not.a.valid.jwt") is None


def test_decode_access_token_rejects_a_token_signed_with_a_different_key():
    from jose import jwt as _jwt
    bad_token = _jwt.encode({"sub": "1", "org_id": 1}, "wrong-secret-key", algorithm="HS256")
    assert decode_access_token(bad_token) is None


def test_decode_access_token_rejects_an_expired_token():
    with freeze_time("2026-01-01"):
        token = create_access_token(user_id=1, org_id=1)
    with freeze_time("2026-01-01") as frozen:
        frozen.move_to("2026-01-09")   # ACCESS_TOKEN_EXPIRE_DAYS is 7
        assert decode_access_token(token) is None
