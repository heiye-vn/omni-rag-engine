from abc import ABC, abstractmethod
from app.models import ParsedDocument


class BaseEnricher(ABC):
    """语义与上下文增强器抽象基类"""

    @abstractmethod
    def enrich(self, doc: ParsedDocument) -> ParsedDocument:
        """
        对 ParsedDocument 进行语义或上下文增强处理

        Args:
            doc: 原始 ParsedDocument 实例

        Returns:
            增强处理后的新 ParsedDocument 实例
        """
        pass
