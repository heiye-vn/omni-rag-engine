import base64
import json
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
