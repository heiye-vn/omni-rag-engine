from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag, NavigableString

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


# 需要提取内容的块级标签集合
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_LIST_TAGS = {"ul", "ol"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "meta", "link", "template"}


class HTMLParser(BaseParser):
    """HTML 文档解析器（支持标题、段落、表格、列表、图片、代码块提取与 CSS Selector 定位）"""

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        html_text = path.read_text(encoding="utf-8")

        soup = BeautifulSoup(html_text, "html.parser")

        # 提取 <title> 作为文档级元数据
        doc_title = soup.title.get_text(strip=True) if soup.title else ""

        elements: list[Element] = []

        # 从 <body> 开始遍历（如果没有 body 则从根开始）
        root = soup.body if soup.body else soup
        self._walk(root, elements)

        return ParsedDocument(
            file_name=path.name,
            file_type="html",
            raw_text=soup.get_text(separator="\n", strip=True),
            file_path=str(path.absolute()),
            metadata={"title": doc_title} if doc_title else {},
            elements=elements,
        )

    # ------------------------------------------------------------------ #
    #  递归遍历 DOM 树
    # ------------------------------------------------------------------ #

    def _walk(self, node: Tag, elements: list[Element]) -> None:
        """深度优先遍历 DOM 节点树，按标签类型分发处理"""
        for child in node.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue

            tag_name = child.name.lower()

            # 跳过脚本/样式等非内容标签
            if tag_name in _SKIP_TAGS:
                continue

            # ==================== 标题 ====================
            if tag_name in _HEADING_TAGS:
                self._extract_heading(child, elements)

            # ==================== 表格 ====================
            elif tag_name == "table":
                self._extract_table(child, elements)

            # ==================== 列表 ====================
            elif tag_name in _LIST_TAGS:
                self._extract_list(child, elements)

            # ==================== 图片 ====================
            elif tag_name == "img":
                self._extract_image(child, elements)

            # ==================== 代码块 ====================
            elif tag_name == "pre":
                self._extract_code_block(child, elements)

            # ==================== 段落 ====================
            elif tag_name == "p":
                self._extract_paragraph(child, elements)

            # ==================== 引用块 ====================
            elif tag_name == "blockquote":
                self._extract_blockquote(child, elements)

            # ==================== 分隔线 ====================
            elif tag_name == "hr":
                elements.append(
                    Element(
                        type="hr",
                        content="---",
                        raw_content=str(child),
                        location=Location(selector=self._css_selector(child)),
                    )
                )

            # ==================== 其它容器标签：递归进入 ====================
            else:
                self._walk(child, elements)

    # ------------------------------------------------------------------ #
    #  各元素类型的提取方法
    # ------------------------------------------------------------------ #

    def _extract_heading(self, tag: Tag, elements: list[Element]) -> None:
        """提取标题 h1-h6"""
        text = tag.get_text(separator=" ", strip=True)
        if not text:
            return
        level = int(tag.name[1])  # h1 -> 1, h2 -> 2
        elements.append(
            Element(
                type="heading",
                content=text,
                raw_content=str(tag),
                location=Location(selector=self._css_selector(tag)),
                metadata={"level": level},
            )
        )

    def _extract_paragraph(self, tag: Tag, elements: list[Element]) -> None:
        """提取段落，同时检测内嵌图片"""
        # 先提取内嵌的 <img> 标签
        for img in tag.find_all("img", recursive=True):
            self._extract_image(img, elements)

        text = tag.get_text(separator=" ", strip=True)
        if not text:
            return
        elements.append(
            Element(
                type="paragraph",
                content=text,
                raw_content=str(tag),
                location=Location(selector=self._css_selector(tag)),
            )
        )

    def _extract_blockquote(self, tag: Tag, elements: list[Element]) -> None:
        """提取引用块"""
        text = tag.get_text(separator="\n", strip=True)
        if not text:
            return
        elements.append(
            Element(
                type="blockquote",
                content=text,
                raw_content=str(tag),
                location=Location(selector=self._css_selector(tag)),
            )
        )

    def _extract_table(self, tag: Tag, elements: list[Element]) -> None:
        """提取表格并转换为 Markdown 与 HTML 双格式"""
        rows_data: list[list[str]] = []

        for tr in tag.find_all("tr"):
            row_cells = []
            for cell in tr.find_all(["th", "td"]):
                row_cells.append(cell.get_text(separator=" ", strip=True))
            if row_cells:
                rows_data.append(row_cells)

        if not rows_data:
            return

        markdown = self._rows_to_markdown(rows_data)
        # raw_content 直接保留原始 HTML 结构以便前端渲染
        raw_html = str(tag)

        elements.append(
            Element(
                type="table",
                content=markdown,
                raw_content=raw_html,
                location=Location(selector=self._css_selector(tag)),
                metadata={
                    "headers": rows_data[0],
                    "rows_count": len(rows_data),
                },
            )
        )

    def _extract_list(self, tag: Tag, elements: list[Element]) -> None:
        """提取有序/无序列表的所有列表项"""
        is_ordered = tag.name.lower() == "ol"

        for li in tag.find_all("li", recursive=False):
            text = li.get_text(separator=" ", strip=True)
            if not text:
                continue
            elements.append(
                Element(
                    type="list_item",
                    content=text,
                    raw_content=str(li),
                    location=Location(selector=self._css_selector(li)),
                    metadata={"ordered": is_ordered},
                )
            )

    def _extract_image(self, tag: Tag, elements: list[Element]) -> None:
        """提取图片元素"""
        src = tag.get("src", "") or ""
        alt = tag.get("alt", "") or ""
        title = tag.get("title", "") or ""

        if not src:
            return

        metadata: dict = {"src": src, "alt": alt}
        if title:
            metadata["title"] = title

        elements.append(
            Element(
                type="image",
                content=alt or src,
                raw_content=str(tag),
                location=Location(selector=self._css_selector(tag)),
                metadata=metadata,
            )
        )

    def _extract_code_block(self, tag: Tag, elements: list[Element]) -> None:
        """提取 <pre> 代码块，尝试识别内嵌 <code> 的语言属性"""
        code_tag = tag.find("code")
        code_text = code_tag.get_text() if code_tag else tag.get_text()

        metadata: dict = {}
        if code_tag:
            # 尝试从 class 属性提取语言信息 (如 class="language-python")
            css_classes = code_tag.get("class", [])
            for cls in css_classes:
                if cls.startswith("language-"):
                    metadata["language"] = cls[len("language-"):]
                    break
                elif cls.startswith("lang-"):
                    metadata["language"] = cls[len("lang-"):]
                    break

        elements.append(
            Element(
                type="code",
                content=code_text,
                raw_content=str(tag),
                location=Location(selector=self._css_selector(tag)),
                metadata=metadata,
            )
        )

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _css_selector(tag: Tag) -> str:
        """生成元素的 CSS Selector 路径（用于前端定位高亮）"""
        parts: list[str] = []
        current = tag
        while current and isinstance(current, Tag) and current.name != "[document]":
            selector = current.name

            # 优先使用 id 属性（全局唯一，最精确）
            tag_id = current.get("id")
            if tag_id:
                parts.insert(0, f"{selector}#{tag_id}")
                break  # id 全局唯一，无需继续向上遍历

            # 计算同名兄弟节点中的索引 (nth-of-type)
            if current.parent:
                same_type_siblings = [
                    s for s in current.parent.children
                    if isinstance(s, Tag) and s.name == current.name
                ]
                if len(same_type_siblings) > 1:
                    idx = same_type_siblings.index(current) + 1
                    selector = f"{selector}:nth-of-type({idx})"

            parts.insert(0, selector)
            current = current.parent

        return " > ".join(parts)

    @staticmethod
    def _rows_to_markdown(rows: list[list[str]]) -> str:
        """将二维列表转换为 Markdown 表格"""
        if not rows:
            return ""
        header = rows[0]
        result = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in rows[1:]:
            padded = row + [""] * (len(header) - len(row))
            result.append("| " + " | ".join(padded) + " |")
        return "\n".join(result)
