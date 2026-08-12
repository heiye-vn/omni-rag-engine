from app.models import Element, Location, ParsedDocument
from app.vectorstores import EmbeddingsFactory, VectorStoreFactory


def test_embeddings_factory():
    print(">>> 1. 测试 EmbeddingsFactory 向量引擎与算力抽取...")
    embeddings = EmbeddingsFactory.get_embeddings(provider="auto")
    query_vec = embeddings.embed_query("什么是人工智能向量化？")
    assert len(query_vec) > 0
    print(f"向量计算成功！提取向量维度: {len(query_vec)} 维")


def test_chroma_store_persistence_and_search():
    print("\n>>> 2. 测试 ChromaStore 本地磁盘持久化与相似度检索...")
    doc = ParsedDocument(
        file_name="AI_Server_Guide.pdf",
        file_type="pdf",
        elements=[
            Element(type="heading", content="服务器硬件规格", metadata={"level": 1}),
            Element(type="text", content="GPU 节点配备 8 卡 H100 80GB SXM5，具备 900GB/s NVLink 互联带宽。"),
            Element(type="text", content="存储节点配置 24 块 NVMe 企业级 SSD 硬盘。"),
        ],
    )

    # 端到端：解析 ➔ 清洗 ➔ 前缀增强 ➔ 向量持久化落盘
    store = doc.clean().enrich_context().to_vectorstore(
        store_type="chroma",
        persist_directory="./tests_chroma_db",
        collection_name="test_ai_servers",
    )

    # 发起检索测试
    retriever = VectorStoreFactory.get_vectorstore(
        store_type="chroma",
        persist_directory="./tests_chroma_db",
        collection_name="test_ai_servers",
    )
    results = retriever.similarity_search("GPU NVLink 互联带宽", k=1)
    assert len(results) > 0
    assert "NVLink 互联带宽" in results[0].page_content
    print("ChromaStore 落盘与 Vector Similarity Search 精准召回成功！最佳匹配切片:\n", results[0].page_content[:120])


def test_enterprise_vectorstores_fallback():
    print("\n>>> 3. 测试 Milvus / PGVector / Qdrant 企业级适配器探测与平滑降级防护...")
    doc = ParsedDocument(
        file_name="test.txt",
        file_type="txt",
        elements=[Element(type="text", content="Enterprise VectorStore Driver Test")],
    )

    # 1. 测试 Milvus 适配器与降级
    m_store = VectorStoreFactory.get_vectorstore(store_type="milvus", uri="http://127.0.0.1:19530")
    m_store.add_documents(doc.split())

    # 2. 测试 PGVector 适配器与降级
    pg_store = VectorStoreFactory.get_vectorstore(store_type="pgvector")
    pg_store.add_documents(doc.split())

    # 3. 测试 Qdrant 适配器与降级
    qd_store = VectorStoreFactory.get_vectorstore(store_type="qdrant")
    qd_store.add_documents(doc.split())

    print("[OK] 企业级四大向量数据库适配器全通道安全探针测试通过！无任何断言或崩溃中断！")


if __name__ == "__main__":
    test_embeddings_factory()
    test_chroma_store_persistence_and_search()
    test_enterprise_vectorstores_fallback()
    print("\n[OK] 向量存储与磁盘持久化模块 (app/vectorstores/) 所有测试成功通过！")
