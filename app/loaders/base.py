from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models import ParsedDocument


@dataclass
class BatchParsedDocument:
    """
    批量解析结果容器类，聚合存储多个 ParsedDocument
    """

    documents: list[ParsedDocument] = field(default_factory=list)
    failed_files: list[dict[str, str]] = field(default_factory=list)  # 记录解析失败的文件及原因

    def to_langchain_documents(self) -> list[Any]:
        """将所有解析成功的文档统一聚合导出为标准的 LangChain Document 列表"""
        all_docs = []
        for doc in self.documents:
            all_docs.extend(doc.to_langchain_documents())
        return all_docs

    def clean(self, pipeline: Any = None) -> "BatchParsedDocument":
        """对容器内所有文档一键链式执行数据清洗"""
        cleaned_docs = [doc.clean(pipeline=pipeline) for doc in self.documents]
        return BatchParsedDocument(
            documents=cleaned_docs,
            failed_files=self.failed_files,
        )

    def describe_images(self, captioner: Any = None, provider: str = "auto", **kwargs: Any) -> "BatchParsedDocument":
        """对容器内所有文档一键批量调用多模态大模型生成图片描述"""
        described_docs = [doc.describe_images(captioner=captioner, provider=provider, **kwargs) for doc in self.documents]
        return BatchParsedDocument(
            documents=described_docs,
            failed_files=self.failed_files,
        )


class BaseLoader(ABC):
    """批量与归档加载器抽象基类"""

    @abstractmethod
    def load(self) -> BatchParsedDocument:
        """
        执行加载与批量解析逻辑

        Returns:
            包含所有成功解析文档的 BatchParsedDocument 容器对象
        """
        pass
