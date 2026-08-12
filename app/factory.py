from pathlib import Path

from app.parsers.base import BaseParser
from app.parsers.txt import TxtParser
from app.parsers.markdown import MarkdownParser
from app.parsers.docx import DOCXParser
from app.parsers.xlsx import XLSXParser
from app.parsers.pptx import PPTXParser
from app.parsers.pdf import PDFParser
from app.parsers.html import HTMLParser
from app.parsers.csv import CSVParser
from app.parsers.json import JSONParser
from app.parsers.image import ImageParser
from app.parsers.audio import AudioParser
from app.parsers.vedio import VideoParser


# 文件扩展名 → 解析器类型映射表
_EXTENSION_MAP: dict[str, type[BaseParser]] = {
    # 纯文本
    ".txt": TxtParser,
    ".log": TxtParser,
    # Markdown
    ".md": MarkdownParser,
    ".markdown": MarkdownParser,
    # Office 文档
    ".docx": DOCXParser,
    ".xlsx": XLSXParser,
    ".xls": XLSXParser,
    ".pptx": PPTXParser,
    # PDF
    ".pdf": PDFParser,
    # Web
    ".html": HTMLParser,
    ".htm": HTMLParser,
    ".csv": CSVParser,
    ".tsv": CSVParser,
    ".json": JSONParser,
    # 图片
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".gif": ImageParser,
    ".bmp": ImageParser,
    ".tiff": ImageParser,
    ".tif": ImageParser,
    ".webp": ImageParser,
    # 音频
    ".mp3": AudioParser,
    ".wav": AudioParser,
    ".flac": AudioParser,
    ".m4a": AudioParser,
    ".ogg": AudioParser,
    ".wma": AudioParser,
    ".aac": AudioParser,
    # 视频
    ".mp4": VideoParser,
    ".avi": VideoParser,
    ".mkv": VideoParser,
    ".mov": VideoParser,
    ".wmv": VideoParser,
    ".flv": VideoParser,
    ".webm": VideoParser,
    ".m4v": VideoParser,
}


def get_parser(file_path: str, **kwargs) -> BaseParser:
    """
    根据文件扩展名自动选择并返回对应的解析器实例

    Args:
        file_path: 文件路径
        **kwargs: 传递给特定解析器构造函数的参数 (如 Whisper model_name)

    Returns:
        对应的 BaseParser 实例

    Raises:
        ValueError: 不支持的文件类型
    """
    ext = Path(file_path).suffix.lower()
    parser_cls = _EXTENSION_MAP.get(ext)

    if parser_cls is None:
        supported = sorted(set(_EXTENSION_MAP.keys()))
        raise ValueError(
            f"不支持的文件类型: '{ext}'。\n"
            f"当前支持的格式: {', '.join(supported)}"
        )

    # 音频/视频解析器支持传入 model_name 参数
    if parser_cls in (AudioParser, VideoParser):
        model_name = kwargs.get("model_name", "base")
        return parser_cls(model_name=model_name)

    return parser_cls()


def get_supported_extensions() -> list[str]:
    """返回所有支持的文件扩展名列表"""
    return sorted(set(_EXTENSION_MAP.keys()))
