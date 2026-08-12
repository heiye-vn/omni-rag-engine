from pathlib import Path
from typing import Any
from PIL import Image

from .base import BaseOCR, OCRLine, OCRResult


class MockOCREngine(BaseOCR):
    """
    免环境依赖降级兜底 OCR 引擎：
    当环境未安装 Paddle/PaddleOCR 或离线模型缺失时，安全提取基本信息，保证系统 100% 不崩溃。
    """

    def recognize(self, image_input: str | bytes | Path, **kwargs: Any) -> OCRResult:
        width, height = 800, 600
        filename = "image"

        if isinstance(image_input, (str, Path)):
            p = Path(image_input)
            filename = p.name
            if p.exists():
                try:
                    with Image.open(p) as img:
                        width, height = img.size
                except Exception:
                    pass
        elif isinstance(image_input, bytes):
            try:
                import io
                with Image.open(io.BytesIO(image_input)) as img:
                    width, height = img.size
            except Exception:
                pass

        mock_lines = [
            OCRLine(
                text=f"[OCR Mock Text]: {filename} 图像文本行 1",
                confidence=0.99,
                bbox=[0.05, 0.05, 0.95, 0.15],
            ),
            OCRLine(
                text="[OCR Mock Text]: 样例表格/段落文本行 2",
                confidence=0.98,
                bbox=[0.05, 0.20, 0.95, 0.35],
            ),
        ]

        full_text = "\n".join(line.text for line in mock_lines)

        return OCRResult(
            lines=mock_lines,
            full_text=full_text,
            width=width,
            height=height,
            metadata={"engine": "MockOCREngine"},
        )
