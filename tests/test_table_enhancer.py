from app.enrichers import TableEnhancer
from app.models import Element, ParsedDocument


def test_table_enhancer():
    print(">>> 1. 测试 TableEnhancer 自动捕获关联表格标题与 KV 提炼...")
    table_md = (
        "| 部门 | 2026预算(万) | 负责人 |\n"
        "| --- | --- | --- |\n"
        "| 基础架构部 | 1200 | 张三 |\n"
        "| 人工智能实验室 | 3500 | 李四 |\n"
    )

    doc = ParsedDocument(
        file_name="公司预算报告.docx",
        file_type="docx",
        elements=[
            Element(type="heading", content="第三章 部门财务预算", metadata={"level": 1}),
            Element(type="text", content="表 3-1: 2026年二季度各部门预算对比表"),
            Element(type="table", content=table_md),
            Element(type="text", content="注：以上预算包含硬件采购费用。"),
        ],
    )

    enhancer = TableEnhancer(associate_caption=True, generate_kv_summary=True)
    enriched_doc = enhancer.enrich(doc)

    table_elem = enriched_doc.elements[2]
    assert table_elem.metadata.get("table_caption") == "表 3-1: 2026年二季度各部门预算对比表"
    assert "【表格: 表 3-1: 2026年二季度各部门预算对比表】" in table_elem.content

    kv_pairs = table_elem.metadata.get("kv_pairs", [])
    assert len(kv_pairs) == 2
    assert kv_pairs[0]["部门"] == "基础架构部"
    assert kv_pairs[0]["2026预算(万)"] == "1200"
    assert kv_pairs[1]["负责人"] == "李四"
    print("表格标题捕获成功！标题:", table_elem.metadata["table_caption"])
    print("结构化 Key-Value 行数据提炼成功! KV Preview:", kv_pairs[0])


def test_table_enricher_full_pipeline():
    print("\n>>> 2. 测试 ParsedDocument.enrich_tables() 全流程链式集成...")
    table_md = (
        "| 接口名 | 方法 | 耗时(ms) |\n"
        "| --- | --- | --- |\n"
        "| /api/v1/parse | POST | 45 |\n"
    )

    doc = ParsedDocument(
        file_name="性能测试.pdf",
        file_type="pdf",
        elements=[
            Element(type="text", content="表 1: 核心接口性能指标"),
            Element(type="table", content=table_md),
        ],
    )

    # 全流畅链式：解析 ➔ 清洗 ➔ 表格结构化增强 ➔ 上下文前缀缝合 ➔ 智能切块
    chunks = doc.clean().enrich_tables().enrich_context().split(strategy="auto")
    assert len(chunks) > 0
    table_chunk = chunks[0]
    assert "【表格: 表 1: 核心接口性能指标】" in table_chunk.page_content
    print("端到端表格自解释切片内容 preview:\n", table_chunk.page_content)

    print("\n[OK] 复杂表格结构化与上下文增强器 (TableEnhancer) 所有测试成功通过！")


if __name__ == "__main__":
    test_table_enhancer()
    test_table_enricher_full_pipeline()
