"""Đăng nhập giao diện: đổi tên đăng nhập + mật khẩu lấy token phiên."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import Settings
from ..observability import AUTH_EVENTS, log_event
from .auth import check_credentials
from .deps import get_app_settings
from .security import client_ip, limit_login, require_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SessionOut(BaseModel):
    username: str
    expires_at: datetime


class LoginResponse(SessionOut):
    token: str
    token_type: str = "Bearer"


def _ts(value: int) -> datetime:
    return datetime.fromtimestamp(value, UTC)


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(limit_login)])
async def login(body: LoginRequest, request: Request, settings: Settings = Depends(get_app_settings)):
    users = settings.auth_user_map
    if not users:
        raise HTTPException(status_code=404, detail="Máy chủ không bật đăng nhập (AUTH_USERS trống)")
    username = body.username.strip()
    if not check_credentials(users, username, body.password):
        AUTH_EVENTS.labels("login_failed").inc()
        log_event(log, "login_failed", username=username[:64], client=client_ip(request, settings))
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
    token, session = request.app.state.session_signer.issue(username)
    AUTH_EVENTS.labels("login_ok").inc()
    log_event(log, "login_ok", username=username, client=client_ip(request, settings))
    return LoginResponse(token=token, username=session.username, expires_at=_ts(session.expires_at))


@router.get("/me", response_model=SessionOut, dependencies=[Depends(require_auth)])
async def me(request: Request):
    session = getattr(request.state, "session", None)
    if session is None:
        # Xác thực bằng API key: không có phiên người dùng
        raise HTTPException(status_code=404, detail="Yêu cầu dùng API key, không có phiên đăng nhập")
    return SessionOut(username=session.username, expires_at=_ts(session.expires_at))
