"""
MinIO 对象存储 + 后端工厂测试

测试策略：
- MinioStore 单元测试：mock `minio.Minio` 客户端，验证方法 → SDK 调用的映射关系
  （key 清洗、bucket 选取、S3 错误码归一化为 None/False 等）。
- 后端工厂测试：env 变量驱动的 backend 选型 + 严格模式降级。
- 不依赖真实的 MinIO 服务，CI 与本机零依赖即可运行。
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.storage import (
    LocalFSStore,
    MinioStore,
    OBJECT_STORE_BACKEND_LOCAL,
    OBJECT_STORE_BACKEND_MINIO,
    get_object_store,
)
from app.storage.object_store import current_object_store_name


# ---------------------------------------------------------------------------- #
#  Fixtures
# ---------------------------------------------------------------------------- #


class _FakeS3Error(Exception):
    """模拟 minio.error.S3Error：仅暴露 code 属性"""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@pytest.fixture
def fake_minio_client():
    """构造一个 mock Minio 客户端，挂到 MinioStore 内部"""
    client = MagicMock(name="Minio")
    client.bucket_exists.return_value = True  # 默认 bucket 已存在，避开创建分支
    return client


@pytest.fixture
def minio_store(fake_minio_client, monkeypatch):
    """构造一个 MinioStore：patch 掉 Minio 类以注入 mock 客户端"""
    monkeypatch.setenv("MINIO_ENDPOINT", "test-minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "ak")
    monkeypatch.setenv("MINIO_SECRET_KEY", "sk")
    monkeypatch.setenv("MINIO_BUCKET", "test-bucket")

    with patch("app.storage.object_store.MinioStore._ensure_bucket"):
        store = MinioStore(
            endpoint="test-minio:9000",
            access_key="ak",
            secret_key="sk",
            bucket="test-bucket",
            ensure_bucket=False,  # 跳过真实连通性校验
        )
    # 用 mock 客户端替换真实客户端
    store._client = fake_minio_client
    return store


# ---------------------------------------------------------------------------- #
#  MinioStore 基础读写
# ---------------------------------------------------------------------------- #


def test_minio_store_put_calls_sdk_with_correct_args(minio_store, fake_minio_client):
    """put_bytes 应把字节流 + 长度 + bucket/key 透传给 SDK"""
    fake_minio_client.put_object.return_value = None

    key = minio_store.put_bytes("jobs/abc/result.json", b"hello")

    assert key == "jobs/abc/result.json"
    fake_minio_client.put_object.assert_called_once()
    call_kwargs = fake_minio_client.put_object.call_args.kwargs
    assert call_kwargs["bucket_name"] == "test-bucket"
    assert call_kwargs["object_name"] == "jobs/abc/result.json"
    assert call_kwargs["length"] == len(b"hello")
    # data 是 BytesIO，校验可读且内容一致
    assert call_kwargs["data"].read() == b"hello"


def test_minio_store_get_returns_bytes(minio_store, fake_minio_client):
    """get_bytes 应读取 SDK 返回流的全部字节，并显式关闭"""
    response = MagicMock()
    response.read.return_value = b"hello world"
    fake_minio_client.get_object.return_value = response

    data = minio_store.get_bytes("jobs/abc/result.json")

    assert data == b"hello world"
    fake_minio_client.get_object.assert_called_once_with("test-bucket", "jobs/abc/result.json")
    response.close.assert_called_once()
    response.release_conn.assert_called_once()


def test_minio_store_get_missing_key_returns_none(minio_store, fake_minio_client):
    """NoSuchKey 应归一化为 None，不向上抛"""
    fake_minio_client.get_object.side_effect = _FakeS3Error("NoSuchKey")

    assert minio_store.get_bytes("jobs/missing/result.json") is None


def test_minio_store_get_other_error_propagates(minio_store, fake_minio_client):
    """非 NotFound 错误必须向上抛，调用方决定是否降级"""
    fake_minio_client.get_object.side_effect = _FakeS3Error("AccessDenied")

    with pytest.raises(RuntimeError, match="MinIO 读取失败"):
        minio_store.get_bytes("jobs/abc/result.json")


def test_minio_store_delete_returns_true_when_called(minio_store, fake_minio_client):
    """delete 调用成功即返回 True（minio 对不存在对象无副作用）"""
    fake_minio_client.remove_object.return_value = None

    assert minio_store.delete("jobs/abc/result.json") is True
    fake_minio_client.remove_object.assert_called_once_with("test-bucket", "jobs/abc/result.json")


def test_minio_store_delete_missing_returns_false(minio_store, fake_minio_client):
    """delete 遇到 NoSuchKey 应返回 False，不抛"""
    fake_minio_client.remove_object.side_effect = _FakeS3Error("NoSuchKey")

    assert minio_store.delete("jobs/missing/result.json") is False


def test_minio_store_exists_uses_stat_object(minio_store, fake_minio_client):
    """exists 走 stat_object，避免大对象下载开销"""
    fake_minio_client.stat_object.return_value = MagicMock()

    assert minio_store.exists("jobs/abc/result.json") is True
    fake_minio_client.stat_object.assert_called_once_with("test-bucket", "jobs/abc/result.json")

    fake_minio_client.stat_object.side_effect = _FakeS3Error("NoSuchKey")
    assert minio_store.exists("jobs/missing/result.json") is False


# ---------------------------------------------------------------------------- #
#  MinIO 安全 & bucket 生命周期
# ---------------------------------------------------------------------------- #


def test_minio_store_rejects_path_traversal(minio_store):
    """MinIO key 与 LocalFSStore 共用 _sanitize_key：../ 必须拒绝"""
    with pytest.raises(ValueError):
        minio_store.put_bytes("../escape.txt", b"evil")
    with pytest.raises(ValueError):
        minio_store.put_bytes("/abs/path.txt", b"evil")
    with pytest.raises(ValueError):
        minio_store.put_bytes("", b"x")


def test_minio_store_ensure_bucket_creates_when_missing(monkeypatch):
    """bucket 不存在时应主动创建；bucket 已存在则直接跳过"""
    fake_client = MagicMock()
    fake_client.bucket_exists.return_value = False

    monkeypatch.setenv("MINIO_ENDPOINT", "test-minio:9000")

    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value = fake_client
        MinioStore(
            endpoint="test-minio:9000",
            access_key="ak",
            secret_key="sk",
            bucket="new-bucket",
            ensure_bucket=True,
        )

    fake_client.bucket_exists.assert_called_once_with("new-bucket")
    fake_client.make_bucket.assert_called_once_with("new-bucket")


def test_minio_store_ensure_bucket_skips_when_exists(monkeypatch):
    """bucket 已存在时不调用 make_bucket"""
    fake_client = MagicMock()
    fake_client.bucket_exists.return_value = True

    monkeypatch.setenv("MINIO_ENDPOINT", "test-minio:9000")

    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value = fake_client
        MinioStore(
            endpoint="test-minio:9000",
            access_key="ak",
            secret_key="sk",
            bucket="existing-bucket",
            ensure_bucket=True,
        )

    fake_client.bucket_exists.assert_called_once()
    fake_client.make_bucket.assert_not_called()


def test_minio_store_from_env_reads_all_settings(monkeypatch):
    """from_env 必须完整读取 5 个配置项（含 secure 解析）"""
    monkeypatch.setenv("MINIO_ENDPOINT", "env-host:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("MINIO_SECRET_KEY", "env-sk")
    monkeypatch.setenv("MINIO_BUCKET", "env-bucket")
    monkeypatch.setenv("MINIO_SECURE", "1")

    fake_client = MagicMock()
    fake_client.bucket_exists.return_value = True

    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value = fake_client
        store = MinioStore.from_env()

    MockMinio.assert_called_once_with(
        endpoint="env-host:9000",
        access_key="env-ak",
        secret_key="env-sk",
        secure=True,
    )
    assert store._bucket == "env-bucket"


# ---------------------------------------------------------------------------- #
#  后端工厂
# ---------------------------------------------------------------------------- #


def test_factory_default_is_local(monkeypatch):
    """未设 OBJECT_STORE_BACKEND 时默认 local"""
    monkeypatch.delenv("OBJECT_STORE_BACKEND", raising=False)

    store = get_object_store()

    assert isinstance(store, LocalFSStore)
    assert current_object_store_name() == OBJECT_STORE_BACKEND_LOCAL


def test_factory_returns_local_for_explicit_local(monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")

    store = get_object_store()

    assert isinstance(store, LocalFSStore)


def test_factory_returns_minio_when_endpoint_reachable(monkeypatch):
    """env=minio + endpoint 可连通时直接返回 MinioStore"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "minio")
    monkeypatch.setenv("MINIO_ENDPOINT", "test-minio:9000")

    fake_client = MagicMock()
    fake_client.bucket_exists.return_value = True

    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value = fake_client
        store = get_object_store()

    assert isinstance(store, MinioStore)


def test_factory_falls_back_to_local_when_minio_unreachable(monkeypatch):
    """默认（严格=0）：MinIO 不可达时回退 LocalFSStore 并打 ERROR 日志"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "minio")
    monkeypatch.setenv("MINIO_ENDPOINT", "nonexistent-host:9000")
    monkeypatch.setenv("OBJECT_STORE_STRICT", "0")

    # bucket_exists 直接抛网络异常（模拟 MinIO 不可用）
    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value.bucket_exists.side_effect = ConnectionError("nope")
        store = get_object_store()

    assert isinstance(store, LocalFSStore)


def test_factory_object_store_strict_independent_of_job_store_strict(monkeypatch):
    """对象存储严格模式仅看 OBJECT_STORE_STRICT，不被 JOB_STORE_STRICT 干扰"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "minio")
    monkeypatch.setenv("MINIO_ENDPOINT", "nonexistent-host:9000")
    # 即便数据库侧是严格模式，对象存储也应回退而非直接抛错
    monkeypatch.setenv("JOB_STORE_STRICT", "1")
    monkeypatch.setenv("OBJECT_STORE_STRICT", "0")

    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value.bucket_exists.side_effect = ConnectionError("nope")
        store = get_object_store()

    assert isinstance(store, LocalFSStore)


def test_factory_strict_mode_raises_when_minio_unreachable(monkeypatch):
    """严格模式：MinIO 不可用必须直接拒绝启动"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "minio")
    monkeypatch.setenv("MINIO_ENDPOINT", "nonexistent-host:9000")
    monkeypatch.setenv("OBJECT_STORE_STRICT", "1")

    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value.bucket_exists.side_effect = ConnectionError("nope")
        with pytest.raises(RuntimeError, match="严格模式下 MinIO 对象存储不可用"):
            get_object_store()


def test_factory_unknown_backend_falls_back_to_local(monkeypatch):
    """未知 backend 应回退 local 并打 WARNING，避免崩溃"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "azure-blob")

    store = get_object_store()

    assert isinstance(store, LocalFSStore)


def test_factory_aliases(monkeypatch):
    """fs / filesystem → local；s3 → minio"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "fs")
    assert isinstance(get_object_store(), LocalFSStore)

    monkeypatch.setenv("OBJECT_STORE_BACKEND", "s3")
    monkeypatch.setenv("MINIO_ENDPOINT", "test-minio:9000")
    with patch("minio.Minio") as MockMinio:
        MockMinio.return_value.bucket_exists.return_value = True
        assert isinstance(get_object_store(), MinioStore)


# ---------------------------------------------------------------------------- #
#  DatabaseJobRegistry 集成：默认走工厂
# ---------------------------------------------------------------------------- #


def test_database_registry_uses_factory_when_no_store_passed(tmp_path, monkeypatch):
    """未显式注入 ObjectStore 时，DatabaseJobRegistry 默认走 get_object_store()"""
    monkeypatch.setenv("OBJECT_STORE_BACKEND", "local")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'jobs.db'}")
    monkeypatch.setenv("JOB_STORE_BACKEND", "database")

    from app.storage import DatabaseJobRegistry, init_db, reset_engine

    reset_engine()
    init_db()

    reg = DatabaseJobRegistry(ttl_seconds=3600)
    assert isinstance(reg._object_store, LocalFSStore)

    job = reg.create(kind="parse", file_name="x.md")
    job.start()
    job.finish_success([{"page_content": "hello", "metadata": {}}])
    reg.update(job)

    # 反向校验：result 真落到 OBJECT_STORE_ROOT 下的 LocalFSStore
    restored = reg.get(job.id)
    assert restored.result == [{"page_content": "hello", "metadata": {}}]

    reset_engine()


def test_database_registry_accepts_injected_store(tmp_path, monkeypatch):
    """显式注入 object_store 时应绕过工厂，便于测试隔离"""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'inj.db'}")
    monkeypatch.delenv("OBJECT_STORE_BACKEND", raising=False)

    from app.storage import DatabaseJobRegistry, init_db, reset_engine

    reset_engine()
    init_db()

    custom = LocalFSStore(tmp_path / "custom_objects")
    reg = DatabaseJobRegistry(ttl_seconds=3600, object_store=custom)
    assert reg._object_store is custom

    reset_engine()