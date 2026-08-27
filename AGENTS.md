# Agent & AI 开发者协作规范指南 (AGENTS.md)

欢迎加入 **omni-rag-engine** 项目。本文件为 AI Agent（如 Claude / Antigravity / Cursor 等）与人类开发者共同维护和扩展本项目时的核心指导规范。

---

## 1. 项目定位与架构概要 (Project Overview)

**omni-rag-engine** 是一款高可用、全模态（包含文档、图片、音视频、网页等）、具备物理定位与清洗脱敏能力的企业级 RAG 基础设施引擎与 FastAPI 微服务后端。

### 核心技术栈
* **核心语言**: Python >= 3.13
* **包管理器**: `uv`
* **Web 框架**: FastAPI + Uvicorn
* **数据校验**: Pydantic v2
* **多模态与解析**: Docling, PyMuPDF (fitz), python-docx, python-pptx, openpyxl, PaddleOCR, OpenAI Whisper
* **向量数据库**: ChromaDB, Milvus, Qdrant, PgVector

---

## 2. 目录架构与设计模式 (Directory & Architecture)

代码库的核心业务逻辑存放于 `app/` 目录下：

```text
app/
├── loaders/        # 1. 多源加载器 (支持本地文件、网络 URL、压缩包解压等)
├── parsers/        # 2. 格式解析器 (覆盖 37+ 文本/文档/音视频/图片格式)
├── ocr/            # 3. OCR 识别引擎集成 (PaddleOCR 等)
├── captioners/     # 4. 多模态理解引擎 (图像描述生成/图文分析)
├── cleaners/       # 5. 数据清洗与隐私脱敏管线 (CleanerPipeline)
├── chunkers/       # 6. 智能文本切块与重叠策略 (语义/固定长度/标题层级)
├── enrichers/      # 7. 上下文增强与元数据补充
├── vectorstores/   # 8. 向量数据库适配器 (Chroma, Milvus, Qdrant, PgVector)
├── config.py       # 系统配置管理 (自研 .env 加载器，读取环境变量)
├── factory.py      # 解析器自动路由工厂 (ParserFactory)
├── models.py       # 核心数据模型 (Location / Element / ParsedDocument dataclass)
├── server.py       # FastAPI Web 微服务入口 (/api/v1 RESTful API)
└── main.py         # CLI 批量解析演示入口
```

---

## 3. Agent 编码与设计铁律 (Engineering Protocol)

在为此仓库生成或修改代码时，Agent 必须严格遵守以下规则：

### 3.1 类型安全与数据模型 (Type Safety & Schemas)
* **核心跨模块数据模型**：所有跨模块传递的解析节点、切块数据、元数据，必须严格使用 `app/models.py` 中定义的 dataclass 数据模型：`Location`（物理定位）、`Element`（语义节点）、`ParsedDocument`（完整文档容器）。切块产物统一导出为 LangChain `Document`（含 `page_content` 与 `metadata`）。
* **Pydantic 仅用于 API 边界**：Pydantic v2 模型只允许出现在 `app/server.py` 的请求/响应 Schema 定义中，不得替代内部 dataclass 数据流。
* **全面使用类型注解**：方法与函数签名必须显式声明输入与返回值类型。

### 3.2 物理定位元数据保护 (Location Grounding)
* **保留原物理定位**：文档切块或解析时，必须完整继承与透传源文档的定位信息：
  * PDF / PPTX: `bbox` 归一化坐标 + `page_number`
  * Markdown / TXT / CSV: `start_line` / `end_line` 行号
  * HTML / DOCX: DOM `selector` / XPath
  * 音视频: `start_time` / `end_time` 时间戳
* **严禁丢弃定位数据**：在清洗 (`cleaners`) 或切块 (`chunkers`) 时，不得剥离节点的定位元数据。

### 3.3 数据清洗与隐私安全 (Security & Cleaning)
* **隐私脱敏链条**：解析出的文本必须经过 `CleanerPipeline`，防范控制字符乱码以及敏感隐私（手机号、身份证、邮箱等）。
* **敏感信息隔离**：绝不将真实 `.env` 密钥或本地向量库持久化目录（如 `*_fallback_db/`）提交至 Git 仓库（需由 `.gitignore` 约束）。

### 3.4 异常处理与工程规范
* **注释规范**：业务逻辑代码采用**纯中文**注释，方法名/变量名/属性保持**纯英文**。
* **优雅降级 (Fallback)**：向量数据库适配器或外部模型服务不可用时，必须实现友好的回退逻辑与标准错误日志输出。

---

## 4. 常见开发与测试指令 (Developer Commands)

所有的环境依赖均通过 `uv` 管理，Agent 在推荐命令或执行测试时必须使用 `uv run`：

```bash
# 1. 安装/同步项目依赖
uv sync

# 2. 启动 FastAPI 本地开发服务
uv run uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

# 2.1 运行 CLI 批量解析演示 (单文件/目录/压缩包)
uv run app/main.py examples/

# 3. 运行项目测试套件
uv run pytest

# 4. 添加新依赖包
uv add <package_name>
```

---

## 5. 项目路线图索引 (Roadmap Pointer)

关于核心功能的扩展规划、增量 CDC 引擎、GraphRAG 等进阶 roadmap，请优先查阅根目录的 [RAG_ROADMAP.md](RAG_ROADMAP.md)。
