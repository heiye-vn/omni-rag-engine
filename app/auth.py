"""
API Key 鉴权：基于 Bearer Token 的简单认证

设计动机：
- 当前所有 /api/v1/* 端点完全裸奔；任何能访问服务的人都能上传文件、查询任务、删除数据。
- 企业内网部署也需要基本门禁：避免测试同学误调生产、避免实习生手滑上传 N GB。

实现策略：
- 多 Key 支持：env API_KEYS=key1,key2,key3（逗号分隔），支持随时增删
- 默认关闭：AUTH_ENABLED=1 才启用；=0 时完全放行（方便本地开发）
- 健康检查豁免：/health 与 / 必须永远放行（K8s/容器探针依赖）
- 详细日志：每次鉴权失败打 WARNING（含 client IP + 路径），便于排障
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# 自动禁用 header 自动报错（401 vs 403 的细节，按需调整）
_bearer_scheme = HTTPBearer(auto_error=False)


def _is_auth_enabled() -> bool:
    """鉴权总开关：默认关闭（开发态友好），生产必须显式开启"""
    raw = os.environ.get("AUTH_ENABLED", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _load_api_keys() -> set[str]:
    """从 env API_KEYS 读取合法 key 集合（去重 + 去除空白）"""
    raw = os.environ.get("API_KEYS", "")
    keys = {k.strip() for k in raw.split(",") if k.strip()}
    return keys


def _whitelist_paths() -> set[str]:
    """鉴权豁免的精确路径（探针 + 服务元信息；前缀匹配在调用处处理）"""
    return {"/", "/health", "/docs", "/redoc", "/openapi.json"}


def _is_whitelisted(path: str) -> bool:
    """路径白名单：精确匹配 + 前缀匹配（/docs 与 /openapi.json 的子资源）"""
    if path in _whitelist_paths():
        return True
    # FastAPI 自动文档会拉 /docs/oauth2-redirect 等子资源
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
        return True
    return False


async def verify_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> str:
    """
    FastAPI 鉴权依赖：注入到需要保护的端点

    用法:
        @app.get("/api/v1/foo")
        def foo(_: Annotated[str, Depends(verify_api_key)]):
            ...

    Returns:
        鉴权成功时返回使用的 key（用于审计/日志）

    Raises:
        HTTPException 401 / 403
    """
    # 1. 豁免路径（探针 + 文档）：永远放行
    if _is_whitelisted(request.url.path):
        return ""

    # 2. 总开关关闭：放行（开发模式）
    if not _is_auth_enabled():
        return ""

    # 3. 解析 Bearer token
    token = credentials.credentials if credentials else None
    if not token:
        client = request.client.host if request.client else "unknown"
        logger.warning("鉴权失败: 缺失 Authorization header (client=%s, path=%s)", client, request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. 比对 key 集合
    valid_keys = _load_api_keys()
    if not valid_keys:
        # 配置错误（AUTH_ENABLED=1 但没配 key）→ 直接 503 而非全放行，避免生产裸奔
        logger.error("AUTH_ENABLED=1 但 API_KEYS 为空，请在环境变量中配置至少一个 key")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is enabled but no API_KEYS configured",
        )

    if token not in valid_keys:
        client = request.client.host if request.client else "unknown"
        # 截断 token 防止日志泄漏（仅前 4 + 后 2）
        masked = token[:4] + "***" + token[-2:] if len(token) > 6 else "***"
        logger.warning("鉴权失败: 无效 key (client=%s, path=%s, key=%s)", client, request.url.path, masked)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return token