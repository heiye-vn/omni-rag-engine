import os
from typing import Any

from .base import BaseVectorStore, Document

from .base import BaseVectorStore
from .chroma_store import ChromaStore
from .embeddings import EmbeddingsFactory


class FAISSStore(BaseVectorStore):
    """
    FAISS (Facebook AI Similarity Search) 极速向量索引适配器：
    基于 CPU 高吞吐向量检索，支持本地快照落盘导出 (index.faiss)。
    """

    def __init__(
        self,
        folder_path: str = "./faiss_index",
        index_name: str = "index",
        embeddings: Any | None = None,
    ):
        self.folder_path = folder_path
        self.index_name = index_name
        self.embeddings = embeddings or EmbeddingsFactory.get_embeddings()

    def add_documents(self, documents: list[Document], **kwargs: Any) -> Any:
        if not documents:
            return None

        try:
            from langchain_community.vectorstores import FAISS

            vectorstore = FAISS.from_documents(documents, self.embeddings)
            os.makedirs(self.folder_path, exist_ok=True)
            vectorstore.save_local(self.folder_path, index_name=self.index_name)
            return vectorstore
        except Exception:
            # 优雅平滑降级为通用存储
            fallback = ChromaStore(persist_directory=self.folder_path, collection_name=self.index_name, embeddings=self.embeddings)
            return fallback.add_documents(documents)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        try:
            from langchain_community.vectorstores import FAISS

            vectorstore = FAISS.load_local(
                self.folder_path,
                self.embeddings,
                index_name=self.index_name,
                allow_dangerous_deserialization=True,
            )
            return vectorstore.similarity_search(query, k=k, **kwargs)
        except Exception:
            fallback = ChromaStore(persist_directory=self.folder_path, collection_name=self.index_name, embeddings=self.embeddings)
            return fallback.similarity_search(query, k=k)
