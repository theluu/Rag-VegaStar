from fastapi import Request

import asyncpg

from ..chat.service import ChatService
from ..config import Settings


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


def get_service(request: Request) -> ChatService:
    return request.app.state.service


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
