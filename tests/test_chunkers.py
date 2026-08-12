from app.chunkers import (
    AutoChunker,
    HeaderAwareChunker,
    ParentChildChunker,
    SlidingWindowChunker,
)
from app.models import Element, Location, ParsedDocument


def test_chunkers():
    print(">>> 1. 构造具有层级标题、正文、表格与代码块的测试 ParsedDocument...")
    doc = ParsedDocument(
        file_name="test_architecture.md",
        file_type="markdown",
        elements=[
            Element(type="heading", content="第一章 系统架构总览", metadata={"level": 1}, location=Location(start_line=1)),
            Element(type="paragraph", content="本项目是一个企业级 RAG 多模态文档解析与数据治理预处理引擎。", location=Location(start_line=3)),
            Element(type="heading", content="1.1 模块拆分", metadata={"level": 2}, location=Location(start_line=5)),
            Element(type="paragraph", content="模块包含了解析器 Parser、清洗器 Cleaner 以及智能切块器 Chunker。", location=Location(start_line=7)),
            Element(type="code", content="def main():\n    print('Hello RAG')\n", raw_content="```python\ndef main():\n    print('Hello RAG')\n```", location=Location(start_line=9)),
            Element(type="table", content="| 模块 | 说明 |\n|---|---|\n| Parser | 解析 |", raw_content="<table></table>", location=Location(start_line=13)),
        ],
    )

    print(">>> 2. 测试 SlidingWindowChunker 滑动窗口切块...")
    sw = SlidingWindowChunker(chunk_size=150, chunk_overlap=20)
    sw_docs = sw.split_document(doc)
    assert len(sw_docs) > 0
    print(f"滑动窗口切分出 {len(sw_docs)} 个 Chunk 节点")
    print("SlidingWindowChunker #1 page_content:\n", sw_docs[0].page_content)
    assert "primary_element_type" in sw_docs[0].metadata

    print("\n>>> 3. 测试 ParentChildChunker 父子块关联切片...")
    pc = ParentChildChunker(parent_chunk_size=300, child_chunk_size=80)
    child_docs, parent_store = pc.split_document(doc)
    assert len(child_docs) > 0
    assert len(parent_store) > 0
    first_child = child_docs[0]
    assert "parent_id" in first_child.metadata
    parent_id = first_child.metadata["parent_id"]
    assert parent_id in parent_store
    print(f"父子块切分出 {len(child_docs)} 个 Child Docs，{len(parent_store)} 个 Parent Store 关联映射")
    print(f"Child metadata 包含 parent_id={parent_id}")
    print("对应 Parent Document 内容 preview:\n", parent_store[parent_id][:80])

    print("\n>>> 4. 测试 HeaderAwareChunker 标题层级感知切片...")
    ha = HeaderAwareChunker()
    ha_docs = ha.split_document(doc)
    assert len(ha_docs) == 2  # 两个章节
    assert ha_docs[0].metadata["header_path"] == "第一章 系统架构总览"
    assert ha_docs[1].metadata["header_path"] == "第一章 系统架构总览 > 1.1 模块拆分"
    print("HeaderAwareChunker 标题路径导航成功!")
    print(f"章节 2 路径: {ha_docs[1].metadata['header_path']}")

    print("\n>>> 5. 测试 AutoChunker 自动智能路由与 ParsedDocument.split()...")
    auto = AutoChunker()
    detected_strategy = auto.detect_strategy(doc)
    assert detected_strategy == "header_aware"
    print(f"AutoChunker 自动判定最佳策略为: '{detected_strategy}'")

    # 端到端：解析 ➔ 清洗 ➔ 智能切块
    auto_docs = doc.clean().split(strategy="auto")
    assert len(auto_docs) == 2
    print("ParsedDocument.clean().split(strategy='auto') 端到端流水线运行成功!")

    print("\n[OK] 智能切块模块 (Chunkers) 所有 4 种策略全部测试成功通过！")


if __name__ == "__main__":
    test_chunkers()
