# omni-rag-engine 全模态企业级 RAG 基础设施引擎

<p align="center">
  <strong>高可用 · 全模态 · 物理几何定位 · 隐私脱敏管线 · 向量检索与 FastAPI 微服务</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-3776AB?style=flat&logo=python&logoColor=white" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Package_Manager-uv-261230?style=flat" alt="uv">
  <img src="https://img.shields.io/badge/Docker-Supported-2496ED?style=flat&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-green.style=flat" alt="License">
</p>

---

## 📖 项目简介

**omni-rag-engine** 是一款面向企业级应用的开源全模态 RAG（检索增强生成）基础设施与后端微服务引擎。项目整合了文档解析、音视频转写、视觉图文理解、数据清洗脱敏、物理几何定位 (Location Grounding)、智能切块编排以及多向量数据库持久化，旨在为企业提供一站式、生产可用的 RAG 数据预处理与 API 服务支持。

---

## ✨ 核心特性

* 📁 **全模态多源解析 (37+ 格式)**
  支持纯文本、Markdown、Office 三大件 (`.docx`, `.xlsx`, `.pptx`)、PDF、HTML、CSV、JSON、图片 (EXIF/OCR)、音视频 (OpenAI Whisper ASR) 以及 ZIP 压缩包防解压注入扫描。

* 🎯 **精准物理/几何定位 (Location Grounding)**
  解析与切块过程全程透传物理定位元数据：
  * PDF / PPTX：归一化坐标 `bbox` + 页码 `page_number`
  * Markdown / TXT / CSV：行号 `start_line` / `end_line`
  * HTML / DOCX：DOM `selector` / XPath
  * 音视频：ASR `start_time` / `end_time` 时间戳

* 🧹 **数据清洗与隐私脱敏管线 (CleanerPipeline)**
  内置多重过滤机制，自动剔除 Unicode 不可见控制字符、规范全半角空格，并自动对手机号、身份证、邮箱等敏感隐私 (PII) 进行掩码脱敏。

* 🧩 **上下文缝合与智能切块策略**
  * 支持滑动窗口切块 (`SlidingWindowChunker`)、父子块切片 (`ParentChildChunker`) 和标题层级感知切块 (`HeaderAwareChunker`)。
  * 遵循 Anthropic Contextual Retrieval 规范，自动进行上下文大纲前缀缝合与表格结构化增强。

* 🗄️ **主流向量数据库原生适配**
  原生集成 **ChromaDB**、**Milvus**、**Qdrant**、**PGVector** 与 **FAISS**，支持平滑降级与一键切片落盘。

* ⚡ **FastAPI 微服务 & Docker 一键部署**
  内置开箱即用的 RESTful API（文件解析、智能切块、知识库入库、相似度检索），并配备完整 Dockerfile 及 Docker Compose 一键启动依赖基础设施；SSE 流式问答接口规划中（见 Roadmap Phase 2）。

---

## 🏗️ 架构与数据流图

```mermaid
flowchart TD
    A[多源数据输入] --> B[ParserFactory 解析工厂]
    B --> C[ParsedDocument 语义节点模型]
    C --> D[CleanerPipeline 数据清洗与 PII 脱敏]
    D --> E[ContextPrefixInjector & TableEnhancer 语义增强]
    E --> F[AutoChunker 智能切块路由]
    F --> G[LangChain Document 切片 + Location 元数据]
    G --> H[VectorStore 向量库适配器]
    H --> I[(Chroma / FAISS / Milvus / Qdrant / PgVector)]
    G --> J[FastAPI 微服务 /api/v1]
```

---

## 🚀 快速开始

### 方式 1：基于 `uv` 本地开发运行

#### 1. 克隆仓库与安装依赖
```bash
# 1. 克隆项目
git clone git@github.com:heiye-vn/omni-rag-engine.git
cd omni-rag-engine

# 2. 基于 uv 快速同步项目虚拟环境与依赖
uv sync
```

#### 2. 配置环境变量
```bash
# 复制配置文件模板
cp .env.example .env

# 根据需要编辑 .env 中的 API Key (如 DashScope / DeepSeek 等)
```

#### 3. 启动 FastAPI 微服务
```bash
uv run uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
```
访问 http://localhost:8000/docs 即可在线测试交互式 OpenAPI (Swagger) 文档。

#### 4. （可选）启用真实向量库与大模型
向量数据库客户端属于可选依赖组，按需安装：
```bash
# 安装全部向量数据库客户端 (Chroma / FAISS / Milvus / Qdrant / PGVector)
uv sync --extra vectordb

# 安装阿里百炼 DashScope 真实 Embedding 与 Qwen-VL 图文理解
uv sync --extra dashscope
```
未安装任何客户端或未配置 API Key 时，引擎自动降级为零依赖的本地 JSON 快照存储与 Mock 向量，保证功能链路始终可跑通。

#### 5. （可选）启用任务状态持久化（数据库）

异步解析任务 `/api/v1/jobs` 的状态默认保存在**进程内存**中，服务重启即丢失。开启数据库持久化：

```bash
# 安装持久化依赖 (SQLAlchemy 2.0 + PostgreSQL 驱动)
uv sync --extra persistence
```

```bash
# .env 中配置（完整模板见 .env.example 第 4 节）
JOB_STORE_BACKEND=database
DATABASE_URL=postgresql+psycopg://postgres:postgrespassword@localhost:5432/omni_rag
JOB_STORE_STRICT=0
```

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `JOB_STORE_BACKEND` | `memory` | `memory` 进程内内存（零依赖）/ `database` 关系型数据库持久化 |
| `DATABASE_URL` | compose 中的 PostgreSQL | 支持 PostgreSQL，也支持 SQLite：`sqlite:///./data/omni_rag.db` |
| `JOB_STORE_STRICT` | `0` | `1` = 数据库不可用时拒绝启动，杜绝静默降级（生产建议开启） |
| `JOB_RESULT_TTL` | `1800` | 终态任务保留时长（秒），到期由后台协程清理行记录与产物对象 |
| `OBJECT_STORE_BACKEND` | `local` | 异步任务 result 的对象存储后端：`local` 本地文件系统 / `minio` S3 兼容对象存储 |
| `OBJECT_STORE_ROOT` | `./data/objects` | `OBJECT_STORE_BACKEND=local` 时 result 文件落地目录 |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO 服务地址（Docker 内填 `minio:9000`） |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `minioadmin` | MinIO 访问凭据（与 compose 中 minio 服务保持一致） |
| `MINIO_BUCKET` | `omni-rag-objects` | MinIO 存储桶名（compose 中 minio-init 自动创建） |
| `MINIO_SECURE` | `0` | `1` = 启用 HTTPS（生产建议开启） |
| `OBJECT_STORE_STRICT` | `0` | `1` = MinIO 不可用时拒绝启动（生产建议开启，避免静默回退本地导致多副本丢数据） |

> 未安装 `minio` SDK 或对象存储不可用时，引擎会打印 ERROR 日志并回退本地文件系统；
> 访问 `GET /health` 查看 `job_store` / `object_store` / `database` 字段，可确认当前**实际生效**的后端。

### 核心 API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查探针（含任务存储后端与数据库连通性） |
| POST | `/api/v1/documents/parse` | 上传文件，返回结构化语义节点（含物理定位） |
| POST | `/api/v1/documents/parse-and-chunk` | 上传文件，一键解析 ➔ 清洗 ➔ 智能切块 |
| POST | `/api/v1/knowledge-bases/{kb}/ingest` | 文档切块后写入指定知识库向量库 |
| POST | `/api/v1/knowledge-bases/{kb}/search` | 对知识库发起 Top-K 相似度检索 |
| POST | `/api/v1/jobs` | 提交大文件异步解析任务（立即返回 202 + job_id） |
| GET | `/api/v1/jobs/{job_id}` | 轮询任务状态与结果（兼容旧前端，含 result） |
| GET | `/api/v1/jobs/{job_id}/result` | 独立查询任务的完整解析产物（避免元数据查询附带大 result） |
| GET | `/api/v1/jobs` | 最近任务列表（按提交时间倒序，不含 result） |

curl 示例：
```bash
# 解析并切块
curl -X POST http://localhost:8000/api/v1/documents/parse-and-chunk \
  -F "file=@examples/test.md" -F "strategy=auto"

# 写入知识库并检索
curl -X POST http://localhost:8000/api/v1/knowledge-bases/demo/ingest -F "file=@examples/test.md"
curl -X POST http://localhost:8000/api/v1/knowledge-bases/demo/search \
  -H "Content-Type: application/json" \
  -d '{"query": "切块策略", "k": 3}'
```

> **鉴权提示**：以上 curl 示例假设 `AUTH_ENABLED=0`（本地开发态）。生产环境必须
> 设置 `AUTH_ENABLED=1` + `API_KEYS=key1,key2,...`，所有 `/api/v1/*` 请求需携带
> `Authorization: Bearer <key>` 头；详见下方「鉴权与限流」一节。

---

### 鉴权与限流（生产必读）

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTH_ENABLED` | `0` | `1` = 强制鉴权，`0` = 完全放行（**生产必须 1**） |
| `API_KEYS` | 空 | 合法 key 列表，逗号分隔；`AUTH_ENABLED=1` 时必填，否则所有请求 503 |
| `RATE_LIMIT_DEFAULT` | `60/minute` | 普通端点 IP 级限流速率（slowapi 语法） |
| `RATE_LIMIT_UPLOAD` | `10/hour` | 上传端点（parse / parse-and-chunk / ingest / jobs）单独限流 |

**端到端使用流程**：

```bash
# 1. 在 .env 里启用鉴权
AUTH_ENABLED=1
API_KEYS=sk-prod-xxx,sk-prod-yyy

# 2. 启动后无 token 直接 401
curl http://localhost:8000/api/v1/jobs
# {"detail":"Missing or invalid Authorization header. Expected: Bearer <api_key>"}

# 3. 错 key 403
curl -H "Authorization: Bearer wrong" http://localhost:8000/api/v1/jobs
# {"detail":"Invalid API key"}

# 4. 对 key 200
curl -H "Authorization: Bearer sk-prod-xxx" http://localhost:8000/api/v1/jobs

# 5. 触发限流：第 61 次请求返回 429 + Retry-After
for i in $(seq 1 65); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer sk-prod-xxx" \
    http://localhost:8000/api/v1/jobs
done
```

**白名单**（永远放行，无需鉴权）：`GET /`、`GET /health`、`/docs`、`/redoc`、`/openapi.json`
—— 确保 K8s 探针和 FastAPI 自动文档始终可访问。

**安全细节**：
- 鉴权失败打 WARNING 日志（含客户端 IP + 路径），便于排查暴力枚举
- token 在日志中按"前 4 + 掩码 + 后 2"格式记录，避免明文泄漏
- 鉴权失败的请求**不消耗限流配额**（防止暴力枚举消耗限流名额）
- 限流响应自动带 `Retry-After` header，符合 RFC 6585

---

### 数据库迁移（Alembic）

从 `result JSON → result_ref String` 的破坏式 schema 变更开始，所有后续 schema 调整
**必须走 Alembic**。

```bash
# 查看当前已应用的 migration 版本
uv run alembic current

# 应用所有 pending 迁移
uv run alembic upgrade head

# 回滚一个版本
uv run alembic downgrade -1

# 生成新的 migration（基于 ORM 模型差异自动检测）
uv run alembic revision --autogenerate -m "新增 retry_count 字段"

# 标记数据库为最新版本（首次接入 Alembic 时使用）
uv run alembic stamp head
```

- 启动期 `init_db()` 会自动调用 `alembic upgrade head`，应用服务无需手动跑迁移
- migration 脚本位于 `alembic/versions/`，进 git 即可审计
- 见 `app/storage/db.py` 与 `tests/test_alembic_migrations.py`

---

### 方式 2：使用 Docker Compose 一键容器化部署

包含 `FastAPI 服务` + `Qdrant 向量库` + `PGVector 数据库` + `Redis 缓存` 的全套基础设施：

```bash
# 一键构建后台启动
docker compose up -d --build

# 查看运行状态
docker compose ps
```

---

## 📂 项目目录结构

```text
omni-rag-engine/
├── app/
│   ├── loaders/        # 多源加载器 (本地文件/网络 URL/压缩包递归解析)
│   ├── parsers/        # 格式解析器 (PDF, DOCX, XLSX, PPTX, HTML, 音视频等)
│   ├── ocr/            # PaddleOCR 离线文字与表格识别
│   ├── captioners/     # 视觉大模型图文描述与理解引擎
│   ├── cleaners/       # CleanerPipeline 数据清洗与隐私脱敏管线
│   ├── chunkers/       # 智能切块策略 (滑动窗口/父子块/标题层级感知)
│   ├── enrichers/      # 上下文前缀缝合与表格自解释描述增强
│   ├── vectorstores/   # 向量数据库适配器 (Chroma/Milvus/Qdrant/PgVector)
│   ├── storage/        # 状态持久化层 (SQLAlchemy 引擎/ORM/job_records 仓储)
│   ├── config.py       # 系统配置与环境变量自动加载器
│   ├── factory.py      # 解析器自动路由工厂
│   ├── jobs.py         # 异步任务状态机与存储后端路由 (内存 / 数据库)
│   ├── models.py       # 核心数据模型 (Location / Element / ParsedDocument)
│   ├── server.py       # FastAPI 微服务入口 (/api/v1 RESTful API)
│   └── main.py         # CLI 批量解析演示入口
├── tests/              # 单元测试与集成测试套件
├── Dockerfile          # 容器构建描述文件
├── docker-compose.yml  # 多服务集群编排文件
├── pyproject.toml      # 项目依赖与构建元数据
├── AGENTS.md           # AI 助手与开发者协作规范
└── RAG_ROADMAP.md      # 功能规划与演进路线图
```

---

## 🖥️ 可视化控制台（frontend/）

仓库内置一个基于 **Next.js 15 + Tailwind CSS v4 + TanStack Query** 的 RAG 引擎控制台，为 `/api/v1` 提供可视化操作界面：

| 页面 | 路径 | 能力 |
| --- | --- | --- |
| 仪表盘 | `/` | 引擎状态轮询、能力矩阵、最近异步任务列表 |
| 解析工作台 | `/parse` | 上传 → Element 列表 ↔ 原文行号高亮对照（Location Grounding 可视化） |
| 切块实验室 | `/chunk-lab` | 同一文件 × 4 种切片策略切换与并排对比、指标统计 |
| 知识库检索 | `/kb` | 多文件入库 → Top-K 相似检索 → 结果溯源徽章 |

> 大文件（>5MB）自动切换为**异步任务**路径：`POST /api/v1/jobs` 提交后前端 1.5s 轮询至终态，解析期间事件循环不被阻塞。

```bash
# 1. 启动后端引擎 (端口 8000)
uv run uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

# 2. 启动前端控制台 (端口 3000，另开终端)
cd frontend && pnpm install && pnpm dev

# 可选：自定义后端地址
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > frontend/.env.local
```

访问 http://localhost:3000 即可使用。详见 [design.md](design.md)（设计文档）与 [plan.md](plan.md)（实施计划）。

---

## 📄 开发与协作指南

在为项目提交 Pull Request 或编写新模块前，请先参阅项目内的开发规范文件：
* 📜 **架构规范与 AI 协作准则**：[AGENTS.md](AGENTS.md)
* 🗺️ **功能 roadmap 与 TODO 清单**：[RAG_ROADMAP.md](RAG_ROADMAP.md)

---

## 📝 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。
