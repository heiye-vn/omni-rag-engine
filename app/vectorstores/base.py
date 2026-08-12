from abc import ABC, abstractmethod
from typing import Any

from dataclasses import dataclass, field

try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document
    except ImportError:
        @dataclass
        class Document:
            page_content: str
            metadata: dict = field(default_factory=dict)


class BaseVectorStore(ABC):
    """向量数据库适配器统一抽象基类"""

    @abstractmethod
    def add_documents(self, documents: list[Document], **kwargs: Any) -> Any:
        """
        向向量数据库中批量添加/写入 LangChain Document 切片

        Args:
            documents: 待写入的 Document 列表

        Returns:
            写入成功后的文档 ID 列表或写入状态
        """
        pass

    @abstractmethod
    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        """
        基于查询文本对向量数据库发起向量相似度检索

        Args:
            query: 用户提问或查询语句
            k: Top-K 召回数量

        Returns:
            按相似度排序的最高相关 LangChain Document 列表
        """
        pass
