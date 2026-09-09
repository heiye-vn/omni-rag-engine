from __future__ import annotations

"""
进程内异步解析任务模块：Job 状态机 + 线程安全 JobRegistry + 线程池执行器

设计说明（见 design.md §11）：
- 大文件解析 (PDF/OCR/Whisper) 为 CPU 密集同步调用，直接在 async 端点内执行会阻塞
  整个事件循环，导致服务对所有请求无响应。
- 本模块通过 ThreadPoolExecutor 将解析任务移出事件循环，进程内注册表登记任务状态，
  前端通过轮询 GET /api/v1/jobs/{job_id} 获取结果。
- Stage 2 (生产级) 将替换为 Celery + Redis 分布式队列，本模块的 Job 状态机与
  API 契约保持不变。
- Stage 2.5 (当前)：新增数据库持久化后端。JobRegistry 保留为内存实现，
  DatabaseJobRegistry（见 app/storage/）提供同签名的数据库实现，由
  get_job_registry() 按 env JOB_STORE_BACKEND 统一路由：
    memory   (默认) —— 进程内 dict，重启即失，零外部依赖
    database         —— PostgreSQL / SQLite 持久化，重启不丢、支持多副本共享
  数据库后端不可用时默认回退内存并打印 ERROR 日志；设 JOB_STORE_STRICT=1 改为直接失败，
  杜绝"静默降级"掩盖真实故障。
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 可选的任务存储后端标识
JOB_BACKEND_MEMORY = "memory"
JOB_BACKEND_DATABASE = "database"
# database 后端在环境变量中的等价别名
_DATABASE_ALIASES = frozenset({"database", "db", "postgres", "postgresql", "sqlite"})
_MEMORY_ALIASES = frozenset({"memory", "mem", ""})


# ---------------------------------------------------------------------------- #
#  任务状态机
# ---------------------------------------------------------------------------- #


class JobStatus(str, Enum):
    """任务生命周期状态：queued → running → succeeded | failed（终态不可变更）"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """是否为终态（succeeded / failed）"""
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED)


@dataclass
class Job:
    """
    一个异步解析任务的完整状态快照
    """

    kind: str  # 任务类型: parse | parse_and_chunk
    file_name: str  # 原始上传文件名
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])  # 任务唯一标识
    status: JobStatus = JobStatus.QUEUED
    strategy: str | None = None  # 切块策略 (仅 kind=parse_and_chunk 时有效)
    created_at: float = field(default_factory=time.time)  # 提交时间戳 (秒)
    started_at: float | None = None  # 开始执行时间戳
    finished_at: float | None = None  # 终态时间戳
    error: str | None = None  # 失败原因 (可读信息)
    result: Any = None  # 成功结果 (ParsedDocument[] | ChunkOut[])

    def start(self) -> None:
        """转移到 running 状态"""
        if self.status != JobStatus.QUEUED:
            raise RuntimeError(f"任务 {self.id} 状态为 {self.status.value}，无法开始执行")
        self.status = JobStatus.RUNNING
        self.started_at = time.time()

    def finish_success(self, result: Any) -> None:
        """转移到 succeeded 终态并登记结果"""
        if self.status != JobStatus.RUNNING:
            raise RuntimeError(f"任务 {self.id} 状态为 {self.status.value}，无法标记成功")
        self.status = JobStatus.SUCCEEDED
        self.result = result
        self.finished_at = time.time()

    def finish_failure(self, error: str) -> None:
        """转移到 failed 终态并记录错误信息"""
        if self.status not in (JobStatus.RUNNING, JobStatus.QUEUED):
            raise RuntimeError(f"任务 {self.id} 状态为 {self.status.value}，无法标记失败")
        self.status = JobStatus.FAILED
        self.error = error
        self.finished_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        """导出为可直接 json.dumps 的干净字典（result 原样透传，由调用方保证可序列化）"""
        return {
            "job_id": self.id,
            "kind": self.kind,
            "file_name": self.file_name,
            "status": self.status.value,
            "strategy": self.strategy,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": self.result,
        }


# ---------------------------------------------------------------------------- #
#  线程安全任务注册表
# ---------------------------------------------------------------------------- #


class JobRegistry:
    """
    进程内任务注册表：dict + 互斥锁，支持并发创建/查询与 TTL 过期清理
    """

    def __init__(self, ttl_seconds: float | None = None) -> None:
        # 结果保留时长，默认从环境变量 JOB_RESULT_TTL 读取 (秒)，缺省 1800 (30 分钟)
        if ttl_seconds is None:
            ttl_seconds = float(os.environ.get("JOB_RESULT_TTL", "1800"))
        self._ttl = ttl_seconds
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str, file_name: str, strategy: str | None = None) -> Job:
        """创建并登记一个新任务（queued 状态）"""
        job = Job(kind=kind, file_name=file_name, strategy=strategy)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        """按 id 查询任务，不存在返回 None"""
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[Job]:
        """按创建时间倒序返回最近任务（不包含 result 以外的字段裁剪，由调用方决定）"""
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def cleanup_expired(self) -> list[str]:
        """
        清理超过 TTL 的终态任务及其产物目录，返回被清理的 job_id 列表。
        运行中/排队中的任务不受影响。
        """
        now = time.time()
        expired_ids: list[str] = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.status.is_terminal and job.finished_at is not None:
                    if now - job.finished_at > self._ttl:
                        expired_ids.append(job_id)
                        del self._jobs[job_id]
        # 清理任务产物目录 (data/jobs/{job_id}/)
        for job_id in expired_ids:
            job_dir = _jobs_data_dir() / job_id
            if job_dir.exists():
                _remove_tree_safe(job_dir)
        return expired_ids

    def update(self, job: Job) -> None:
        """
        状态回写钩子：内存后端为空实现

        内存注册表中 get() 返回的是同一对象引用，就地修改即可见；
        此处仅为与 DatabaseJobRegistry 保持接口一致而保留。
        """


# ---------------------------------------------------------------------------- #
#  线程池执行器与任务提交
# ---------------------------------------------------------------------------- #


def _jobs_data_dir() -> Path:
    """任务产物根目录：data/jobs/（可用 env JOBS_DATA_DIR 覆盖，便于测试隔离）"""
    return Path(os.environ.get("JOBS_DATA_DIR", os.path.join("data", "jobs")))


def _remove_tree_safe(path: Path) -> None:
    """安全递归删除目录，失败时仅记录日志不抛出（清理是非关键路径）"""
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # pragma: no cover - rmtree(ignore_errors) 基本不抛
        pass


# 解析线程池：Whisper / PaddleOCR 内存开销大，默认并发 4，可用 env PARSE_WORKERS 覆盖。
# 调高并发需同时关注物理机内存（每路解析约 1-3 GB），可通过 `top` / `docker stats` 观察。
_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, int(os.environ.get("PARSE_WORKERS", "4"))),
    thread_name_prefix="parse-job",
)

def get_job_registry(
    backend: str | None = None,
    ttl_seconds: float | None = None,
) -> Any:
    """
    任务注册表后端工厂：按 env JOB_STORE_BACKEND 路由到内存或数据库实现

    Args:
        backend: 显式指定后端 (memory / database)，缺省读取 env JOB_STORE_BACKEND
        ttl_seconds: 结果保留时长，缺省沿用各后端的 env 默认值

    Returns:
        JobRegistry (内存) 或 DatabaseJobRegistry (数据库) 实例

    Raises:
        RuntimeError: JOB_STORE_STRICT=1 且数据库后端初始化失败时抛出
    """
    chosen = (backend or os.environ.get("JOB_STORE_BACKEND", JOB_BACKEND_DATABASE)).strip().lower()

    if chosen in _MEMORY_ALIASES:
        return JobRegistry(ttl_seconds=ttl_seconds)

    if chosen not in _DATABASE_ALIASES:
        logger.warning("未知的任务存储后端 '%s'，回退使用内存后端", chosen)
        return JobRegistry(ttl_seconds=ttl_seconds)

    strict = os.environ.get("JOB_STORE_STRICT", "0").strip().lower() in ("1", "true", "yes")

    try:
        from app.storage import DatabaseJobRegistry, get_database_url, health_check, init_db

        # 建表（幂等）并做一次连通性校验，确保后端真实可用
        init_db()
        if not health_check():
            raise RuntimeError(f"数据库连通性检查未通过: {get_database_url()}")

        registry = DatabaseJobRegistry(ttl_seconds=ttl_seconds)
        logger.info("任务存储后端已启用: database (%s)", get_database_url())
        return registry
    except Exception as e:  # noqa: BLE001 - 后端选型失败必须有兜底，但绝不静默
        if strict:
            raise RuntimeError(f"严格模式下数据库后端不可用，拒绝启动: {e}") from e
        logger.error(
            "数据库任务后端初始化失败，已回退为内存后端（任务状态将在重启后丢失）。原因: %s",
            e,
            exc_info=True,
        )
        return JobRegistry(ttl_seconds=ttl_seconds)


def current_backend_name() -> str:
    """返回当前生效的任务存储后端名称，供 /health 等可观测性接口使用"""
    backend = os.environ.get("JOB_STORE_BACKEND", JOB_BACKEND_DATABASE).strip().lower()
    if backend in _DATABASE_ALIASES:
        # 实际可能已回退内存，以实例类型为准
        return JOB_BACKEND_DATABASE if type(job_registry).__name__ == "DatabaseJobRegistry" else JOB_BACKEND_MEMORY
    return JOB_BACKEND_MEMORY


# 全局任务注册表 (进程内单例，后端由 JOB_STORE_BACKEND 决定)
job_registry = get_job_registry()

# 允许的任务类型白名单
JOB_KINDS = frozenset({"parse", "parse_and_chunk"})


def submit_job(
    kind: str,
    file_name: str,
    work: Callable[[Job], Any],
    strategy: str | None = None,
) -> Job:
    """
    提交一个异步任务到线程池执行。

    Args:
        kind: 任务类型 (parse | parse_and_chunk)
        file_name: 原始上传文件名（用于展示）
        work: 任务执行体，入参为 Job（已在 running 状态），返回值作为任务结果；
              抛出的异常会被捕获并转为 failed 终态
        strategy: 切块策略 (可选)

    Returns:
        已登记为 queued 状态的 Job（调用方立即返回 job_id 给前端）
    """
    job = job_registry.create(kind=kind, file_name=file_name, strategy=strategy)

    def _persist() -> None:
        """把当前状态写回存储后端（内存后端为空操作，失败仅记录不阻断任务）"""
        try:
            job_registry.update(job)
        except Exception as e:  # noqa: BLE001 - 持久化失败不得让解析任务崩溃
            logger.error("任务 %s 状态持久化失败: %s", job.id, e)

    def _run() -> None:
        job.start()
        _persist()  # queued → running
        try:
            result = work(job)
            job.finish_success(result)
        except Exception as exc:  # noqa: BLE001 - 任意解析异常统一转失败终态
            job.finish_failure(f"{type(exc).__name__}: {exc}")
        _persist()  # running → succeeded / failed

    _EXECUTOR.submit(_run)
    return job


async def cleanup_loop(interval_seconds: float = 60.0) -> None:
    """
    后台 TTL 清理协程：由 FastAPI lifespan 启动，周期性清理过期终态任务。

    独立线程池中触发清理（避免在事件循环内做文件 IO），仅周期性调度。
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            # cleanup_expired 只做 dict 删除与轻量文件删除，放到默认执行器执行
            await asyncio.get_running_loop().run_in_executor(None, job_registry.cleanup_expired)
        except Exception:  # pragma: no cover - 清理失败不影响主流程
            continue
