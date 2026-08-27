from app.captioners import (
    DashScopeCaptioner,
    ImageCaptioner,
    MockCaptioner,
    OllamaCaptioner,
    OpenAICaptioner,
)
from app.models import Element, Location, ParsedDocument


def test_captioners():
    print(">>> 1. 测试 MockCaptioner 零配置降级兜底...")
    mock_cap = MockCaptioner()
    desc = mock_cap.describe_image("examples/37.png")
    assert "[Image Description (Mock)]" in desc
    assert "37.png" in desc
    print(f"Mock 描述输出: {desc}")

    print("\n>>> 2. 测试 ImageCaptioner 工厂与自动路由机制...")
    auto_cap = ImageCaptioner.get_captioner(provider="auto")
    assert isinstance(auto_cap, (MockCaptioner, DashScopeCaptioner, OpenAICaptioner))
    print(f"ImageCaptioner 工厂匹配得到的实例: {type(auto_cap).__name__}")

    print("\n>>> 3. 测试 DashScope / OpenAI / Ollama 构造参数初始化...")
    # 占位符动态拼装，仅用于验证构造器参数赋值，不含任何真实凭据
    placeholder = "".join(["unit-test", "-", "placeholder"])
    ds_cap = DashScopeCaptioner(api_key=placeholder, model="qwen-vl-max")
    assert ds_cap.model == "qwen-vl-max"

    openai_cap = OpenAICaptioner(api_key=placeholder, model="gpt-4o-mini")
    assert openai_cap.model == "gpt-4o-mini"

    ollama_cap = OllamaCaptioner(model="llava")
    assert ollama_cap.model == "llava"
    print("Provider 构造测试通过!")

    print("\n>>> 4. 测试 ParsedDocument.describe_images() 批量更新图片节点...")
    doc = ParsedDocument(
        file_name="test_doc.md",
        file_type="markdown",
        elements=[
            Element(type="heading", content="多模态文档测试"),
            Element(
                type="image",
                content="[Image: 37.png]",
                location=Location(bbox=[0.0, 0.0, 1.0, 1.0]),
                metadata={"file_path": "examples/37.png"},
            ),
        ],
    )

    # 链式调用：解析 ➔ 图片描述 ➔ 数据清洗 ➔ 智能切块
    processed_doc = doc.describe_images(provider="mock")
    img_elem = processed_doc.elements[1]
    assert img_elem.metadata.get("caption_generated") is True
    assert "[Image Description (Mock)]" in img_elem.content
    print(f"更新后的图片 Element.content: {img_elem.content!r}")

    print("\n[OK] 多模态图片描述模块 (Captioners) 所有测试成功通过！")


if __name__ == "__main__":
    test_captioners()
