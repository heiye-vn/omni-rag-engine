# omni-rag-engine 企业级全模态 RAG 基础设施引擎规划与演进路线图 & TODO 清单

本项目旨在构建一个高可用、多模态、带精准定位与数据清洗的企业级 RAG 数据预处理与基础设施引擎。以下为完整 RAG 处理流程与当前项目的**已实现 (`[x]`)** 与 **待扩展 (`[ ]`)** 功能对比清单及分阶段演进路线。

---

## 1. 多源数据接入与加载 (Data Ingestion & Loaders)

- [x] **1.1 本地多格式文件解析 (37+ 格式全覆盖)**
  - [x] 纯文本与 Markdown 解析 ([txt.py](app/parsers/txt.py), [markdown.py](app/parsers/markdown.py))
  - [x] Office 三大件解析 ([docx.py](app/parsers/docx.py), [xlsx.py](app/parsers/xlsx.py), [pptx.py](app/parsers/pptx.py))
  - [x] PDF 文档解析 ([pdf.py](app/parsers/pdf.py))
  - [x] 网页与结构化数据解析 ([html.py](app/parsers/html.py), [csv.py](app/parsers/csv.py), [json.py](app/parsers/json.py))
  - [x] 图片与音视频解析 ([image.py](app/parsers/image.py), [audio.py](app/parsers/audio.py), [video.py](app/parsers/video.py))
  - [x] 基于扩展名自动路由的解析工厂 ([factory.py](app/factory.py))
- [x] **1.2 流式与网络加载器 (Stream & HTTP/OSS Loaders)**
  - [x] 支持通过 HTTP / HTTPS / 阿里云 OSS 远程 URL 直接加载文件进行解析与多模态大模型识别
  - [x] 网络 HTTP URL 网页抓取与自动解析
- [x] **1.3 批量扫描与压缩包加载 (Batch Loaders)**
  - [x] ZIP / TAR / TAR.GZ 压缩包 Zip Slip 安全解压与隔离文件解析 ([archive.py](app/loaders/archive.py))
  - [x] 目录树批量递归扫描与自动过滤 ([directory.py](app/loaders/directory.py))
  - [x] 全局智能批处理入口 `load_batch` ([helper.py](app/loaders/helper.py))
- [ ] **1.4 企业级第三方数据源连接器 (Enterprise Connectors)**
  - [ ] Notion / Confluence 官方 API 增量文档拉取与文档树抓取
  - [ ] 飞书 (Feishu) / 钉钉 (DingTalk) / 企微文档在线协作文档同步连接器
  - [ ] 对象存储 (S3 / MinIO / 腾讯云 COS) Webhook 变更监听与增量加载器
- [ ] **1.5 增量同步与变更数据捕捉 (CDC & Incremental Engine)**
  - [ ] 基于 ETag / File MD5 Hash 校验的文档修改感知与增量解析
  - [ ] 源文档物理删除同步触发向量库失效切片自动清理
- [ ] **1.6 高并发分布式解析调度 (Distributed Parsing Pipeline)**
  - [ ] 基于 Celery / Redis Task Queue / Ray 的分布式解析任务队列
  - [ ] 大文件并发 Chunk 粒度并行解析与解析速率限流防护

---

## 2. 结构化抽取与定位 (Structured Parsing & Grounding)

- [x] **2.1 语义节点分类 (Element Type Classification)**
  - [x] 区分 `heading` (含 level)、`paragraph`、`table`、`code`、`image`、`list_item`、`blockquote` 等节点类型
- [x] **2.2 可渲染原格式保存 (Renderable Raw Content)**
  - [x] 保存可直接在前端 UI 渲染的 HTML 表格 `<table>` / 源码片段存入 `raw_content`
- [x] **2.3 全场景物理/几何定位数据 (Location Grounding)**
  - [x] PDF/PPTX 归一化坐标 `bbox` + 页码 `page_number`
  - [x] Markdown/TXT/CSV 行号 `start_line` / `end_line`
  - [x] HTML/DOCX 节点的 DOM `selector` / XPath
  - [x] 音视频 ASR `start_time` / `end_time` 时间戳
- [ ] **2.4 复杂版面分析与布局解析 (Advanced Layout Analysis)**
  - [ ] 基于 PP-Structure / LayoutLMv3 / DocLayout-YOLO 的双栏/多栏 PDF 顺序恢复
  - [ ] 复杂的无线表格 (Borderless Tables) 重构与单元格跨行合并解析
  - [ ] 数学公式 (LaTeX / MathJax / OCR Formula) 结构化抽取
  - [ ] 页眉页脚、水印、版权提示词的 AI 自动检测与剔除

---

## 3. 数据清洗与治理 (Data Cleaning & Governance)

- [x] **3.1 解耦清洗管线架构 ([CleanerPipeline](app/cleaners/pipeline.py))**
  - [x] `ControlCharCleaner` (不可见控制字符与 NULL 乱码剔除)
  - [x] `WhitespaceCleaner` (Unicode 全半角归一化与冗余空格合并)
  - [x] `PIIMaskerCleaner` (敏感隐私数据脱敏：手机号、身份证、邮箱)
  - [x] `LengthFilterCleaner` (无意义极短文本与全标点符号节点过滤)
  - [x] `ParsedDocument.clean()` 一键链式清洗
- [x] **3.2 上下文前缀缝合与语义增强 ([enrichers/](app/enrichers/))**
  - [x] 动态标题层级大纲栈维护 (H1 -> H2 -> H3 升级与回退)
  - [x] Anthropic Contextual Retrieval 规范的上下文前缀缝合注入器 (`ContextPrefixInjector`)
  - [x] 复杂表格结构化增强与标题上下文自动关联 (`TableEnhancer`: 抽取 `kv_pairs` JSON 与自解释描述)
  - [x] 结构化导出 `metadata["header_path"]` 与 `metadata["table_caption"]`
- [ ] **3.3 LLM 驱动的知识提炼与反向生成 (Knowledge Generation & HyDE)**
  - [ ] 针对 Chunk 节点的 LLM 自动摘要与 Abstract 生成
  - [ ] 假设性问题反向生成 (Hypothetical Questions / HyDE)，提升问答召回率
- [ ] **3.4 知识图谱与 GraphRAG 关系抽取 (GraphRAG & Entity Extraction)**
  - [ ] 命名实体 (NER: 人名、机构、专业术语) 抽取与语义关联
  - [ ] SPO 关系三元组构建与知识拓扑图谱 (Graph Topology) 节点链组装
- [ ] **3.5 跨语言识别与机器翻译对齐 (Language Detection & Alignment)**
  - [ ] 多语种文本自动识别 (Language Detection)
  - [ ] 小语种切片统一翻译对齐与多语言混合索引构建

---

## 4. 智能切块与分词 (Smart Chunking & Text Splitting)

- [x] **4.1 节点 UUID 全局追踪**
  - [x] 为每个 `Element` 分配唯一 `id`，打通 Chunk -> Element -> Location 的追踪链
- [x] **4.2 LangChain 生态适配**
  - [x] [to_langchain_documents()](app/models.py#L120) 输出标准 `LangChain Document` 列表
- [x] **4.3 智能切块策略支持 ([chunkers/](app/chunkers/))**
  - [x] 滑动窗口切块器 `SlidingWindowChunker` (保持 Element 逻辑完好，不剪断代码与表格)
  - [x] 父子块切片器 `ParentChildChunker` (小块检索精准召回，父块提供完整 LLM 上下文)
  - [x] 标题层级切片器 `HeaderAwareChunker` (维持大纲结构树，附带 `header_path` 路径)
  - [x] 自适应智能路由器 `AutoChunker` (自动分析 `ParsedDocument` 结构路由最适策略)
- [ ] **4.4 深度语义与多模态切块策略 (Semantic & Late Chunking)**
  - [ ] 基于 Embedding 相似度突变点的语义切块器 (Semantic Chunking)
  - [ ] Late Chunking 延迟切块 (基于 Long-Context 统一 Context 编码导出 Token Embedding)
  - [ ] 跨模态文本-图像混合交叉切片 (Interleaved Multimodal Chunking)

---

## 5. 多模态语义增强 (Multimodal Enrichment)

- [x] **5.1 多媒体基础属性与 ASR 转写**
  - [x] 图像尺寸、格式、色彩模式、EXIF 元数据提取
  - [x] 基于 OpenAI Whisper 的音视频语音识别 (ASR) 与时间戳导出
- [x] **5.2 视觉大模型图文理解 ([captioners/](app/captioners/))**
  - [x] 阿里通义千问 Qwen-VL 视觉大模型接口 (`DashScopeCaptioner`)
  - [x] OpenAI Vision (GPT-4o / GPT-4o-mini) 接口 (`OpenAICaptioner`)
  - [x] 本地 Ollama 视觉大模型接口 (`OllamaCaptioner`)
  - [x] 零配置防崩降级兜底器 (`MockCaptioner`)
- [x] **5.3 扫描件图片 OCR 识别 ([ocr/](app/ocr/))**
  - [x] 基于 PaddleOCR 的离线印刷体文字与表格文字提取 (`PaddleOCREngine`)
  - [x] 精准几何 BBox 坐标计算与归一化标定 `Location(bbox=[x0, y0, x1, y1])`
  - [x] 扫描版 PDF 页面自动感应识别与位图渲染 OCR 补偿提取

---

## 6. 向量存储与数据库索引 (Vector Storage & DB Ingestion)

- [x] **6.1 标准框架导出接口**
  - [x] 兼容任意 LangChain VectorStore (FAISS, Chroma, Milvus, Qdrant, PGVector)
- [x] **6.2 向量计算引擎 ([embeddings.py](app/vectorstores/embeddings.py))**
  - [x] 阿里百炼 `text-embedding-v3` 中文高精度向量引擎与配置自动感知
  - [x] OpenAI `text-embedding-3-small` / `text-embedding-3-large` 支持
  - [x] 零 API 场景下的 `MockEmbeddings` 平滑降级兜底器
- [x] **6.3 企业级主流向量数据库集成 ([vectorstores/](app/vectorstores/))**
  - [x] **Milvus**: 大型企业海量分布式向量数据库适配器 (`MilvusStore`)
  - [x] **PGVector**: PostgreSQL 关系型数据库向量扩展适配器 (`PGVectorStore`)
  - [x] **Qdrant**: 高性能 Rust 引擎与 Payload 过滤向量适配器 (`QdrantStore`)
  - [x] **Chroma**: 本地嵌入式磁盘持久化向量数据库 (`ChromaStore`)
  - [x] **FAISS**: Meta 开源高性能 CPU 向量索引与落盘快照 (`FAISSStore`)
- [x] **6.4 统一持久化路由与可视化检查工具**
  - [x] `ParsedDocument.to_vectorstore()` 一键流水线落盘快捷入口
  - [x] `inspect_store.py` 本地向量数据库 Terminal 终端彩色可视化查看器
- [ ] **6.5 混合索引与多向量构建 (Hybrid Indexing & Sparse Embeddings)**
  - [ ] Dense (密集向量) + Sparse (BM25/SPLADE 稀疏向量) 混合联合索引
  - [ ] 多向量关联存储 (Multi-Vector Retriever: 摘要向量与全文本切片 1:N 建立索引关系)
  - [ ] 跨模态文本-图像统一向量空间索引 (CLIP / Qwen-VL-Embedding / BGE-M3 Multimodal)
- [ ] **6.6 切片去重与高级元数据过滤构造 (Deduplication & Metadata Expression)**
  - [ ] 基于 MinHash / SimHash 的海量 Chunk 局部敏感哈希 (LSH) 文本去重
  - [ ] 高效构造符合 SQL / JSON 标准的组隔离与多条件动态 Metadata 过滤表达式

---

## 7. 检索优化、多路召回与重排序 (Retrieval, Reranking & Fusion)

- [ ] **7.1 多路召回与算法融合 (Hybrid Retrieval & RRF Fusion)**
  - [ ] 密集向量召回 (Dense Retrieval) 与关键词/稀疏向量 (BM25 / Sparse) 联合多路召回
  - [ ] Reciprocal Rank Fusion (RRF) 倒数排名融合算法与 Score 动态归一化打分
- [ ] **7.2 精细化重排序引擎 (Cross-Encoder / Rerank Engine)**
  - [ ] 接入 BGE-Reranker, Cohere Rerank, Jina Reranker 等 Cross-Encoder 模型
  - [ ] 对 Top-K 召回结果进行二次精度重排与相关度得分阈值过滤 (Score Cutoff)
- [ ] **7.3 查询变换与扩展 (Query Transformation & Expansion)**
  - [ ] LLM 驱动的 Query Rewriting (查询改写) 与 Query Decomposition (多子问题拆解)
  - [ ] Multi-Query Expansion (多角度同义查询扩展)
- [ ] **7.4 上下文动态裁剪与 Prompt 压缩 (Context Trimming & Compression)**
  - [ ] 动态 Context Window 预算控制与冗余信息硬裁剪 (Long-Context Loss-in-the-Middle 优化)
  - [ ] LLM 语义压缩引擎 (Selective Context / LLMLingua 压缩)

---

## 8. 企业级权限隔离、治理服务与可观测性 (Enterprise Security, Service & Governance)

- [ ] **8.1 细粒度 RBAC / ABAC 文档权限控制 (Multi-Tenancy & Document ACL)**
  - [ ] 租户数据硬隔离与多租户 Collection 路由
  - [ ] 用户/角色级别文档访问控制列表 (ACL) 与向量检索 Metadata Filter 自动拼接
- [ ] **8.2 端到端数据血缘与防篡改审计日志 (Data Lineage & Audit Logging)**
  - [ ] 文档生命周期血缘追踪: 源文件 -> 节点 Element -> Chunk ID -> Vector ID -> LLM Reference 完整路径溯源
  - [ ] 操作防篡改审计日志与数据合规导出
- [ ] **8.3 RAG 质量自动化评估与基准测试 (RAG Benchmark & Evaluation)**
  - [ ] 接入 Ragas / TruLens / DeepEval 评估框架
  - [ ] 忠实度 (Faithfulness)、回答相关性 (Answer Relevance)、上下文精准度与召回率 (Context Precision & Recall) 指标自动化大盘
- [ ] **8.4 生产级 API 服务化与可观测性 (RESTful API, Microservices & Observability)**
  - [ ] 基于 FastAPI 的生产级 HTTP / RESTful API 接口封装 (包含流式 SSE 接口)
  - [ ] Prometheus 监控指标暴露 (解析 QPS、向量写入吞吐率、Embedding / Captioner 延迟分布)
  - [ ] OpenTelemetry / LangSmith 端到端链路追踪与性能耗时可视化分析

---

## 9. 生产级 FastAPI 服务端与全量 API 矩阵体系 (FastAPI Server & API Matrix)

- [ ] **9.0 用户身份认证与账号管理 API 子系统 (`/api/v1/auth/*`)**
  - [ ] `POST /api/v1/auth/register`: 新用户注册（邮箱/手机号验证码）
  - [ ] `POST /api/v1/auth/login`: 用户登录与 JWT Access/Refresh Token 签发
  - [ ] `POST /api/v1/auth/refresh-token`: 刷新 JWT Token 保持登录状态
  - [ ] `POST /api/v1/auth/sso/callback`: 企微 / 飞书 / 钉钉 / OAuth2 企业单点登录 (SSO) 对接
  - [ ] `GET /api/v1/auth/me`: 获取当前登录用户信息、可切换租户与权限角色
- [ ] **9.1 文档解析、上传与生命周期 CRUD API 子系统 (`/api/v1/documents/*`)**
  - [x] `POST /api/v1/documents/parse`: 上传本地文件/压缩包，返回结构化语义节点列表（含 Location 物理定位）
  - [x] `POST /api/v1/documents/parse-and-chunk`: 上传本地文件/压缩包并返回结构化切片
  - [ ] `POST /api/v1/documents/parse-url`: 解析远程 HTTP / 阿里云 OSS 文件 URL
  - [ ] `GET /api/v1/knowledge-bases/{kb}/documents`: 分页查询文档列表（支持状态过滤、关键词搜索与排序）
  - [ ] `GET /api/v1/documents/{doc_id}`: 获取单条文档的元数据与解析概览
  - [ ] `POST /api/v1/documents/{doc_id}/reparse`: 变更切片策略后一键触发重新解析/重新切片
  - [ ] `GET /api/v1/documents/{doc_id}/parse-logs`: 查看解析失败文档的日志与 Stack Trace
  - [ ] `DELETE /api/v1/documents/{doc_id}`: 级联删除文档、向量库切片及源文件
- [ ] **9.2 细粒度切片管理与人工在线调优 CRUD API 子系统 (`/api/v1/chunks/*`)**
  - [ ] `GET /api/v1/documents/{doc_id}/chunks`: 分页获取文档下的所有切片列表
  - [ ] `GET /api/v1/chunks/{chunk_id}`: 获取单条切片详情与向量 Embedding 状态
  - [ ] `PUT /api/v1/chunks/{chunk_id}`: 人工在线修改切片文本并自动更新向量库
  - [ ] `POST /api/v1/chunks/{chunk_id}/toggle-enable`: 一键启用/禁用特定切片（检索忽略噪声切片）
  - [ ] `POST /api/v1/documents/{doc_id}/chunks`: 手动新增自定义知识切片
- [ ] **9.3 原文档在线预览与原文几何高亮定位 API 子系统 (`/api/v1/grounding/*`)**
  - [ ] `GET /api/v1/documents/{doc_id}/raw-stream`: 获取原文档 Preview 二进制文件流 (用于 pdfjs 渲染)
  - [ ] `GET /api/v1/chunks/{chunk_id}/grounding-location`: 获取切片的页码、物理坐标 `bbox`、行号与 DOM Selector (用于前端高亮发光框定位)
- [x] **9.4 向量知识库持久化与检索 API 子系统 (`/api/v1/knowledge-bases/*`)**
  - [x] `POST /api/v1/knowledge-bases/{kb}/ingest`: 一键导入文档切块并持久化写入向量库 (chroma/faiss/milvus/pgvector/qdrant)
  - [x] `POST /api/v1/knowledge-bases/{kb}/search`: Top-K 向量相似度检索 (混合多路召回见 7.1 规划)
- [ ] **9.5 RAG 检索问答与 SSE 打字机流式 API 子系统 (`/api/v1/chat/*`)**
  - [ ] `POST /api/v1/chat/completions/stream`: SSE (Server-Sent Events) 打字机流式问答 (兼容 Vercel AI SDK `useChat`)
- [ ] **9.4 租户隔离、大文件直传与生命周期 API 子系统**
  - [ ] `GET/POST /api/v1/tenants/{id}/workspaces`: 租户隔离空间与配额查询
  - [ ] `POST /api/v1/documents/presigned-url`: 申请 OSS / S3 大文件直传预签名地址
  - [ ] `DELETE /api/v1/documents/{id}`: 文档软/硬删除与向量库同步级联清理
- [ ] **9.5 敏感词合规审核与 PII 脱敏 API 子系统 (`/api/v1/documents/{id}/moderate`)**
  - [ ] 触发文档敏感词审查、政治敏感检测与 PII 手机/身份证脱敏合规校验
- [ ] **9.6 细粒度 RBAC / ABAC 权限与 ACL 控制 API 子系统 (`/api/v1/permissions/acl`)**
  - [ ] 配置资源访问控制列表 (ACL)，自动拼装向量库请求的 `tenant_id` 与 `allowed_roles` Metadata Filter 算子
- [ ] **9.7 Prompt 模板与 Agent 编排 API 子系统 (`/api/v1/prompts/*`)**
  - [ ] Prompt 模板 CRUD、版本历史回滚与 A/B Test 实验组管理
- [ ] **9.8 问答人工干预与 FAQ 标注硬匹配 API 子系统 (`/api/v1/knowledge-bases/{kb}/annotations`)**
  - [ ] 人工添加高频问答对 (QA Pair / FAQ 命中)，干预与强覆盖 LLM 答案
- [ ] **9.9 Ragas 质量评估、点赞点踩与 Zero-Hit 反馈 API 子系统**
  - [ ] `POST /api/v1/chat/feedback`: 用户点赞/点踩与 Bad-Case 报错提交
  - [ ] `GET /api/v1/evaluation/metrics`: 自动计算 Faithfulness / Context Recall 评估指标大盘
- [ ] **9.10 外部 Connector (Confluence/飞书/S3) 增量同步 API 子系统 (`/api/v1/connectors/*`)**
  - [ ] 触发第三方云端在线文档同步与 Webhook 实时监听处理
- [ ] **9.11 Token 算力用量账单与 OpenTelemetry 链路追踪 API 子系统**
  - [ ] `GET /api/v1/analytics/costs`: 按部门/用户/模型统计算力费用折线图
  - [ ] `GET /api/v1/observability/traces/{id}`: LangSmith / OpenTelemetry 节点耗时 Trace 分析

---

## 🚀 10. 演进实施路线与分阶段执行里程碑 (Phased Execution Milestones)

按以下 5 大阶段逐步推进落地，避免过度设计与一步登天：

```
Phase 1: 核心算力与引擎构建 [已完成] ➔ Phase 2: FastAPI Web 服务化 (当前阶段) ➔ Phase 3: 检索优化与 Rerank ➔ Phase 4: 企业级多租户与权限 ➔ Phase 5: 运营干预、评估与可观测性
```

* **✅ Phase 1: 核心算力与数据预处理引擎构建（已完成）**
  * 完成 37+ 格式解析器、`CleanerPipeline` 清洗、`AutoChunker` 切块、多模态 Caption/OCR、5 大向量库适配器与 `inspect_store` 可视化看盘。
* **🚩 Phase 2: FastAPI Web 服务化与开箱即用 API 封装（当前正在推进）**
  * ✅ 基础服务层已上线：[app/server.py](app/server.py) 提供 `/health`、文档解析 (`/documents/parse`)、智能切块 (`/documents/parse-and-chunk`)、知识库入库与 Top-K 检索 (`/knowledge-bases/{kb}/ingest|search`) 五组 RESTful 接口，附 OpenAPI Swagger 文档。
  * 待推进：远程 URL 解析接口、SSE 打字机流式问答 API (`/chat/completions/stream`)。
  * 对接 React 前端 (`Vercel AI SDK / useChat`) 验证效果。
* **🎯 Phase 3: 检索优化、Rerank 重排与多路召回（算法增强）**
  * 引入 BGE-Reranker 交叉编码器，实现 Dense + Sparse (BM25) 混合检索与 RRF 融合打分。
* **🛡️ Phase 4: 企业级多租户隔离、ACL 权限与大文件直传（安全合规）**
  * 引入 `tenant_id` 硬隔离，实现 OSS 直传预签名与向量库 ACL Metadata Filter 自动注入算子。
* **📊 Phase 5: 运营干预、Ragas 质量评估与 Token 算力可观测性（生产运营）**
  * 引入 FAQ 人工硬匹配干预、用户 Feedback 点赞点踩、Ragas 评估指标大盘与 OpenTelemetry 耗时链路追踪。
