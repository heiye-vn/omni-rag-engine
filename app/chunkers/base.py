from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models import Element, Location, ParsedDocument


@dataclass
class Chunk:
    """
    智能切片块（包含多个 Element 的归一化组装与溯源信息）
    """

    content: str
    chunk_id: str
    element_ids: list[str] = field(default_factory=list)
    parent_id: str | None = None
    location: Location | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        res = {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "element_ids": self.element_ids,
            "parent_id": self.parent_id,
            "location": self.location.to_dict() if self.location else None,
            "metadata": self.metadata,
        }
        return {k: v for k, v in res.items() if v is not None}


class BaseChunker(ABC):
    """智能切块器抽象基类"""

    @abstractmethod
    def split_document(self, doc: ParsedDocument) -> Any:
        """
        对 ParsedDocument 进行智能切块

        Args:
            doc: 待切块的 ParsedDocument 实例

        Returns:
            根据具体策略返回切块后的 Document 列表或 (child_docs, parent_store) 元组
        """
        pass
