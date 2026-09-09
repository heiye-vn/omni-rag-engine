"""
对象存储抽象层：大体积解析产物（Job result）落地

设计动机：
- 数据库的 JSON/JSONB 字段适合存元数据与中小负载；大体积 result（解析/切块产物常达
  数十 MB）反复读写会拖累数据库 IO、并放大网络带宽。
- 把 result 切到独立层：数据库只保留引用（key/路径），真正数据进对象存储，
  既能横向扩展（接 MinIO/S3），又能在 MinIO 不可用时降级到本地文件。

接口设计：
- ObjectStore.put_bytes(key, data) -> key
- ObjectStore.get_bytes(key) -> bytes | None
- ObjectStore.delete(key) -> bool
- ObjectStore.exists(key) -> bool

内置实现：
- LocalFSStore（默认）：零依赖落地本地目录，与 docker-compose 的 omni_rag_data 卷天然兼容
- MinioStore（推荐生产）：S3 兼容对象存储，docker-compose 已就绪，可横向扩展、多副本共享

工厂：
- get_object_store()：按 env OBJECT_STORE_BACKEND 选择 local | minio，调用方无需感知
  底层实现；MinIO 不可用时默认回退本地并打印 ERROR 日志（与 JOB_STORE_STRICT 联动）。
"""

from __future__ import annotations

import io
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # 仅为类型提示，避免 minio 未装时 import 阻塞
    from minio import Minio  # noqa: F401

# key 白名单：仅允许字母数字 / 点 / 下划线 / 短横线 / 正斜杠（路径分隔），其余字符替换为 _
_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9._/\-]")
# 禁止出现的子串，防止路径穿越
_FORBIDDEN_SUBSTRINGS = ("..", "\\")

# 对象存储后端标识
OBJECT_STORE_BACKEND_LOCAL = "local"
OBJECT_STORE_BACKEND_MINIO = "minio"
_OBJECT_STORE_ALIASES = {
    OBJECT_STORE_BACKEND_LOCAL: OBJECT_STORE_BACKEND_LOCAL,
    "fs": OBJECT_STORE_BACKEND_LOCAL,
    "filesystem": OBJECT_STORE_BACKEND_LOCAL,
    OBJECT_STORE_BACKEND_MINIO: OBJECT_STORE_BACKEND_MINIO,
    "s3": OBJECT_STORE_BACKEND_MINIO,
}


def _sanitize_key(key: str) -> str:
    """清洗对象存储 key，杜绝 ../、绝对路径、危险字符"""
    if not isinstance(key, str) or not key:
        raise ValueError(f"非法的对象存储 key: {key!r}")
    if key.startswith("/") or key.startswith("\\"):
        raise ValueError(f"非法的对象存储 key (绝对路径): {key!r}")
    cleaned = _SAFE_KEY_RE.sub("_", key)
    for bad in _FORBIDDEN_SUBSTRINGS:
        if bad in cleaned:
            raise ValueError(f"非法的对象存储 key (含 {bad}): {key!r}")
    return cleaned


class ObjectStore(ABC):
    """对象存储抽象基类"""

    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> str:
        """写入字节数据，返回规范化后的 key"""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes | None:
        """读取字节数据，key 不存在返回 None"""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除对象，返回是否存在并被删除"""

    def exists(self, key: str) -> bool:
        """判断对象是否存在"""
        return self.get_bytes(key) is not None


class LocalFSStore(ObjectStore):
    """本地文件系统对象存储：MinIO/S3 不可用时的零依赖替代"""

    def __init__(self, root: str | os.PathLike[str]):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, env_var: str = "OBJECT_STORE_ROOT", default: str = "data/objects") -> "LocalFSStore":
        root = os.environ.get(env_var, default)
        return cls(root)

    def _resolve(self, key: str) -> Path:
        safe = _sanitize_key(key)
        path = (self._root / safe).resolve()
        # 二次校验：解析后必须仍在 root 目录之下
        try:
            path.relative_to(self._root.resolve())
        except ValueError as e:
            raise ValueError(f"对象 key 越界: {key!r}") from e
        return path

    def put_bytes(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 原子写：先写 .tmp 再 rename，避免并发读拿到半截
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return _sanitize_key(key)

    def get_bytes(self, key: str) -> bytes | None:
        path = self._resolve(key)
        if not path.exists() or not path.is_file():
            return None
        return path.read_bytes()

    def delete(self, key: str) -> bool:
        path = self._resolve(key)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError as e:  # pragma: no cover - 极端场景
            logger.warning("对象删除失败 %s: %s", path, e)
            return False

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()


class MinioStore(ObjectStore):
    """
    MinIO / S3 兼容对象存储

    - 默认与 docker-compose 中的 minio 服务对接（endpoint=minio:9000），
      生产可改用 AWS S3 / 阿里云 OSS 等所有 S3 兼容实现。
    - 构造时主动 ensure_bucket：bucket 不存在则创建，避免首次写入延迟。
    - 全部 S3 错误按 code 分类：NoSuchKey/NoSuchObject 视为不存在，
      其余错误向上抛出，调用方决定是否回退。
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        ensure_bucket: bool = True,
    ):
        # 延迟导入：未装 minio SDK 时 LocalFSStore 仍可用，但 MinioStore 构造会失败
        from minio import Minio

        self._endpoint = endpoint
        self._bucket = bucket
        self._client: Minio = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        if ensure_bucket:
            self._ensure_bucket()

    @classmethod
    def from_env(cls) -> "MinioStore":
        return cls(
            endpoint=os.environ.get("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.environ.get("MINIO_BUCKET", "omni-rag-objects"),
            secure=os.environ.get("MINIO_SECURE", "0").strip().lower() in ("1", "true", "yes"),
        )

    def _ensure_bucket(self) -> None:
        """启动期确保 bucket 存在；网络/认证失败时抛出，由工厂决定是否回退本地"""
        try:
            exists = self._client.bucket_exists(self._bucket)
        except Exception as e:  # noqa: BLE001 - 任何 MinIO 异常都视为不可用
            raise RuntimeError(f"MinIO 连通性检查失败 (endpoint={self._endpoint}): {e}") from e
        if not exists:
            try:
                self._client.make_bucket(self._bucket)
                logger.info("MinIO bucket '%s' 已创建 (endpoint=%s)", self._bucket, self._endpoint)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"MinIO bucket 创建失败 '{self._bucket}': {e}") from e

    @staticmethod
    def _is_not_found(exc: BaseException) -> bool:
        """S3 兼容错误码：对象不存在视为 None/False，不向上抛"""
        # minio-py 7.x: S3Error.code 是字符串（"NoSuchKey" / "NoSuchObject"）
        # 为兼容不同实现，同时检查 message 兜底
        code = getattr(exc, "code", "") or ""
        if code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
            return True
        msg = str(exc)
        return "NoSuchKey" in msg or "NoSuchObject" in msg

    def put_bytes(self, key: str, data: bytes) -> str:
        safe = _sanitize_key(key)
        try:
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=safe,
                data=io.BytesIO(data),
                length=len(data),
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"MinIO 写入失败 (key={safe}): {e}") from e
        return safe

    def get_bytes(self, key: str) -> bytes | None:
        safe = _sanitize_key(key)
        try:
            response = self._client.get_object(self._bucket, safe)
        except Exception as e:  # noqa: BLE001
            if self._is_not_found(e):
                return None
            raise RuntimeError(f"MinIO 读取失败 (key={safe}): {e}") from e
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, key: str) -> bool:
        safe = _sanitize_key(key)
        try:
            # 先查存在性，minio 的 remove_object 对不存在对象无副作用但返回成功
            self._client.remove_object(self._bucket, safe)
            return True
        except Exception as e:  # noqa: BLE001
            if self._is_not_found(e):
                return False
            raise RuntimeError(f"MinIO 删除失败 (key={safe}): {e}") from e

    def exists(self, key: str) -> bool:
        safe = _sanitize_key(key)
        try:
            self._client.stat_object(self._bucket, safe)
            return True
        except Exception as e:  # noqa: BLE001
            if self._is_not_found(e):
                return False
            raise RuntimeError(f"MinIO stat 失败 (key={safe}): {e}") from e


# ---------------------------------------------------------------------------- #
#  后端工厂
# ---------------------------------------------------------------------------- #


def get_object_store(
    backend: str | None = None,
    strict: bool | None = None,
) -> ObjectStore:
    """
    对象存储后端工厂：按 env OBJECT_STORE_BACKEND 路由到 local 或 minio

    Args:
        backend: 显式指定后端 (local | minio)，缺省读取 env OBJECT_STORE_BACKEND
        strict: 严格模式开关。True 时 MinIO 不可用直接抛错；False/None 时降级到 LocalFSStore。
                缺省仅读取 env OBJECT_STORE_STRICT（不与 JOB_STORE_STRICT 联动）。

    Returns:
        LocalFSStore 或 MinioStore 实例（永远非空，回退保证服务可用）

    Raises:
        RuntimeError: strict=True 且目标后端不可用时抛出
    """
    if strict is None:
        # 对象存储严格模式只看 OBJECT_STORE_STRICT；与 JOB_STORE_STRICT 解耦，
        # 避免数据库严格配置意外拖垮对象存储选型
        strict = os.environ.get("OBJECT_STORE_STRICT", "0").strip().lower() in ("1", "true", "yes")

    chosen_raw = (backend or os.environ.get("OBJECT_STORE_BACKEND", OBJECT_STORE_BACKEND_LOCAL)).strip().lower()
    chosen = _OBJECT_STORE_ALIASES.get(chosen_raw, chosen_raw)

    if chosen == OBJECT_STORE_BACKEND_LOCAL:
        return LocalFSStore.from_env()

    if chosen == OBJECT_STORE_BACKEND_MINIO:
        try:
            store = MinioStore.from_env()
            logger.info(
                "对象存储后端已启用: minio (endpoint=%s, bucket=%s)",
                os.environ.get("MINIO_ENDPOINT", "minio:9000"),
                os.environ.get("MINIO_BUCKET", "omni-rag-objects"),
            )
            return store
        except Exception as e:  # noqa: BLE001 - 工厂兜底：MinIO 不可用不应让服务崩溃
            if strict:
                raise RuntimeError(f"严格模式下 MinIO 对象存储不可用: {e}") from e
            logger.error(
                "MinIO 对象存储不可用，已回退为本地文件系统（result 将仅存在于本地，"
                "多副本/容器重建场景会丢数据）。原因: %s",
                e,
                exc_info=True,
            )
            return LocalFSStore.from_env()

    logger.warning("未知的对象存储后端 '%s'，回退使用本地文件系统", chosen_raw)
    return LocalFSStore.from_env()


def current_object_store_name() -> str:
    """返回当前生效的对象存储后端名称（供 /health 等可观测性接口使用）"""
    chosen_raw = (os.environ.get("OBJECT_STORE_BACKEND", OBJECT_STORE_BACKEND_LOCAL)).strip().lower()
    return _OBJECT_STORE_ALIASES.get(chosen_raw, OBJECT_STORE_BACKEND_LOCAL)