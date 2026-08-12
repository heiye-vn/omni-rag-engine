from app.cleaners import HeaderFooterCleaner, SimHashDeduplicator
from app.models import Element, Location, ParsedDocument


def test_header_footer_cleaner():
    print(">>> 1. 测试 HeaderFooterCleaner 跨页页眉页脚自动过滤...")
    # 模拟一个 3 页的 PDF，每一页顶部都有 "华为技术有限公司 保密文件"，底部都有 "第 X 页"
    elements = [
        # Page 1
        Element(type="text", content="华为技术有限公司 保密文件", location=Location(page_number=1, bbox=[0.1, 0.05, 0.9, 0.10])),
        Element(type="heading", content="第一章 系统架构设计", location=Location(page_number=1, bbox=[0.1, 0.20, 0.9, 0.30])),
        Element(type="text", content="本文档介绍了核心管道架构方案。", location=Location(page_number=1, bbox=[0.1, 0.35, 0.9, 0.50])),
        Element(type="text", content="内部资料 请勿外传 - 第 1 页", location=Location(page_number=1, bbox=[0.1, 0.90, 0.9, 0.95])),

        # Page 2
        Element(type="text", content="华为技术有限公司 保密文件", location=Location(page_number=2, bbox=[0.1, 0.05, 0.9, 0.10])),
        Element(type="heading", content="第二章 数据清洗模块", location=Location(page_number=2, bbox=[0.1, 0.20, 0.9, 0.30])),
        Element(type="text", content="清洗管道负责去除无用字符与敏感信息。", location=Location(page_number=2, bbox=[0.1, 0.35, 0.9, 0.50])),
        Element(type="text", content="内部资料 请勿外传 - 第 2 页", location=Location(page_number=2, bbox=[0.1, 0.90, 0.9, 0.95])),

        # Page 3
        Element(type="text", content="华为技术有限公司 保密文件", location=Location(page_number=3, bbox=[0.1, 0.05, 0.9, 0.10])),
        Element(type="heading", content="第三章 总结", location=Location(page_number=3, bbox=[0.1, 0.20, 0.9, 0.30])),
        Element(type="text", content="内部资料 请勿外传 - 第 3 页", location=Location(page_number=3, bbox=[0.1, 0.90, 0.9, 0.95])),
    ]

    cleaner = HeaderFooterCleaner(frequency_threshold=0.3)
    cleaned = cleaner.clean(elements)

    contents = [e.content for e in cleaned]
    assert "华为技术有限公司 保密文件" not in contents
    assert not any("内部资料 请勿外传" in c for c in contents)
    assert "第一章 系统架构设计" in contents
    assert "第二章 数据清洗模块" in contents
    print(f"原始 11 个节点，过滤页眉页脚后保留 {len(cleaned)} 个节点！成功剔除所有跨页页眉与页脚！")


def test_simhash_deduplicator():
    print("\n>>> 2. 测试 SimHashDeduplicator 海明距离语义近重复去重...")
    elements = [
        Element(type="text", content="这是一段非常标准的企业级 RAG 数据清洗管道测试示例文本。"),
        Element(type="text", content="这是一段非常标准的企业级 RAG 数据清洗管道测试示例文本。"),  # 完全重复
        Element(type="text", content="这是一段极度标准的企业级 RAG 数据清洗管道测试示例文本！"), # 近重复 (变动一两个字)
        Element(type="text", content="完全不一样的全新章节内容，讨论关于人工智能大模型向量化的应用。"), # 独立非重复
    ]

    cleaner = SimHashDeduplicator(distance_threshold=15)
    cleaned = cleaner.clean(elements)

    assert len(cleaned) == 2
    assert cleaned[0].content == "这是一段非常标准的企业级 RAG 数据清洗管道测试示例文本。"
    assert "人工智能大模型向量化" in cleaned[1].content
    print(f"原始 4 个文本段落，SimHash 去重后保留 {len(cleaned)} 个完全唯一的独立段落！")


def test_parsed_document_integration():
    print("\n>>> 3. 测试 ParsedDocument.clean() 默认链式集成...")
    doc = ParsedDocument(
        file_name="test.pdf",
        file_type="pdf",
        elements=[
            Element(type="text", content="华为技术有限公司 保密文件", location=Location(page_number=1, bbox=[0.1, 0.05, 0.9, 0.10])),
            Element(type="text", content="华为技术有限公司 保密文件", location=Location(page_number=2, bbox=[0.1, 0.05, 0.9, 0.10])),
            Element(type="text", content="欢迎使用 omni-rag-engine 预处理平台！"),
            Element(type="text", content="欢迎使用 omni-rag-engine 预处理平台！"),
        ]
    )

    cleaned_doc = doc.clean()
    contents = [e.content for e in cleaned_doc.elements]
    assert "华为技术有限公司 保密文件" not in contents
    assert any("欢迎使用 omni-rag-engine 预处理平台" in c for c in contents)
    print(f"ParsedDocument.clean() 链式调用成功！剔除页眉页脚与重复文本，最终保留干净节点数: {len(cleaned_doc.elements)}")


if __name__ == "__main__":
    test_header_footer_cleaner()
    test_simhash_deduplicator()
    test_parsed_document_integration()
    print("\n[OK] 文档去重与跨页页眉页脚过滤模块所有测试成功通过！")
