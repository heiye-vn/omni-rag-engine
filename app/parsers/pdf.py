import os
from pathlib import Path

import pymupdf  # PyMuPDF

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class PDFParser(BaseParser):
    """PDF 文档解析器（基于 PyMuPDF，支持文本块、表格、图片提取、扫描件 OCR 与页码 + bbox 坐标定位）"""

    def parse(self, file_path: str, image_output_dir: str | None = None, enable_ocr: bool = True) -> ParsedDocument:
        path = Path(file_path)
        doc = pymupdf.open(file_path)

        elements: list[Element] = []
        raw_text_parts: list[str] = []
        total_pages = len(doc)

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_number = page_idx + 1  # 1-indexed
            page_width = page.rect.width
            page_height = page.rect.height

            page_text_parts: list[str] = []

            # ==================== 1. 文本块提取 ====================
            text_dict = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # type 0 = 文本块, type 1 = 图片块
                    continue

                block_text_lines: list[str] = []
                for line in block.get("lines", []):
                    spans_text = "".join(span["text"] for span in line.get("spans", []))
                    stripped = spans_text.strip()
                    if stripped:
                        block_text_lines.append(stripped)

                if not block_text_lines:
                    continue

                block_text = "\n".join(block_text_lines)
                page_text_parts.append(block_text)

                # 获取块坐标并归一化为 [x0, y0, x1, y1] (0~1)
                bbox_raw = block.get("bbox", [0, 0, 0, 0])
                bbox = self._normalize_bbox(bbox_raw, page_width, page_height)

                # 判断文本块是否为标题 (启发式策略：基于字号大小)
                max_font_size = max(
                    (span.get("size", 0) for line in block.get("lines", []) for span in line.get("spans", [])),
                    default=0,
                )
                is_heading = max_font_size >= 16  # 字号 >= 16pt 视为标题

                elements.append(
                    Element(
                        type="heading" if is_heading else "paragraph",
                        content=block_text,
                        raw_content=block_text,  # PDF 文本块无富文本标记，原文即纯文本
                        location=Location(page_number=page_number, bbox=bbox),
                        metadata={"font_size": round(max_font_size, 1)} if is_heading else {},
                    )
                )

            # ==================== 2. 图片提取 ====================
            for img_idx, img_info in enumerate(page.get_images(full=True)):
                xref = img_info[0]

                try:
                    base_image = doc.extract_image(xref)
                except Exception:
                    continue

                if not base_image:
                    continue

                ext = base_image.get("ext", "png")
                img_blob = base_image.get("image", b"")

                img_save_path: str | None = None
                if image_output_dir and img_blob:
                    os.makedirs(image_output_dir, exist_ok=True)
                    img_filename = f"{path.stem}_p{page_number}_img{img_idx}.{ext}"
                    img_save_path = os.path.join(image_output_dir, img_filename)
                    with open(img_save_path, "wb") as f:
                        f.write(img_blob)

                elements.append(
                    Element(
                        type="image",
                        content=img_save_path or f"[Image: page {page_number}, xref {xref}]",
                        raw_content=None,
                        location=Location(page_number=page_number),
                        metadata={
                            "xref": xref,
                            "ext": ext,
                            "file_path": img_save_path,
                            "size_bytes": len(img_blob),
                            "width": base_image.get("width"),
                            "height": base_image.get("height"),
                        },
                    )
                )

            # ==================== 3. 表格提取 ====================
            try:
                tables = page.find_tables()
                for table in tables:
                    rows_data = table.extract()
                    if not rows_data:
                        continue

                    # 清理 None 值
                    cleaned_rows = [
                        [str(cell).strip() if cell else "" for cell in row]
                        for row in rows_data
                    ]

                    if not any(any(cell for cell in row) for row in cleaned_rows):
                        continue

                    markdown = self._rows_to_markdown(cleaned_rows)
                    html_table = self._rows_to_html(cleaned_rows)
                    table_bbox = self._normalize_bbox(list(table.bbox), page_width, page_height)

                    elements.append(
                        Element(
                            type="table",
                            content=markdown,
                            raw_content=html_table,
                            location=Location(page_number=page_number, bbox=table_bbox),
                            metadata={
                                "headers": cleaned_rows[0] if cleaned_rows else [],
                                "rows_count": len(cleaned_rows),
                            },
                        )
                    )
            except Exception:
                # find_tables 在部分复杂 PDF 上可能失败，安全降级跳过
                pass

            # ==================== 4. 扫描件 PDF OCR 补全 ====================
            if enable_ocr and not page_text_parts:
                try:
                    from app.ocr.helper import is_scanned_pdf_page, extract_ocr_from_image
                    if is_scanned_pdf_page(page):
                        # 渲染页面为高清位图像素
                        pix = page.get_pixmap(dpi=150)
                        img_bytes = pix.tobytes("png")
                        ocr_res = extract_ocr_from_image(img_bytes)

                        for line in ocr_res.lines:
                            page_text_parts.append(line.text)
                            elements.append(
                                Element(
                                    type="text",
                                    content=line.text,
                                    location=Location(page_number=page_number, bbox=line.bbox),
                                    metadata={"confidence": line.confidence, "ocr_extracted": True},
                                )
                            )
                except Exception:
                    pass

            if page_text_parts:
                raw_text_parts.append(f"--- Page {page_number} ---\n" + "\n".join(page_text_parts))

        doc.close()

        return ParsedDocument(
            file_name=path.name,
            file_type="pdf",
            raw_text="\n\n".join(raw_text_parts),
            file_path=str(path.absolute()),
            total_pages=total_pages,
            metadata={"total_pages": total_pages},
            elements=elements,
        )

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize_bbox(bbox: list[float], page_width: float, page_height: float) -> list[float]:
        """将 PyMuPDF 的绝对像素坐标 bbox 归一化为 0~1 范围"""
        pw = page_width or 1
        ph = page_height or 1
        return [
            round(bbox[0] / pw, 4),
            round(bbox[1] / ph, 4),
            round(bbox[2] / pw, 4),
            round(bbox[3] / ph, 4),
        ]

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

    @staticmethod
    def _rows_to_html(rows: list[list[str]]) -> str:
        """将二维列表转换为 HTML <table>"""
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
