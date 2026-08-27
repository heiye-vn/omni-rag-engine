import base64
import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from .base import BaseCaptioner


class OllamaCaptioner(BaseCaptioner):
    """
    本地 Ollama 视觉大模型描述器 (llava / qwen2-vl / bakllava)
    """

    DEFAULT_PROMPT = "请详细描述这张图片的内容与文字信息。"

    def __init__(
        self,
        model: str = "llava",
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.host = host.rstrip("/")

    def describe_image(self, image_input: str | bytes | Path, prompt: str | None = None) -> str:
        prompt_text = prompt or self.DEFAULT_PROMPT
        raw_b64 = self._to_pure_base64(image_input)

        url = f"{self.host}/api/generate"

        # ---------------- 内联 SSRF 防护（协议白名单 + 解析后 IP 边界校验）----------------
        # Ollama 面向本机/内网部署是默认场景，故默认放行私有网段；
        # 严格的纯公网环境可设置 RAG_ALLOW_PRIVATE_URLS=false 收紧
        _parsed = urllib.parse.urlparse(url)
        if _parsed.scheme not in ("http", "https") or not _parsed.hostname:
            raise ValueError(f"不支持的出站地址 (仅允许 http/https): {url!r}")
        if os.getenv("RAG_ALLOW_PRIVATE_URLS", "true").strip().lower() not in ("1", "true", "yes"):
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
                    raise ValueError(f"拒绝请求受限网络地址 ({_ip})")

        payload = {
            "model": self.model,
            "prompt": prompt_text,
            "images": [raw_b64],
            "stream": False,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                return resp_data.get("response", "").strip()
        except Exception as e:
            raise RuntimeError(f"Ollama API 请求失败: {e}") from e

    @staticmethod
    def _to_pure_base64(image_input: str | bytes | Path) -> str:
        if isinstance(image_input, (str, Path)):
            b_data = Path(image_input).read_bytes()
            return base64.b64encode(b_data).decode("utf-8")
        elif isinstance(image_input, bytes):
            return base64.b64encode(image_input).decode("utf-8")
        else:
            raise ValueError(f"不受支持的图片输入类型: {type(image_input)}")
