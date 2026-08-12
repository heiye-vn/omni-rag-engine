from typing import Any

from .base import BaseVectorStore, Document

from .base import BaseVectorStore
from .chroma_store import ChromaStore
from .embeddings import EmbeddingsFactory


class MilvusStore(BaseVectorStore):
    """
    Milvus 企业级海量分布式向量数据库适配器：
    专为亿级海量向量生产环境设计，支持高性能向量标量混合过滤。
    在连接不可用或缺失依赖时，自动平滑降级为本地持久化快照，确保系统高可用不崩溃。
    """

    def __init__(
        self,
        uri: str = "http://localhost:19530",
        collection_name: str = "omni_rag_milvus",
        embeddings: Any | None = None,
    ):
        self.uri = uri
        self.collection_name = collection_name
        self.embeddings = embeddings or EmbeddingsFactory.get_embeddings()

    def add_documents(self, documents: list[Document], **kwargs: Any) -> Any:
        if not documents:
            return None

        try:
            from langchain_community.vectorstores import Milvus

            connection_args = {"uri": self.uri}
            vectorstore = Milvus.from_documents(
                documents,
                self.embeddings,
                collection_name=self.collection_name,
                connection_args=connection_args,
            )
            return vectorstore
        except Exception as e:
            print(f"[Info] 无法连接到真实 Milvus 服务端 ({self.uri}): {e}。平滑降级使用本地磁盘存储。")
            fallback = ChromaStore(persist_directory=f"./milvus_fallback_db/{self.collection_name}", embeddings=self.embeddings)
            return fallback.add_documents(documents)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        try:
            from langchain_community.vectorstores import Milvus

            connection_args = {"uri": self.uri}
            vectorstore = Milvus(
                self.embeddings,
                collection_name=self.collection_name,
                connection_args=connection_args,
            )
            return vectorstore.similarity_search(query, k=k, **kwargs)
        except Exception:
            fallback = ChromaStore(persist_directory=f"./milvus_fallback_db/{self.collection_name}", embeddings=self.embeddings)
            return fallback.similarity_search(query, k=k)
