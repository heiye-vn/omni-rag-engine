from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OCRLine:
    """OCR 单行/单块文本识别结果"""
    text: str
    confidence: float
    bbox: list[float]  # 归一化坐标 [x0, y0, x1, y1]，取值范围 0.0 - 1.0


@dataclass
class OCRResult:
    """OCR 全图识别结果集合"""
    lines: list[OCRLine] = field(default_factory=list)
    full_text: str = ""
    width: int = 0
    height: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseOCR(ABC):
    """OCR 识别引擎抽象基类"""

    @abstractmethod
    def recognize(self, image_input: str | bytes | Path, **kwargs: Any) -> OCRResult:
        """
        对给定的图片输入进行印刷体文字识别与几何定位

        Args:
            image_input: 图片路径 (str/Path) 或图片二进制字节流 (bytes)

        Returns:
            OCRResult 结果模型对象
        """
        pass
