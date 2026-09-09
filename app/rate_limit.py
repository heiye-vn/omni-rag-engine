"""
基于 slowapi 的 IP 级限流

设计目标：
- 默认 60 次/分钟（与一般 SaaS API 持平）：防止脚本刷接口
- 大文件上传端点单独收紧到 10 次/小时：上传是重资源操作（解析链 + 对象存储写入），
  防止恶意上传把 PARSE_WORKERS 打满
- 限流异常统一返回 429 + Retry-After header（标准 HTTP 语义）
- 探针与文档路径不受限流影响
- 限流配置走动态读取：env 改变后通过 rebuild_limiter() 立即生效，
  方便测试不重启进程就能切换限流阈值
"""

from __future__ import annotations

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _default_rate() -> str:
    """默认 IP 限流速率"""
    return os.environ.get("RATE_LIMIT_DEFAULT", "60/minute")


def _upload_rate() -> str:
    """上传端点 IP 限流速率"""
    return os.environ.get("RATE_LIMIT_UPLOAD", "10/hour")


def _build_limiter() -> Limiter:
    """根据当前 env 构造一个全新 Limiter 实例

    注：X关闭 Ratelimit headers 自动注入。原因是 slowapi 的 _inject_headers 要求
    路由必须返回 starlette.responses.Response 实例，否则抛 "parameter `response`
    must be an instance of starlette.responses.Response"。我们的端点大多返回 Pydantic
    模型（FastAPI 自动 JSON 序列化），与 Response 注入路径不兼容。如需手动注入，
    可在端点显式返回 Response(rate_limit_headers)。
    """
    return Limiter(
        key_func=get_remote_address,
        default_limits=[_default_rate()],
        headers_enabled=False,
    )


# 进程级单例；测试可在 fixture 中调用 rebuild_limiter() 重置
limiter: Limiter = _build_limiter()


def rebuild_limiter() -> Limiter:
    """
    重建 limiter 实例，清空旧 storage + 应用最新 env 限流阈值

    生产代码通常不需要调用（启动时构造即可），主要用于测试隔离。
    返回新 limiter 实例，调用方需自行同步更新 app.state.limiter。
    """
    global limiter
    limiter = _build_limiter()
    return limiter


# 装饰器别名：模块加载时绑定；如需运行时切换限流，先 rebuild_limiter() 再重新取属性
def upload_limit_deco():
    """动态获取当前 limiter 的 upload 限流装饰器（解决模块加载时绑定问题）"""
    return limiter.limit(_upload_rate())


# 兼容旧名：模块加载时绑定一份"默认"装饰器。
# 若测试调整了 env 后想生效，请改用 upload_limit_deco()。
upload_limit = upload_limit_deco()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    限流异常统一处理器：返回 429 + 标准 Retry-After
    """
    logger.warning(
        "限流触发: client=%s path=%s limit=%s",
        get_remote_address(request),
        request.url.path,
        exc.detail,
    )
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "limit": str(exc.detail),
        },
    )
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        response.headers["Retry-After"] = str(int(retry_after))
    return response