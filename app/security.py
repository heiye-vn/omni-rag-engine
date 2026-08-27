"""
安全工具集：文件路径穿越防护与出站 URL 校验

供 parsers / loaders / captioners / vectorstores 等模块复用，
所有外部输入（上传文件名、URL、集合名等）在落盘或发起网络请求前必须经过本模块校验。
"""

import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

# 文件名片段仅保留安全字符集，其余一律替换为下划线
_SAFE_PART_PATTERN = re.compile(r"[^A-Za-z0-9._-]")

# 允许放行内网地址的环境变量开关（默认拒绝，用于特殊内网部署场景）
_PRIVATE_ALLOW_ENV = "RAG_ALLOW_PRIVATE_URLS"


def sanitize_filename_part(name: str, fallback: str = "file") -> str:
    """
    清理不可信的文件名/扩展名/标识符片段

    剔除路径分隔符与控制字符类内容，防止 "../" 类路径穿越注入到拼接结果中。
    """
    cleaned = _SAFE_PART_PATTERN.sub("_", str(name)).strip("._") or fallback
    return cleaned


def resolve_safe_join_path(base_dir: str | Path, filename: str) -> Path:
    """
    在 base_dir 内安全拼接待写入文件路径

    filename 先经 sanitize_filename_part 清洗，再做 realpath 包含性校验，
    确保最终路径不会逃逸出 base_dir。

    Raises:
        ValueError: 拼接结果试图越出 base_dir 时抛出
    """
    base = Path(base_dir).resolve()
    target = base.joinpath(sanitize_filename_part(filename)).resolve()

    if target != base and base not in target.parents:
        raise ValueError(f"非法的文件写入路径，已越出目标目录: {filename!r}")

    return target


def ensure_http_url(url: str) -> str:
    """
    校验出站 URL 协议合法性：仅允许 http / https

    阻断 file:// / ftp:// 等协议被注入到 urllib 网络请求中造成本地文件读取。
    适用场景：运维配置的服务端点（如 Ollama 本机地址允许回环）。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"不支持的出站地址 (仅允许 http/https): {url!r}")
    return url


def _private_targets_allowed() -> bool:
    """读取环境变量判断是否放行内网地址访问"""
    return os.getenv(_PRIVATE_ALLOW_ENV, "").strip().lower() in ("1", "true", "yes")


def validate_public_http_url(url: str, timeout: float = 5.0) -> str:
    """
    校验面向用户可控输入的出站 URL（SSRF 防护）

    在 ensure_http_url 的协议白名单基础上，进一步解析 DNS 并拒绝解析到
    回环/内网/链路本地/保留/组播地址的目标，防止借文档导入探测云元数据
    接口或内网服务。可通过设置 RAG_ALLOW_PRIVATE_URLS=true 显式放行。

    Raises:
        ValueError: 协议不合法或主机解析命中受限地址段时抛出
    """
    ensure_http_url(url)
    if _private_targets_allowed():
        return url

    parsed = urlparse(url)
    host = parsed.hostname or ""
    default_port = 443 if parsed.scheme == "https" else 80

    try:
        infos = socket.getaddrinfo(host, parsed.port or default_port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"无法解析目标主机 {host!r}: {e}") from e

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(
                f"拒绝请求受限网络地址 ({ip})：如需访问内网资源请设置 {_PRIVATE_ALLOW_ENV}=true"
            )

    return url
