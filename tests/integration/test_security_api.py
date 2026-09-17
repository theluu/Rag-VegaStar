"""Test tích hợp cho lớp bảo mật / vận hành của API."""

import asyncpg
import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from fakes import HashEmbedder, ScriptedLLM, Step
from vessel_chat.api.app import create_app


def make_app(settings, **overrides):
    s = settings.model_copy(update=overrides)
    llm = ScriptedLLM(router=lambda messages: [Step(text="xin chào " * 200)])
    return create_app(settings=s, llm=llm, embedder=HashEmbedder(s.embedding_dim))


@pytest_asyncio.fixture
async def open_client(settings, pool):
    app = make_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            c.app = app
            yield c


async def test_security_headers_and_request_id(open_client):
    r = await open_client.get("/conversations", headers={"X-Request-ID": "abc123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "abc123"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    generated = await open_client.get("/health")
    assert len(generated.headers["x-request-id"]) == 32


async def test_docs_are_served_without_strict_csp(open_client):
    r = await open_client.get("/docs")
    assert r.status_code == 200 and "content-security-policy" not in r.headers


async def test_body_size_limit(open_client):
    r = await open_client.post("/conversations", content=b"x" * 70_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["request_id"]


async def test_gzip_for_json_but_not_for_sse(open_client):
    r = await open_client.get("/tracks", params={"start": "2026-09-10", "end": "2026-09-12"},
                              headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    cid = (await open_client.post("/conversations", json={})).json()["id"]
    r = await open_client.post(f"/conversations/{cid}/chat", json={"message": "chào"},
                               headers={"Accept-Encoding": "gzip"})
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "content-encoding" not in r.headers


async def test_metrics_endpoint(open_client):
    await open_client.get("/conversations")
    body = (await open_client.get("/metrics")).text
    assert 'vc_http_requests_total{method="GET",route="/conversations",status="200"}' in body


async def test_unhandled_errors_do_not_leak_details(open_client):
    @open_client.app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    r = await open_client.get("/boom")
    assert r.status_code == 500
    assert "secret" not in r.text and r.json()["request_id"]


async def test_api_key_required_when_configured(settings, pool):
    app = make_app(settings, api_keys="k-one,k-two")
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            assert (await c.get("/health")).status_code == 200
            r = await c.get("/conversations")
            assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
            assert (await c.get("/conversations", headers={"X-API-Key": "wrong"})).status_code == 401
            assert (await c.get("/conversations", headers={"X-API-Key": "k-two"})).status_code == 200
            assert (await c.get("/conversations", headers={"Authorization": "Bearer k-one"})).status_code == 200
            missing = "00000000-0000-0000-0000-000000000000"
            assert (await c.post(f"/conversations/{missing}/chat", json={"message": "x"})).status_code == 401


async def test_rate_limits(settings, pool):
    app = make_app(settings, rate_limit_api_per_minute=3, rate_limit_chat_per_minute=1)
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            codes = [(await c.get("/conversations")).status_code for _ in range(4)]
            assert codes == [200, 200, 200, 429]
            limited = await c.get("/conversations")
            assert int(limited.headers["retry-after"]) >= 1
            assert (await c.get("/health")).status_code == 200  # không bị giới hạn

    app = make_app(settings, rate_limit_chat_per_minute=1)
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            cid = (await c.post("/conversations", json={})).json()["id"]
            assert (await c.post(f"/conversations/{cid}/chat", json={"message": "a"})).status_code == 200
            assert (await c.post(f"/conversations/{cid}/chat", json={"message": "b"})).status_code == 429


async def test_tool_pool_is_read_only(open_client):
    tool_pool = open_client.app.state.tool_pool
    async with tool_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM vessels") == 6
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            await conn.execute("DELETE FROM vessels")


async def test_login_flow_protects_api(settings, pool):
    app = make_app(settings, auth_users="demo:demo", session_secret="test-secret", rate_limit_login_per_minute=100)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            health = (await c.get("/health")).json()
            assert health["auth_required"] is True and health["login_enabled"] is True
            for path in ("/conversations", "/stats", "/tracks?company=x", "/auth/me"):
                assert (await c.get(path)).status_code == 401, path

            bad = await c.post("/auth/login", json={"username": "demo", "password": "sai"})
            assert bad.status_code == 401 and "token" not in bad.json()
            assert (await c.post("/auth/login", json={"username": "ai-do", "password": "demo"})).status_code == 401
            assert (await c.post("/auth/login", json={"username": "", "password": "demo"})).status_code == 422

            ok = await c.post("/auth/login", json={"username": " demo ", "password": "demo"})
            assert ok.status_code == 200
            body = ok.json()
            assert body["username"] == "demo" and body["token_type"] == "Bearer" and body["expires_at"]
            auth = {"Authorization": f"Bearer {body['token']}"}

            me = await c.get("/auth/me", headers=auth)
            assert me.status_code == 200 and me.json()["username"] == "demo"
            cid = (await c.post("/conversations", json={}, headers=auth)).json()["id"]
            r = await c.post(f"/conversations/{cid}/chat", json={"message": "xin chào"}, headers=auth)
            assert r.status_code == 200 and "event: done" in r.text
            assert (await c.get("/conversations", headers={"Authorization": "Bearer v1.x.y"})).status_code == 401

            # token ký bằng khoá khác (vd. server đổi SESSION_SECRET) bị từ chối
            other = make_app(settings, auth_users="demo:demo", session_secret="other-secret")
            forged, _ = other.state.session_signer.issue("demo")
            assert (await c.get("/conversations", headers={"Authorization": f"Bearer {forged}"})).status_code == 401


async def test_login_rate_limit_and_disabled_login(settings, pool):
    app = make_app(settings, auth_users="demo:demo", session_secret="s", rate_limit_login_per_minute=2)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            codes = [(await c.post("/auth/login", json={"username": "demo", "password": "x"})).status_code
                     for _ in range(3)]
            assert codes == [401, 401, 429]

    app = make_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            assert (await c.post("/auth/login", json={"username": "demo", "password": "demo"})).status_code == 404
            assert (await c.get("/conversations")).status_code == 200


async def test_api_key_still_works_with_login_enabled(settings, pool):
    app = make_app(settings, auth_users="demo:demo", session_secret="s", api_keys="svc-key")
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            assert (await c.get("/conversations", headers={"X-API-Key": "svc-key"})).status_code == 200
            assert (await c.get("/auth/me", headers={"X-API-Key": "svc-key"})).status_code == 404
