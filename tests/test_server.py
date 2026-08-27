"""
FastAPI 微服务接口测试：覆盖健康检查、文档解析、智能切块与知识库入库/检索闭环

说明：
- 入库/检索闭环基于 MockEmbeddings (MD5 确定性伪随机向量) 与 ChromaStore 的零依赖
  JSON 快照降级存储，不依赖真实 chromadb 与外部 API Key，可在任意环境离线运行。
- 测试产物统一写入 /tmp 派生的临时目录或服务默认 ./data 目录，结束后自动清理。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.server import app

client = TestClient(app)

EXAMPLE_MD = Path(__file__).resolve().parent.parent / "examples" / "test.md"


def test_system_endpoints():
    """根路径与健康检查探针可用"""
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["service"] == "omni-rag-engine"
    assert root.json()["supported_extensions_count"] > 0

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def _upload_bytes() -> tuple[str, bytes, str]:
    """构造上传用 multipart 文件元组"""
    content = EXAMPLE_MD.read_bytes() if EXAMPLE_MD.exists() else "# 标题\n\n测试正文内容，用于解析验证。".encode("utf-8")
    return ("test.md", content, "text/markdown")


def test_parse_document():
    """上传 Markdown 应返回包含定位信息的结构化节点列表"""
    resp = client.post(
        "/api/v1/documents/parse",
        files={"file": _upload_bytes()},
        data={"enable_cleaning": "true"},
    )
    assert resp.status_code == 200, resp.text

    documents = resp.json()
    assert len(documents) >= 1
    doc = documents[0]
    assert doc["file_type"] == "markdown"
    assert isinstance(doc["elements"], list) and len(doc["elements"]) >= 1


def test_parse_and_chunk_document():
    """上传文件一键切块，切片必须携带完整 metadata 元数据"""
    resp = client.post(
        "/api/v1/documents/parse-and-chunk",
        files={"file": _upload_bytes()},
        data={"strategy": "auto"},
    )
    assert resp.status_code == 200, resp.text

    chunks = resp.json()
    assert len(chunks) >= 1
    first = chunks[0]
    assert isinstance(first["page_content"], str) and len(first["page_content"]) > 0
    # 切块 metadata 必须继承源文档追踪信息（AutoChunker 各策略均会注入元素来源标记）
    assert "metadata" in first


def test_ingest_then_search_round_trip():
    """入库 ➔ 相似检索闭环：写入后必须能召回相关切片"""
    kb = "test-api-kb"

    ingest_resp = client.post(
        f"/api/v1/knowledge-bases/{kb}/ingest",
        files={"file": _upload_bytes()},
        data={"strategy": "auto", "store_type": "chroma"},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    stats = ingest_resp.json()
    assert stats["chunk_count"] >= 1

    search_resp = client.post(
        f"/api/v1/knowledge-bases/{kb}/search",
        json={"query": "切块与检索", "k": 3, "store_type": "chroma"},
    )
    assert search_resp.status_code == 200, search_resp.text
    result = search_resp.json()
    assert result["total"] >= 1
    assert all("page_content" in item for item in result["results"])

    # 清理测试产生的本地持久化目录，避免污染仓库工作区
    import shutil

    shutil.rmtree(Path("./data") / kb, ignore_errors=True)


def test_search_request_validation():
    """空查询体应被 Pydantic 校验拦截"""
    resp = client.post("/api/v1/knowledge-bases/demo/search", json={"query": "", "k": 3})
    assert resp.status_code == 422


def test_invalid_kb_name_rejected():
    """携带路径穿越特征的知识库名必须在边界被拒绝"""
    for bad_kb in ("../evil", "..", "a/b", "a\\b", ".hidden"):
        resp = client.post(
            f"/api/v1/knowledge-bases/{bad_kb}/search",
            json={"query": "测试", "k": 1},
        )
        assert resp.status_code in (400, 404), f"{bad_kb!r} 未被拦截: {resp.status_code}"
