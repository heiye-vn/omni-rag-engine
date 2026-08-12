import csv
import io
from pathlib import Path

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class CSVParser(BaseParser):
    """CSV / TSV 文件解析器（支持自动分隔符检测、Markdown/HTML 表格转换与行号定位）"""

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")

        # 自动检测分隔符（csv.Sniffer）
        try:
            dialect = csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            dialect = csv.excel  # 检测失败默认为标准 CSV

        reader = csv.reader(io.StringIO(text), dialect)
        rows_data: list[list[str]] = []
        for row in reader:
            stripped_row = [cell.strip() for cell in row]
            if any(stripped_row):  # 过滤全空行
                rows_data.append(stripped_row)

        elements: list[Element] = []

        if rows_data:
            # 裁切右侧全空列
            max_col = max(
                (idx for row in rows_data for idx, val in enumerate(row) if val),
                default=0,
            ) + 1
            trimmed_rows = [row[:max_col] for row in rows_data]
            headers = trimmed_rows[0]

            markdown = self._rows_to_markdown(trimmed_rows)
            html_table = self._rows_to_html(trimmed_rows)

            elements.append(
                Element(
                    type="table",
                    content=markdown,
                    raw_content=html_table,
                    location=Location(start_line=1, end_line=len(trimmed_rows)),
                    metadata={
                        "headers": headers,
                        "rows_count": len(trimmed_rows),
                        "cols_count": max_col,
                        "delimiter": getattr(dialect, "delimiter", ","),
                    },
                )
            )

        return ParsedDocument(
            file_name=path.name,
            file_type="csv",
            raw_text=text,
            file_path=str(path.absolute()),
            elements=elements,
        )

    @staticmethod
    def _rows_to_markdown(rows: list[list[str]]) -> str:
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

    @staticmethod
    def _rows_to_html(rows: list[list[str]]) -> str:
        if not rows:
            return "<table></table>"
        header = rows[0]
        lines = [
            "<table border='1'>",
            "  <thead>\n    <tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr>\n  </thead>",
            "  <tbody>",
        ]
        for row in rows[1:]:
            padded = row + [""] * (len(header) - len(row))
            lines.append("    <tr>" + "".join(f"<td>{c}</td>" for c in padded) + "</tr>")
        lines.append("  </tbody>\n</table>")
        return "\n".join(lines)
