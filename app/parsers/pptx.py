import os
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class PPTXParser(BaseParser):
    """PPTX 演示文稿解析器（支持文本框、表格、图片提取与幻灯片页码定位）"""

    def parse(self, file_path: str, image_output_dir: str | None = None) -> ParsedDocument:
        path = Path(file_path)
        prs = Presentation(file_path)

        elements: list[Element] = []
        raw_text_parts: list[str] = []
        total_slides = len(prs.slides)

        # 幻灯片画布尺寸 (EMU 单位)，用于计算归一化 bbox
        slide_width = prs.slide_width or Emu(9144000)   # 默认 25.4cm
        slide_height = prs.slide_height or Emu(6858000)  # 默认 19.05cm

        for slide_idx, slide in enumerate(prs.slides, start=1):
            slide_text_parts: list[str] = []

            for shape in slide.shapes:
                self._process_shape(
                    shape=shape,
                    slide_idx=slide_idx,
                    slide_width=slide_width,
                    slide_height=slide_height,
                    elements=elements,
                    slide_text_parts=slide_text_parts,
                    image_output_dir=image_output_dir,
                    file_stem=path.stem,
                )

            if slide_text_parts:
                raw_text_parts.append(f"--- Slide {slide_idx} ---\n" + "\n".join(slide_text_parts))

        return ParsedDocument(
            file_name=path.name,
            file_type="pptx",
            raw_text="\n\n".join(raw_text_parts),
            file_path=str(path.absolute()),
            total_pages=total_slides,
            metadata={"total_slides": total_slides},
            elements=elements,
        )

    # ------------------------------------------------------------------ #
    #  Shape 分发处理
    # ------------------------------------------------------------------ #

    def _process_shape(
        self,
        shape,
        slide_idx: int,
        slide_width: int,
        slide_height: int,
        elements: list[Element],
        slide_text_parts: list[str],
        image_output_dir: str | None,
        file_stem: str,
    ) -> None:
        """根据 Shape 类型分发处理逻辑"""

        # 递归处理 Group Shape 内嵌的子形状
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child_shape in shape.shapes:
                self._process_shape(
                    shape=child_shape,
                    slide_idx=slide_idx,
                    slide_width=slide_width,
                    slide_height=slide_height,
                    elements=elements,
                    slide_text_parts=slide_text_parts,
                    image_output_dir=image_output_dir,
                    file_stem=file_stem,
                )
            return

        # 计算 Shape 在幻灯片中的归一化坐标 bbox [x0, y0, x1, y1] (0~1 范围)
        bbox = self._compute_bbox(shape, slide_width, slide_height)

        # 1. 表格 Shape
        if shape.has_table:
            self._process_table(shape, slide_idx, bbox, elements, slide_text_parts)

        # 2. 图片 Shape
        elif shape.shape_type in (MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.LINKED_PICTURE):
            self._process_image(shape, slide_idx, bbox, elements, image_output_dir, file_stem)

        # 3. 文本框 / 标题等具有 text_frame 的 Shape
        elif shape.has_text_frame:
            self._process_text_frame(shape, slide_idx, bbox, elements, slide_text_parts)

    # ------------------------------------------------------------------ #
    #  文本框处理
    # ------------------------------------------------------------------ #

    def _process_text_frame(
        self, shape, slide_idx: int, bbox: list[float] | None,
        elements: list[Element], slide_text_parts: list[str],
    ) -> None:
        """提取文本框中的段落内容"""
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # 判断是否为标题占位符 (python-pptx 在非占位符上访问 placeholder_format 会抛 ValueError)
            is_title = False
            placeholder_type_str: str | None = None
            try:
                if shape.placeholder_format is not None:
                    is_title = True
                    placeholder_type_str = str(shape.placeholder_format.type)
            except (ValueError, AttributeError):
                pass

            element_type = "heading" if is_title else "paragraph"

            # 构建可渲染的 HTML 片段 (保留粗体/斜体等行内样式)
            html_parts: list[str] = []
            for run in para.runs:
                run_text = run.text
                if run.font.bold:
                    run_text = f"<b>{run_text}</b>"
                if run.font.italic:
                    run_text = f"<i>{run_text}</i>"
                html_parts.append(run_text)
            raw_html = "".join(html_parts) if html_parts else text

            metadata: dict = {}
            if placeholder_type_str:
                metadata["placeholder_type"] = placeholder_type_str

            elements.append(
                Element(
                    type=element_type,
                    content=text,
                    raw_content=raw_html,
                    location=Location(page_number=slide_idx, bbox=bbox),
                    metadata=metadata,
                )
            )
            slide_text_parts.append(text)

    # ------------------------------------------------------------------ #
    #  表格处理
    # ------------------------------------------------------------------ #

    def _process_table(
        self, shape, slide_idx: int, bbox: list[float] | None,
        elements: list[Element], slide_text_parts: list[str],
    ) -> None:
        """提取表格 Shape 中的行列数据"""
        table = shape.table
        rows_data: list[list[str]] = []

        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells]
            rows_data.append(row_cells)

        if not rows_data:
            return

        markdown_text = self._rows_to_markdown(rows_data)
        html_table = self._rows_to_html(rows_data)
        slide_text_parts.append(markdown_text)

        elements.append(
            Element(
                type="table",
                content=markdown_text,
                raw_content=html_table,
                location=Location(page_number=slide_idx, bbox=bbox),
                metadata={
                    "headers": rows_data[0],
                    "rows_count": len(rows_data),
                },
            )
        )

    # ------------------------------------------------------------------ #
    #  图片处理
    # ------------------------------------------------------------------ #

    def _process_image(
        self, shape, slide_idx: int, bbox: list[float] | None,
        elements: list[Element], image_output_dir: str | None, file_stem: str,
    ) -> None:
        """提取图片 Shape 的二进制数据并保存到磁盘"""
        image = shape.image
        content_type = image.content_type  # 如 image/png
        ext = content_type.split("/")[-1] if "/" in content_type else "png"
        img_blob = image.blob

        img_save_path: str | None = None
        if image_output_dir:
            os.makedirs(image_output_dir, exist_ok=True)
            img_filename = f"{file_stem}_slide{slide_idx}_{shape.shape_id}.{ext}"
            img_save_path = os.path.join(image_output_dir, img_filename)
            with open(img_save_path, "wb") as f:
                f.write(img_blob)

        elements.append(
            Element(
                type="image",
                content=img_save_path or f"[Image: slide {slide_idx}, shape {shape.shape_id}]",
                raw_content=None,  # 图片二进制无法直接序列化为字符串
                location=Location(page_number=slide_idx, bbox=bbox),
                metadata={
                    "content_type": content_type,
                    "file_path": img_save_path,
                    "size_bytes": len(img_blob),
                },
            )
        )

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_bbox(shape, slide_width: int, slide_height: int) -> list[float] | None:
        """计算 Shape 在幻灯片中的归一化坐标 [x0, y0, x1, y1]，值域 0~1"""
        if shape.left is None or shape.top is None or shape.width is None or shape.height is None:
            return None
        sw = int(slide_width) or 1
        sh = int(slide_height) or 1
        x0 = round(int(shape.left) / sw, 4)
        y0 = round(int(shape.top) / sh, 4)
        x1 = round((int(shape.left) + int(shape.width)) / sw, 4)
        y1 = round((int(shape.top) + int(shape.height)) / sh, 4)
        return [x0, y0, x1, y1]

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
