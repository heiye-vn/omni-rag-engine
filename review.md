# Code Review 报告（review.md）

> 范围：M0~M5 全部交付物（后端异步任务模块 + 前端控制台）
> 日期：2026-09-08 · 依据：plan.md 验收标准

## 总体结论：通过

后端 36 个测试全绿（含 12 个新增 jobs 测试）；前端 `tsc --noEmit` 零错误；四路由 SSR 渲染验证通过；异步任务全链路（提交 → 轮询 → 终态取结果）实测成功，解析期间 `/health` 延迟 5~24ms，事件循环无阻塞。

## 分级问题清单

### Critical（阻塞）：无

### Major（应修）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| M1 | `app/jobs.py` `submit_job` | `_EXECUTOR.submit(_run)` 的 Future 未持有引用，若线程池已满且任务异常，异常只写入 Future 无人读取（静默）。当前 `_run` 内部已全量 try/except，实际无泄漏，但防御性不足 | 可加 `future.add_done_callback` 记录意外异常日志（非阻塞改进） |
| M2 | `app/server.py` `submit_parse_job` | `strategy` 未做白名单校验，非法值要到切块阶段才报错（任务 failed 而非提交即 400） | 提交时校验 `strategy in STRATEGIES`，与 kind 校验对齐 |
| M3 | `frontend hooks/use-job.ts` | 组件卸载时轮询查询仍在后台 refetch（enabled 由 mutation data 驱动，页面切换后 query 未失效） | 页面卸载时调用 `job.reset()` 已部分缓解；可在 useEffect cleanup 中统一 reset |

### Minor（可选）

| # | 位置 | 问题 |
|---|---|---|
| m1 | `frontend lib/constants.ts` | `SUPPORTED_EXTENSIONS` 为后端镜像常量，后端新增格式需手动同步（已加注释说明） |
| m2 | `frontend app/(admin)/chunk-lab/page.tsx` | 对比模式采用按钮多选而非 Checkbox 语义，可访问性可再打磨 |
| m3 | `app/jobs.py` | TTL 清理协程异常仅 `continue`，未记录日志 |
| m4 | `tests/test_jobs.py` | 轮询用 sleep 0.1 忙等，量大时可换 event 驱动（当前测试量级可接受） |

## 对照计划验收结果

| 验收项 | 结果 |
|---|---|
| M0：四路由可达 + 导航高亮 + tsc 零错误 | ✅ |
| M1：TDD 红→绿、全量回归 36 passed、/health 不阻塞（<50ms）| ✅ |
| M2：仪表盘状态卡/能力矩阵/最近任务/离线横幅 | ✅ |
| M3：上传→Element 列表↔行号高亮联动、>5MB 异步分流 | ✅（代码完成 + 类型验证；浏览器交互待人工点验） |
| M4：4 策略切换缓存、指标条、对比模式 | ✅（同上） |
| M5：入库→检索→溯源徽章、kb 名称校验、最近 KB 记忆 | ✅（同上） |
| M6：README 前端章节、review.md、全链路 | ✅（本文件） |

## 遗留事项（移交后续迭代）

1. Stage 2 Celery + Redis 分布式任务（design.md §11.2）
2. PDF bbox 原位叠加渲染（pdf.js，design.md §4.2 Phase 2）
3. parent_child 父块信息展示（后端目前仅返回子块）
4. 暗色主题（当前固定亮色，遵循 design.md §8 MVP 决策）
