import uuid
from typing import Any

from app.models import ParsedDocument
from .base import BaseChunker
from .sliding_window import SlidingWindowChunker


class ParentChildChunker(BaseChunker):
    """
    父子块关联切片器 (ParentChildChunker)

    【核心逻辑】
    生成大尺寸 Parent Document (默认 1024 字符) 与小尺寸 Child Chunk (默认 256 字符)，
    每个 Child Chunk 的 metadata 中均携带 parent_id 绑定追溯链。

    【RAG 应用优势】
    完美解决“检索精准度”与“回答上下文完整度”的矛盾：
    小块 (Child) 用于向量数据库计算相似度，实现极高精准度召回；
    命中后通过 parent_id 提取大块 (Parent) 提交给 LLM，确保大模型获取充沛、连贯的上下文信息。

    【适用场景】
    密集长文档、学术论文、小说、会议纪要、长篇知识库。
    """

    def __init__(
        self,
        parent_chunk_size: int = 1024,
        child_chunk_size: int = 256,
        child_overlap: int = 32,
    ):
        self.parent_chunk_size = parent_chunk_size
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap

    def split_document(self, doc: ParsedDocument) -> tuple[list[Any], dict[str, str]]:
        """
        执行父子块切片

        Returns:
            (child_docs, parent_store)
            - child_docs: 带有 'parent_id' 元数据的子切块 LangChain Document 列表
            - parent_store: 父文档字典 {parent_id: parent_text}
        """
        # 1. 首先使用大尺寸滑动窗口切出 Parent 级块
        parent_window = SlidingWindowChunker(
            chunk_size=self.parent_chunk_size,
            chunk_overlap=self.child_overlap * 2,
        )
        parent_docs = parent_window.split_document(doc)

        child_docs: list[Any] = []
        parent_store: dict[str, str] = {}

        child_window = SlidingWindowChunker(
            chunk_size=self.child_chunk_size,
            chunk_overlap=self.child_overlap,
        )

        for p_doc in parent_docs:
            parent_id = f"parent_{uuid.uuid4().hex[:12]}"
            parent_text = p_doc.page_content
            parent_store[parent_id] = parent_text

            # 根据当前 Parent 所覆盖的 Element 节点或者纯文本构造微型虚拟文档切出 Child
            virtual_doc = ParsedDocument(
                file_name=doc.file_name,
                file_type=doc.file_type,
                file_path=doc.file_path,
                elements=[
                    e for e in doc.elements if e.id in p_doc.metadata.get("element_ids", [])
                ] or doc.elements,
            )

            c_docs = child_window.split_document(virtual_doc)

            for c in c_docs:
                # 绑定 parent_id 与 parent_text
                c.metadata["parent_id"] = parent_id
                c.metadata["chunk_type"] = "parent_child_child"
                child_docs.append(c)

        return child_docs, parent_store
