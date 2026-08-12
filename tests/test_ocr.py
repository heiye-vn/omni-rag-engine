from app.ocr import (
    BaseOCR,
    MockOCREngine,
    OCREngine,
    PaddleOCREngine,
    extract_ocr_from_image,
)


def test_ocr():
    print(">>> 1. 测试 MockOCREngine 零依赖降级兜底引擎...")
    mock_ocr = MockOCREngine()
    res = mock_ocr.recognize("examples/37.png")
    assert len(res.lines) > 0
    assert "[OCR Mock Text]" in res.full_text
    assert res.lines[0].bbox == [0.05, 0.05, 0.95, 0.15]
    print(f"Mock OCR 提取成功！识别行数: {len(res.lines)}, 首行文本: {res.lines[0].text}")

    print("\n>>> 2. 测试 OCREngine 统一工厂与自动匹配...")
    engine = OCREngine.get_engine(engine_type="auto")
    assert isinstance(engine, (PaddleOCREngine, MockOCREngine))
    print(f"OCREngine 工厂匹配得到的引擎类型: {type(engine).__name__}")

    print("\n>>> 3. 测试 extract_ocr_from_image 全局快捷提取...")
    ocr_result = extract_ocr_from_image("examples/37.png", engine_type="mock")
    assert ocr_result.width == 1663
    assert ocr_result.height == 937
    print(f"图片尺寸: {ocr_result.width}x{ocr_result.height}, 提取字符数: {len(ocr_result.full_text)}")

    print("\n[OK] 扫描件与图片 OCR 文字提取模块 (app/ocr/) 所有测试成功通过！")


if __name__ == "__main__":
    test_ocr()
