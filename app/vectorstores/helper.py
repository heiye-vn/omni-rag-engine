from typing import Any

from .base import BaseVectorStore
from .chroma_store import ChromaStore
from .embeddings import EmbeddingsFactory
from .faiss_store import FAISSStore
from .milvus_store import MilvusStore
from .pgvector_store import PGVectorStore
from .qdrant_store import QdrantStore


class VectorStoreFactory:
    """向量数据库统一路由工厂"""

    @classmethod
    def get_vectorstore(
        cls,
        store_type: str = "chroma",
        embeddings: Any | None = None,
        **kwargs: Any,
    ) -> BaseVectorStore:
        store_type = store_type.lower()
        emb = embeddings or EmbeddingsFactory.get_embeddings()

        if store_type == "chroma":
            return ChromaStore(embeddings=emb, **kwargs)
        elif store_type == "faiss":
            return FAISSStore(embeddings=emb, **kwargs)
        elif store_type == "milvus":
            return MilvusStore(embeddings=emb, **kwargs)
        elif store_type in ("pgvector", "postgres", "postgresql"):
            return PGVectorStore(embeddings=emb, **kwargs)
        elif store_type == "qdrant":
            return QdrantStore(embeddings=emb, **kwargs)
        else:
            print(f"[Warning] 未知向量库类型 '{store_type}'，默认路由至 ChromaStore")
            return ChromaStore(embeddings=emb, **kwargs)
