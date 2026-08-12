from app.cleaners import (
    CleanerPipeline,
    ControlCharCleaner,
    LengthFilterCleaner,
    PIIMaskerCleaner,
    WhitespaceCleaner,
)
from app.models import Element, ParsedDocument


def test_cleaner_rules():
    print(">>> 1. 测试 ControlCharCleaner 控制字符清除...")
    cleaner = ControlCharCleaner()
    elem = Element(type="text", content="Hello\x00World\x08!", raw_content="Hello\x00World\x08!")
    res = cleaner.clean_element(elem)
    assert res is not None
    assert res.content == "HelloWorld!"
    print(f"清洗后 content: {res.content!r}")

    print(">>> 2. 测试 WhitespaceCleaner 空白与全半角归一化...")
    ws_cleaner = WhitespaceCleaner()
    elem_ws = Element(type="text", content="  张   三   \n\n\n  李   四  ")
    res_ws = ws_cleaner.clean_element(elem_ws)
    assert res_ws is not None
    assert res_ws.content == "张 三\n\n李 四"
    print(f"清洗后 content:\n{res_ws.content!r}")

    print(">>> 3. 测试 PIIMaskerCleaner 敏感数据脱敏...")
    pii_cleaner = PIIMaskerCleaner()
    elem_pii = Element(
        type="text",
        content="联系电话：13812345678，身份证：110101199003072345，邮箱：user@example.com",
    )
    res_pii = pii_cleaner.clean_element(elem_pii)
    assert res_pii is not None
    assert "138****5678" in res_pii.content
    assert "110101********2345" in res_pii.content
    assert "u**r@example.com" in res_pii.content or "u*r@example.com" in res_pii.content
    print(f"脱敏后 content:\n{res_pii.content}")

    print(">>> 4. 测试 LengthFilterCleaner 无意义节点过滤...")
    lf_cleaner = LengthFilterCleaner(min_length=3)
    elem_short = Element(type="text", content="a")
    elem_punct = Element(type="text", content="...")
    elem_valid = Element(type="text", content="正常有效文本")

    assert lf_cleaner.clean_element(elem_short) is None
    assert lf_cleaner.clean_element(elem_punct) is None
    assert lf_cleaner.clean_element(elem_valid) is not None
    print("节点过滤规则测试成功!")

    print(">>> 5. 测试 ParsedDocument.clean() 端到端管线...")
    doc = ParsedDocument(
        file_name="test.txt",
        file_type="txt",
        elements=[
            Element(type="text", content="联系人电话: 13988889999\x00"),
            Element(type="text", content=".."),  # 将被过滤
            Element(type="text", content="  有效    内容  "),
        ],
    )

    cleaned_doc = doc.clean()
    assert len(cleaned_doc.elements) == 2
    assert "139****9999" in cleaned_doc.elements[0].content
    assert cleaned_doc.elements[1].content == "有效 内容"
    print("ParsedDocument.clean() 端到端链式清洗成功!")

    print("\n[OK] 数据清洗模块 (Cleaners) 全部测试成功通过！")


if __name__ == "__main__":
    test_cleaner_rules()
