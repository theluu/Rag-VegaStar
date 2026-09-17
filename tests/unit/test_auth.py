"""Băm mật khẩu và token phiên."""

import pytest

from vessel_chat.api.auth import SessionSigner, check_credentials, hash_password, verify_password
from vessel_chat.config import Settings


def test_password_hash_roundtrip_and_plaintext():
    stored = hash_password("s3cret", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", "pbkdf2_sha256$broken")
    assert verify_password("demo", "demo") and not verify_password("demo", "Demo")


def test_check_credentials_unknown_user():
    users = {"demo": "demo"}
    assert check_credentials(users, "demo", "demo")
    assert not check_credentials(users, "demo", "nope")
    assert not check_credentials(users, "ghost", "demo")


def test_session_token_signing_and_expiry():
    now = [1_000_000.0]
    signer = SessionSigner("secret-a", ttl_seconds=60, clock=lambda: now[0])
    token, session = signer.issue("demo")
    assert token.startswith("v1.") and session.expires_at == 1_000_060
    assert signer.verify(token).username == "demo"

    # sai khoá, bị sửa, sai định dạng
    assert SessionSigner("secret-b", 60, clock=lambda: now[0]).verify(token) is None
    head, payload, sig = token.split(".")
    assert signer.verify(f"{head}.{payload}x.{sig}") is None
    assert signer.verify(f"{head}.{payload}.{sig[:-2]}AA") is None
    assert signer.verify("not-a-token") is None and signer.verify("v2.a.b") is None

    now[0] += 61
    assert signer.verify(token) is None


def test_session_signer_requires_secret():
    with pytest.raises(ValueError):
        SessionSigner("", 60)


def test_auth_user_map_parsing():
    s = Settings(auth_users=" demo:demo , admin:pbkdf2_sha256$1$a$b ,broken, :x, y: ", api_keys="")
    assert s.auth_user_map == {"demo": "demo", "admin": "pbkdf2_sha256$1$a$b"}
    assert s.auth_enabled
    assert not Settings(auth_users="", api_keys="").auth_enabled
    assert Settings(auth_users="", api_keys="k").auth_enabled
