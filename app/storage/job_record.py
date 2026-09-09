from __future__ import annotations

"""
异步任务持久化表模型：job_records

字段与 app.jobs.Job 状态机一一对应，时间戳沿用 Unix epoch 秒（float），
保证 to_dict() 输出结构与内存后端完全一致，前端无需适配。
"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class JobRecord(Base):
    """异步解析任务的数据库行映射"""

    __tablename__ = "job_records"

    # 任务唯一标识：与内存后端同为 12 位 hex
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # 任务类型: parse | parse_and_chunk
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # 原始上传文件名（展示用）
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    # 生命周期状态: queued | running | succeeded | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # 切块策略 (仅 parse_and_chunk 有效)
    strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 提交时间戳 (epoch 秒)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    # 开始执行时间戳
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 终态时间戳，TTL 清理的判定依据
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    # 失败原因（可读信息）
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 成功结果的对象存储引用（如 jobs/abc123/result.json）；
    # 数据库只存引用，真正数据落对象存储（LocalFSStore / MinIO），避免大 JSONB 拖累 IO。
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 重试次数（为后续失败重试预留，当前恒为 0）
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # TTL 清理的核心查询：按状态 + 终态时间扫描
    __table_args__ = (Index("ix_job_records_status_finished", "status", "finished_at"),)
