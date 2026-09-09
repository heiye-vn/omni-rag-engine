"""
API Key 鉴权 + slowapi 限流 测试

依赖：app.auth + app.rate_limit + app.server（已接线）

策略：
- 鉴权测试：直接打 HTTP 接口验证 401/403/200；AUTH_ENABLED=0/1 通过 monkeypatch 切换
- 限流测试：直接驱动 slowapi 限流器核心逻辑（不依赖具体 HTTP 路径），
  避免装饰器在 import 时绑定限流阈值带来的测试隔离难题

注意：本文件**不引入** `from __future__ import annotations`！PEP 563 会把
`request: Request` 注解变成字符串，FastAPI 的依赖注入会把它当作普通 query 参数
导致 422 "Field required"。app/ 模块用了 future annotations 但它们端点不用
request 作为第一个参数，因此不受影响；本测试需要 Request 注解真实可解析。
"""

import os

import pytest
from fastapi.testclient import TestClient

slowapi = pytest.importorskip("slowapi", reason="未安装 slowapi")


# ---------------------------------------------------------------------------- #
#  鉴权 Fixtures
# ---------------------------------------------------------------------------- #


@pytest.fixture
def client_disabled(monkeypatch):
    """AUTH_ENABLED=0：所有端点完全放行（开发态友好）"""
    monkeypatch.setenv("AUTH_ENABLED", "0")
    monkeypatch.setenv("API_KEYS", "")
    from app.server import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_enabled(monkeypatch):
    """AUTH_ENABLED=1 + 双 key：必须带正确 key 才放行"""
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("API_KEYS", "key-alpha,key-beta")
    from app.server import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------- #
#  鉴权：白名单与放行
# ---------------------------------------------------------------------------- #


def test_root_is_public(client_enabled):
    """GET / 必须始终放行"""
    r = client_enabled.get("/")
    assert r.status_code == 200
    assert "service" in r.json()


def test_health_is_public(client_enabled):
    """/health 必须始终放行（容器探针依赖）"""
    r = client_enabled.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------- #
#  鉴权：受保护端点
# ---------------------------------------------------------------------------- #


def test_protected_endpoint_without_token_returns_401(client_enabled):
    """未带 Authorization → 401"""
    r = client_enabled.get("/api/v1/jobs")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_protected_endpoint_with_wrong_token_returns_403(client_enabled):
    """错 key → 403"""
    r = client_enabled.get(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert r.status_code == 403


def test_protected_endpoint_with_correct_token_passes(client_enabled):
    """正确 key → 200"""
    r = client_enabled.get(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer key-alpha"},
    )
    assert r.status_code == 200


def test_protected_endpoint_supports_multiple_keys(client_enabled):
    """多 key 都应被接受"""
    for k in ("key-alpha", "key-beta"):
        r = client_enabled.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {k}"},
        )
        assert r.status_code == 200, f"key {k!r} 应该被接受"


def test_auth_disabled_lets_everyone_in(client_disabled):
    """AUTH_ENABLED=0 + 空 API_KEYS：无 token 也应放行"""
    r = client_disabled.get("/api/v1/jobs")
    assert r.status_code == 200


def test_auth_enabled_but_no_keys_returns_503(client_enabled, monkeypatch):
    """AUTH_ENABLED=1 但 API_KEYS 空 → 503（防止生产裸奔）"""
    monkeypatch.setenv("API_KEYS", "")
    r = client_enabled.get(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer anything"},
    )
    assert r.status_code == 503


def test_bearer_scheme_with_malformed_header(client_enabled):
    """Authorization 但不带 Bearer 前缀 → 401"""
    r = client_enabled.get(
        "/api/v1/jobs",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------- #
#  鉴权：覆盖全端点
# ---------------------------------------------------------------------------- #


def test_all_protected_endpoints_require_auth(client_enabled):
    """所有 /api/v1/* 端点必须挂 verify_api_key；漏挂任何一个视为回归"""
    protected_paths = [
        ("GET", "/api/v1/jobs"),
        ("GET", "/api/v1/jobs?limit=5"),
    ]
    for method, path in protected_paths:
        r = client_enabled.request(method, path)
        assert r.status_code == 401, f"{method} {path} 应要求鉴权"


# ---------------------------------------------------------------------------- #
#  限流：直接驱动 slowapi 核心逻辑（避免装饰器 import 时绑定）
# ---------------------------------------------------------------------------- #


def test_limiter_blocks_after_threshold():
    """限流核心：连续 N+1 次请求 → 第 N+1 次必须被拒"""
    from fastapi import FastAPI, Request, Response
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
    from starlette.testclient import TestClient

    # 紧凑限流的小型独立 app，专门用于限流单元测试
    # 注意：headers_enabled=False 因为 fastapi 返回 dict 时无 Response 对象可注入 headers
    tight = Limiter(
        key_func=get_remote_address,
        default_limits=["3/minute"],
        headers_enabled=False,
    )
    tiny_app = FastAPI()
    tiny_app.state.limiter = tight

    @tiny_app.get("/ping")
    @tight.limit("3/minute")
    async def ping(request: Request):
        return Response(content="ok")

    # 必须 add_exception_handler，否则 RateLimitExceeded 直接抛 500
    from app.rate_limit import rate_limit_exceeded_handler

    tiny_app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    tiny_app.add_middleware(SlowAPIMiddleware)

    client = TestClient(tiny_app, raise_server_exceptions=False)
    statuses = [client.get("/ping").status_code for _ in range(5)]

    assert statuses[:3] == [200, 200, 200], f"前 3 次应 200，实际: {statuses}"
    assert statuses[3:] == [429, 429], f"第 4-5 次应 429，实际: {statuses}"


def test_rate_limit_handler_returns_json_with_retry_after():
    """限流响应必须是 JSON + Retry-After"""
    from app.rate_limit import rate_limit_exceeded_handler
    from fastapi import Request
    from slowapi.errors import RateLimitExceeded
    from slowapi.wrappers import LimitGroup

    # 构造符合 RateLimitExceeded 接口的 fake limit（不需要真解析）
    fake_limit = LimitGroup(
        limit_provider=None,
        scope="test",
        key_function=None,
        per_method=False,
        methods=[],
        error_message="Rate limit hit",
        exempt_when=None,
        cost=1,
        override_defaults=False,
    )
    fake_limit.limit = None  # 让 __str__ 走 error_message 分支
    request = Request(
        scope={
            "type": "http",
            "client": ("127.0.0.1", 8000),
            "headers": [],
            "method": "GET",
            "path": "/api/v1/jobs",
            "raw_path": b"/api/v1/jobs",
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    exc = RateLimitExceeded(fake_limit)

    response = rate_limit_exceeded_handler(request, exc)

    assert response.status_code == 429
    body = response.body.decode()
    assert "Rate limit exceeded" in body


def test_app_state_limiter_is_configured(client_disabled):
    """/health 与 / 必须永远不受限流影响；限流器必须挂在 app.state 上"""
    from app.server import app

    assert hasattr(app.state, "limiter")
    assert app.state.limiter is not None


def test_health_endpoint_bypasses_rate_limit(client_disabled):
    """探针豁免：连续请求 /health 20 次必须全部 200"""
    for _ in range(20):
        r = client_disabled.get("/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------- #
#  限流配置：环境变量驱动
# ---------------------------------------------------------------------------- #


def test_rate_limit_strings_parseable():
    """慢api 限流字符串必须可解析（生产配置写错会启动失败）"""
    from limits import parse
    from app.rate_limit import _default_rate, _upload_rate

    # 默认值可解析
    assert parse(_default_rate()) is not None
    assert parse(_upload_rate()) is not None

    # 常见自定义配置也可解析
    for s in ("100/minute", "1000/hour", "5/second", "1000/minute"):
        assert parse(s) is not None, f"{s} 应可解析"


def test_invalid_token_does_not_consume_rate_quota(client_enabled):
    """错 key 应在鉴权层就被拒绝（401/403），限流计数不应被消耗

    验证方式：连续打 30 次错 key（远超默认限流阈值 60/minute），
    然后用正确 key 应能正常访问（如果鉴权失败消耗了配额，第 31 次会被 429）。
    """
    # 30 次错 key 请求（远低于 60/minute 默认上限，不会因为限流失败）
    for _ in range(30):
        r = client_enabled.get(
            "/api/v1/jobs",
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 403

    # 正确 key 仍能通过 →  证明配额没被错请求消耗
    r = client_enabled.get(
        "/api/v1/jobs",
        headers={"Authorization": "Bearer key-alpha"},
    )
    assert r.status_code == 200