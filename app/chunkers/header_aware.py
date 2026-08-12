from typing import Any

from app.models import Element, Location, ParsedDocument
from .base import BaseChunker


class HeaderAwareChunker(BaseChunker):
    """
    标题层级感知切片器 (HeaderAwareChunker)

    【核心逻辑】
    根据 type="heading" 节点的层级结构构建章节树，将同一标题下的正文段落、表格与代码归为一块，
    并在 metadata 中记录完整的 `header_path` (如 `"第一章 > 1.2 架构设计"`)。

    【RAG 应用优势】
    保持文档天然的大纲逻辑，赋予向量检索完整的层次导航元数据；
    检索时大模型能清晰得知该切片属于文档的哪一章节，极大地提升复杂结构文档的答疑准确度。

    【适用场景】
    Markdown、Word (.docx)、规范的技术报告、产品 API 手册、法律法规文件。
    """

    def split_document(self, doc: ParsedDocument) -> list[Any]:
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
        current_header_stack: list[dict] = []  # 存储当前标题堆栈 [{"level": 1, "text": "第一章"}]
        current_section_elements: list[Element] = []

        for elem in elements:
            if elem.type == "heading":
                # 当遇到新标题时，结算上一章节积累的元素
                if current_section_elements:
                    chunks.append(self._build_header_chunk(current_section_elements, current_header_stack, doc))
                    current_section_elements = []

                # 更新标题堆栈 (依据 level 层级维护树状堆栈)
                level = elem.metadata.get("level", 1)
                while current_header_stack and current_header_stack[-1]["level"] >= level:
                    current_header_stack.pop()

                current_header_stack.append({"level": level, "text": elem.content})
                current_section_elements.append(elem)
            else:
                current_section_elements.append(elem)

        # 结算最后一个章节
        if current_section_elements:
            chunks.append(self._build_header_chunk(current_section_elements, current_header_stack, doc))

        lc_docs = []
        for c in chunks:
            lc_docs.append(LCDocument(page_content=c["page_content"], metadata=c["metadata"]))

        return lc_docs

    @staticmethod
    def _build_header_chunk(batch: list[Element], header_stack: list[dict], doc: ParsedDocument) -> dict:
        """根据章节批次与标题路径构建 Chunk"""
        header_path_str = " > ".join(h["text"] for h in header_stack) if header_stack else "root"
        contents = [e.content for e in batch if e.content]
        combined_text = "\n\n".join(contents)

        element_ids = [e.id for e in batch]
        first_loc = batch[0].location
        last_loc = batch[-1].location
        combined_loc = None
        if first_loc or last_loc:
            combined_loc = Location(
                start_line=first_loc.start_line if first_loc else None,
                end_line=last_loc.end_line if last_loc else None,
                page_number=first_loc.page_number if first_loc else None,
            )

        metadata = {
            "source": doc.file_path or doc.file_name,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "chunk_type": "header_aware",
            "header_path": header_path_str,
            "element_ids": element_ids,
            "elements_count": len(batch),
        }
        if combined_loc:
            metadata.update(combined_loc.to_dict())

        return {"page_content": combined_text, "metadata": metadata}
