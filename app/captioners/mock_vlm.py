from pathlib import Path
from PIL import Image

from .base import BaseCaptioner


class MockCaptioner(BaseCaptioner):
    """
    零配置 / 降级 Mock 描述器：
    当未配置 API Key 或未连接真实大模型时提供稳定安全的元数据属性描述，确保系统 100% 不崩溃。
    """

    def describe_image(self, image_input: str | bytes | Path, prompt: str | None = None) -> str:
        if isinstance(image_input, (str, Path)):
            img_str = str(image_input)
            if img_str.startswith(("http://", "https://")):
                return f"[Image Description (Mock)]: 远程图片 URL: {img_str}"

            p = Path(image_input)
            if p.exists():
                try:
                    with Image.open(p) as img:
                        w, h = img.size
                        fmt = img.format or p.suffix.lstrip(".").upper()
                        mode = img.mode
                        return f"[Image Description (Mock)]: 文件名={p.name}, 尺寸={w}x{h}, 格式={fmt}, 色彩={mode}"
                except Exception:
                    return f"[Image Description (Mock)]: 图片文件 {p.name}"
            return f"[Image Description (Mock)]: 图片路径 {image_input}"

        elif isinstance(image_input, bytes):
            try:
                import io
                with Image.open(io.BytesIO(image_input)) as img:
                    w, h = img.size
                    fmt = img.format or "UNKNOWN"
                    return f"[Image Description (Mock)]: 二进制图像数据, 尺寸={w}x{h}, 格式={fmt}"
            except Exception:
                return f"[Image Description (Mock)]: 二进制图像数据 ({len(image_input)} bytes)"

        return f"[Image Description (Mock)]: 图像元素 {image_input}"
