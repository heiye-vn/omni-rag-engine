from __future__ import annotations

"""
数据库基础设施：SQLAlchemy 2.0 引擎 / 会话工厂 / 建表 / 健康检查

设计说明：
- 引擎为进程内懒加载单例，首次访问时按 DATABASE_URL 建连，避免 import 即连接。
- PostgreSQL 为生产目标（与 docker-compose 的 pgvector 服务同实例，复用现有容器），
  SQLite 仅用于本地零依赖启动与单元测试。
- 连接池开启 pool_pre_ping，缓解数据库重启/网络闪断后的"僵尸连接"问题。
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# 默认连接串：与 docker-compose.yml 中 pgvector 服务的库名/账号/密码保持一致
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/omni_rag"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类，Alembic 迁移的 metadata 来源"""


def get_database_url() -> str:
    """读取数据库连接串（env DATABASE_URL 优先，缺省回落到 compose 中的 PostgreSQL）"""
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _build_engine(url: str) -> Engine:
    """按数据库类型构造引擎，差异化配置连接参数"""
    kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}

    if url.startswith("sqlite"):
        # SQLite：允许多线程共享连接，并放宽锁等待超时（解析线程会并发写状态）
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs["pool_size"] = int(os.environ.get("DB_POOL_SIZE", "5"))
        kwargs["max_overflow"] = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
        kwargs["pool_recycle"] = int(os.environ.get("DB_POOL_RECYCLE", "1800"))

    return create_engine(url, **kwargs)


def get_engine() -> Engine:
    """获取（或懒加载创建）全局引擎单例"""
    global _engine

    if _engine is None:
        url = get_database_url()
        _engine = _build_engine(url)

        # SQLite 开启 WAL：读写不互相阻塞，避免解析线程写状态时阻塞轮询查询
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _enable_sqlite_wal(dbapi_conn: object, _: object) -> None:
                cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        logger.info("数据库引擎已初始化: %s", _engine.url.render_as_string(hide_password=True))

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """获取（或懒加载创建）会话工厂单例"""
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)

    return _session_factory


def reset_engine() -> None:
    """
    释放并重置全局引擎与会话工厂

    主要用于测试隔离（切换 DATABASE_URL 后重建连接）与运维场景下的重连。
    """
    global _engine, _session_factory

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务性会话上下文：正常退出提交、异常回滚、最终关闭会话"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    将数据库 schema 迁移到最新版本（head）

    - 走 Alembic 迁移链而非 Base.metadata.create_all，避免破坏式变更
    - 已是 head 时为 no-op，可放心在每次启动时调用
    - Alembic 是主依赖（uv add alembic），未安装则降级 create_all 并打 ERROR 日志

    手动迁移命令（CI/CD 推荐）：
        uv run alembic upgrade head
    """
    try:
        from alembic import command
        from alembic.config import Config

        # alembic.ini 与 alembic/ 与 app/storage/ 同级
        project_root = Path(__file__).resolve().parent.parent.parent
        cfg = Config(str(project_root / "alembic.ini"))
        # env.py 内部读 DATABASE_URL（env 优先于 alembic.ini）
        command.upgrade(cfg, "head")
        logger.info("Alembic 迁移已应用至 head")
    except ImportError as e:
        # 极端兜底：alembic 未装时回退 create_all（仅 MVP 场景）
        from .job_record import JobRecord  # noqa: F401

        logger.error(
            "alembic 未安装，回退为 Base.metadata.create_all（仅 MVP 适用，"
            "schema 演进将不可控）。原因: %s", e
        )
        Base.metadata.create_all(bind=get_engine())


def health_check() -> bool:
    """数据库连通性检查：执行 SELECT 1，异常返回 False 而不抛出"""
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as e:  # noqa: BLE001 - 健康检查不允许抛出异常打断调用方
        logger.warning("数据库健康检查失败: %s", e)
        return False


def database_is_configured() -> bool:
    """判断是否显式配置了数据库（用于决定默认后端行为）"""
    return bool(os.environ.get("DATABASE_URL")) or os.environ.get(
        "JOB_STORE_BACKEND", ""
    ).lower() in ("database", "db", "postgres", "postgresql", "sqlite")
