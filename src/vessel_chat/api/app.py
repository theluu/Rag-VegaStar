"""Ứng dụng FastAPI.

    uvicorn vessel_chat.api.app:app --port 8000
"""

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..chat.service import ChatService, build_system_prompt
from ..chat.verifier import SecondOpinion
from ..config import Settings, get_settings
from ..db import create_pool
from ..guardrails.input import Moderator
from ..llm.client import (
    Embedder,
    FallbackLLM,
    LLMClient,
    LocalHashEmbedder,
    NullLLM,
    OpenAIEmbedder,
    OpenAILLM,
    OpenAIModerator,
)
from ..observability import MetricsMiddleware, configure_logging
from ..rag.store import ingest_directory
from . import routes_auth, routes_chat, routes_conversations, routes_map, routes_stats
from .auth import SessionSigner
from .security import RateLimiter, SecurityMiddleware, limit_api, require_auth

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    embedder: Embedder | None = None,
    moderator: Moderator | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.require("database_url")
        pool = await create_pool(settings)
        tool_pool = await create_pool(settings, readonly=True)
        chat_llm = llm or _build_llm(settings)
        chat_embedder = embedder or (
            OpenAIEmbedder(settings) if settings.openai_api_key else LocalHashEmbedder(settings.embedding_dim)
        )
        # Moderation thật chỉ bật khi dùng LLM thật (test truyền LLM giả và moderator giả nếu cần)
        chat_moderator = moderator
        if (chat_moderator is None and llm is None and settings.guardrail_moderation_enabled
                and settings.openai_api_key):
            chat_moderator = OpenAIModerator(settings)
        verifier = SecondOpinion(settings) if llm is None else None
        if settings.rag_auto_ingest and Path(settings.knowledge_dir).is_dir():
            try:
                async with pool.acquire() as conn:
                    await ingest_directory(conn, chat_embedder, settings.knowledge_dir, settings.rag_chunk_max_chars)
            except Exception:  # noqa: BLE001
                log.exception("Không đồng bộ được kho tri thức; tiếp tục chạy với dữ liệu hiện có")
        system_prompt = await build_system_prompt(pool)
        service = ChatService(pool, chat_llm, chat_embedder, settings, system_prompt,
                              tool_pool=tool_pool, moderator=chat_moderator, verifier=verifier)
        app.state.pool = pool
        app.state.tool_pool = tool_pool
        app.state.service = service
        app.state.started_at = datetime.now(UTC)
        log.info(
            "API sẵn sàng",
            extra={"fields": {
                "model": settings.llm_model if settings.llm_enabled else "(không có AI)",
                "fallback_llm": settings.fallback_llm_model or None,
                "verifier_llm": settings.verifier_llm_model or None,
                "memory_window_turns": settings.memory_window_turns,
                "api_keys": bool(settings.api_key_list),
                "login_users": len(settings.auth_user_map),
            }},
        )
        try:
            yield
        finally:
            await service.close()
            await tool_pool.close()
            await pool.close()

    app = FastAPI(
        title="Vessel Chat API",
        version="0.2.0",
        description=(
            "Chatbot tra cứu tàu biển: chat streaming (SSE), bộ nhớ dài hạn, kho tri thức (RAG), "
            "guardrails, dữ liệu bản đồ GeoJSON. Khi bật `API_KEYS`, gửi `X-API-Key` hoặc `Authorization: Bearer`."
        ),
        lifespan=lifespan,
        root_path=settings.root_path,
    )
    # Trạng thái không phụ thuộc DB gắn ngay để dependency dùng được cả khi test
    app.state.settings = settings
    app.state.api_limiter = RateLimiter(settings.rate_limit_api_per_minute)
    app.state.chat_limiter = RateLimiter(settings.rate_limit_chat_per_minute)
    app.state.login_limiter = RateLimiter(settings.rate_limit_login_per_minute)
    session_secret = settings.session_secret
    if not session_secret:
        session_secret = secrets.token_urlsafe(32)
        if settings.auth_user_map:
            log.warning("SESSION_SECRET trống: dùng khoá ngẫu nhiên, mọi phiên đăng nhập mất khi khởi động lại")
    app.state.session_signer = SessionSigner(session_secret, int(settings.session_ttl_hours * 3600))

    # Thứ tự: middleware thêm sau nằm ngoài cùng
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )
    app.add_middleware(SecurityMiddleware, max_request_bytes=settings.max_request_bytes)
    if settings.metrics_enabled:
        app.add_middleware(MetricsMiddleware)

    protected = [Depends(require_auth), Depends(limit_api)]
    app.include_router(routes_auth.router)
    app.include_router(routes_conversations.router, dependencies=protected)
    app.include_router(routes_chat.router, dependencies=[Depends(require_auth)])
    app.include_router(routes_map.router, dependencies=protected)
    if settings.stats_enabled:
        app.include_router(routes_stats.router, dependencies=protected)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", None) or request.scope.get("state", {}).get("request_id")
        log.exception("Lỗi không xử lý", extra={"fields": {"request_id": request_id, "path": request.url.path}})
        # Không lộ chi tiết nội bộ ra ngoài
        return JSONResponse(status_code=500, content={"detail": "Lỗi hệ thống", "request_id": request_id})

    @app.get("/health", tags=["system"])
    async def health(request: Request):
        async with request.app.state.pool.acquire() as conn:
            vessels = await conn.fetchval("SELECT count(*) FROM vessels")
            kb_chunks = await conn.fetchval("SELECT count(*) FROM kb_chunks")
        return {
            "status": "ok",
            "vessels": vessels,
            "knowledge_chunks": kb_chunks,
            "model": settings.llm_model if settings.llm_enabled else None,
            "llm": {
                "available": settings.llm_enabled,
                "fallback_configured": settings.fallback_llm_enabled,
                "verifier_configured": settings.verifier_enabled,
            },
            "memory_window_turns": settings.memory_window_turns,
            "auth_required": settings.auth_enabled,
            "login_enabled": bool(settings.auth_user_map),
        }

    if settings.metrics_enabled:

        @app.get("/metrics", tags=["system"], include_in_schema=False)
        async def metrics():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def _build_llm(settings: Settings) -> LLMClient:
    """LLM chính + bản dự phòng (nếu có). Không cấu hình gì → chế độ không có AI."""
    providers: list[LLMClient] = []
    if settings.openai_api_key and settings.llm_model:
        providers.append(OpenAILLM(settings))
    if settings.fallback_llm_enabled:
        providers.append(OpenAILLM(
            settings,
            api_key=settings.fallback_llm_api_key,
            base_url=settings.fallback_llm_base_url,
            model=settings.fallback_llm_model,
            name="fallback",
        ))
    if not providers:
        log.warning("Chưa cấu hình LLM: chạy ở chế độ không có AI (chỉ các API dữ liệu hoạt động)")
        return NullLLM()
    return providers[0] if len(providers) == 1 else FallbackLLM(providers)


def _make_default_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_json)
    return create_app(settings)


app = _make_default_app()
