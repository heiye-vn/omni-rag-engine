import json
from pathlib import Path
from app.models import Element, Location, ParsedDocument
from app.parsers.txt import TxtParser
from app.parsers.markdown import MarkdownParser
from app.parsers.docx import DOCXParser


def test_models_serialization():
    print(">>> 1. 测试 Element 与 Location 的创建与序列化...")
    loc = Location(start_line=10, end_line=12, bbox=[0.1, 0.2, 0.5, 0.8])
    elem = Element(type="heading", content="测试标题", location=loc, raw_content="## 测试标题")

    assert elem.id is not None
    assert len(elem.id) == 12  # UUID 截取 12 位
    print(f"生成的 Element UUID: {elem.id}")

    elem_dict = elem.to_dict()
    assert elem_dict["location"]["start_line"] == 10
    json_str = json.dumps(elem_dict, ensure_ascii=False)
    print(f"Element JSON: {json_str}")

    print(">>> 2. 测试 TxtParser 位置与 JSON 转换...")
    test_txt_path = Path("tests/sample.txt")
    test_txt_path.parent.mkdir(exist_ok=True)
    test_txt_path.write_text("第一行文本\n第二行文本\n\n第四行文本", encoding="utf-8")

    parser = TxtParser()
    parsed_doc = parser.parse(str(test_txt_path))
    assert len(parsed_doc.elements) == 3
    assert parsed_doc.elements[0].location.start_line == 1
    assert parsed_doc.elements[2].location.start_line == 4

    doc_dict = parsed_doc.to_dict()
    doc_json = json.dumps(doc_dict, ensure_ascii=False, indent=2)
    print("TXT 解析与序列化成功!")

    print(">>> 3. 测试 MarkdownParser 定位与转化...")
    test_md_path = Path("tests/sample.md")
    test_md_path.write_text("# 标题一\n\n这是一个段落内容。\n\n- 列表项1\n- 列表项2", encoding="utf-8")

    md_parser = MarkdownParser()
    md_doc = md_parser.parse(str(test_md_path))
    assert len(md_doc.elements) > 0
    first_elem = md_doc.elements[0]
    assert first_elem.type == "heading"
    assert first_elem.location.start_line == 1

    md_json = json.dumps(md_doc.to_dict(), ensure_ascii=False)
    print("Markdown 解析与序列化成功!")

    # 清理临时文件
    if test_txt_path.exists():
        test_txt_path.unlink()
    if test_md_path.exists():
        test_md_path.unlink()
    if test_txt_path.parent.exists() and not list(test_txt_path.parent.glob("*")):
        test_txt_path.parent.rmdir()

    print("\n[OK] 所有测试通过！模型与解析器完美支持 UUID、切片定位与 JSON 序列化！")


if __name__ == "__main__":
    test_models_serialization()
