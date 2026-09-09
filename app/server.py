"""
omni-rag-engine FastAPI 微服务入口

提供五大基础能力域的 RESTful API：
  1. 文档解析        POST /api/v1/documents/parse
  2. 解析并智能切块   POST /api/v1/documents/parse-and-chunk
  3. 知识库向量入库   POST /api/v1/knowledge-bases/{kb}/ingest
  4. 知识库相似检索   POST /api/v1/knowledge-bases/{kb}/search
  5. 大文件异步解析   POST /api/v1/jobs + GET /api/v1/jobs/{id} (轮询)

启动方式:
    uv run uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import load_env_file
from app.factory import get_supported_extensions
from app.rate_limit import limiter, rate_limit_exceeded_handler, upload_limit
from slowapi.errors import RateLimitExceeded

# 容器/服务启动前先注入 .env 环境变量 (幂等操作)
load_env_file()

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """服务生命周期：启动后台任务 TTL 清理协程，退出时取消"""
    from app.jobs import cleanup_loop, current_backend_name, job_registry

    # 启动日志显式声明任务存储后端，避免"以为用了数据库、实际在跑内存"的误判
    print(f"[Startup] 任务存储后端: {current_backend_name()} ({type(job_registry).__name__})")

    cleanup_task = asyncio.create_task(cleanup_loop())
    yield
    cleanup_task.cancel()


app = FastAPI(
    title="omni-rag-engine",
    version=APP_VERSION,
    description="全模态企业级 RAG 基础设施引擎：多源解析 / 数据清洗脱敏 / 智能切块 / 多模态理解 / 向量检索",
    lifespan=lifespan,
)

# 慢api 限流：单例挂到 app.state，必须在 add_middleware 之后注入
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# 允许跨域，便于前端 (React / Vercel AI SDK) 本地联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------- #
#  Pydantic API Schema (仅用于 API 边界的请求/响应建模，内部数据仍走 app/models 数据模型)
# ---------------------------------------------------------------------------- #


class ChunkOut(BaseModel):
    """单个切片节点的序列化结构"""

    page_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    """知识库相似度检索请求"""

    query: str = Field(min_length=1, description="查询文本")
    k: int = Field(default=4, ge=1, le=100, description="Top-K 召回数量")
    store_type: str = Field(default="chroma", description="向量库类型: chroma/faiss/milvus/pgvector/qdrant")
    provider: str = Field(default="auto", description="Embedding 引擎: auto/dashscope/mock")
    store_kwargs: dict[str, Any] | None = Field(default=None, description="透传给向量库适配器的额外参数")


class SearchResult(BaseModel):
    """知识库相似度检索响应"""

    query: str
    total: int
    results: list[ChunkOut]


class IngestResult(BaseModel):
    """知识库入库结果统计"""

    knowledge_base: str
    store_type: str
    document_count: int
    chunk_count: int
    detail: Any | None = None


# ---------------------------------------------------------------------------- #
#  内部工具方法
# ---------------------------------------------------------------------------- #


def _save_upload_to_temp(file: UploadFile) -> Path:
    """
    将上传文件落盘为带原始扩展名的临时文件，返回临时路径。
    扩展名是解析器工厂路由的依据，必须原样保留。
    """
    filename = file.filename or "upload.bin"
    suffix = Path(filename).suffix or ".bin"

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file.file.read())
            tmp_path = Path(tmp.name)
    finally:
        file.file.close()

    return tmp_path


def _validate_kb_name(kb: str) -> str:
    """
    校验知识库标识符合法性

    kb 会参与本地持久化目录/集合名构造，必须限制为安全的短标识字符集，
    防止路径分隔符或父目录引用注入到文件系统操作中。
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", kb):
        raise HTTPException(
            status_code=400,
            detail="非法的知识库名称：仅允许 1~64 位字母、数字、下划线与连字符，且以字母或数字开头",
        )
    return kb


# 允许调用方透传给向量库适配器的参数白名单：
# 排除一切存储位置类键，防止远端请求改写服务端落盘目录
_SAFE_STORE_KWARG_KEYS = frozenset({"host", "port", "user", "password", "api_key", "url", "timeout"})


def _sanitize_store_kwargs(store_kwargs: dict[str, Any] | None) -> dict[str, Any]:
    """过滤掉存储位置类覆盖参数（persist_directory/folder_path/collection_name 等）"""
    if not store_kwargs:
        return {}
    return {k: v for k, v in store_kwargs.items() if k in _SAFE_STORE_KWARG_KEYS}


def _default_store_kwargs(store_type: str, kb: str) -> dict[str, Any]:
    """按知识库名称生成本地持久化默认参数，保证 ingest 与 search 的读写路径一致"""
    base_dir = os.path.join("./data", kb)
    if store_type == "faiss":
        return {"folder_path": base_dir, "index_name": kb}
    # chroma 及未知类型统一按 Chroma 目录约定
    return {"persist_directory": base_dir, "collection_name": kb}


def _serialize_chunks(chunks: list[Any]) -> list[ChunkOut]:
    """将切块产物 (LangChain Document 或内置降级 Document) 统一序列化为 API 模型"""
    return [
        ChunkOut(
            page_content=getattr(doc, "page_content", ""),
            metadata=getattr(doc, "metadata", {}) or {},
        )
        for doc in chunks
    ]


async def _load_batch_from_upload(
    file: UploadFile,
    enable_cleaning: bool,
) -> tuple[list[Any], Path]:
    """
    将上传文件解析为 ParsedDocument 列表（支持单文件与压缩包）

    Returns:
        (ParsedDocument 列表, 临时文件路径)；调用方负责在响应完成后清理临时文件

    性能说明：解析链路为 CPU/IO 密集同步调用（Docling/PyMuPDF/PaddleOCR/Whisper），
    必须通过 asyncio.to_thread 切到默认线程池执行，**否则会阻塞事件循环**导致
    所有其他请求（/health /jobs 轮询 /search）排队等待，引发"上传大文件后整个页面卡"。
    """
    from app.loaders.helper import load_batch

    tmp_path = _save_upload_to_temp(file)
    try:
        batch = await asyncio.to_thread(
            load_batch,
            str(tmp_path),
            enable_cleaning=enable_cleaning,
            enable_describe_images=False,
        )
        return batch.documents, tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------- #
#  基础信息与健康检查
# ---------------------------------------------------------------------------- #


@app.get("/", tags=["system"])
def root() -> dict[str, Any]:
    """服务根路径：返回基础信息与交互式文档入口"""
    return {
        "service": "omni-rag-engine",
        "version": APP_VERSION,
        "docs": "/docs",
        "supported_extensions_count": len(get_supported_extensions()),
    }


@app.get("/health", tags=["system"])
def health() -> dict[str, Any]:
    """
    容器健康检查探针

    除存活状态外，额外暴露任务存储后端、对象存储后端与数据库连通性，
    便于运维确认"状态持久化与产物存储是否真正生效"而非静默回退到内存/本地。
    """
    from app.jobs import current_backend_name

    backend = current_backend_name()
    payload: dict[str, Any] = {"status": "ok", "job_store": backend}

    if backend == "database":
        try:
            from app.storage import health_check

            payload["database"] = "up" if health_check() else "down"
        except Exception as e:  # noqa: BLE001 - 探针不应因依赖异常而 500
            payload["database"] = f"error: {e}"

    # 对象存储后端可观测（即使 job_store=memory 也会展示 local 状态）
    try:
        from app.storage import current_object_store_name

        payload["object_store"] = current_object_store_name()
    except Exception:  # noqa: BLE001
        payload["object_store"] = "unknown"

    return payload


# ---------------------------------------------------------------------------- #
#  文档解析与切块
# ---------------------------------------------------------------------------- #


@app.post("/api/v1/documents/parse", tags=["documents"])
@upload_limit
async def parse_document(
    request: Request,
    file: UploadFile = File(...),
    enable_cleaning: bool = Form(default=True),
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> list[dict[str, Any]]:
    """
    上传单文件或压缩包，解析为结构化语义节点列表

    - 支持全部已注册格式 (见 GET / 返回的 supported_extensions_count)
    - enable_cleaning 控制是否执行数据清洗与 PII 脱敏管线
    - 返回每个文档的 ParsedDocument 序列化结果 (含 Location 物理定位)
    """
    try:
        documents, tmp_path = await _load_batch_from_upload(file, enable_cleaning=enable_cleaning)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}") from e

    try:
        return [doc.to_dict() for doc in documents]
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/v1/documents/parse-and-chunk", tags=["documents"])
@upload_limit
async def parse_and_chunk_document(
    request: Request,
    file: UploadFile = File(...),
    strategy: str = Form(default="auto"),
    enable_cleaning: bool = Form(default=True),
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> list[ChunkOut]:
    """
    上传文件一键完成：解析 ➔ 清洗 ➔ 智能切块，返回携带完整定位元数据的切片列表

    - strategy 可选: auto / sliding_window / parent_child / header_aware
    """
    from app.chunkers.auto import AutoChunker

    try:
        documents, tmp_path = await _load_batch_from_upload(file, enable_cleaning=enable_cleaning)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}") from e

    try:
        # 切块链路同样 CPU 密集，需移出事件循环避免阻塞其他请求
        def _do_chunk() -> list[Any]:
            chunker = AutoChunker()
            chunks: list[Any] = []
            for doc in documents:
                res = chunker.split_document(doc, strategy=strategy)
                # Parent-Child 策略返回 (child_docs, parent_store) 元组，此处仅取可直接检索的子块
                if isinstance(res, tuple):
                    chunks.extend(res[0])
                else:
                    chunks.extend(res)
            return chunks

        all_chunks = await asyncio.to_thread(_do_chunk)
        return _serialize_chunks(all_chunks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"切块失败: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------- #
#  知识库向量化入库与检索
# ---------------------------------------------------------------------------- #


@app.post("/api/v1/knowledge-bases/{kb}/ingest", tags=["knowledge-bases"])
@upload_limit
async def ingest_knowledge_base(
    request: Request,
    kb: str,
    file: UploadFile = File(...),
    strategy: str = Form(default="auto"),
    store_type: str = Form(default="chroma"),
    provider: str = Form(default="auto"),
    enable_cleaning: bool = Form(default=True),
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> IngestResult:
    """
    上传文档并一键写入指定知识库的向量数据库

    - 默认本地 Chroma 持久化至 ./data/{kb}/ (Docker 部署时挂载至 omni_rag_data 卷)
    - store_type 可选: chroma / faiss / milvus / pgvector / qdrant
    """
    _validate_kb_name(kb)

    from app.chunkers.auto import AutoChunker
    from app.vectorstores import VectorStoreFactory
    from app.vectorstores.embeddings import EmbeddingsFactory

    kwargs: dict[str, Any] = {}
    if store_type.lower() in ("chroma", "faiss"):
        kwargs = _default_store_kwargs(store_type.lower(), kb)

    try:
        documents, tmp_path = await _load_batch_from_upload(file, enable_cleaning=enable_cleaning)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}") from e

    try:
        # 1. 全量文档统一切块 (CPU 密集：移出事件循环)
        def _do_chunk() -> list[Any]:
            chunker = AutoChunker()
            chunks: list[Any] = []
            for doc in documents:
                res = chunker.split_document(doc, strategy=strategy)
                if isinstance(res, tuple):
                    chunks.extend(res[0])
                else:
                    chunks.extend(res)
            return chunks

        all_chunks = await asyncio.to_thread(_do_chunk)

        if not all_chunks:
            raise HTTPException(status_code=400, detail="解析后的文档没有任何可写入的有效内容")

        # 2. 路由到目标向量库适配器并批量写入
        # (含远程 embedding 同步调用，同样必须移出事件循环，否则长文件入库期间前端全卡)
        def _do_ingest() -> Any:
            store_adapter = VectorStoreFactory.get_vectorstore(
                store_type=store_type,
                embeddings=EmbeddingsFactory.get_embeddings(provider=provider),
                **kwargs,
            )
            return store_adapter.add_documents(all_chunks)

        detail = await asyncio.to_thread(_do_ingest)

        return IngestResult(
            knowledge_base=kb,
            store_type=store_type.lower(),
            document_count=len(documents),
            chunk_count=len(all_chunks),
            detail=str(detail) if not isinstance(detail, (str, list)) else detail,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量入库失败: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/v1/knowledge-bases/{kb}/search", tags=["knowledge-bases"])
def search_knowledge_base(
    kb: str,
    req: SearchRequest,
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> SearchResult:
    """
    对指定知识库发起向量相似度检索，返回 Top-K 相关切片

    - store_type / provider 必须与写入时保持一致才能命中同一数据集
    - store_kwargs 仅允许连接类参数（host/port/api_key 等），存储位置由服务端统一管控
    """
    _validate_kb_name(kb)

    from app.vectorstores import VectorStoreFactory
    from app.vectorstores.embeddings import EmbeddingsFactory

    store_type = req.store_type.lower()
    kwargs = _sanitize_store_kwargs(req.store_kwargs) or _default_store_kwargs(store_type, kb)

    try:
        store_adapter = VectorStoreFactory.get_vectorstore(
            store_type=store_type,
            embeddings=EmbeddingsFactory.get_embeddings(provider=req.provider),
            **kwargs,
        )
        docs = store_adapter.similarity_search(req.query, k=req.k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {e}") from e

    chunks = _serialize_chunks(docs)
    return SearchResult(query=req.query, total=len(chunks), results=chunks)


# ---------------------------------------------------------------------------- #
#  大文件异步解析任务 (design.md §11：解析移入线程池，不阻塞事件循环)
# ---------------------------------------------------------------------------- #


class JobCreateOut(BaseModel):
    """异步任务提交响应"""

    job_id: str = Field(description="任务唯一标识，用于后续轮询")
    status: str = Field(description="初始状态，固定为 queued")


@app.post("/api/v1/jobs", status_code=202, tags=["jobs"])
@upload_limit
async def submit_parse_job(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form(default="parse"),
    strategy: str = Form(default="auto"),
    enable_cleaning: bool = Form(default=True),
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> JobCreateOut:
    """
    提交大文件异步解析任务，立即返回 job_id（202）

    - kind 可选: parse (仅解析) | parse_and_chunk (解析并切块)
    - 解析在线程池中执行，不阻塞事件循环，前端通过 GET /api/v1/jobs/{job_id} 轮询结果
    - 结果结构成功后与同步端点完全一致 (ParsedDocument 列表 / ChunkOut 列表)
    """
    from app.jobs import JOB_KINDS, submit_job

    if kind not in JOB_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"非法的任务类型: '{kind}'，可选: {', '.join(sorted(JOB_KINDS))}",
        )

    tmp_path = _save_upload_to_temp(file)
    file_name = file.filename or tmp_path.name

    def _work(_: Any) -> Any:
        """任务执行体：在线程池中运行同步解析链路，结束后清理临时文件"""
        from app.chunkers.auto import AutoChunker
        from app.loaders.helper import load_batch

        try:
            batch = load_batch(
                str(tmp_path), enable_cleaning=enable_cleaning, enable_describe_images=False
            )

            if kind == "parse":
                # 与同步 /parse 端点输出结构一致
                return [doc.to_dict() for doc in batch.documents]

            # 与同步 /parse-and-chunk 端点输出结构一致 (parent_child 元组仅取子块)
            chunker = AutoChunker()
            all_chunks: list[Any] = []
            for doc in batch.documents:
                res = chunker.split_document(doc, strategy=strategy)
                if isinstance(res, tuple):
                    all_chunks.extend(res[0])
                else:
                    all_chunks.extend(res)
            return [
                {
                    "page_content": getattr(doc, "page_content", ""),
                    "metadata": getattr(doc, "metadata", {}) or {},
                }
                for doc in all_chunks
            ]
        finally:
            tmp_path.unlink(missing_ok=True)

    job = submit_job(
        kind=kind,
        file_name=file_name,
        work=_work,
        strategy=strategy if kind == "parse_and_chunk" else None,
    )
    return JobCreateOut(job_id=job.id, status=job.status.value)


@app.get("/api/v1/jobs/{job_id}", tags=["jobs"])
def get_parse_job(
    job_id: str,
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> dict[str, Any]:
    """
    查询单个异步任务的状态与结果

    - 仍包含 result（兼容旧前端）。
    - 大体积 result 场景建议改用 `GET /api/v1/jobs/{job_id}/result` 独立端点，
      避免元数据查询一并下载几十 MB 产物。
    """
    from app.jobs import job_registry

    job = job_registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"任务不存在或已过期: {job_id}")
    return job.to_dict()


@app.get("/api/v1/jobs/{job_id}/result", tags=["jobs"])
def get_parse_job_result(
    job_id: str,
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> Any:
    """
    独立查询任务的完整解析/切块产物

    设计动机：result 可能数十 MB，若塞进 GET /api/v1/jobs/{id} 会拖累所有轮询。
    数据库行仅保留引用（result_ref），真正数据从对象存储（LocalFSStore / 未来 MinIO）
    加载；对象存储异常或已过期（被 TTL 清理）会返回 410 Gone。
    """
    from app.jobs import job_registry

    job = job_registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"任务不存在或已过期: {job_id}")

    if job.result is None:
        # 任务未完成，或 result 已 TTL 清理
        if job.status.value in ("queued", "running"):
            raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态: {job.status.value}")
        raise HTTPException(status_code=410, detail=f"任务 result 不可用：可能已完成但未产出，或已被 TTL 清理")

    return job.result


@app.get("/api/v1/jobs", tags=["jobs"])
def list_parse_jobs(
    limit: int = 20,
    _: Annotated[str, Depends(verify_api_key)] = "",
) -> list[dict[str, Any]]:
    """按提交时间倒序返回最近任务列表（不含 result，避免大响应体）"""
    from app.jobs import job_registry

    return [
        {k: v for k, v in job.to_dict().items() if k != "result"}
        for job in job_registry.list(limit=limit)
    ]
