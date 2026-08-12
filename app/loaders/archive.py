import os
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .base import BaseLoader, BatchParsedDocument
from .directory import DirectoryLoader


class ArchiveLoader(BaseLoader):
    """
    归档压缩包加载器：支持安全解压 .zip / .tar / .tar.gz 并在隔离临时目录中批量解析
    """

    SUPPORTED_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".tar.gz"}

    def __init__(
        self,
        archive_path: str | Path,
        enable_cleaning: bool = True,
        **parser_kwargs: Any,
    ):
        self.archive_path = Path(archive_path)
        self.enable_cleaning = enable_cleaning
        self.parser_kwargs = parser_kwargs

    def load(self) -> BatchParsedDocument:
        """安全解压压缩包并在临时目录中调用 DirectoryLoader 解析"""
        if not self.archive_path.exists():
            raise FileNotFoundError(f"归档文件不存在: {self.archive_path}")

        # 使用隔离的临时目录，保障解析完成后自动销毁垃圾文件
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self._safe_extract(self.archive_path, temp_path)

            # 调用 DirectoryLoader 扫描解压出来的临时文件夹
            dir_loader = DirectoryLoader(
                directory_path=temp_path,
                recursive=True,
                enable_cleaning=self.enable_cleaning,
                **self.parser_kwargs,
            )
            batch_result = dir_loader.load()

            # 将临时文件路径修正为原始压缩包内相对路径表现
            for doc in batch_result.documents:
                if doc.file_path:
                    try:
                        rel_p = Path(doc.file_path).relative_to(temp_path)
                        doc.file_path = f"{self.archive_path.name}/{rel_p.as_posix()}"
                    except ValueError:
                        pass

            return batch_result

    @classmethod
    def _safe_extract(cls, archive_path: Path, target_dir: Path) -> None:
        """安全解压文件，带 Zip Slip / 路径穿越防护校验"""
        target_dir_resolved = target_dir.resolve()

        ext = archive_path.name.lower()
        if ext.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                for member in zip_ref.namelist():
                    # 校验解压目标路径防止 Zip Slip 跨目录攻击
                    member_path = (target_dir / member).resolve()
                    if not str(member_path).startswith(str(target_dir_resolved)):
                        raise SecurityError(f"防范 Zip Slip 攻击：非法解压路径 {member}")
                zip_ref.extractall(target_dir)

        elif ext.endswith((".tar", ".tar.gz", ".tgz", ".gz")):
            with tarfile.open(archive_path, "r:*") as tar_ref:
                for member in tar_ref.getmembers():
                    member_path = (target_dir / member.name).resolve()
                    if not str(member_path).startswith(str(target_dir_resolved)):
                        raise SecurityError(f"防范 Zip Slip 攻击：非法解压路径 {member.name}")
                tar_ref.extractall(target_dir)
        else:
            raise ValueError(f"不支持的压缩包扩展名: {archive_path.suffix}")


class SecurityError(Exception):
    """安全越权异常"""
    pass
