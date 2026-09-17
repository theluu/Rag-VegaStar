"""Xác thực (API key hoặc token phiên đăng nhập), rate limit và middleware bảo mật (ASGI thuần để không ảnh hưởng stream SSE)."""

import hashlib
import hmac
import json
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import Settings
from ..observability import AUTH_EVENTS, RATE_LIMITED

log = logging.getLogger(__name__)

class RateLimiter:
    """Token bucket theo khoá (API key hoặc IP), lưu trong tiến trình.

    Chạy nhiều bản API thì cần chuyển sang Redis (xem SECURITY.md).
    """

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic, max_keys: int = 10_000):
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.clock = clock
        self.max_keys = max_keys
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def check(self, key: str) -> tuple[bool, float]:
        """Trả (được phép, số giây nên chờ)."""
        if self.capacity <= 0:
            return True, 0.0
        now = self.clock()
        tokens, last = self._buckets.pop(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        allowed = tokens >= 1
        if allowed:
            tokens -= 1
        self._buckets[key] = (tokens, now)
        while len(self._buckets) > self.max_keys:
            self._buckets.popitem(last=False)
        return allowed, 0.0 if allowed else (1 - tokens) / self.rate


def key_matches(provided: str | None, valid: list[str]) -> bool:
    if not provided:
        return False
    return any(hmac.compare_digest(provided.encode(), k.encode()) for k in valid)


def _provided_key(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if key:
        return key
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return "ip:" + forwarded.split(",")[0].strip()
    return "ip:" + (request.client.host if request.client else "unknown")


def client_id(request: Request, settings: Settings) -> str:
    """Khoá rate limit: người dùng / API key đã xác thực, nếu không thì theo IP."""
    principal = getattr(request.state, "principal", None)
    return principal or client_ip(request, settings)


def require_auth(request: Request) -> None:
    """Chấp nhận API key (`API_KEYS`) hoặc token phiên từ `POST /auth/login` (`AUTH_USERS`).

    Không cấu hình cả hai thì API mở (chế độ phát triển).
    """
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return
    provided = _provided_key(request)
    if provided:
        keys = settings.api_key_list
        if keys and key_matches(provided, keys):
            request.state.principal = "key:" + hashlib.sha256(provided.encode()).hexdigest()[:16]
            return
        users = settings.auth_user_map
        signer = request.app.state.session_signer
        session = signer.verify(provided) if users else None
        if session is not None and session.username in users:
            request.state.principal = "user:" + session.username
            request.state.session = session
            return
    AUTH_EVENTS.labels("rejected").inc()
    raise HTTPException(
        status_code=401,
        detail="Cần đăng nhập hoặc API key hợp lệ",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _limit(request: Request, limiter_name: str) -> None:
    settings: Settings = request.app.state.settings
    limiter: RateLimiter = getattr(request.app.state, limiter_name)
    allowed, retry_after = limiter.check(client_id(request, settings))
    if not allowed:
        RATE_LIMITED.labels(limiter_name).inc()
        raise HTTPException(
            status_code=429,
            detail="Quá nhiều yêu cầu, vui lòng thử lại sau",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )


def limit_api(request: Request) -> None:
    _limit(request, "api_limiter")


def limit_chat(request: Request) -> None:
    _limit(request, "chat_limiter")


def limit_login(request: Request) -> None:
    """Giới hạn số lần thử đăng nhập theo IP (chống dò mật khẩu)."""
    settings: Settings = request.app.state.settings
    limiter: RateLimiter = request.app.state.login_limiter
    allowed, retry_after = limiter.check(client_ip(request, settings))
    if not allowed:
        RATE_LIMITED.labels("login_limiter").inc()
        raise HTTPException(
            status_code=429,
            detail="Thử đăng nhập quá nhiều lần, vui lòng đợi rồi thử lại",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )


class SecurityMiddleware:
    """Gắn X-Request-ID, header bảo mật và chặn body quá lớn."""

    def __init__(self, app: ASGIApp, max_request_bytes: int):
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        request_id = headers.get(b"x-request-id", b"").decode()[:64] or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        path: str = scope["path"]

        length = headers.get(b"content-length")
        if length and length.isdigit() and int(length) > self.max_request_bytes:
            await self._reject(send, 413, request_id, "Yêu cầu quá lớn")
            return

        is_docs = path.startswith(("/docs", "/redoc"))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
                    (b"cross-origin-resource-policy", b"cross-origin"),
                ]
                if not is_docs:
                    # API chỉ trả dữ liệu, không bao giờ cần chạy script
                    extra.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    async def _reject(send: Send, status: int, request_id: str, detail: str) -> None:
        body = json.dumps({"detail": detail, "request_id": request_id}, ensure_ascii=False).encode()
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"x-request-id", request_id.encode())],
        })
        await send({"type": "http.response.body", "body": body})
