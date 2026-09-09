"""
异步解析任务模块测试：Job 状态机 / JobRegistry 线程安全 / TTL 清理 / jobs API 端点

说明：
- JobRegistry 的并发与 TTL 逻辑不依赖外部服务，纯内存测试。
- jobs API 端点测试基于 TestClient 与零依赖的 Mock 解析链路（Markdown 小文件），
  与 test_server.py 的离线运行约定一致。
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.jobs import Job, JobRegistry, JobStatus
from app.server import app

client = TestClient(app)


# ---------------------------------------------------------------------------- #
#  Job 状态机
# ---------------------------------------------------------------------------- #


def test_job_initial_state_is_queued():
    """新建任务初始状态应为 queued"""
    job = Job(kind="parse", file_name="test.md")
    assert job.status == JobStatus.QUEUED
    assert job.id  # 自动生成 job_id
    assert job.result is None and job.error is None


def test_job_lifecycle_transitions():
    """状态机应支持 queued → running → succeeded，且终态不可再变更"""
    job = Job(kind="parse", file_name="test.md")

    job.start()
    assert job.status == JobStatus.RUNNING
    assert job.started_at is not None

    job.finish_success([{"file_name": "test.md"}])
    assert job.status == JobStatus.SUCCEEDED
    assert job.result == [{"file_name": "test.md"}]

    # 终态不可变更：再次转移应抛出状态机异常
    with pytest.raises(RuntimeError):
        job.start()


def test_job_failure_records_error():
    """失败终态应记录可读错误信息"""
    job = Job(kind="parse", file_name="test.md")
    job.start()
    job.finish_failure("解析失败: 不支持的格式")
    assert job.status == JobStatus.FAILED
    assert job.error == "解析失败: 不支持的格式"
    assert job.finished_at is not None


# ---------------------------------------------------------------------------- #
#  JobRegistry 注册表
# ---------------------------------------------------------------------------- #


def test_registry_create_and_get():
    """注册任务后可按 job_id 查询，未知 id 返回 None"""
    registry = JobRegistry()
    job = registry.create(kind="parse", file_name="a.md")
    assert registry.get(job.id) is job
    assert registry.get("nonexistent") is None


def test_registry_list_sorted_desc():
    """列表应按创建时间倒序（最新在前）"""
    registry = JobRegistry()
    first = registry.create(kind="parse", file_name="1.md")
    time.sleep(0.01)
    second = registry.create(kind="parse", file_name="2.md")

    jobs = registry.list(limit=10)
    assert [j.id for j in jobs][:2] == [second.id, first.id]

    limited = registry.list(limit=1)
    assert len(limited) == 1
    assert limited[0].id == second.id


def test_registry_thread_safety():
    """多线程并发创建任务，注册表应无丢失且 job_id 唯一"""
    registry = JobRegistry()

    def create_batch(prefix: str) -> list[str]:
        return [registry.create(kind="parse", file_name=f"{prefix}-{i}.md").id for i in range(50)]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(create_batch, f"t{t}") for t in range(4)]
        all_ids = [jid for fut in futures for jid in fut.result()]

    assert len(all_ids) == 200
    assert len(set(all_ids)) == 200  # 无重复
    assert len(registry.list(limit=1000)) == 200


def test_registry_ttl_cleanup():
    """超过 TTL 的终态任务应被清理，未完结任务不受影响"""
    registry = JobRegistry(ttl_seconds=0.05)

    finished = registry.create(kind="parse", file_name="done.md")
    finished.start()
    finished.finish_success([])

    running = registry.create(kind="parse", file_name="busy.md")
    running.start()

    time.sleep(0.08)
    removed = registry.cleanup_expired()

    assert finished.id in removed
    assert registry.get(finished.id) is None  # 已清理
    assert registry.get(running.id) is not None  # 运行中不清理


# ---------------------------------------------------------------------------- #
#  jobs API 端点（TestClient 离线测试）
# ---------------------------------------------------------------------------- #


def _md_upload() -> tuple[str, bytes, str]:
    """构造上传用 Markdown 文件元组（零依赖解析链路）"""
    content = "# 异步测试\n\n用于异步任务端点验证的正文内容。".encode("utf-8")
    return ("test.md", content, "text/markdown")


def _wait_job_done(client, job_id: str, timeout: float = 10.0) -> dict:
    """轮询任务直至终态或超时，返回最终任务 JSON"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.1)
    raise TimeoutError(f"任务 {job_id} 在 {timeout}s 内未到达终态")


def test_submit_job_returns_202_and_polls_to_success():
    """提交异步任务应立即返回 202 + job_id，轮询至 succeeded 且结果结构正确"""
    resp = client.post(
        "/api/v1/jobs",
        files={"file": _md_upload()},
        data={"kind": "parse", "enable_cleaning": "true"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    # 小文件任务可能在线程池中瞬间启动，202 返回时允许 queued 或 running
    assert body["status"] in ("queued", "running")
    job_id = body["job_id"]

    job = _wait_job_done(client, job_id)
    assert job["status"] == "succeeded", job.get("error")
    assert job["kind"] == "parse"

    # 结果结构应与同步 /parse 端点一致（ParsedDocument 列表）
    documents = job["result"]
    assert isinstance(documents, list) and len(documents) >= 1
    assert documents[0]["file_type"] == "markdown"
    assert isinstance(documents[0]["elements"], list)


def test_submit_job_chunk_kind():
    """kind=parse_and_chunk 的任务结果应为 ChunkOut 列表"""
    resp = client.post(
        "/api/v1/jobs",
        files={"file": _md_upload()},
        data={"kind": "parse_and_chunk", "strategy": "sliding_window"},
    )
    assert resp.status_code == 202, resp.text
    job = _wait_job_done(client, resp.json()["job_id"])

    assert job["status"] == "succeeded", job.get("error")
    chunks = job["result"]
    assert isinstance(chunks, list) and len(chunks) >= 1
    assert "page_content" in chunks[0]
    assert "metadata" in chunks[0]


def test_submit_job_invalid_kind_rejected():
    """kind 白名单校验：非法取值应返回 400"""
    resp = client.post(
        "/api/v1/jobs",
        files={"file": _md_upload()},
        data={"kind": "delete_database"},
    )
    assert resp.status_code == 400


def test_get_unknown_job_returns_404():
    """查询不存在的任务应返回 404"""
    fake_id = uuid.uuid4().hex[:12]
    resp = client.get(f"/api/v1/jobs/{fake_id}")
    assert resp.status_code == 404


def test_list_jobs_endpoint():
    """任务列表端点应返回最近任务（倒序）"""
    resp = client.get("/api/v1/jobs", params={"limit": 10})
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    # 若有任务，第一条应为最新
    if len(jobs) >= 2:
        assert jobs[0]["created_at"] >= jobs[1]["created_at"]
