import json
import math
import os
import re
from typing import Any

from .base import BaseVectorStore, Document
from .embeddings import EmbeddingsFactory


class ChromaStore(BaseVectorStore):
    """
    Chroma 本地嵌入式磁盘持久化向量数据库适配器：
    数据自动序列化落盘保存至指定目录 (默认 ./chroma_db)，
    原生支持 Metadata Filter 过滤与高维度向量余弦相似度检索。
    """

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "omni_rag_collection",
        embeddings: Any | None = None,
    ):
        # 集合名属于外部可控输入，在构造边界即做字符白名单净化，
        # 确保后续所有落盘拼接都不可能携带路径分隔符或父目录引用
        self.persist_directory = persist_directory
        self.collection_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(collection_name)).strip("._") or "omni_rag_collection"
        self.embeddings = embeddings or EmbeddingsFactory.get_embeddings()

    def add_documents(self, documents: list[Document], **kwargs: Any) -> Any:
        if not documents:
            return []

        # 校验是否具备真实 chromadb 库
        try:
            from langchain_community.vectorstores import Chroma

            vectorstore = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                collection_name=self.collection_name,
                persist_directory=self.persist_directory,
            )
            return vectorstore
        except Exception as e:
            # 优雅平滑降级：使用轻量 JSON/Dict 磁盘快照存取
            return self._fallback_add_documents(documents)

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        try:
            from langchain_community.vectorstores import Chroma

            vectorstore = Chroma(
                collection_name=self.collection_name,
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings,
            )
            return vectorstore.similarity_search(query, k=k, **kwargs)
        except Exception:
            return self._fallback_similarity_search(query, k=k)

    def _fallback_add_documents(self, documents: list[Document]) -> str:
        """纯 Python 零依赖本地快照存储降级"""
        # 三重防穿越：白名单净化 ➔ 显式拒绝分隔符与父目录引用 ➔ realpath 目录包含校验
        safe_collection = re.sub(r"[^A-Za-z0-9._-]", "_", str(self.collection_name)).strip("._")
        safe_collection = safe_collection or "omni_rag_collection"
        if ".." in safe_collection or "/" in safe_collection or "\\" in safe_collection:
            raise ValueError(f"非法的集合名: {self.collection_name!r}")
        allowed_real = os.path.realpath(self.persist_directory)
        dump_real = os.path.realpath(os.path.join(allowed_real, f"{safe_collection}.json"))
        if os.path.dirname(dump_real) != allowed_real:
            raise ValueError("非法的快照存储路径，已越出目标目录")

        os.makedirs(allowed_real, exist_ok=True)
        dump_path = dump_real

        texts = [doc.page_content for doc in documents]
        vecs = self.embeddings.embed_documents(texts)

        records = []
        if os.path.exists(dump_path):
            try:
                with open(dump_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []

        for doc, vec in zip(documents, vecs):
            records.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "vector": vec,
            })

        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        return dump_path

    def _fallback_similarity_search(self, query: str, k: int = 4) -> list[Document]:
        # 三重防穿越：白名单净化 ➔ 显式拒绝分隔符与父目录引用 ➔ realpath 目录包含校验
        safe_collection = re.sub(r"[^A-Za-z0-9._-]", "_", str(self.collection_name)).strip("._")
        safe_collection = safe_collection or "omni_rag_collection"
        if ".." in safe_collection or "/" in safe_collection or "\\" in safe_collection:
            raise ValueError(f"非法的集合名: {self.collection_name!r}")
        allowed_real = os.path.realpath(self.persist_directory)
        dump_path = os.path.realpath(os.path.join(allowed_real, f"{safe_collection}.json"))
        if os.path.dirname(dump_path) != allowed_real:
            raise ValueError("非法的快照存储路径，已越出目标目录")

        if not os.path.exists(dump_path):
            return []

        with open(dump_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        query_vec = self.embeddings.embed_query(query)

        scored = []
        for r in records:
            doc_vec = r.get("vector", [])
            sim = self._cosine_similarity(query_vec, doc_vec)
            scored.append((sim, Document(page_content=r["page_content"], metadata=r["metadata"])))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:k]]

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
