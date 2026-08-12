import base64
import json
import os
import urllib.request
from pathlib import Path

from .base import BaseCaptioner


class OpenAICaptioner(BaseCaptioner):
    """
    OpenAI Vision 视觉大模型描述器 (GPT-4o / GPT-4o-mini)
    """

    DEFAULT_PROMPT = "Please describe the contents, main elements, text, or chart structure of this image in detail for RAG indexing."

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url.rstrip("/")

    def describe_image(self, image_input: str | bytes | Path, prompt: str | None = None) -> str:
        if not self.api_key:
            raise ValueError(
                "调用 OpenAI Vision 失败：未提供 OPENAI_API_KEY。\n"
                "请设置环境变量 `OPENAI_API_KEY` 或在构造函数中传入 `api_key='sk-xxx'`。"
            )

        prompt_text = prompt or self.DEFAULT_PROMPT
        base64_url = self._to_data_url(image_input)

        url = f"{self.base_url}/chat/completions"
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
        except Exception as e:
            raise RuntimeError(f"OpenAI Vision API 请求失败: {e}") from e

    @staticmethod
    def _to_data_url(image_input: str | bytes | Path) -> str:
        if isinstance(image_input, (str, Path)):
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
