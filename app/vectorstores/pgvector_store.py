import os
from typing import Any

from .base import BaseVectorStore, Document

from .base import BaseVectorStore
from .chroma_store import ChromaStore
from .embeddings import EmbeddingsFactory

# 与 docker-compose.yml 中 pgvector 服务一致的连接串（库名 omni_rag / 密码 postgrespassword）
DEFAULT_PGVECTOR_DSN = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/omni_rag"


class PGVectorStore(BaseVectorStore):
    """
    PostgreSQL (pgvector 插件) 企业向量存储适配器：
    直接利用企业已有 PostgreSQL 关系型数据库，实现 SQL 逻辑与向量语义无缝 JOIN 混查。

    连接串优先级：显式入参 > env DATABASE_URL（与任务状态持久化共用同一实例）> 默认值。
    说明：默认库名必须与 docker-compose 中实际创建的库保持一致，否则会静默降级到本地快照。
    """

    def __init__(
        self,
        connection_string: str | None = None,
        collection_name: str = "omni_rag_pgvector",
        embeddings: Any | None = None,
    ):
        self.connection_string = connection_string or os.environ.get("DATABASE_URL") or DEFAULT_PGVECTOR_DSN
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
