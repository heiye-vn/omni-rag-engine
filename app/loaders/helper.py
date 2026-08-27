from pathlib import Path
from typing import Any

from app.factory import get_parser
from .archive import ArchiveLoader
from .base import BatchParsedDocument
from .directory import DirectoryLoader


def load_batch(
    target_path: str | Path,
    enable_cleaning: bool = True,
    enable_describe_images: bool = True,
    **kwargs: Any,
) -> BatchParsedDocument:
    """
    通用智能批处理加载入口：自动根据路径类型（文件夹 / 压缩包 / 单文件）分发解析

    Args:
        target_path: 目标路径 (可以是一个文件夹、ZIP/TAR 压缩包或单个文件)
        enable_cleaning: 是否自动进行数据清洗
        enable_describe_images: 是否自动使用多模态视觉大模型生成图片描述
        **kwargs: 传给特定解析器的选填参数

    Returns:
        包含所有成功解析文档的 BatchParsedDocument 批量容器
    """
    target_str = str(target_path).strip("'\"")

    # 0. 支持网络与 OSS 远程 URL (http:// 或 https://)
    if target_str.startswith(("http://", "https://")):
        import ipaddress
        import os
        import socket
        import tempfile
        import urllib.request
        from urllib.parse import unquote, urlparse

        parsed_url = urlparse(target_str)
        # 解码 URL 中的文件名，提取文件扩展名 (如 .jpg)
        url_path = unquote(parsed_url.path)
        filename = Path(url_path).name or "downloaded_file"
        suffix = Path(filename).suffix or ".jpg"

        # ---------------- 内联 SSRF 防护（协议白名单 + 解析后 IP 边界校验）----------------
        _parsed = urlparse(target_str)
        if _parsed.scheme not in ("http", "https") or not _parsed.hostname:
            raise ValueError(f"不支持的下载地址 (仅允许 http/https): {target_str!r}")

        # 默认拒绝解析到内网/回环/链路本地等受限地址段的目标；
        # 内网部署场景可通过 RAG_ALLOW_PRIVATE_URLS=true 显式放行
        if os.getenv("RAG_ALLOW_PRIVATE_URLS", "").strip().lower() not in ("1", "true", "yes"):
            for _info in socket.getaddrinfo(_parsed.hostname, None):
                _ip = ipaddress.ip_address(_info[4][0])
                if (
                    _ip.is_loopback
                    or _ip.is_private
                    or _ip.is_link_local
                    or _ip.is_reserved
                    or _ip.is_multicast
                    or _ip.is_unspecified
                ):
                    raise ValueError(
                        f"拒绝请求受限网络地址 ({_ip})：如需访问内网资源请设置 RAG_ALLOW_PRIVATE_URLS=true"
                    )

        req = urllib.request.Request(
            target_str,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                file_bytes = resp.read()
        except Exception as e:
            raise RuntimeError(f"下载网络/OSS 资源失败: {target_str}, 错误原因: {e}") from e

        # 保存到临时文件进行解析
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            parser = get_parser(str(tmp_path), **kwargs)
            parsed_doc = parser.parse(str(tmp_path))
            parsed_doc.file_name = filename
            parsed_doc.file_path = target_str

            # 将 Element 元数据中的 file_path 统一更正为原始网络/OSS URL
            for elem in parsed_doc.elements:
                elem.metadata["file_path"] = target_str

            if enable_cleaning:
                parsed_doc = parsed_doc.clean()

            batch_res = BatchParsedDocument(documents=[parsed_doc])

            if enable_describe_images:
                batch_res = batch_res.describe_images()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        return batch_res

    path = Path(target_str)

    if not path.exists():
        raise FileNotFoundError(f"目标路径不存在: {path}")

    # 1. 文件夹路径
    ext = path.name.lower()
    if path.is_dir():
        loader = DirectoryLoader(
            directory_path=path,
            enable_cleaning=enable_cleaning,
            **kwargs,
        )
        batch_res = loader.load()
    # 2. 压缩包路径
    elif ext.endswith(tuple(ArchiveLoader.SUPPORTED_ARCHIVE_EXTENSIONS)):
        loader = ArchiveLoader(
            archive_path=path,
            enable_cleaning=enable_cleaning,
            **kwargs,
        )
        batch_res = loader.load()
    # 3. 单个常规文件
    else:
        parser = get_parser(str(path), **kwargs)
        parsed_doc = parser.parse(str(path))
        if enable_cleaning:
            parsed_doc = parsed_doc.clean()
        batch_res = BatchParsedDocument(documents=[parsed_doc])

    # 4. 如果开启了图片描述，自动调用多模态大模型
    if enable_describe_images:
        batch_res = batch_res.describe_images()

    return batch_res
