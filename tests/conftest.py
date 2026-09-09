"""
pytest 全局配置

- 默认强制使用内存任务后端，避免测试套件依赖外部 PostgreSQL 数据库。
- 关闭鉴权与限流（默认状态），避免对常规 API 测试造成干扰；
  tests/test_auth_and_rate_limit.py 单独启用。
- tests/test_job_persistence.py 自行 monkeypatch 到 SQLite 临时文件验证数据库后端，
  不受本设置影响。
"""
import os

os.environ.setdefault("JOB_STORE_BACKEND", "memory")
os.environ.setdefault("AUTH_ENABLED", "0")
# 极高限流，避免常规 API 测试自击中
os.environ.setdefault("RATE_LIMIT_DEFAULT", "100000/second")
os.environ.setdefault("RATE_LIMIT_UPLOAD", "100000/second")