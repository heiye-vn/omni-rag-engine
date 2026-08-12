from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.models import Element, Location, ParsedDocument

from .base import BaseParser


class MarkdownParser(BaseParser):
    """Markdown 文件解析器，支持所有常见 Markdown 元素类型与精准行号定位"""

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()

        md = MarkdownIt()
        try:
            md.enable("table")
        except ValueError:
            pass

        tokens = md.parse(text)
        elements: list[Element] = []
        context_stack: list[dict] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]
            i = self._process_token(token, tokens, i, context_stack, elements, lines)
            i += 1

        return ParsedDocument(
            file_name=path.name,
            file_type="markdown",
            raw_text=text,
            file_path=str(path.absolute()),
            elements=elements,
        )

    # ------------------------------------------------------------------ #
    #  Token 分发
    # ------------------------------------------------------------------ #

    def _process_token(
        self,
        token: Token,
        tokens: list[Token],
        index: int,
        context_stack: list[dict],
        elements: list[Element],
        source_lines: list[str],
    ) -> int:
        """处理单个 Token，返回处理后的索引位置"""

        # ==================== 标题 ====================
        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 → 1, h2 → 2, …
            context_stack.append({"type": "heading", "level": level, "map": token.map})

        elif token.type == "heading_close":
            self._pop_context(context_stack, "heading")

        # ==================== 段落 ====================
        elif token.type == "paragraph_open":
            context_stack.append({"type": "paragraph", "map": token.map})

        elif token.type == "paragraph_close":
            self._pop_context(context_stack, "paragraph")

        # ==================== 引用块 ====================
        elif token.type == "blockquote_open":
            context_stack.append({"type": "blockquote", "map": token.map})

        elif token.type == "blockquote_close":
            self._pop_context(context_stack, "blockquote")

        # ==================== 无序列表 ====================
        elif token.type == "bullet_list_open":
            context_stack.append({"type": "list", "ordered": False, "map": token.map})

        elif token.type == "bullet_list_close":
            self._pop_context(context_stack, "list")

        # ==================== 有序列表 ====================
        elif token.type == "ordered_list_open":
            start = token.attrGet("start") if token.attrGet else 1
            context_stack.append(
                {"type": "list", "ordered": True, "start": int(start or 1), "map": token.map}
            )

        elif token.type == "ordered_list_close":
            self._pop_context(context_stack, "list")

        # ==================== 列表项 ====================
        elif token.type == "list_item_open":
            context_stack.append({"type": "list_item", "map": token.map})

        elif token.type == "list_item_close":
            self._pop_context(context_stack, "list_item")

        # ==================== 行内内容 ====================
        elif token.type == "inline":
            self._process_inline(token, context_stack, elements, source_lines)

        # ==================== 围栏代码块 ====================
        elif token.type == "fence":
            metadata = {}
            if token.info:
                metadata["language"] = token.info
            loc = self._create_location_from_map(token.map)
            raw = self._get_raw_content(source_lines, token.map)
            elements.append(
                Element(type="code", content=token.content, raw_content=raw, location=loc, metadata=metadata)
            )

        # ==================== 缩进代码块 ====================
        elif token.type == "code_block":
            loc = self._create_location_from_map(token.map)
            raw = self._get_raw_content(source_lines, token.map)
            elements.append(
                Element(type="code", content=token.content, raw_content=raw, location=loc)
            )

        # ==================== 分隔线 ====================
        elif token.type == "hr":
            loc = self._create_location_from_map(token.map)
            raw = self._get_raw_content(source_lines, token.map)
            elements.append(
                Element(type="hr", content="---", raw_content=raw or "---", location=loc)
            )

        # ==================== HTML 块 ====================
        elif token.type == "html_block":
            loc = self._create_location_from_map(token.map)
            raw = token.content.strip()
            elements.append(
                Element(type="html", content=raw, raw_content=raw, location=loc)
            )

        # ==================== 表格 ====================
        elif token.type == "table_open":
            loc = self._create_location_from_map(token.map)
            raw = self._get_raw_content(source_lines, token.map)
            table_data = self._parse_table(tokens, index)
            elements.append(
                Element(
                    type="table",
                    content=table_data["text"],
                    raw_content=raw,
                    location=loc,
                    metadata={
                        "headers": table_data["headers"],
                        "rows": table_data["rows"],
                    },
                )
            )
            while index < len(tokens) and tokens[index].type != "table_close":
                index += 1

        return index

    # ------------------------------------------------------------------ #
    #  行内内容处理
    # ------------------------------------------------------------------ #

    def _process_inline(
        self,
        token: Token,
        context_stack: list[dict],
        elements: list[Element],
        source_lines: list[str],
    ) -> None:
        """处理 inline Token：提取图片、根据上下文分类文本并加入位置信息"""

        # 1. 从子 Token 中提取图片，单独作为 image 元素
        if token.children:
            for child in token.children:
                if child.type == "image":
                    src = child.attrGet("src") or ""
                    alt = child.content or ""
                    title = child.attrGet("title") or ""
                    metadata = {"src": src, "alt": alt}
                    if title:
                        metadata["title"] = title
                    raw_img = f"![{alt}]({src})"
                    elements.append(
                        Element(type="image", content=alt, raw_content=raw_img, metadata=metadata)
                    )

        # 2. 构建纯文本内容
        content = (
            self._build_text_from_children(token)
            if token.children
            else token.content
        )
        content = content.strip()

        if not content:
            return

        # 获取上下文中的 location 信息
        ctx = context_stack[-1] if context_stack else {}
        token_map = ctx.get("map") or token.map
        loc = self._create_location_from_map(token_map)
        raw = self._get_raw_content(source_lines, token_map) or content

        # 3. 根据上下文栈确定元素类型
        heading_ctx = self._find_context(context_stack, "heading")
        if heading_ctx:
            elements.append(
                Element(
                    type="heading",
                    content=content,
                    raw_content=raw,
                    location=loc,
                    metadata={"level": heading_ctx["level"]},
                )
            )
            return

        list_ctx = self._find_context(context_stack, "list")
        blockquote_ctx = self._find_context(context_stack, "blockquote")

        if list_ctx:
            metadata: dict = {"ordered": list_ctx["ordered"]}
            if list_ctx["ordered"]:
                metadata["start"] = list_ctx.get("start", 1)
            if blockquote_ctx:
                metadata["in_blockquote"] = True
            elements.append(
                Element(type="list_item", content=content, raw_content=raw, location=loc, metadata=metadata)
            )
        elif blockquote_ctx:
            elements.append(Element(type="blockquote", content=content, raw_content=raw, location=loc))
        else:
            elements.append(Element(type="text", content=content, raw_content=raw, location=loc))

    # ------------------------------------------------------------------ #
    #  辅助方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _create_location_from_map(token_map: list[int] | None) -> Location | None:
        """根据 markdown-it 的 map 属性（[start, end]）构建 Location 对象"""
        if token_map and len(token_map) >= 2:
            return Location(start_line=token_map[0] + 1, end_line=token_map[1])
        return None

    @staticmethod
    def _get_raw_content(source_lines: list[str], token_map: list[int] | None) -> str | None:
        """根据行号范围切取原始 Markdown 字符串"""
        if token_map and len(token_map) >= 2 and source_lines:
            start, end = token_map[0], token_map[1]
            if 0 <= start < len(source_lines):
                return "\n".join(source_lines[start:end])
        return None

    @staticmethod
    def _pop_context(stack: list[dict], context_type: str) -> dict | None:
        """安全弹出上下文栈顶指定类型的上下文"""
        if stack and stack[-1]["type"] == context_type:
            return stack.pop()
        return None

    @staticmethod
    def _find_context(stack: list[dict], context_type: str) -> dict | None:
        """从栈顶向下查找最近的指定类型上下文"""
        for ctx in reversed(stack):
            if ctx["type"] == context_type:
                return ctx
        return None

    @staticmethod
    def _build_text_from_children(token: Token) -> str:
        """从 inline Token 的子节点构建纯文本，排除图片标记"""
        parts: list[str] = []
        for child in token.children or []:
            if child.type == "image":
                continue
            elif child.type in ("softbreak", "hardbreak"):
                parts.append("\n")
            elif child.type in ("text", "code_inline"):
                parts.append(child.content)
        return "".join(parts)

    @staticmethod
    def _parse_table(tokens: list[Token], start_index: int) -> dict:
        """解析表格 Token 序列，提取表头和数据行"""
        headers: list[str] = []
        rows: list[list[str]] = []
        current_row: list[str] = []
        in_head = False
        in_body = False

        for i in range(start_index, len(tokens)):
            t = tokens[i]
            if t.type == "table_close":
                break
            elif t.type == "thead_open":
                in_head = True
            elif t.type == "thead_close":
                in_head = False
            elif t.type == "tbody_open":
                in_body = True
            elif t.type == "tbody_close":
                in_body = False
            elif t.type == "tr_open":
                current_row = []
            elif t.type == "tr_close":
                if in_head:
                    headers = current_row
                elif in_body:
                    rows.append(current_row)
                current_row = []
            elif t.type == "inline":
                current_row.append(t.content)

        text_lines: list[str] = []
        if headers:
            text_lines.append(" | ".join(headers))
            text_lines.append(" | ".join("---" for _ in headers))
        for row in rows:
            text_lines.append(" | ".join(row))

        return {"headers": headers, "rows": rows, "text": "\n".join(text_lines)}
