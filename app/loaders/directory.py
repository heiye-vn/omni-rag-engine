from pathlib import Path
from typing import Any

from app.factory import get_parser, get_supported_extensions
from app.models import ParsedDocument
from .base import BaseLoader, BatchParsedDocument


class DirectoryLoader(BaseLoader):
    """
    目录树批量加载器：递归扫描目标文件夹，自动识别受支持的文件并批量解析
    """

    DEFAULT_EXCLUDES = {
        ".git",
        "__pycache__",
        ".venv",
        ".uv-cache",
        ".idea",
        ".vscode",
        ".ds_store",
    }

    def __init__(
        self,
        directory_path: str | Path,
        recursive: bool = True,
        exclude_patterns: set[str] | None = None,
        enable_cleaning: bool = True,
        **parser_kwargs: Any,
    ):
        self.directory_path = Path(directory_path)
        self.recursive = recursive
        self.exclude_patterns = exclude_patterns if exclude_patterns is not None else self.DEFAULT_EXCLUDES
        self.enable_cleaning = enable_cleaning
        self.parser_kwargs = parser_kwargs
        self.supported_exts = set(get_supported_extensions())

    def load(self) -> BatchParsedDocument:
        """扫描目录并批量解析受支持的文件"""
        if not self.directory_path.exists():
            raise FileNotFoundError(f"目标目录不存在: {self.directory_path}")
        if not self.directory_path.is_dir():
            raise ValueError(f"指定的路径不是一个目录: {self.directory_path}")

        parsed_documents: list[ParsedDocument] = []
        failed_files: list[dict[str, str]] = []

        # 获取迭代模式
        pattern_glob = "**/*" if self.recursive else "*"

        for file_path in self.directory_path.glob(pattern_glob):
            if not file_path.is_file():
                continue

            # 排除匹配的目录与系统盲区文件
            if self._should_exclude(file_path):
                continue

            # 检查文件后缀是否在支持列表中
            ext = file_path.suffix.lower()
            if ext not in self.supported_exts:
                continue

            # 执行解析
            try:
                parser = get_parser(str(file_path), **self.parser_kwargs)
                parsed_doc = parser.parse(str(file_path))

                if self.enable_cleaning:
                    parsed_doc = parsed_doc.clean()

                parsed_documents.append(parsed_doc)
            except Exception as e:
                failed_files.append({"file_path": str(file_path), "error": str(e)})

        return BatchParsedDocument(
            documents=parsed_documents,
            failed_files=failed_files,
        )

    def _should_exclude(self, file_path: Path) -> bool:
        """判断文件路径是否命中排除规则"""
        parts = {p.lower() for p in file_path.parts}
        return bool(parts.intersection(self.exclude_patterns))
