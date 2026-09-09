# omni-rag-engine 前端控制台设计文档（design.md）

> 状态：Brainstorming 产出，待用户确认后进入 Implementation Planning（plan.md）
> 日期：2026-09-08

---

## 1. 目标与用户

**定位**：RAG 引擎控制台（developer-facing console），为 omni-rag-engine 后端（FastAPI `/api/v1`）提供可视化操作与演示界面。

**目标用户**：
- 开发者/自己：调试解析、切块、检索链路，直观验证 Location Grounding 是否生效
- 面试官/演示观众：5 分钟内看懂引擎的核心能力（多格式解析、切块策略、溯源高亮）

**成功标准**：
1. 上传一个文件，30 秒内看到「Element 列表 + 原文高亮对照」
2. 同一文件切换 4 种切块策略，能并排对比结果差异
3. 完成「入库 → 检索」闭环，检索结果可溯源到原文位置

## 2. 范围与非目标（YAGNI）

**做**：
- 4 个 MVP 页面：仪表盘、解析工作台、切块实验室、知识库检索
- 与现有 5 个后端端点的完整对接（health / parse / parse-and-chunk / ingest / search）
- Location 溯源可视化（行号高亮为主，bbox/时间戳以徽章展示）

**不做（明确排除）**：
- 登录/权限/多用户（企业平台阶段再做，此处与 shadcn-admin 的 auth 模板解耦）
- 后端新端点开发（前端只消费现有 API；缺口记录在 §5，用前端手段绕过）
- PDF 原位 bbox 叠加渲染（依赖 pdf.js，列为 Phase 2 拓展项；MVP 展示坐标徽章）
- SSE 流式问答、Agent 评测中心（后端尚未提供，roadmap Phase 2）
- 复杂全局状态管理（无跨页共享业务态，TanStack Query + 页面局部 state 足够）

## 3. 信息架构

```
控制台（App Shell：左侧导航 + 顶栏）
├── 仪表盘        /            引擎状态 + 能力总览 + 会话记录
├── 解析工作台    /parse       上传 → Element 列表 ↔ 原文高亮对照
├── 切块实验室    /chunk-lab   同文件 × 4 策略对比 + 切片卡片
└── 知识库检索    /kb          入库 → Top-K 检索 → 结果溯源
```

导航顺序即用户旅程：先看状态 → 解析单个文件 → 对比切块 → 入库检索。

## 4. 页面详设

### 4.1 仪表盘 `/`

| 区块 | 内容 | 数据来源 |
|---|---|---|
| 引擎状态卡 | 后端在线状态、版本、API 地址、延迟 | `GET /health`（轮询 30s） |
| 能力矩阵卡 | 支持的格式数（37+）、切块策略（4）、向量库（5）、Embedding 供应商 | 静态文案 + `get_supported_extensions()` 常量镜像 |
| 快速开始卡 | 三步引导：解析 → 切块对比 → 检索，各带跳转按钮 | 纯前端 |
| 最近活动 | 本次会话解析过的文件、检索历史（时间倒序，可清空） | localStorage（`rag-console:history`） |

设计动机：后端没有统计端点，仪表盘诚实呈现「状态 + 引导 + 本地会话记录」，不造假数据。

### 4.2 解析工作台 `/parse`（核心页）

**三栏布局**：

```
┌─────────┬──────────────────┬─────────────────┐
│ 上传与筛选 │  Element 列表      │  原文对照视图      │
│ (280px)  │  (点击选中联动)     │  (行号高亮渲染)    │
└─────────┴──────────────────┴─────────────────┘
```

- **左栏**：拖拽上传区（accept 由支持扩展名列表生成）+ 文件信息卡（名称/类型/元素数/页数）+ Element 类型筛选 chips（heading / paragraph / table / code / image / list_item）
- **中栏**：Element 卡片列表，每张卡片含：类型徽章、location 徽章（`L12-L18` / `P3 bbox` / `selector`）、内容预览（截断 3 行）、raw_content 折叠查看（表格 HTML / 代码片段）
- **右栏**：原文对照视图
  - Markdown/TXT/CSV：按行渲染 + 行号槽，选中 Element 的 `start_line~end_line` 高亮（蓝底），自动滚动到视口
  - PDF/PPTX：显示「第 N 页 + bbox 坐标」徽章（Phase 2 做 pdf.js 叠加矩形）
  - 音视频：显示 `start_time ~ end_time` 时间戳徽章
  - 无 raw_text 的格式：降级显示 Element 详情面板（type/content/location/metadata 完整 JSON）

**数据流**：`POST /api/v1/documents/parse`（FormData: file）→ `ParsedDocument` → 中栏渲染 elements，右栏渲染 raw_text。

**组件**：`UploadZone`、`ElementList` / `ElementCard` / `TypeBadge` / `LocationBadge`、`SourceViewer`（内含 `LineHighlighter`）。

### 4.3 切块实验室 `/chunk-lab`

**单文件 × 多策略对比**：

- **顶部**：上传区（与解析工作台复用 `UploadZone` 组件）+ 策略 Tabs：`auto` / `sliding_window` / `parent_child` / `header_aware`（支持多选进入对比模式）
- **指标条**（切完展示）：切片总数、平均字符长度、最长切片、含 header_path 切片占比
- **切片卡片流**：每张卡片含：
  - 策略徽章 + 切片序号 + 字符数
  - `header_path` 面包屑（如 `安装指南 > 环境准备`，来自 enricher 注入的 metadata）
  - 内容预览（可展开全文）
  - location 徽章（点击跳转解析工作台同文件的对应位置——MVP 可先不做联动，仅展示）
- **对比模式**：选中 ≥2 个策略时，左右分栏并排展示各自切片列表 + 指标对比表

**数据流**：切换策略时 `POST /api/v1/documents/parse-and-chunk`（FormData: file, strategy）→ `ChunkOut[]`。同一 File 对象缓存在页面 state，切策略只需重发请求；4 个策略可用 `Promise.all` 并行。

**说明**：后端暂无「解析一次、多次切块」的独立端点（无 `/chunk` API），MVP 用「重复上传同一文件到不同 strategy」实现，文件走内存 FormData 无额外开销，接口缺口记入 §5。

### 4.4 知识库检索 `/kb`

**左右两栏**：

- **左栏（入库面板）**：
  - 知识库标识输入（正则前端校验 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`，与后端一致）
  - store_type 下拉（chroma / faiss / milvus / pgvector / qdrant）
  - 上传区（支持多文件批量，逐个调 ingest 并展示成功/失败状态）
  - 最近使用的知识库列表（localStorage 记忆，点击回填）
- **右栏（检索面板）**：
  - query 输入 + k 值滑块（1-100，默认 4）+ provider 下拉（auto/dashscope/mock）
  - 结果卡片：相似度上下文中的 page_content + metadata 徽章（file_name / element_type / location / header_path）
  - 空态/加载态/错误态（后端不可达时给出「请先启动 uvicorn」提示）

**数据流**：`POST /api/v1/knowledge-bases/{kb}/ingest`（FormData: file）→ `IngestResult`；`POST /api/v1/knowledge-bases/{kb}/search`（JSON: query/k/store_type/provider）→ `SearchResult`。

## 5. API 契约映射与缺口

| 前端功能 | 现有端点 | 状态 |
|---|---|---|
| 引擎状态 | `GET /health` | ✅ 直接可用 |
| 解析预览 | `POST /api/v1/documents/parse` | ✅ 直接可用 |
| 切块对比 | `POST /api/v1/documents/parse-and-chunk?strategy=` | ✅ 可用（需多次调用） |
| 知识库入库 | `POST /api/v1/knowledge-bases/{kb}/ingest` | ✅ 直接可用 |
| 相似检索 | `POST /api/v1/knowledge-bases/{kb}/search` | ✅ 直接可用 |
| 知识库列表 | — | ⚠️ 缺口：前端用 localStorage 记忆已用 KB 绕过 |
| 解析历史 | — | ⚠️ 缺口：同上，本地会话记录绕过 |
| 单次解析多次切块 | — | ⚠️ 缺口：重复调用 parse-and-chunk 绕过 |

> 缺口均不阻塞 MVP；后续后端补端点时前端只需把 localStorage 数据源换成 API。

## 6. 前端类型定义（镜像后端 models.py）

```typescript
// lib/types.ts —— 与 app/models.py 的 dataclass 一一对应
interface Location {
  page_number?: number
  bbox?: [number, number, number, number]
  start_line?: number
  end_line?: number
  start_char?: number
  end_char?: number
  selector?: string
  start_time?: number
  end_time?: number
}

interface Element {
  id: string
  type: 'heading' | 'paragraph' | 'table' | 'code' | 'image' | 'list_item' | 'blockquote' | string
  content: string
  raw_content?: string
  location?: Location
  metadata: Record<string, unknown>
}

interface ParsedDocument {
  file_name: string
  file_type: string
  raw_text?: string
  file_path?: string
  total_pages?: number
  metadata: Record<string, unknown>
  elements: Element[]
}

interface ChunkOut {
  page_content: string
  metadata: Record<string, unknown> // 含 element_id/location/header_path 等
}

interface SearchResult { query: string; total: number; results: ChunkOut[] }
interface IngestResult { knowledge_base: string; store_type: string; document_count: number; chunk_count: number }
```

## 7. 技术栈与目录结构

**技术栈**（与简历规划统一）：
- Next.js 15（App Router）+ TypeScript
- shadcn-admin 模板（satnaing/shadcn-admin）：自带侧边栏/主题/布局，裁掉 auth 相关页面
- Tailwind CSS v4 + shadcn/ui 组件
- TanStack Query：服务端状态（请求缓存/重试/loading 态）
- 无额外状态库、无 UI 级测试框架（MVP 以 E2E 手测 + 类型安全兜底）

**目录结构**（置于仓库 `frontend/` 子目录，演示与 docker-compose 编排方便）：

```
frontend/
├── app/
│   ├── (admin)/
│   │   ├── layout.tsx            # App Shell：侧边栏 + 顶栏
│   │   ├── page.tsx              # 仪表盘
│   │   ├── parse/page.tsx        # 解析工作台
│   │   ├── chunk-lab/page.tsx    # 切块实验室
│   │   └── kb/page.tsx           # 知识库检索
│   ├── layout.tsx                # 根布局 + Providers
│   └── globals.css
├── components/
│   ├── layout/                   # sidebar-nav 配置、header
│   ├── parse/                    # UploadZone / ElementCard / SourceViewer / LineHighlighter
│   ├── chunk/                    # StrategyTabs / ChunkCard / StatsBar / CompareView
│   ├── kb/                       # IngestPanel / SearchPanel / ResultCard
│   └── ui/                       # shadcn/ui 生成组件
├── hooks/
│   ├── use-health.ts / use-parse.ts / use-chunk.ts / use-ingest.ts / use-search.ts
├── lib/
│   ├── api-client.ts             # fetch 封装：baseURL 来自 env、超时、错误归一化
│   ├── types.ts                  # §6 类型定义
│   └── constants.ts              # 支持扩展名、策略名、store_type 等枚举镜像
├── .env.local                    # NEXT_PUBLIC_API_BASE=http://localhost:8000
└── package.json
```

**关键工程约定**：
- `api-client.ts` 统一处理超时（30s）、非 2xx 错误转 `EngineApiError`、上传走 FormData
- 后端已开启 CORS（`allow_origins=["*"]`），前端直连 `NEXT_PUBLIC_API_BASE`，无需代理
- 所有徽章/高亮色遵循后端语义：heading=紫、paragraph=蓝、table=绿、code=灰、image=珊瑚、定位高亮=蓝

## 8. 交互与视觉规范

- 亮/暗主题跟随 shadcn-admin 内置 ThemeProvider，MVP 默认亮色
- 加载态：上传/解析期间按钮置 spinner + 骨架屏（Element 列表）
- 错误态：后端不可达 → 顶部横幅「无法连接引擎 (localhost:8000)，请运行 uv run uvicorn app.server:app」
- 空态：每页有引导插画位 + 主行动按钮（shadcn 空态模式）
- 溯源高亮为全站最強调色（blue-100 底 + blue-600 边），确保「Location Grounding」卖点一眼可见

## 9. 里程碑（供 plan.md 细化）

| 里程碑 | 内容 | 验证方式 |
|---|---|---|
| M0 脚手架 | Next.js + shadcn-admin 初始化、api-client、types、导航 | `pnpm dev` 可跑通 4 个空路由 + /health 连通 |
| M1 仪表盘 | 状态卡 + 能力卡 + 会话记录 | 停后端显示离线横幅 |
| M2 解析工作台 | 上传 → Element 列表 ↔ 行号高亮 | 上传 test.md 点 Element 右栏高亮 |
| M3 切块实验室 | 4 策略 Tabs + 指标 + 对比模式 | 同文件 4 策略指标不同 |
| M4 知识库检索 | ingest + search + 结果溯源 | demo 库入库后检索命中 |

## 10. 风险与开放问题

1. **大文件上传**：~~parse-and-chunk 是同步阻塞接口，大 PDF 会超时~~ → 已升级为后端异步化改造需求，方案见 §11（前端配合轮询改造，30s 超时仅保留在同步旧端点）
2. **parent_child 策略返回结构**：后端 `split()` 对 parent_child 可能返回 `(child_docs, parent_store)` 元组而非 `ChunkOut[]`，M3 前需实测响应结构，必要时前端做联合类型兼容（注：server.py 已确认取元组首项子块，风险解除，仅父块信息暂缺）
3. **音视频格式**：Whisper 依赖较重，演示环境可能不可用 → 前端对 audio/video 扩展名给出「依赖较重，解析可能较慢」提示
4. **multipart 超时**：Next.js 无代理层直连，风险低；若日后加 middleware 需注意 body 大小限制

---

## 11. 大文件异步解析设计（Addendum，2026-09-08）

### 11.1 动机与现状问题

- 当前 `parse_document` / `parse_and_chunk_document` 虽为 `async def`，但内部直接调用同步的 `load_batch`（PDF/OCR/Whisper 均为 CPU 密集阻塞调用），**大文件解析期间整个事件循环被阻塞，服务对所有请求无响应**
- docker-compose 已包含 Redis（注释即"异步任务队列"），RAG_ROADMAP 1.6 已规划分布式解析——异步化为既定演进方向，提前落地

### 11.2 分阶段方案

**Stage 1（MVP，零新依赖，随前端 M2 一起交付）**：进程内 JobRegistry + ThreadPoolExecutor

- 新增 `app/jobs.py`：`Job` dataclass（id/kind/status/created_at/started_at/finished_at/error/result）+ 线程安全的 `JobRegistry`（dict + Lock，TTL 清理后台任务，默认结果保留 30 分钟，env `JOB_RESULT_TTL` 可配）
- 新增执行器：`ThreadPoolExecutor(max_workers)`，max_workers 由 env `PARSE_WORKERS` 控制（默认 2，Whisper/PaddleOCR 内存重，不宜多开）
- 解析函数通过 `loop.run_in_executor(_EXECUTOR, ...)` 提交，**不阻塞事件循环**
- 临时文件生命周期：提交时落盘至 `data/jobs/{job_id}/`（不再是 tempfile 立删），任务结束（成功取走结果或 TTL 过期）后清理

**Stage 2（生产级，对应 Roadmap 1.6）**：Celery + Redis

- compose 增加 `celery-worker` 服务，broker/result backend 均用现有 Redis
- Job 状态存 Redis（带 TTL），支持多副本水平扩展、服务重启任务不丢
- 进度推送：Redis pubsub → SSE `/api/v1/jobs/{id}/events`（与 roadmap Phase 2 的 SSE 规划合流）

### 11.3 新增 API 契约

```
POST /api/v1/jobs                        # 提交异步任务，立即返回
  multipart: file, kind(parse|parse_and_chunk), strategy, enable_cleaning
  → 202 { "job_id": "...", "status": "queued" }

GET /api/v1/jobs/{job_id}                # 查询单任务状态与结果
  → 200 { "job_id", "status": "queued|running|succeeded|failed",
          "kind", "file_name", "created_at", "started_at", "finished_at",
          "error": null, "result": <ParsedDocument[] | ChunkOut[]> }

GET /api/v1/jobs?limit=20                # 最近任务列表（仪表盘「最近活动」数据源）
```

- 状态机：`queued → running → succeeded | failed`，终态后不可变更
- 兼容性：**现有同步端点保留不动**（小文件仍走同步路径，<5MB 前端直接用旧端点），异步端点为增量

### 11.4 前端配合改造

- 新增 `hooks/use-job.ts`：提交 → `refetchInterval: 1500` 轮询 → 终态停止轮询取 `result`
- 上传交互升级：大文件（>5MB）自动走异步路径，任务卡片显示排队/解析中状态（含已耗时）；小文件走同步路径保持即时反馈
- 仪表盘「最近活动」数据源从 localStorage 换为 `GET /api/v1/jobs`（§5 缺口之一同步消除）
- 解析工作台 / 切块实验室的 loading 态改为任务进度态（可展示「第 N 个文档解析中」——Stage 1 先展示已耗时，Stage 2 接 SSE 真进度）

### 11.5 验收标准

1. 上传 >5MB PDF，提交立即返回 job_id（<200ms），期间 `/health` 持续可响应
2. 轮询至 succeeded 后 result 与同步端点输出结构完全一致（前端渲染组件零改动复用）
3. 并发提交 3 个任务：PARSE_WORKERS=2 时第 3 个保持 queued，前两个完成后自动执行
4. 任务失败时 failed 态含可读 error 信息，临时文件被清理
