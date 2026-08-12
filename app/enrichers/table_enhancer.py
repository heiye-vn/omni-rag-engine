import copy
import re
from typing import Any

from app.models import Element, ParsedDocument
from .base import BaseEnricher


class TableEnhancer(BaseEnricher):
    """
    复杂表格结构化与上下文增强器 (TableEnhancer)：
    自适应智能识别 type="table" 节点：
    1. 向上自动检索关联表格标题说明 (如 "表 3-1: 2026年部门预算表")；
    2. 解析并提取 Key-Value 键值对 JSON 数组 (存入 metadata['kv_pairs'])；
    3. 生成高度自解释的增强表格文本，显著提升向量召回率与大模型精准表格答疑能力。
    """

    # 常用表格标题正则模式
    _CAPTION_RE = re.compile(r"^(表\s*[\d\.\-\_A-Za-z]+|Table\s*[\d\.\-\_A-Za-z]+)[:：\s]?", re.IGNORECASE)

    def __init__(
        self,
        associate_caption: bool = True,
        generate_kv_summary: bool = True,
        max_caption_search_distance: int = 2,
    ):
        self.associate_caption = associate_caption
        self.generate_kv_summary = generate_kv_summary
        self.max_caption_search_distance = max_caption_search_distance

    def enrich(self, doc: ParsedDocument) -> ParsedDocument:
        if not doc.elements:
            return doc

        elements = doc.elements
        enriched_elements: list[Element] = []

        for idx, elem in enumerate(elements):
            new_elem = copy.deepcopy(elem)

            # 自适应条件：仅针对表格节点生效
            if new_elem.type != "table":
                enriched_elements.append(new_elem)
                continue

            table_caption = ""

            # 1. 自动向上搜寻并关联表格标题上下文
            if self.associate_caption:
                table_caption = self._find_table_caption(elements, idx)
                if table_caption:
                    new_elem.metadata["table_caption"] = table_caption

            # 2. 提取 Key-Value 键值对行记录 JSON
            kv_pairs = []
            if self.generate_kv_summary and new_elem.content:
                kv_pairs = self._extract_kv_pairs(new_elem.content)
                if kv_pairs:
                    new_elem.metadata["kv_pairs"] = kv_pairs

            # 3. 缝合表格标题前缀与增强描述
            if table_caption:
                prefix = f"【表格: {table_caption}】\n"
                new_elem.metadata["table_prefix"] = f"【表格: {table_caption}】"
                new_elem.content = f"{prefix}{new_elem.content}"

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

    def _find_table_caption(self, elements: list[Element], table_idx: int) -> str:
        """向上搜寻最邻近的表格标题说明文本"""
        start_idx = max(0, table_idx - self.max_caption_search_distance)
        for i in range(table_idx - 1, start_idx - 1, -1):
            prev_elem = elements[i]
            text = prev_elem.content.strip()
            if not text:
                continue

            # 命中类似 "表 1-1" 或 "Table 2:" 开头的通用模式
            if self._CAPTION_RE.search(text):
                return text

            # 如果前一个文本极短 (< 35 字符) 且紧邻表格，亦视为表格描述
            if len(text) <= 35 and prev_elem.type in ("text", "heading"):
                return text

        return ""

    @staticmethod
    def _extract_kv_pairs(table_md: str) -> list[dict[str, str]]:
        """从 Markdown 表格中提取结构化 Key-Value 行数据"""
        lines = [line.strip() for line in table_md.splitlines() if line.strip().startswith("|")]
        if len(lines) < 2:
            return []

        # 解析表头
        headers = [cell.strip() for cell in lines[0].strip("|").split("|")]

        kv_results = []
        for line in lines[1:]:
            # 过滤 Markdown 表格分割线 |---|---|
            if re.match(r"^\|[\s\:\-]+\|$", line) or "---" in line:
                continue

            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) == len(headers):
                row_dict = {headers[i]: cells[i] for i in range(len(headers)) if headers[i]}
                if row_dict:
                    kv_results.append(row_dict)

        return kv_results
