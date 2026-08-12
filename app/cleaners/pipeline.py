from app.models import Element
from .base import BaseCleaner
from .rules import (
    ControlCharCleaner,
    LengthFilterCleaner,
    PIIMaskerCleaner,
    WhitespaceCleaner,
)


class CleanerPipeline:
    """
    数据清洗管道组合器：支持链式添加清洗规则并依序处理 Element 列表
    """

    def __init__(self, cleaners: list[BaseCleaner] | None = None):
        self._cleaners: list[BaseCleaner] = cleaners if cleaners is not None else []

    def add_cleaner(self, cleaner: BaseCleaner) -> "CleanerPipeline":
        """链式添加一条清洗规则"""
        self._cleaners.append(cleaner)
        return self

    def clean(self, elements: list[Element]) -> list[Element]:
        """
        依次对 Element 列表执行所有清洗规则 (支持单节点清洗与列表级全局去重)

        Args:
            elements: 原始 Element 节点列表

        Returns:
            清洗与过滤后的 Element 节点列表
        """
        current_elements = list(elements)
        for cleaner in self._cleaners:
            current_elements = cleaner.clean(current_elements)
            if not current_elements:
                break

        return current_elements

    @classmethod
    def default(cls, enable_deduplication: bool = True) -> "CleanerPipeline":
        """
        构造预设的标准生产级清洗管道：
        包含控制字符过滤、Unicode 标准化与空白压缩、PII 敏感数据脱敏、短垃圾字符过滤与跨页页眉页脚/SimHash 去重
        """
        from .deduplicator import HeaderFooterCleaner, SimHashDeduplicator

        cleaners = [
            ControlCharCleaner(),
            WhitespaceCleaner(),
            PIIMaskerCleaner(),
            LengthFilterCleaner(min_length=2),
        ]
        if enable_deduplication:
            cleaners.extend([
                HeaderFooterCleaner(),
                SimHashDeduplicator(),
            ])
        return cls(cleaners)
