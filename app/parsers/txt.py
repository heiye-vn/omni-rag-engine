from pathlib import Path

from app.models import Element, Location, ParsedDocument

from .base import BaseParser


class TxtParser(BaseParser):
    """TXT 纯文本文件解析器"""

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")

        lines = text.splitlines()
        elements: list[Element] = []

        current_line = 1
        for line in lines:
            stripped = line.strip()
            if stripped:
                elements.append(
                    Element(
                        type="paragraph",
                        content=stripped,
                        raw_content=line,  # 保留原始未 strip 的文本行以便渲染
                        location=Location(
                            start_line=current_line, end_line=current_line
                        ),
                    )
                )
            current_line += 1

        return ParsedDocument(
            file_name=path.name,
            file_type="txt",
            raw_text=text,
            file_path=str(path.absolute()),
            elements=elements,
        )
