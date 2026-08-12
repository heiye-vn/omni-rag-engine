from pathlib import Path
from typing import Any

from .base import BaseOCR, OCRResult
from .mock_ocr import MockOCREngine
from .paddle_ocr import PaddleOCREngine


class OCREngine:
    """
    OCR 识别引擎统一工厂适配器
    """

    @classmethod
    def get_engine(
        cls,
        engine_type: str = "auto",
        lang: str = "ch",
        **kwargs: Any,
    ) -> BaseOCR:
        """
        根据指定的引擎类型实例化 OCR 处理器

        Args:
            engine_type: 引擎模式 ("auto", "paddle", "mock")
            lang: 识别语言类型 (如 "ch", "en")
            **kwargs: 扩展参数

        Returns:
            BaseOCR 实例
        """
        e_type = engine_type.lower()

        if e_type == "paddle":
            return PaddleOCREngine(lang=lang, **kwargs)
        elif e_type == "mock":
            return MockOCREngine()
        elif e_type == "auto":
            try:
                import paddleocr  # noqa: F401
                return PaddleOCREngine(lang=lang, **kwargs)
            except Exception:
                return MockOCREngine()

        raise ValueError(f"不受支持的 OCR 引擎类型: '{engine_type}'")


def is_scanned_pdf_page(page: Any, min_text_chars: int = 20) -> bool:
    """
    智能判定 PDF 页面是否为纯图片/扫描件：
    如果抽取出的文本字符数小于阈值 (默认 20 字) 且页面包含位图图像，判定为扫描件。
    """
    try:
        text = page.get_text("text").strip()
        if len(text) < min_text_chars:
            image_list = page.get_images()
            if image_list:
                return True
    except Exception:
        pass
    return False


def extract_ocr_from_image(
    image_input: str | bytes | Path,
    engine: BaseOCR | None = None,
    engine_type: str = "auto",
    **kwargs: Any,
) -> OCRResult:
    """对给定图片提取 OCR 文字与 BBox 坐标"""
    if engine is None:
        engine = OCREngine.get_engine(engine_type=engine_type, **kwargs)
    return engine.recognize(image_input)
