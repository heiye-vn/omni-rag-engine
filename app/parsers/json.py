import json as json_stdlib
from pathlib import Path

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class JSONParser(BaseParser):
    """JSON 文件解析器（支持对象/数组的递归展平与 JSONPath 定位）"""

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        data = json_stdlib.loads(text)

        elements: list[Element] = []

        if isinstance(data, list):
            # 顶层为 JSON Array：尝试提取为表格 + 逐项展平
            self._process_array(data, json_path="$", elements=elements)
        elif isinstance(data, dict):
            # 顶层为 JSON Object：按 key 递归展平
            self._process_object(data, json_path="$", elements=elements)
        else:
            # 基本类型
            elements.append(
                Element(
                    type="text",
                    content=str(data),
                    raw_content=text.strip(),
                    location=Location(selector="$"),
                )
            )

        return ParsedDocument(
            file_name=path.name,
            file_type="json",
            raw_text=text,
            file_path=str(path.absolute()),
            metadata={"root_type": type(data).__name__},
            elements=elements,
        )

    # ------------------------------------------------------------------ #
    #  递归处理逻辑
    # ------------------------------------------------------------------ #

    def _process_object(self, obj: dict, json_path: str, elements: list[Element]) -> None:
        """递归处理 JSON Object，将叶节点展平为 key-value Element"""
        for key, value in obj.items():
            current_path = f"{json_path}.{key}"

            if isinstance(value, dict):
                self._process_object(value, json_path=current_path, elements=elements)
            elif isinstance(value, list):
                self._process_array(value, json_path=current_path, elements=elements)
            else:
                # 叶节点：生成 key-value 文本元素
                elements.append(
                    Element(
                        type="text",
                        content=f"{key}: {value}",
                        raw_content=json_stdlib.dumps({key: value}, ensure_ascii=False),
                        location=Location(selector=current_path),
                        metadata={"key": key, "value_type": type(value).__name__},
                    )
                )

    def _process_array(self, arr: list, json_path: str, elements: list[Element]) -> None:
        """处理 JSON Array：若为同构对象数组则提取为表格，否则逐项处理"""

        # 尝试将同构对象数组提取为表格
        if arr and all(isinstance(item, dict) for item in arr):
            all_keys: list[str] = []
            seen: set[str] = set()
            for item in arr:
                for k in item.keys():
                    if k not in seen:
                        all_keys.append(k)
                        seen.add(k)

            if all_keys:
                rows: list[list[str]] = [all_keys]  # 表头
                for item in arr:
                    row = [str(item.get(k, "")) for k in all_keys]
                    rows.append(row)

                markdown = self._rows_to_markdown(rows)
                html_table = self._rows_to_html(rows)

                elements.append(
                    Element(
                        type="table",
                        content=markdown,
                        raw_content=html_table,
                        location=Location(selector=json_path),
                        metadata={
                            "headers": all_keys,
                            "rows_count": len(rows),
                            "array_length": len(arr),
                        },
                    )
                )
                return

        # 非同构数组：逐项处理
        for idx, item in enumerate(arr):
            item_path = f"{json_path}[{idx}]"
            if isinstance(item, dict):
                self._process_object(item, json_path=item_path, elements=elements)
            elif isinstance(item, list):
                self._process_array(item, json_path=item_path, elements=elements)
            else:
                elements.append(
                    Element(
                        type="text",
                        content=str(item),
                        raw_content=json_stdlib.dumps(item, ensure_ascii=False),
                        location=Location(selector=item_path),
                    )
                )

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

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
