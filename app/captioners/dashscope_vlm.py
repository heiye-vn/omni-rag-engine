import base64
import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request
from pathlib import Path

from .base import BaseCaptioner


class DashScopeCaptioner(BaseCaptioner):
    """
    阿里通义千问 Qwen-VL 视觉大模型描述器
    使用 DashScope OpenAI 兼容模式接口调用
    """

    DEFAULT_PROMPT = "请用简洁精炼的中文详细描述这张图片的内容、关键对象、图表含义或文字信息，适合用于 RAG 检索索引。"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model or os.getenv("DASHSCOPE_VISION_MODEL", "qwen3.7-plus")
        self.base_url = base_url.rstrip("/")

    def describe_image(self, image_input: str | bytes | Path, prompt: str | None = None) -> str:
        if not self.api_key:
            raise ValueError(
                "调用 DashScope Qwen-VL 失败：未提供 DASHSCOPE_API_KEY。\n"
                "请设置环境变量 `DASHSCOPE_API_KEY` 或在构造函数中传入 `api_key='sk-xxx'`。"
            )

        prompt_text = prompt or self.DEFAULT_PROMPT
        base64_url = self._to_data_url(image_input)

        url = f"{self.base_url}/chat/completions"

        # ---------------- 内联 SSRF 防护（协议白名单 + 解析后 IP 边界校验）----------------
        # 云端服务端点默认要求公网地址，内网调试可通过 RAG_ALLOW_PRIVATE_URLS=true 放行
        _parsed = urllib.parse.urlparse(url)
        if _parsed.scheme not in ("http", "https") or not _parsed.hostname:
            raise ValueError(f"不支持的出站地址 (仅允许 http/https): {url!r}")
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
                    raise ValueError(f"拒绝请求受限网络地址 ({_ip})")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": base64_url}},
                    ],
                }
            ],
            "max_tokens": 512,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                return resp_data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                err_json = json.loads(err_body)
                msg = err_json.get("message") or err_json.get("error", {}).get("message") or err_body
            except Exception:
                msg = str(e)
            raise RuntimeError(f"DashScope Qwen-VL API 拒绝 ({e.code}): {msg}") from e
        except Exception as e:
            raise RuntimeError(f"DashScope Qwen-VL API 请求失败: {e}") from e

    @staticmethod
    def _to_data_url(image_input: str | bytes | Path) -> str:
        """将图片路径或二进制数据转为 base64 data URL"""
        if isinstance(image_input, (str, Path)):
            img_str = str(image_input)
            # 如果是网络或 OSS 公网图片 URL，可以直接返回该 URL 或自动下载转为 base64
            if img_str.startswith(("http://", "https://")):
                return img_str

            p = Path(image_input)
            ext = p.suffix.lstrip(".").lower() or "png"
            if ext == "jpg":
                ext = "jpeg"
            b_data = p.read_bytes()
            b64_str = base64.b64encode(b_data).decode("utf-8")
            return f"data:image/{ext};base64,{b64_str}"
        elif isinstance(image_input, bytes):
            b64_str = base64.b64encode(image_input).decode("utf-8")
            return f"data:image/png;base64,{b64_str}"
        else:
            raise ValueError(f"不受支持的图片输入类型: {type(image_input)}")
