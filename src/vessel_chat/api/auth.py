"""Đăng nhập bằng tài khoản cấu hình sẵn và token phiên ký HMAC (không cần bảng người dùng).

- Tài khoản: `AUTH_USERS=tên:mật_khẩu,...`. Mật khẩu có thể là chuỗi băm
  `pbkdf2_sha256$<vòng lặp>$<salt>$<hash>` sinh bằng `scripts/hash_password.py`.
- Token: `v1.<payload base64url>.<chữ ký base64url>`, payload gồm tên người dùng, thời điểm cấp và hết hạn.
  Token không lưu phía server; đổi `SESSION_SECRET` sẽ vô hiệu hoá mọi phiên.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
TOKEN_VERSION = "v1"

# Băm giả để thời gian xử lý tên đăng nhập không tồn tại giống tên có thật
_DUMMY_HASH = None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, *, salt: str | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"{PBKDF2_PREFIX}${iterations}${salt}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """So khớp mật khẩu với giá trị cấu hình (chuỗi băm PBKDF2 hoặc mật khẩu thường)."""
    if stored.startswith(PBKDF2_PREFIX + "$"):
        try:
            _, iterations, salt, expected = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        except ValueError:
            return False
        return hmac.compare_digest(_b64(digest), expected)
    return hmac.compare_digest(password.encode(), stored.encode())


def check_credentials(users: dict[str, str], username: str, password: str) -> bool:
    global _DUMMY_HASH
    stored = users.get(username)
    if stored is None:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password(secrets.token_hex(8))
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, stored)


@dataclass(frozen=True)
class Session:
    username: str
    issued_at: int
    expires_at: int


class SessionSigner:
    def __init__(self, secret: str, ttl_seconds: int, clock=time.time):
        if not secret:
            raise ValueError("Cần SESSION_SECRET để ký token phiên")
        self._key = hashlib.sha256(("vessel-chat-session:" + secret).encode()).digest()
        self.ttl = ttl_seconds
        self.clock = clock

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._key, f"{TOKEN_VERSION}.{payload}".encode(), hashlib.sha256).digest())

    def issue(self, username: str) -> tuple[str, Session]:
        now = int(self.clock())
        session = Session(username=username, issued_at=now, expires_at=now + self.ttl)
        payload = _b64(json.dumps({"u": username, "iat": now, "exp": session.expires_at}, separators=(",", ":")).encode())
        return f"{TOKEN_VERSION}.{payload}.{self._sign(payload)}", session

    def verify(self, token: str) -> Session | None:
        try:
            version, payload, signature = token.split(".")
        except ValueError:
            return None
        if version != TOKEN_VERSION or not hmac.compare_digest(signature, self._sign(payload)):
            return None
        try:
            data = json.loads(_unb64(payload))
            session = Session(username=str(data["u"]), issued_at=int(data["iat"]), expires_at=int(data["exp"]))
        except (ValueError, KeyError, TypeError):
            return None
        if session.expires_at <= self.clock():
            return None
        return session
