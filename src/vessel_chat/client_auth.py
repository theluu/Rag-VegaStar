"""Header xác thực cho các script gọi API (harness, chạy kịch bản).

Ưu tiên API key; nếu có tên đăng nhập + mật khẩu thì gọi `POST /auth/login` lấy token phiên.
"""

import argparse
import os

import httpx


def add_auth_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--api-key", default=os.environ.get("API_KEY"), help="API key (biến API_KEY)")
    parser.add_argument("--username", default=os.environ.get("API_USERNAME"), help="Tài khoản đăng nhập (API_USERNAME)")
    parser.add_argument("--password", default=os.environ.get("API_PASSWORD"), help="Mật khẩu (API_PASSWORD)")


async def auth_headers(api_url: str, api_key: str | None, username: str | None, password: str | None) -> dict[str, str]:
    if api_key:
        return {"X-API-Key": api_key}
    if username and password:
        async with httpx.AsyncClient(base_url=api_url, timeout=15) as client:
            resp = await client.post("/auth/login", json={"username": username, "password": password})
            if resp.status_code != 200:
                raise SystemExit(f"Đăng nhập thất bại ({resp.status_code}): {resp.text[:200]}")
            return {"Authorization": f"Bearer {resp.json()['token']}"}
    return {}
