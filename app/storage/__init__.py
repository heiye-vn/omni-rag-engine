"""
状态持久化层：基于 SQLAlchemy 2.0 的关系型数据库存储

模块职责：
- db.py            引擎 / 会话 / 建表与健康检查基础设施
- job_record.py    异步任务的 ORM 表模型 (job_records)
- job_store.py     面向 Job 状态机的仓储实现 (DatabaseJobRegistry)
- object_store.py  任务大体积产物的对象存储抽象 (LocalFSStore / MinioStore)

设计约定（见 design.md §11 与 RAG_ROADMAP 6.x）：
- 数据库与对象存储为**默认配置**：均已在 pyproject 主依赖组，无需 uv sync --extra。
  启动时按 env 选型：
    - JOB_STORE_BACKEND:   memory | database（默认 database）
    - OBJECT_STORE_BACKEND: local  | minio  （默认 local；推荐生产 minio）
- 数据库/对象存储任一不可用时默认回退到本地/内存并打印 ERROR 日志；
  严格模式（env *_STRICT=1）改为直接失败，避免"静默降级"掩盖真实故障。
- 默认连接串与 docker-compose 中的 pgvector (PostgreSQL 16) + minio 服务保持一致，
  同时兼容 SQLite，便于本地零依赖启动与单元测试。
"""

from .db import (
    Base,
    DEFAULT_DATABASE_URL,
    database_is_configured,
    get_database_url,
    get_engine,
    health_check,
    init_db,
    reset_engine,
    session_scope,
)
from .job_record import JobRecord
from .job_store import DatabaseJobRegistry
from .object_store import (
    OBJECT_STORE_BACKEND_LOCAL,
    OBJECT_STORE_BACKEND_MINIO,
    LocalFSStore,
    MinioStore,
    ObjectStore,
    current_object_store_name,
    get_object_store,
)

__all__ = [
    "Base",
    "DEFAULT_DATABASE_URL",
    "DatabaseJobRegistry",
    "JobRecord",
    "LocalFSStore",
    "MinioStore",
    "OBJECT_STORE_BACKEND_LOCAL",
    "OBJECT_STORE_BACKEND_MINIO",
    "ObjectStore",
    "current_object_store_name",
    "database_is_configured",
    "get_database_url",
    "get_engine",
    "get_object_store",
    "health_check",
    "init_db",
    "reset_engine",
    "session_scope",
]