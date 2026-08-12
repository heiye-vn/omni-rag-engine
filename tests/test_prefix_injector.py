from app.enrichers import ContextPrefixInjector
from app.models import Element, Location, ParsedDocument


def test_prefix_injector():
    print(">>> 1. 测试 ContextPrefixInjector 动态标题栈与前缀缝合...")
    doc = ParsedDocument(
        file_name="核心服务器配置手册.docx",
        file_type="docx",
        elements=[
            Element(type="heading", content="第一章 网络规格设计", metadata={"level": 1}),
            Element(type="heading", content="1.1 核心防火墙规格", metadata={"level": 2}),
            Element(type="text", content="核心防火墙支持最高 100Gbps 吞吐量与双机热备能力。"),
            Element(type="heading", content="1.2 交换机配置", metadata={"level": 2}),
            Element(type="text", content="交换机支持 48 个万兆光口与 L3 路由协议。"),
            Element(type="heading", content="第二章 存储架构", metadata={"level": 1}),
            Element(type="text", content="存储节点配备 NVMe SSD 阵列。"),
        ],
    )

    injector = ContextPrefixInjector(inject_file_name=True, inject_header_path=True)
    enriched_doc = injector.enrich(doc)

    elems = enriched_doc.elements
    # 验证 1.1 核心防火墙规格 下的段落
    p1 = elems[2]
    assert "【文档: 核心服务器配置手册.docx | 上下文: 第一章 网络规格设计 > 1.1 核心防火墙规格】" in p1.content
    assert p1.metadata["header_path"] == "第一章 网络规格设计 > 1.1 核心防火墙规格"
    print(f"段落 1 前缀缝合成果:\n{p1.content}")

    # 验证 1.2 交换机配置 (证明 H2 升级切换成功)
    p2 = elems[4]
    assert "上下文: 第一章 网络规格设计 > 1.2 交换机配置" in p2.content

    # 验证 第二章 存储架构 (证明 H1 覆盖回退成功)
    p3 = elems[6]
    assert "上下文: 第二章 存储架构" in p3.content
    print("标题栈 H1->H2 升级与回退验证成功！")


def test_parsed_document_enrich_context_integration():
    print("\n>>> 2. 测试 ParsedDocument.enrich_context() 链式全流程集成...")
    doc = ParsedDocument(
        file_name="API_Guide.md",
        file_type="markdown",
        elements=[
            Element(type="heading", content="用户认证 API", metadata={"level": 1}),
            Element(type="text", content="POST /api/v1/login 接口说明。"),
        ],
    )

    # 链式：解析 ➔ 清洗 ➔ 上下文前缀增强 ➔ 智能切块
    langchain_docs = doc.clean().enrich_context().split(strategy="auto")
    assert len(langchain_docs) > 0
    first_chunk = langchain_docs[0]
    assert "【文档: API_Guide.md | 上下文: 用户认证 API】" in first_chunk.page_content
    print(f"端到端链式 LangChain Document 切片内容 preview:\n{first_chunk.page_content}")

    print("\n[OK] 上下文前缀自动缝合注入器 (Context Prefix Injector) 所有测试成功通过！")


if __name__ == "__main__":
    test_prefix_injector()
    test_parsed_document_enrich_context_integration()
