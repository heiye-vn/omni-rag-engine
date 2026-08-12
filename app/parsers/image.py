from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class ImageParser(BaseParser):
    """图片文件解析器（提取图片基础属性、EXIF 元数据与嵌入式文本内容描述）"""

    # 支持的图片格式
    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        img = Image.open(file_path)

        width, height = img.size
        img_format = img.format or path.suffix.lstrip(".").upper()
        color_mode = img.mode  # RGB, RGBA, L, CMYK 等

        # 提取 EXIF 元数据（如果有）
        exif_data: dict[str, str] = {}
        try:
            raw_exif = img._getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    # 过滤不可序列化的值（如 bytes）
                    if isinstance(value, (str, int, float)):
                        exif_data[tag_name] = str(value)
                    elif isinstance(value, tuple) and all(isinstance(v, (int, float)) for v in value):
                        exif_data[tag_name] = str(value)
        except (AttributeError, Exception):
            pass

        img.close()

        # 构建图片描述文本 (内容摘要)
        description = f"Image: {path.name} ({width}x{height}, {img_format}, {color_mode})"

        metadata: dict = {
            "file_path": str(path.absolute()),
            "width": width,
            "height": height,
            "format": img_format,
            "color_mode": color_mode,
            "file_size_bytes": path.stat().st_size,
        }
        if exif_data:
            metadata["exif"] = exif_data

        elements = [
            Element(
                type="image",
                content=description,
                raw_content=None,  # 图片二进制无法序列化为字符串
                location=Location(
                    bbox=[0.0, 0.0, 1.0, 1.0],  # 图片本身即为整个视觉区域
                ),
                metadata=metadata,
            )
        ]

        return ParsedDocument(
            file_name=path.name,
            file_type="image",
            file_path=str(path.absolute()),
            metadata={
                "width": width,
                "height": height,
                "format": img_format,
            },
            elements=elements,
        )
