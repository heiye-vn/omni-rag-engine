"""
Alembic 迁移环境配置

- 数据库连接串统一从环境变量 DATABASE_URL 读取，与 app/storage/db.py 保持一致
  （避免 alembic 与 ORM 各自硬编码连接串的双源真理问题）。
- target_metadata 指向 SQLAlchemy 的元数据，自动比对 ORM 模型变更。
- SQLite / PostgreSQL 都走同一路径，差异由 SQLAlchemy 方言层处理。
- 关闭固定 prefix（truncate_slug_length 仍可用），简化脚本命名。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# 让 alembic 能 import app.*，否则 env.py 找不到 Base 与 JobRecord
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 从 ORM 导入 Base 与所有 model 以确保元数据注册完整
from app.storage.db import Base  # noqa: E402
from app.storage.job_record import JobRecord  # noqa: E402,F401  (确保 ORM 注册到 Base.metadata)

config = context.config

# 接管 sqlalchemy.url：env > .ini 文件，避免两处配置漂移
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# 走标准 logging 配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    离线模式：仅输出 SQL 脚本而不连真实数据库，常用于生成 DBA 审核脚本
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite 关闭 batch 模式（不支持），PostgreSQL 开启（支持 ALTER TABLE 复合操作）
        render_as_batch=url is not None and url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    在线模式：连真实数据库执行迁移
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()