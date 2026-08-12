from abc import ABC, abstractmethod

from app.models import Element


class BaseCleaner(ABC):
    """数据清洗规则抽象基类（支持单 Element 节点清洗与全局 Element 列表去重）"""

    def clean_element(self, element: Element) -> Element | None:
        """对单个 Element 节点进行清洗（可重写）"""
        return element

    def clean(self, elements: list[Element]) -> list[Element]:
        """
        对 Element 列表执行清洗规则（默认循环调用 clean_element，列表级清洗器可重写本方法）
        """
        cleaned: list[Element] = []
        for elem in elements:
            res = self.clean_element(elem)
            if res is not None:
                cleaned.append(res)
        return cleaned
