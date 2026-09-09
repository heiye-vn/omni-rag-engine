"""
任务状态持久化测试：DatabaseJobRegistry + ObjectStore 协作

运行前提：sqlalchemy + psycopg 已在主依赖组（uv sync 默认包含）；
未安装时本文件整体跳过，不阻断主测试套件。

验证点：
- 任务在数据库中的创建 / 查询 / 列表往返
- result 真正落到对象存储（LocalFSStore），数据库行只保留 result_ref 字符串
- 状态流转经 update() 后，重启注册表（等价服务重启）result 可恢复
- TTL 清理同时删除数据库行与对象存储文件
- 后端不可用时：默认回退内存并告警，严格模式下直接抛错
"""

import os
import time

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy", reason="未安装 SQLAlchemy 主依赖")

from app.jobs import Job, JobStatus, get_job_registry  # noqa: E402
from app.storage import DatabaseJobRegistry, LocalFSStore, reset_engine  # noqa: E402


@pytest.fixture
def db_registry(tmp_path, monkeypatch):
    """基于 SQLite 临时文件的数据库注册表 + 配套对象存储"""
    db_file = tmp_path / "jobs.db"
    objects_root = tmp_path / "objects"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("JOBS_DATA_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(objects_root))
    reset_engine()

    from app.storage import init_db

    init_db()

    yield DatabaseJobRegistry(ttl_seconds=3600)

    reset_engine()


# ---------------------------------------------------------------------------- #
#  基础读写
# ---------------------------------------------------------------------------- #


def test_create_and_get_roundtrip(db_registry):
    """创建任务后可按 id 从数据库读回，字段完整一致"""
    job = db_registry.create(kind="parse", file_name="report.pdf")

    loaded = db_registry.get(job.id)
    assert loaded is not None
    assert loaded.id == job.id
    assert loaded.kind == "parse"
    assert loaded.file_name == "report.pdf"
    assert loaded.status == JobStatus.QUEUED


def test_get_unknown_id_returns_none(db_registry):
    """查询不存在的任务应返回 None 而非抛异常"""
    assert db_registry.get("nonexistent") is None


def test_list_sorted_desc(db_registry):
    """列表按创建时间倒序返回（不含 result，避免一次列表触发 N 次对象 IO）"""
    first = db_registry.create(kind="parse", file_name="1.md")
    time.sleep(0.01)
    second = db_registry.create(kind="parse", file_name="2.md")

    ids = [j.id for j in db_registry.list(limit=10)]
    assert ids == [second.id, first.id]
    assert len(db_registry.list(limit=1)) == 1
    # list 不应主动加载 result
    assert all(j.result is None for j in db_registry.list(limit=10))


# ---------------------------------------------------------------------------- #
#  持久化语义（重启不丢）
# ---------------------------------------------------------------------------- #


def test_status_survives_registry_reopen(db_registry):
    """状态流转后重新打开注册表（等价服务重启），running 状态仍可恢复"""
    job = db_registry.create(kind="parse", file_name="重启验证.pdf")
    job.start()
    db_registry.update(job)

    # 丢弃原对象，用指向同一数据库文件的新注册表模拟服务重启
    reopened = DatabaseJobRegistry(ttl_seconds=3600)
    restored = reopened.get(job.id)

    assert restored is not None
    assert restored.status == JobStatus.RUNNING
    assert restored.started_at is not None


def test_result_persisted_in_object_store(db_registry):
    """成功结果应真正落到对象存储（LocalFSStore），数据库只保留 result_ref 引用"""
    from sqlalchemy import select

    from app.storage.db import session_scope
    from app.storage.job_record import JobRecord

    job = db_registry.create(kind="parse_and_chunk", file_name="doc.pdf", strategy="sliding_window")
    job.start()
    payload = [{"page_content": "正文内容", "metadata": {"page_number": 1}}]
    job.finish_success(payload)
    db_registry.update(job)

    # 1. 数据库行：result_ref 是字符串而非 JSON 序列化字段
    with session_scope() as s:
        row = s.execute(select(JobRecord).where(JobRecord.id == job.id)).scalar_one()
        assert row.result_ref is not None
        assert row.result_ref.startswith("jobs/")
        assert row.result_ref.endswith("result.json")
        # 验证 ORM 字段类型已从 JSON 切到 String（数据库里不应是大 JSON 列）
        col_type = str(JobRecord.result_ref.type)
        assert "VARCHAR" in col_type or "STRING" in col_type.upper()

    # 2. 对象存储：能读到原始 JSON
    obj = LocalFSStore.from_env()
    raw = obj.get_bytes(row.result_ref)
    assert raw is not None
    import json

    assert json.loads(raw.decode("utf-8")) == payload

    # 3. get() 反向回填 result 字段
    restored = db_registry.get(job.id)
    assert restored.status == JobStatus.SUCCEEDED
    assert restored.result == payload
    assert restored.finished_at is not None


def test_failure_error_persisted(db_registry):
    """失败终态的错误信息应落库（失败任务不写对象存储）"""
    job = db_registry.create(kind="parse", file_name="broken.pdf")
    job.start()
    job.finish_failure("解析失败: 不支持的格式")
    db_registry.update(job)

    restored = db_registry.get(job.id)

    assert restored.status == JobStatus.FAILED
    assert restored.error == "解析失败: 不支持的格式"
    assert restored.result is None


def test_update_missing_row_compensates_with_insert(db_registry):
    """更新不存在的行时应补偿插入，保证状态不丢（数据库被清空的场景）"""
    job = Job(kind="parse", file_name="orphan.md")
    job.start()
    job.finish_success([{"page_content": "x", "metadata": {}}])

    db_registry.update(job)

    restored = db_registry.get(job.id)
    assert restored is not None
    assert restored.status == JobStatus.SUCCEEDED
    assert restored.result == [{"page_content": "x", "metadata": {}}]
    assert os.environ.get("DATABASE_URL", "").startswith("sqlite")


def test_object_store_key_isolation(tmp_path, monkeypatch):
    """两个 job 的 result 应按 job_id 命名空间隔离，互不污染"""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'iso.db'}")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    reset_engine()
    from app.storage import init_db

    init_db()

    reg = DatabaseJobRegistry(ttl_seconds=3600)
    a = reg.create(kind="parse", file_name="a.md")
    b = reg.create(kind="parse", file_name="b.md")

    a.start()
    a.finish_success([{"page_content": "A", "metadata": {}}])
    reg.update(a)

    b.start()
    b.finish_success([{"page_content": "B", "metadata": {}}])
    reg.update(b)

    # 两个对象的 result 都应可独立读回
    assert reg.get(a.id).result == [{"page_content": "A", "metadata": {}}]
    assert reg.get(b.id).result == [{"page_content": "B", "metadata": {}}]
    reset_engine()


# ---------------------------------------------------------------------------- #
#  TTL 清理
# ---------------------------------------------------------------------------- #


def test_cleanup_expired_removes_row_and_object(tmp_path, monkeypatch):
    """超过 TTL 的终态任务：数据库行 + 对象存储 result 文件应被一并清理"""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cleanup.db'}")
    monkeypatch.setenv("OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    reset_engine()

    from app.storage import init_db

    init_db()

    registry = DatabaseJobRegistry(ttl_seconds=0.05)

    finished = registry.create(kind="parse", file_name="done.md")
    finished.start()
    finished.finish_success([{"page_content": "x", "metadata": {}}])
    registry.update(finished)

    running = registry.create(kind="parse", file_name="busy.md")
    running.start()
    registry.update(running)

    # 验证对象文件已写入
    obj = LocalFSStore.from_env()
    key = f"jobs/{finished.id}/result.json"
    assert obj.exists(key)

    time.sleep(0.08)
    removed = registry.cleanup_expired()

    assert finished.id in removed
    assert registry.get(finished.id) is None
    assert not obj.exists(key)  # 对象文件一并清理
    assert registry.get(running.id) is not None  # 运行中不清理

    reset_engine()


# ---------------------------------------------------------------------------- #
#  后端选型与降级策略
# ---------------------------------------------------------------------------- #


def test_fallback_to_memory_when_database_unavailable(tmp_path, monkeypatch):
    """数据库不可用时：默认回退内存后端（不抛异常），保证服务可用"""
    monkeypatch.setenv("DATABASE_URL", "sqlite:////nonexistent_dir_xyz/jobs.db")
    monkeypatch.setenv("JOB_STORE_STRICT", "0")
    reset_engine()

    registry = get_job_registry("database")

    assert type(registry).__name__ == "JobRegistry"
    job = registry.create(kind="parse", file_name="a.md")
    assert registry.get(job.id).status == JobStatus.QUEUED

    reset_engine()


def test_strict_mode_raises_when_database_unavailable(tmp_path, monkeypatch):
    """严格模式：数据库不可用必须直接失败，杜绝静默降级"""
    monkeypatch.setenv("DATABASE_URL", "sqlite:////nonexistent_dir_xyz/jobs.db")
    monkeypatch.setenv("JOB_STORE_STRICT", "1")
    reset_engine()

    with pytest.raises(RuntimeError, match="严格模式"):
        get_job_registry("database")

    reset_engine()


def test_unknown_backend_falls_back_to_memory(monkeypatch):
    """未知后端标识应回退内存并给出告警，而非崩溃"""
    monkeypatch.setenv("JOB_STORE_BACKEND", "mongodb")
    registry = get_job_registry()
    assert type(registry).__name__ == "JobRegistry"


# ---------------------------------------------------------------------------- #
#  ObjectStore 安全
# ---------------------------------------------------------------------------- #


def test_object_store_rejects_path_traversal(tmp_path):
    """LocalFSStore 应拒绝 ../ 路径穿越，防止越权读取文件"""
    obj = LocalFSStore(tmp_path / "objects")

    with pytest.raises(ValueError):
        obj.put_bytes("../escape.txt", b"evil")
    with pytest.raises(ValueError):
        obj.put_bytes("a\\..\\b.txt", b"evil")
    with pytest.raises(ValueError):
        obj.put_bytes("", b"x")
    with pytest.raises(ValueError):
        obj.put_bytes("/abs/path.txt", b"x")


def test_object_store_atomic_write(tmp_path):
    """写入过程并发读取不应看到半截文件（tmp + rename）"""
    obj = LocalFSStore(tmp_path / "objects")
    key = "atomic/test.bin"
    obj.put_bytes(key, b"x" * 1024)

    # 写入完成不应残留 .tmp
    tmp_file = tmp_path / "objects" / (key + ".tmp")
    assert not tmp_file.exists()
    # 读回完整内容
    assert obj.get_bytes(key) == b"x" * 1024