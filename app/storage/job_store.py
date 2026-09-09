from __future__ import annotations

"""
任务状态数据库仓储：DatabaseJobRegistry

与内存版 JobRegistry 提供同名同签名的 create / get / list / cleanup_expired，
并新增 update(job) 用于把状态机流转结果写回数据库（内存版为 no-op）。

result 大体积产物落对象存储：数据库行只保留 result_ref 字符串引用，
真正数据通过 ObjectStore (LocalFSStore / 未来 MinIO) 读写，
避免大 JSONB 反复读写拖垮数据库 IO。
"""

import json
import logging
import os
import time
from typing import Any

from sqlalchemy import delete, select, update

from .db import session_scope
from .job_record import JobRecord
from .object_store import LocalFSStore, MinioStore, ObjectStore, get_object_store

logger = logging.getLogger(__name__)

# 终态状态集合：与 app.jobs.JobStatus.is_terminal 保持一致（此处以字面量避免循环导入）
_TERMINAL_STATUSES = ("succeeded", "failed")


def _result_object_key(job_id: str) -> str:
    """对象存储中 result 的固定 key（按 job_id 命名空间隔离）"""
    return f"jobs/{job_id}/result.json"


def _serialize_for_object(result: Any) -> bytes:
    """
    将任务结果序列化为字节流落对象存储

    解析产物理论上均为纯 dict/list；此处兜底防止不可 JSON 序列化对象
    （Path / datetime）导致整段产物丢失：
    - 序列化成功 → 直接 dump
    - 失败 → 降级为字符串 repr + 标记，便于事后排查
    """
    if result is None:
        return b"null"
    try:
        return json.dumps(result, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        logger.warning("任务结果包含不可 JSON 序列化的对象，已降级为字符串快照")
        return json.dumps(
            {"__unserializable__": repr(result)},
            ensure_ascii=False,
        ).encode("utf-8")


class DatabaseJobRegistry:
    """基于关系型数据库的任务注册表：支持服务重启后状态不丢失"""

    def __init__(
        self,
        ttl_seconds: float | None = None,
        object_store: ObjectStore | None = None,
    ):
        # 结果保留时长，默认从环境变量 JOB_RESULT_TTL 读取 (秒)，缺省 1800 (30 分钟)
        if ttl_seconds is None:
            ttl_seconds = float(os.environ.get("JOB_RESULT_TTL", "1800"))
        self._ttl = ttl_seconds
        # 对象存储：默认走工厂（按 env OBJECT_STORE_BACKEND 选 local | minio）；
        # 显式传入则用于测试隔离或自定义实现
        self._object_store = object_store or get_object_store()

    # ------------------------------------------------------------------ #
    #  基础 CRUD
    # ------------------------------------------------------------------ #

    def create(self, kind: str, file_name: str, strategy: str | None = None) -> Any:
        """创建并持久化一个新任务（queued 状态），返回 Job 对象"""
        from app.jobs import Job

        job = Job(kind=kind, file_name=file_name, strategy=strategy)

        with session_scope() as session:
            session.add(
                JobRecord(
                    id=job.id,
                    kind=job.kind,
                    file_name=job.file_name,
                    status=job.status.value,
                    strategy=job.strategy,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    error=job.error,
                    result_ref=None,
                    retry_count=0,
                )
            )
        return job

    def get(self, job_id: str) -> Any | None:
        """按 id 查询任务，不存在返回 None（result 从对象存储反序列化填回）"""
        from app.jobs import Job, JobStatus

        with session_scope() as session:
            row = session.get(JobRecord, job_id)

        if row is None:
            return None

        result = self._load_result(row.result_ref)
        return Job(
            kind=row.kind,
            file_name=row.file_name,
            id=row.id,
            status=JobStatus(row.status),
            strategy=row.strategy,
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            error=row.error,
            result=result,
        )

    def list(self, limit: int = 20) -> list[Any]:
        """按创建时间倒序返回最近任务（不含 result，调用方按需单独 GET /jobs/{id}/result）"""
        from app.jobs import Job, JobStatus

        stmt = select(JobRecord).order_by(JobRecord.created_at.desc()).limit(limit)

        with session_scope() as session:
            rows = session.execute(stmt).scalars().all()
            return [
                Job(
                    kind=row.kind,
                    file_name=row.file_name,
                    id=row.id,
                    status=JobStatus(row.status),
                    strategy=row.strategy,
                    created_at=row.created_at,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    error=row.error,
                    # 列表仅元数据，不主动读对象存储，避免一次列表拉取 N 次大 IO
                    result=None,
                )
                for row in rows
            ]

    def update(self, job: Any) -> None:
        """把 Job 的当前状态写回数据库，result 切到对象存储"""
        result_ref = None
        if job.result is not None:
            payload = _serialize_for_object(job.result)
            key = _result_object_key(job.id)
            result_ref = self._object_store.put_bytes(key, payload)

        values = {
            "status": job.status.value,
            "strategy": job.strategy,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
            "result_ref": result_ref,
        }

        with session_scope() as session:
            result = session.execute(update(JobRecord).where(JobRecord.id == job.id).values(**values))
            # 行不存在（例如数据库被清空）：补偿插入，保证状态不丢
            if result.rowcount == 0:
                session.add(
                    JobRecord(
                        id=job.id,
                        kind=job.kind,
                        file_name=job.file_name,
                        **values,
                        created_at=job.created_at,
                        retry_count=0,
                    )
                )

    # ------------------------------------------------------------------ #
    #  TTL 清理
    # ------------------------------------------------------------------ #

    def cleanup_expired(self) -> list[str]:
        """清理超过 TTL 的终态任务：数据库行 + 对象存储产物一并删除"""
        cutoff = time.time() - self._ttl

        with session_scope() as session:
            expired_ids = list(
                session.execute(
                    select(JobRecord.id).where(
                        JobRecord.status.in_(_TERMINAL_STATUSES),
                        JobRecord.finished_at.is_not(None),
                        JobRecord.finished_at < cutoff,
                    )
                ).scalars()
            )
            if expired_ids:
                session.execute(delete(JobRecord).where(JobRecord.id.in_(expired_ids)))

        # 同时清理对象存储中的 result 文件（失败不影响数据库清理结果）
        for job_id in expired_ids:
            try:
                self._object_store.delete(_result_object_key(job_id))
            except Exception as e:  # pragma: no cover - 清理属非关键路径
                logger.warning("清理对象存储 result 失败 (job=%s): %s", job_id, e)

        return expired_ids

    # ------------------------------------------------------------------ #
    #  内部：result 反序列化
    # ------------------------------------------------------------------ #

    def _load_result(self, result_ref: str | None) -> Any:
        """按 result_ref 从对象存储加载并反序列化 result；不存在/失败则返回 None"""
        if not result_ref:
            return None
        try:
            data = self._object_store.get_bytes(result_ref)
        except Exception as e:  # noqa: BLE001 - 对象存储异常不应让查询整体失败
            logger.warning("对象存储读取失败 (ref=%s): %s", result_ref, e)
            return None
        if data is None:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning("result 反序列化失败 (ref=%s): %s", result_ref, e)
            return None