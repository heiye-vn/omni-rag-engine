from typing import Any

from app.models import ParsedDocument
from .base import BaseChunker
from .header_aware import HeaderAwareChunker
from .parent_child import ParentChildChunker
from .sliding_window import SlidingWindowChunker


class AutoChunker(BaseChunker):
    """
    自适应智能切块路由器 (AutoChunker)

    【核心逻辑】
    自动分析 ParsedDocument 的元素特征与文本长度，自适应智能挑选最匹配的切片策略：
    - 若含有 2 个以上的 heading 标题节点 ➔ 自动路由到 HeaderAwareChunker
    - 若无标题但文本总字数较大 (>=1200 字符) ➔ 自动路由到 ParentChildChunker
    - 其它数据/代码混合情况 ➔ 自动路由到 SlidingWindowChunker

    【RAG 应用优势】
    开箱即用，无需开发者人工手动分析文档类型并编写繁琐的规则判断。

    【适用场景】
    通用的多源文档解析与自动化 RAG 预处理 Pipeline 入口。
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        parent_chunk_size: int = 1024,
        child_chunk_size: int = 256,
    ):
        self.sliding_chunker = SlidingWindowChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.parent_child_chunker = ParentChildChunker(
            parent_chunk_size=parent_chunk_size, child_chunk_size=child_chunk_size
        )
        self.header_aware_chunker = HeaderAwareChunker()

    def split_document(self, doc: ParsedDocument, strategy: str = "auto") -> Any:
        """
        根据策略执行切块

        Args:
            doc: ParsedDocument 对象
            strategy: 可选 "auto", "sliding_window", "parent_child", "header_aware"

        Returns:
            切块后的 LangChain Document 列表或 (child_docs, parent_store) 元组
        """
        selected_strategy = strategy.lower()
        if selected_strategy == "auto":
            selected_strategy = self.detect_strategy(doc)

        if selected_strategy == "header_aware":
            return self.header_aware_chunker.split_document(doc)
        elif selected_strategy == "parent_child":
            return self.parent_child_chunker.split_document(doc)
        else:
            return self.sliding_chunker.split_document(doc)

    @staticmethod
    def detect_strategy(doc: ParsedDocument) -> str:
        """自适应分析文档结构，判定最合适的切片策略"""
        headings = [e for e in doc.elements if e.type == "heading"]
        total_len = sum(len(e.content) for e in doc.elements if e.content)

        # 规则 1：如果文档有明确的标题大纲节点，优先采用 HeaderAware 策略
        if len(headings) >= 2:
            return "header_aware"

        # 规则 2：如果文本长度较长且缺乏标题，优先采用 ParentChild 策略保障检索与上下文平衡
        if total_len >= 1200:
            return "parent_child"

        # 规则 3：默认采用 SlidingWindow 滑动窗口策略
        return "sliding_window"
