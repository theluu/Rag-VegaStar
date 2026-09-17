"""Ứng dụng FastAPI.

    uvicorn vessel_chat.api.app:app --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ..chat.service import ChatService, build_system_prompt
from ..config import Settings, get_settings
from ..db import create_pool
from ..llm.client import Embedder, LLMClient, OpenAIEmbedder, OpenAILLM
from . import routes_chat, routes_conversations, routes_map

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, llm: LLMClient | None = None, embedder: Embedder | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.require("database_url")
        pool = await create_pool(settings)
        chat_llm = llm or OpenAILLM(settings)
        chat_embedder = embedder or OpenAIEmbedder(settings)
        system_prompt = await build_system_prompt(pool)
        service = ChatService(pool, chat_llm, chat_embedder, settings, system_prompt)
        app.state.settings = settings
        app.state.pool = pool
        app.state.service = service
        log.info("API sẵn sàng (model=%s, window=%s lượt)", settings.llm_model, settings.memory_window_turns)
        try:
            yield
        finally:
            await service.close()
            await pool.close()

    app = FastAPI(
        title="Vessel Chat API",
        version="0.1.0",
        description="Chatbot tra cứu tàu biển: chat streaming (SSE), bộ nhớ dài hạn, dữ liệu bản đồ GeoJSON.",
        lifespan=lifespan,
    )
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(routes_conversations.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_map.router)

    @app.get("/health", tags=["system"])
    async def health(request: Request):
        async with request.app.state.pool.acquire() as conn:
            vessels = await conn.fetchval("SELECT count(*) FROM vessels")
        return {
            "status": "ok",
            "vessels": vessels,
            "model": settings.llm_model,
            "memory_window_turns": settings.memory_window_turns,
        }

    return app


def _make_default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()


app = _make_default_app()
