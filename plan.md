# omni-rag-engine 前端控制台实施计划（plan.md）

> 依据：design.md（已确认 v2，含 §11 异步解析）
> 方法：superpowers TDD（后端任务先写测试）/ 前端以类型安全 + 组件验收标准兜底
> 约定：所有前端命令在 `frontend/` 下执行；后端命令一律 `uv run`

---

## 里程碑总览

| 里程碑 | 内容 | 依赖 |
|---|---|---|
| M0 | 前端脚手架 + 类型/API 层 + 导航骨架 | 无 |
| M1 | 后端异步任务（app/jobs.py + 3 端点 + pytest） | 无（可与 M0 并行） |
| M2 | 仪表盘 | M0 + M1 |
| M3 | 解析工作台（含异步大文件路径） | M0 + M1 |
| M4 | 切块实验室 | M3 |
| M5 | 知识库检索 | M0 |

---

## M0 前端脚手架（frontend/）

- [ ] **T0.1 初始化项目**
  - 命令：`pnpm create next-app@latest frontend --typescript --tailwind --app --src-dir=false --import-alias "@/*"`（在仓库根执行）
  - 裁剪：不引入 shadcn-admin 全模板，用 `pnpm dlx shadcn@latest init` + 按需添加组件（button/card/input/badge/tabs/select/slider/table/sonner/skeleton），保持目录与 design.md §7 一致
  - 验证：`pnpm dev` → http://localhost:3000 可访问

- [ ] **T0.2 布局与导航**
  - 文件：`app/(admin)/layout.tsx`、`components/layout/sidebar-nav.tsx`
  - 侧边栏四项：仪表盘 `/`、解析工作台 `/parse`、切块实验室 `/chunk-lab`、知识库检索 `/kb`（图标：LayoutDashboard / FileSearch / Scissors / Database）
  - 四个空页面占位（`app/(admin)/{page,parse,chunk-lab,kb}/page.tsx`）
  - 验证：四路由可达，当前项高亮

- [ ] **T0.3 类型与常量**
  - 文件：`lib/types.ts`（design.md §6 全量拷贝）、`lib/constants.ts`
  - constants：`SUPPORTED_EXTENSIONS`（从 `get_supported_extensions()` 输出镜像，写注释注明来源）、`STRATEGIES = ['auto','sliding_window','parent_child','header_aware']`、`STORE_TYPES`、`PROVIDERS`、`ELEMENT_TYPE_COLORS`
  - 验证：`pnpm tsc --noEmit` 零错误

- [ ] **T0.4 API 客户端**
  - 文件：`lib/api-client.ts`
  - 实现：`apiFetch<T>(path, init)`（baseURL=env `NEXT_PUBLIC_API_BASE` 默认 `http://localhost:8000`、30s 超时 AbortController、非 2xx 抛 `EngineApiError(status, detail)`）；`apiUpload<T>(path, formData)` 便捷方法
  - 验证：临时在仪表盘调用 `GET /health`，控制台打印结果后删除临时代码

## M1 后端异步任务（TDD）

- [ ] **T1.1 测试先行：JobRegistry 单元测试**
  - 文件：`tests/test_jobs.py`
  - 用例：create→queued；start→running；finish 成功/失败→终态不可再变更；list 按 created_at 倒序；TTL 过期条目被清理
  - 验证：`uv run pytest tests/test_jobs.py` **先红**

- [ ] **T1.2 实现 app/jobs.py**
  - 文件：`app/jobs.py`
  - 内容：`Job` dataclass（id/kind/status/file_name/created_at/started_at/finished_at/error/result）+ `JobRegistry`（dict + Lock，`cleanup_expired()` 方法）；`_EXECUTOR = ThreadPoolExecutor(max_workers=int(env PARSE_WORKERS, 默认 2))`；`submit_parse_job(kind, file_path, ...)` 返回 job_id，内部 `run_in_executor`；后台 TTL 清理协程（FastAPI lifespan 启动，间隔 60s，TTL=env JOB_RESULT_TTL 默认 1800s）；任务产物目录 `data/jobs/{job_id}/`
  - 注释纯中文、方法名英文（遵守 AGENTS.md）
  - 验证：`uv run pytest tests/test_jobs.py` **转绿**

- [ ] **T1.3 jobs API 端点**
  - 文件：`app/server.py` 追加（Pydantic Schema：`JobOut` / `JobCreateOut`，仅 API 边界）
  - 端点按 design.md §11.3：`POST /api/v1/jobs`（multipart: file/kind/strategy/enable_cleaning → 202）、`GET /api/v1/jobs/{job_id}`、`GET /api/v1/jobs?limit=20`；kind 白名单校验（400）
  - 复用 `_save_upload_to_temp` 但落盘到 `data/jobs/{job_id}/`；执行体复用 `_load_batch_from_upload` 的内部逻辑与 AutoChunker（元组取子块，同现有 L260-263 处理）
  - 验证：`uv run pytest tests/test_server.py`（新增 3 个端点用例：提交返回 202+job_id、轮询到 succeeded 且 result 结构等于同步端点、kind 非法返回 400）

- [ ] **T1.4 事件循环不阻塞验证**
  - 手测脚本（记入测试注释）：启动服务 → 提交大文件 job → 立刻并发 `curl /health` 10 次，全部 <50ms 返回
  - 验证：M3 验收时复测

## M2 仪表盘（/）

- [ ] **T2.1 use-health hook**：`hooks/use-health.ts`，TanStack Query `refetchInterval: 30000`，返回 `{status, latency, error}`；验证：停后端显示离线
- [ ] **T2.2 use-jobs hook**：`hooks/use-jobs.ts`（列表，`refetchInterval: 10000`）；验证：提交过任务后有记录
- [ ] **T2.3 页面组装**：`app/(admin)/page.tsx`——引擎状态卡（在线徽章/版本/延迟）、能力矩阵卡（4 个 metric 卡：37+ 格式/4 策略/5 向量库/3 Embedding 供应商）、最近任务列表（job 状态徽章 + 文件名 + 耗时）、快速开始卡（三步跳转）
- 验收：断网后端 → 横幅「无法连接引擎，请运行 uv run uvicorn app.server:app」

## M3 解析工作台（/parse）

- [ ] **T3.1 use-parse / use-job-polling hooks**：`use-parse.ts`（同步路径，≤5MB）、`use-job.ts`（异步路径：submit → refetchInterval 1500 → 终态停止并取 result）；验证：mock 两种大小文件各自走通
- [ ] **T3.2 UploadZone 组件**：`components/parse/upload-zone.tsx`，拖拽 + 点击，accept 由 SUPPORTED_EXTENSIONS 生成，>5MB 自动走异步并显示任务进度态（已耗时计时器）；audio/video 扩展名给「依赖较重」提示
- [ ] **T3.3 ElementList + 徽章组件**：`components/parse/element-card.tsx`、`type-badge.tsx`（色板：heading紫/paragraph蓝/table绿/code灰/image珊瑚）、`location-badge.tsx`（L12-L18 / P3·bbox / selector / 时间戳，按 location 字段存在性自动选择展示）；类型筛选 chips 统计各类型数量
- [ ] **T3.4 SourceViewer 行号高亮**：`components/parse/source-viewer.tsx`——raw_text 按行渲染 + 行号槽，选中 Element 的 start_line~end_line 区间蓝底高亮 + 自动 scrollIntoView；无行号定位（PDF/音视频）时降级为 Element 详情 JSON 面板
- [ ] **T3.5 三栏联动**：`app/(admin)/parse/page.tsx` 组装（左：上传+文件卡+筛选；中：Element 列表；右：SourceViewer）；raw_content 折叠查看（table 渲染 HTML、code 用 pre）
- 验收：上传 `examples/test.md` → 点击任一 Element → 右栏对应行高亮滚动；上传 >5MB 文件走 job 轮询不阻塞

## M4 切块实验室（/chunk-lab）

- [ ] **T4.1 use-chunk hook**：`use-chunk.ts`——同一 File 缓存于页面 state，strategy 参数化；4 策略可 `Promise.all` 并行请求；结果按 strategy 键缓存（切换 Tab 不重发）
- [ ] **T4.2 指标条 + 切片卡片**：`components/chunk/stats-bar.tsx`（切片总数/平均字符/最长/含 header_path 占比）、`chunk-card.tsx`（策略徽章+序号+字符数+header_path 面包屑+内容展开+location 徽章）
- [ ] **T4.3 策略 Tabs 与对比模式**：`components/chunk/strategy-tabs.tsx`（单选切换）+ `compare-view.tsx`（多选 ≥2 时左右分栏 + 顶部指标对比表）
- [ ] **T4.4 页面组装**：`app/(admin)/chunk-lab/page.tsx`；大文件同样走异步 job（kind=parse_and_chunk）
- 验收：同一 md 文件 4 策略指标明显不同；对比模式并排可滚动

## M5 知识库检索（/kb）

- [ ] **T5.1 use-ingest / use-search hooks**：`hooks/use-ingest.ts`（多文件顺序提交，逐个返回状态）、`use-search.ts`
- [ ] **T5.2 入库面板**：`components/kb/ingest-panel.tsx`——kb 名称输入（前端正则 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` 校验 + 错误提示）、store_type 下拉、多文件上传列表（每行成功/失败状态）、最近 KB 记忆（localStorage `rag-console:kbs`，点击回填）
- [ ] **T5.3 检索面板**：`components/kb/search-panel.tsx`——query 输入 + k 滑块(1-100) + provider 下拉；结果卡片（page_content + metadata 徽章：file_name/element_type/location/header_path）；空态/加载态/错误态（含后端未启动引导文案）
- [ ] **T5.4 页面组装**：`app/(admin)/kb/page.tsx` 左右两栏
- 验收：demo 库 ingest 成功 → search「切块策略」Top-4 命中且卡片带溯源徽章

## 收尾

- [ ] **T6.1 README 前端章节**：启动方式（pnpm i / pnpm dev / NEXT_PUBLIC_API_BASE 说明）
- [ ] **T6.2 Code Review**：对照本计划逐任务核查，产出 `review.md`（Critical/Major/Minor 分级）
- [ ] **T6.3 全链路验收**：后端 `uv run uvicorn` + 前端 `pnpm dev`，按 M2~M5 验收标准过一遍，演示脚本（test.md 全流程）跑通

---

## 执行顺序与并行建议

```
M0 ──┬── M2 仪表盘 ────┐
     │                  ├── M4 切块实验室 ── M6 收尾
M1 ──┴── M3 解析工作台 ─┘
M0 ────── M5 知识库检索（独立，可穿插）
```

- 每完成一个任务先本地验证再勾选；Critical 问题当日修复
- 后端任务（M1）严格 TDD；前端以 `pnpm tsc --noEmit` + 验收标准把关
