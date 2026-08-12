from typing import Any

from .base import BaseVectorStore, Document

from .base import BaseVectorStore
from .chroma_store import ChromaStore
from .embeddings import EmbeddingsFactory


class QdrantStore(BaseVectorStore):
    """
    Qdrant (Rust 高性能下一代向量搜索引擎) 适配器：
    具备极速高并发向量检索与强大的 Payload 元数据过滤能力。
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection_name: str = "omni_rag_qdrant",
        embeddings: Any | None = None,
    ):
        self.url = url
        self.collection_name = collection_name
        self.embeddings = embeddings or EmbeddingsFactory.get_embeddings()

    def add_documents(self, documents: list[Document], **kwargs: Any) -> Any:
        if not documents:
            return None

        try:
            from langchain_community.vectorstores import Qdrant

            vectorstore = Qdrant.from_documents(
                documents,
                self.embeddings,
                url=self.url,
                collection_name=self.collection_name,
            )
            return vectorstore
        except Exception as e:
            print(f"[Info] 无法连接到真实 Qdrant 服务端 ({self.url}): {e}。平滑降级使用本地磁盘存储。")
            fallback = ChromaStore(persist_directory=f"./qdrant_fallback_db/{self.collection_name}", embeddings=self.embeddings)
            return fallback.add_documents(documents)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        try:
            from langchain_community.vectorstores import Qdrant

            vectorstore = Qdrant(
                embeddings=self.embeddings,
                url=self.url,
                collection_name=self.collection_name,
            )
            return vectorstore.similarity_search(query, k=k, **kwargs)
        except Exception:
            fallback = ChromaStore(persist_directory=f"./qdrant_fallback_db/{self.collection_name}", embeddings=self.embeddings)
            return fallback.similarity_search(query, k=k)
