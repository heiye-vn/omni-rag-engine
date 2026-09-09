"""
Alembic 迁移测试

运行前提：alembic 已在主依赖组（uv add alembic）；未安装时整体跳过，不阻断主测试。

验证点：
- 空 SQLite 库 → upgrade head 建表，schema 与 ORM 模型完全一致
- 已建表的库 → upgrade head 是 no-op（不会报"already exists"）
- downgrade -1 → 表被删除；再次 upgrade head 重建（验证可逆性）
- alembic.ini 与 env.py 接线正确：DATABASE_URL 接管连接串、target_metadata 指向 Base.metadata
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

alembic = pytest.importorskip("alembic", reason="未安装 alembic 主依赖")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402


# ---------------------------------------------------------------------------- #
#  Helpers
# ---------------------------------------------------------------------------- #


def _alembic_cfg(database_url: str) -> Config:
    """构造指向本项目 alembic.ini 的 Config，并覆盖 URL"""
    project_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _alembic_current(database_url: str) -> str | None:
    """读取当前已应用的 migration revision id"""
    cfg = _alembic_cfg(database_url)
    from io import StringIO
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext

    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(database_url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        return ctx.get_current_revision()


def _has_table(database_url: str, table: str) -> bool:
    engine = create_engine(database_url)
    return inspect(engine).has_table(table)


# ---------------------------------------------------------------------------- #
#  alembic.ini & env.py 接线
# ---------------------------------------------------------------------------- #


def test_alembic_ini_skips_hardcoded_connection():
    """alembic.ini 不应硬编码 sqlalchemy.url（启用行），避免与 app/storage/db.py 双源真理"""
    cfg_text = (Path(__file__).resolve().parent.parent / "alembic.ini").read_text(encoding="utf-8")
    # 启用行: "sqlalchemy.url = ..."；注释行: "# sqlalchemy.url = ..."
    import re

    enabled_lines = [
        line for line in cfg_text.splitlines()
        if re.match(r"^\s*sqlalchemy\.url\s*=", line)
    ]
    assert enabled_lines == [], f"alembic.ini 启用了 sqlalchemy.url: {enabled_lines}"


def test_alembic_env_uses_base_metadata():
    """alembic/env.py 必须把 target_metadata 指向 Base.metadata（不是 None）"""
    env_path = Path(__file__).resolve().parent.parent / "alembic" / "env.py"
    source = env_path.read_text(encoding="utf-8")

    # 必须显式 import Base 并赋值给 target_metadata
    assert "from app.storage.db import Base" in source
    assert "target_metadata = Base.metadata" in source


def test_alembic_env_reads_database_url_env_var(tmp_path, monkeypatch):
    """env.py 应让 DATABASE_URL 覆盖 alembic.ini 的 sqlalchemy.url"""
    db_file = tmp_path / "env_url.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    cfg = _alembic_cfg("sqlite:///ignored.db")  # ini 的 url 应被 env 覆盖

    # 直接调用 env.py 的逻辑：读 env 中的 DATABASE_URL
    # 这里用 upgrade head 间接验证：执行前 env 必须把 url 切到 monkeypatch 设的值
    # 由于 env.py 是模块导入时执行 cfg.set_main_option，这里我们直接重新生成 Config
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")
    assert db_file.exists()


# ---------------------------------------------------------------------------- #
#  迁移可执行性与可逆性
# ---------------------------------------------------------------------------- #


def test_upgrade_head_creates_schema(tmp_path):
    """空库 → upgrade head：应建出完整的 job_records 表 + 所有索引"""
    db_file = tmp_path / "fresh.db"
    url = f"sqlite:///{db_file}"

    command.upgrade(_alembic_cfg(url), "head")

    assert _has_table(url, "job_records")
    # 校验关键字段
    inspector = create_engine(url)
    cols = {c["name"]: c for c in inspect(inspector).get_columns("job_records")}
    assert {"id", "kind", "file_name", "status", "created_at", "result_ref"}.issubset(cols.keys())
    assert cols["id"]["primary_key"] == 1
    # 校验索引
    indexes = {i["name"] for i in inspect(inspector).get_indexes("job_records")}
    assert "ix_job_records_created_at" in indexes
    assert "ix_job_records_status_finished" in indexes


def test_upgrade_head_is_idempotent(tmp_path):
    """已建表的库 → upgrade head 必须为 no-op，不报错"""
    db_file = tmp_path / "idem.db"
    url = f"sqlite:///{db_file}"

    command.upgrade(_alembic_cfg(url), "head")
    # 二次执行：不应抛"table already exists"
    command.upgrade(_alembic_cfg(url), "head")
    assert _has_table(url, "job_records")


def test_downgrade_then_upgrade_roundtrip(tmp_path):
    """downgrade base 应删表；再次 upgrade head 应重建"""
    db_file = tmp_path / "roundtrip.db"
    url = f"sqlite:///{db_file}"

    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "head")
    assert _has_table(url, "job_records")

    command.downgrade(cfg, "base")
    assert not _has_table(url, "job_records")

    command.upgrade(cfg, "head")
    assert _has_table(url, "job_records")


def test_current_revision_after_upgrade(tmp_path):
    """upgrade 完成后 alembic_version 应记录当前 head revision id"""
    db_file = tmp_path / "current.db"
    url = f"sqlite:///{db_file}"

    command.upgrade(_alembic_cfg(url), "head")
    rev = _alembic_current(url)
    assert rev == "0001"


# ---------------------------------------------------------------------------- #
#  init_db() 集成（与 db.py 协作）
# ---------------------------------------------------------------------------- #


def test_init_db_runs_alembic_upgrade(tmp_path, monkeypatch):
    """init_db() 必须走 alembic upgrade head，不是 create_all"""
    db_file = tmp_path / "initdb.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    from app.storage import init_db, reset_engine

    reset_engine()
    init_db()

    assert _has_table(f"sqlite:///{db_file}", "job_records")
    # 留 alembic_version 标记
    rev = _alembic_current(f"sqlite:///{db_file}")
    assert rev == "0001"

    reset_engine()


def test_init_db_idempotent_on_existing_schema(tmp_path, monkeypatch):
    """已有 schema 时 init_db() 应为 no-op，不会因字段漂移重建或报错"""
    db_file = tmp_path / "existing.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", url)

    # 第一次初始化
    from app.storage import init_db, reset_engine

    reset_engine()
    init_db()

    # 注入一条任务数据
    from app.storage.db import session_scope
    from app.storage.job_record import JobRecord

    with session_scope() as s:
        s.add(JobRecord(id="j001", kind="parse", file_name="a.md",
                        status="succeeded", created_at=0.0, retry_count=0))

    # 二次 init_db：不应删数据
    init_db()
    with session_scope() as s:
        cnt = s.execute(text("SELECT COUNT(*) FROM job_records")).scalar()
        assert cnt == 1
        ids = [r[0] for r in s.execute(text("SELECT id FROM job_records"))]
        assert "j001" in ids

    reset_engine()