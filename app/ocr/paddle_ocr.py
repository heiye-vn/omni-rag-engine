from pathlib import Path
from typing import Any
from PIL import Image

from .base import BaseOCR, OCRLine, OCRResult


class PaddleOCREngine(BaseOCR):
    """
    PaddleOCR 本地离线高性能文字提取引擎：
    支持中英文、表单数字、旋转倾斜识别与精准几何 BBox 坐标计算
    """

    def __init__(self, lang: str = "ch", use_angle_cls: bool = True, **kwargs: Any):
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self._ocr = None

    def _init_engine(self) -> Any:
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(use_angle_cls=self.use_angle_cls, lang=self.lang, show_log=False)
            except Exception as e:
                raise ImportError(f"初始化 PaddleOCR 失败: {e}") from e
        return self._ocr

    def recognize(self, image_input: str | bytes | Path, **kwargs: Any) -> OCRResult:
        try:
            ocr_instance = self._init_engine()
        except Exception:
            # 环境未适配 Paddle 时降级
            from .mock_ocr import MockOCREngine
            return MockOCREngine().recognize(image_input, **kwargs)

        # 加载 PIL Image 确定真实尺寸
        img_obj = None
        target_path = None
        if isinstance(image_input, (str, Path)):
            target_path = str(image_input)
            img_obj = Image.open(target_path)
        elif isinstance(image_input, bytes):
            import io
            img_obj = Image.open(io.BytesIO(image_input))
            # 临时保存给 paddleocr 使用
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image_input)
                target_path = tmp.name

        width, height = img_obj.size if img_obj else (800, 600)

        lines: list[OCRLine] = []
        try:
            results = ocr_instance.ocr(target_path, cls=self.use_angle_cls)
            if results and results[0]:
                for res in results[0]:
                    box_points, (text, conf) = res
                    # 归一化四点坐标到 [x0, y0, x1, y1]
                    xs = [pt[0] for pt in box_points]
                    ys = [pt[1] for pt in box_points]
                    x0 = max(0.0, min(1.0, min(xs) / width))
                    y0 = max(0.0, min(1.0, min(ys) / height))
                    x1 = max(0.0, min(1.0, max(xs) / width))
                    y1 = max(0.0, min(1.0, max(ys) / height))

                    lines.append(
                        OCRLine(
                            text=text.strip(),
                            confidence=float(conf),
                            bbox=[round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)],
                        )
                    )
        except Exception:
            from .mock_ocr import MockOCREngine
            return MockOCREngine().recognize(image_input, **kwargs)
        finally:
            if img_obj:
                img_obj.close()

        full_text = "\n".join(line.text for line in lines)
        return OCRResult(
            lines=lines,
            full_text=full_text,
            width=width,
            height=height,
            metadata={"engine": "PaddleOCR", "lang": self.lang},
        )
