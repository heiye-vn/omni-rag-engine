import json
from pathlib import Path
import openpyxl

from app.parsers.xlsx import XLSXParser


def test_xlsx_parser():
    print(">>> 1. 创建临时测试用 Excel 文件 (sample.xlsx)...")
    test_xlsx_path = Path("tests/sample.xlsx")
    test_xlsx_path.parent.mkdir(exist_ok=True)

    wb = openpyxl.Workbook()

    # Sheet 1: 员工表
    ws1 = wb.active
    ws1.title = "员工信息表"
    ws1.append(["ID", "姓名", "部门"])
    ws1.append([101, "张三", "技术部"])
    ws1.append([102, "李四", "产品部"])

    # Sheet 2: 销售数据表
    ws2 = wb.create_sheet(title="销售数据")
    ws2.append(["月份", "销售额(万)"])
    ws2.append(["1月", 150])
    ws2.append(["2月", 200])

    wb.save(test_xlsx_path)
    wb.close()

    print(">>> 2. 使用 XLSXParser 进行解析...")
    parser = XLSXParser()
    parsed_doc = parser.parse(str(test_xlsx_path))

    print(f"文件名: {parsed_doc.file_name}")
    print(f"文件类型: {parsed_doc.file_type}")
    print(f"解析到 Element 节点数: {len(parsed_doc.elements)}")

    assert parsed_doc.file_type == "xlsx"
    assert len(parsed_doc.elements) == 2

    # 验证 Sheet 1
    elem1 = parsed_doc.elements[0]
    assert elem1.type == "table"
    assert elem1.metadata["sheet_name"] == "员工信息表"
    assert elem1.location.selector == "员工信息表!A1:C3"
    assert "<table" in elem1.raw_content
    print(f"Sheet1 Selector: {elem1.location.selector}")
    print(f"Sheet1 Markdown:\n{elem1.content}")

    # 验证 Sheet 2
    elem2 = parsed_doc.elements[1]
    assert elem2.type == "table"
    assert elem2.metadata["sheet_name"] == "销售数据"
    assert elem2.location.selector == "销售数据!A1:B3"

    # 验证 JSON 序列化
    doc_dict = parsed_doc.to_dict()
    doc_json = json.dumps(doc_dict, ensure_ascii=False, indent=2)
    assert "员工信息表!A1:C3" in doc_json
    print("JSON 序列化验证成功！")

    # 清理测试文件
    if test_xlsx_path.exists():
        test_xlsx_path.unlink()

    print("\n[OK] XLSXParser 测试全部成功通过！")


if __name__ == "__main__":
    test_xlsx_parser()
