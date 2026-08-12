from .base import BaseOCR, OCRLine, OCRResult
from .helper import OCREngine, extract_ocr_from_image, is_scanned_pdf_page
from .mock_ocr import MockOCREngine
from .paddle_ocr import PaddleOCREngine

__all__ = [
    "BaseOCR",
    "MockOCREngine",
    "OCREngine",
    "OCRLine",
    "OCRResult",
    "PaddleOCREngine",
    "extract_ocr_from_image",
    "is_scanned_pdf_page",
]
