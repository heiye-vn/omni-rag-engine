from typing import Any

from app.models import Element, Location, ParsedDocument
from .base import BaseChunker


class SlidingWindowChunker(BaseChunker):
    """
    滑动窗口切块器 (SlidingWindowChunker)

    【核心逻辑】
    顺着 Element 节点流按 chunk_size (默认 512 字符) 拼接相邻节点，并支持 chunk_overlap (默认 64 字符) 重叠滑动。

    【RAG 应用优势】
    基于 Element 的逻辑边界组装，保证单个 Element 节点（如代码块、表格、段落）绝对不被从中间断开；
    通过滑动合并短文本，提升向量检索的语义完整度。

    【适用场景】
    代码块、表格与数据混合文档、配置文件、无明确标题的大段离散文本。
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_document(self, doc: ParsedDocument) -> list[Any]:
        """执行滑动窗口切块，返回适配后的 LangChain Document 列表"""
        try:
            from langchain_core.documents import Document as LCDocument
        except ImportError:
            from dataclasses import dataclass, field
            @dataclass
            class LCDocument:
                page_content: str
                metadata: dict = field(default_factory=dict)

        elements = doc.elements
        if not elements:
            return []

        chunks: list[dict] = []
        current_batch: list[Element] = []
        current_len = 0

        for elem in elements:
            elem_len = len(elem.content) if elem.content else 0

            # 情况 A：如果单个 Element 本身就很大（如代码块/长表格），独占一个 Chunk
            if elem_len >= self.chunk_size:
                if current_batch:
                    chunks.append(self._build_chunk(current_batch, doc))
                    current_batch = []
                    current_len = 0
                chunks.append(self._build_chunk([elem], doc))
                continue

            # 情况 B：合并后未超过 chunk_size，继续追加
            if current_len + elem_len <= self.chunk_size:
                current_batch.append(elem)
                current_len += elem_len
            else:
                # 超过阈值：结算当前批次
                if current_batch:
                    chunks.append(self._build_chunk(current_batch, doc))

                # 计算 overlap：根据 chunk_overlap 保留批次尾部的部分 Element 放入新批次
                overlap_batch: list[Element] = []
                overlap_len = 0
                for prev_elem in reversed(current_batch):
                    p_len = len(prev_elem.content) if prev_elem.content else 0
                    if overlap_len + p_len <= self.chunk_overlap:
                        overlap_batch.insert(0, prev_elem)
                        overlap_len += p_len
                    else:
                        break

                current_batch = overlap_batch + [elem]
                current_len = overlap_len + elem_len

        # 结算剩余批次
        if current_batch:
            chunks.append(self._build_chunk(current_batch, doc))

        # 转化为 LangChain Document 列表
        lc_docs = []
        for c in chunks:
            lc_docs.append(LCDocument(page_content=c["page_content"], metadata=c["metadata"]))

        return lc_docs

    @staticmethod
    def _build_chunk(batch: list[Element], doc: ParsedDocument) -> dict:
        """从一批 Element 构建 Chunk 对象及其合并的 metadata"""
        contents = [e.content for e in batch if e.content]
        combined_text = "\n\n".join(contents)

        element_ids = [e.id for e in batch]
        primary_elem = batch[0]

        # 合并 location 信息 (如 start_line 取首个，end_line 取末个)
        first_loc = batch[0].location
        last_loc = batch[-1].location
        combined_loc = None
        if first_loc or last_loc:
            combined_loc = Location(
                page_number=first_loc.page_number if first_loc else None,
                bbox=first_loc.bbox if first_loc else None,
                start_line=first_loc.start_line if first_loc else None,
                end_line=last_loc.end_line if last_loc else None,
                selector=first_loc.selector if first_loc else None,
                start_time=first_loc.start_time if first_loc else None,
                end_time=last_loc.end_time if last_loc else None,
            )

        metadata = {
            "source": doc.file_path or doc.file_name,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "chunk_type": "sliding_window",
            "element_ids": element_ids,
            "elements_count": len(batch),
            "primary_element_type": primary_elem.type,
        }
        if combined_loc:
            metadata.update(combined_loc.to_dict())

        return {"page_content": combined_text, "metadata": metadata}
