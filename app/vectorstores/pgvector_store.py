from typing import Any

from .base import BaseVectorStore, Document

from .base import BaseVectorStore
from .chroma_store import ChromaStore
from .embeddings import EmbeddingsFactory


class PGVectorStore(BaseVectorStore):
    """
    PostgreSQL (pgvector 插件) 企业向量存储适配器：
    直接利用企业已有 PostgreSQL 关系型数据库，实现 SQL 逻辑与向量语义无缝 JOIN 混查。
    """

    def __init__(
        self,
        connection_string: str = "postgresql+psycopg://postgres:postgres@localhost:5432/rag_db",
        collection_name: str = "omni_rag_pgvector",
        embeddings: Any | None = None,
    ):
        self.connection_string = connection_string
        self.collection_name = collection_name
        self.embeddings = embeddings or EmbeddingsFactory.get_embeddings()

    def add_documents(self, documents: list[Document], **kwargs: Any) -> Any:
        if not documents:
            return None

        try:
            from langchain_community.vectorstores import PGVector

            vectorstore = PGVector.from_documents(
                embedding=self.embeddings,
                documents=documents,
                collection_name=self.collection_name,
                connection_string=self.connection_string,
            )
            return vectorstore
        except Exception as e:
            print(f"[Info] 无法连接到真实 PostgreSQL (pgvector) 服务端: {e}。平滑降级使用本地磁盘存储。")
            fallback = ChromaStore(persist_directory=f"./pgvector_fallback_db/{self.collection_name}", embeddings=self.embeddings)
            return fallback.add_documents(documents)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        try:
            from langchain_community.vectorstores import PGVector

            vectorstore = PGVector(
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
                connection_string=self.connection_string,
            )
            return vectorstore.similarity_search(query, k=k, **kwargs)
        except Exception:
            fallback = ChromaStore(persist_directory=f"./pgvector_fallback_db/{self.collection_name}", embeddings=self.embeddings)
            return fallback.similarity_search(query, k=k)
