import copy
from typing import Any

from app.models import Element, ParsedDocument
from .base import BaseEnricher


class ContextPrefixInjector(BaseEnricher):
    """
    上下文前缀自动缝合注入器 (ContextPrefixInjector)：
    依据 Anthropic Contextual Retrieval 架构规范，在切块与向量计算前，
    动态感知文档标题层级大纲链 (H1 -> H2 -> H3)，自动为段落、表格与代码块缝合包含文件名与大纲路径的上下文前缀，
    大幅提升向量模型与 LLM 检索相似度召回率。
    """

    def __init__(
        self,
        inject_file_name: bool = True,
        inject_header_path: bool = True,
        separator: str = " > ",
        prefix_template: str = "【文档: {file_name} | 上下文: {header_path}】",
    ):
        self.inject_file_name = inject_file_name
        self.inject_header_path = inject_header_path
        self.separator = separator
        self.prefix_template = prefix_template

    def enrich(self, doc: ParsedDocument) -> ParsedDocument:
        if not doc.elements:
            return doc

        # 动态标题大纲层级栈 {level: title_text}
        header_stack: dict[int, str] = {}
        enriched_elements: list[Element] = []

        file_name = doc.file_name or "未命名文档"

        for elem in doc.elements:
            # 深拷贝 Element 避免打乱原对象
            new_elem = copy.deepcopy(elem)

            # 1. 遇到标题节点，更新标题大纲栈
            if new_elem.type == "heading":
                level = new_elem.metadata.get("level", 1)
                # 清除掉所有大于或等于当前层级的旧子标题
                keys_to_remove = [k for k in header_stack.keys() if k >= level]
                for k in keys_to_remove:
                    del header_stack[k]

                header_stack[level] = new_elem.content.strip()
                enriched_elements.append(new_elem)
                continue

            # 2. 构建当前节点的完整标题大纲路径
            sorted_levels = sorted(header_stack.keys())
            header_path_parts = [header_stack[lvl] for lvl in sorted_levels]
            header_path = self.separator.join(header_path_parts) if header_path_parts else "正文全局"

            # 写入结构化元数据
            new_elem.metadata["header_path"] = header_path
            new_elem.metadata["file_name"] = file_name

            # 3. 缝合上下文前缀
            prefix_parts = []
            if self.inject_file_name:
                prefix_parts.append(f"文档: {file_name}")
            if self.inject_header_path and header_path:
                prefix_parts.append(f"上下文: {header_path}")

            if prefix_parts:
                prefix_str = f"【{' | '.join(prefix_parts)}】"
                new_elem.metadata["context_prefix"] = prefix_str
                # 将前缀缝合注入到 Element.content 的头部
                new_elem.content = f"{prefix_str}\n{new_elem.content}"

            enriched_elements.append(new_elem)

        return ParsedDocument(
            file_name=doc.file_name,
            file_type=doc.file_type,
            raw_text=doc.raw_text,
            file_path=doc.file_path,
            total_pages=doc.total_pages,
            metadata=doc.metadata,
            elements=enriched_elements,
        )
