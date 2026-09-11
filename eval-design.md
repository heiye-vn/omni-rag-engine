# omni-rag-engine 检索层评估方案设计（eval-design.md）

> **定位**：`RAG_ROADMAP.md` §8.3「RAG 质量自动化评估」的 **Phase 0 前置层**
> **方法**：retrieval-level eval（只评检索，不评生成），零 LLM 依赖
> **目的**：让 `/chunk-lab` 的策略对比从「结构指标」升级为「**召回质量结论**」，从而回答"哪种切块策略更好、为什么"

---

## 1. 问题定义：为什么现在的对比得不出结论

`/chunk-lab` 当前的指标是：切片总数 / 平均字符 / 最长 / 含 `header_path` 占比（`components/chunk/stats-bar.tsx`）。这些全是**结构指标**，无法回答"哪种策略召回更好"。

反例（说明结构指标会误导）：

| 策略 | 块数 | 平均块长 | 结构指标结论 | 真实召回情况 |
|---|---|---|---|---|
| `sliding_window` | 多 | 短 | 「块数多，覆盖全」 | 命中概率天然更高，但**噪声也更多** |
| `header_aware` | 少 | 长 | 「块数少，可能漏」 | 语义完整，**单块命中率更稳** |

若只看块数，会得出"`sliding_window` 最好"的错误结论——因为它把块切小了，命中是必然的，代价是噪声。

**因此本设计的核心原则是：召回（recall）与噪声（noise）必须成对解读，且判据必须是"期望答案是否被召回"，而不是"块长什么样"。**

---

## 2. 评估分层与本次边界

RAG 评估通常分四层，本次**只做 L2，轻量做 L1**：

| 层级 | 评什么 | 本次范围 | 理由 |
|---|---|---|---|
| L0 解析保真 | 解析是否丢内容 / 串行错乱 | ⬜ 不做 | 改为人工抽样核对（20 条足够） |
| **L1 切块结构** | 结构完整性：标题 / 表格是否被切断 | ✅ **轻量**（2 个指标） | 直接复用 `stats-bar` 已有能力 |
| **L2 检索质量** | Hit@k / recall@k / MRR / noise@k | ✅ **核心** | 前处理的所有决策都是 L2 的函数 |
| L3 生成质量 | Faithfulness / Answer Relevance | ❌ 不做 | 属 Phase 5，需 LLM judge，会引入噪声掩盖切块差异 |

**为什么必须先把 L2 做掉**：切块大小、重叠长度、是否父子块、是否注入上下文前缀——这些决策的优劣**只能由检索质量裁决**。L3 那一层（Ragas/TruLens）会引入 LLM 自身的不确定性，反而会把"切块策略带来的差异"淹没在噪声里。

---

## 3. 核心设计一：黄金集（Golden Set）

### 3.1 关键决策：标注「原文区间」，而不是标注「chunk_id」

这是整个方案最重要的一个设计取舍：

| 方案 | 问题 |
|---|---|
| ❌ 标注 `chunk_id` | chunk_id 随策略变化 → 4 种策略要维护 4 套标注 → 不可维护，且无法横向比较 |
| ✅ 标注**期望答案在原文中的区间**（用 `Location` 表达） | 与策略**无关**，一套标注评所有策略 |

判定规则：**召回 chunk 的 location 与标注区间有交集 → 命中**。

这一决策直接复用了项目已有的 `Location` 模型（`app/models.py`），切块时本就透传（AGENTS.md §3.2 已强制要求），且 `SlidingWindowChunker._build_chunk` 已把 `start_line` 取首、`end_line` 取末做了区间合并——**契约现成，无需改动**。

### 3.2 标注文件格式

路径：`tests/eval/golden/{名称}.yaml`（YAML 便于人工读写与 diff）

```yaml
meta:
  document: examples/test.md      # 被评文档（单文档，避免跨文档干扰）
  eval_target: chunking_strategy  # 本次要裁决的变量
  top_k: 5

queries:
  - id: q001
    query: "滑动窗口切块的默认重叠长度是多少"
    type: fact                    # fact | summary | table | paraphrase | cross_section
    answer_spans:
      - start_line: 42            # Markdown/TXT 用行号
        end_line: 44
    rationale: "答案落在单段落，考察基础召回粒度"

  - id: q002
    query: "有哪些切块策略，各自适用什么场景"
    type: summary
    answer_spans:
      - start_line: 30
      - end_line: 58
    rationale: "答案跨多段落，考察块能否覆盖完整语义"
```

不同文档类型用不同 `Location` 字段（按 AGENTS.md §3.2 的映射）：

| 文档类型 | 标注字段 | 命中判定 |
|---|---|---|
| Markdown / TXT / CSV | `start_line` / `end_line` | 区间相交 |
| PDF / PPTX | `page_number`（+ `bbox` 可选） | 页码相等（bbox 相交作为加分） |
| HTML / DOCX | `selector` | selector 前缀匹配 |
| 音视频 | `start_time` / `end_time` | 时间区间相交 |

### 3.3 query 类型覆盖表（**把"对比"变成"有假设的验证"**）

这是让评估产出**知识**而非仅仅数字的关键。每种类型都事先写明"预期哪种策略占优"，跑完对照预期：

| type | 考察什么 | 预期占优策略 | 若不符则说明 |
|---|---|---|---|
| `fact` | 单点事实召回粒度 | `sliding_window`（小块更易命中） | 小块确实更容易命中，符合预期 |
| `summary` | 跨段落语义完整性 | `parent_child` / `header_aware` | 大块保留了完整语义 |
| `table` | 表格是否被从中间切断 | `parent_child` / `header_aware` | 若表格型 query 大量失败 → 表格被切断 |
| `paraphrase` | embedding 的语义能力（**非 chunking**） | —— | 用于校准：若该组分数普遍低，问题在 embedding 而非切块 |
| `cross_section` | 章节边界的处理 | `header_aware` | 若大量失败 → 块跨越了章节边界 |

**规模**：20~30 条起步。小样本关键是**每类都要有**（分布合理），而非总量大。

---

## 4. 核心设计二：指标定义

设黄金集共 `N` 条 query，`E_q` 为 query `q` 的标注区间集合，`R_q` 为 top-k 召回结果集合。

| 指标 | 定义 | 作用 |
|---|---|---|
| **Hit@k**（主指标） | `命中 query 数 / N`，其中单条 query「命中」= `R_q` 中至少一个 chunk 与 `E_q` 相交 | 最直觉的「能不能找到」 |
| **recall@k**（多区间时） | `Σ 被覆盖的标注区间数 / Σ 标注区间总数` | 答案分散在多个位置时更准确 |
| **MRR@k** | `mean(1 / 首个命中 chunk 的排名)` | 衡量「是否排在前面」，重排/融合阶段的主指标 |
| **noise@k** | `top-k 中与任何标注区间都不相交的 chunk 数 / k` | **衡量"块太碎"**，是 Hit@k 的必要补充 |
| **平均块长**（辅助） | 解释噪声来源 | 无独立结论力，仅用于归因 |

### 4.1 解读矩阵（**本方案的核心洞察**）

必须把 Hit@k 与 noise@k 放在一起看，否则会误判：

| | noise 低（噪声少） | noise 高（噪声多） |
|---|---|---|
| **Hit 高** | ✅ **理想策略** | ⚠️ **块太碎**——命中是靠"块多"堆出来的，实际给 LLM 的上下文中噪声过大 → 应考虑增大 `chunk_size` |
| **Hit 低** | ⚠️ **块太大**——语义被稀释，关键信息淹没在长文本中 → 应减小 `chunk_size` 或改用 `header_aware` | ❌ **该换策略**——两指标同时劣化 |

### 4.2 L1 结构指标（轻量）

| 指标 | 口径 | 现状复用 |
|---|---|---|
| 标题完整性 | chunk 是否携带完整 `header_path` 且不以裸标题结尾 | `stats-bar.tsx` 已有「含 `header_path` 占比」 |
| 表格切断率 | 含 Markdown 表格的 chunk 中，表格行数不连续（被切断）的比例 | 需新增，抽样核对即可 |

### 4.3 结果解读的纪律（避免过度解读）

- **小样本（N≈20）下，差异 < 20% 视为噪声**，不要据此下结论。
- 报告必须**给逐条明细**（哪条 query 在哪个策略失败），不能只给均值——失败模式的分布才是真正有价值的信息。
- `paraphrase` 组分数普遍偏低时，**结论应指向 embedding 模型**，而不是切块策略（该组是校准组）。

---

## 5. 核心设计三：可比性硬约束

⚠️ **本节是全文最容易出错的地方。违反其中任何一条，整轮评估结果作废。**

| # | 约束 | 违反后果 |
|---|---|---|
| 1 | **严禁使用 `MockEmbeddings`**（`app/vectorstores/embeddings.py:6-27`） | 它是 MD5 生成的伪随机向量，**无语义**。用它评估得到的是随机数 → 结论完全无意义 |
| 2 | **锁定同一 embedding provider + 同一维度** | 项目已知冲突：`DashScopeEmbeddings` 为 1024/1536 维、`MockEmbeddings` 固定 1536 维。混用会导致相似度不可比 |
| 3 | 同一 `chunk_size` / `chunk_overlap` | 无法区分是策略差异还是参数差异 |
| 4 | 同一 `top_k`、同一 `store_type`、同一 `enable_cleaning` | 同上 |
| 5 | 记录 **run manifest** | 无 manifest 则结果不可复现 |

### 5.1 run manifest（每次评估必须落盘）

```yaml
run:
  timestamp: 2026-09-11T15:30:00+08:00
  git_commit: <commit hash>
  document: examples/test.md
  embedding_provider: dashscope
  embedding_model: text-embedding-v3
  embedding_dim: 1024              # 必须显式记录
  chunk_size: 512
  chunk_overlap: 64
  top_k: 5
  store_type: chroma
  enable_cleaning: true
```

### 5.2 前置门禁（**M0 必须先过，否则后面全是白做**）

| 检查项 | 命令 / 方法 | 不通过的后果 |
|---|---|---|
| 向量库依赖已装 | `uv sync --extra vectordb` | 默认 `uv sync` **不装** chromadb/faiss → 全部降级为本地 JSON 快照 |
| 真实 embedding 可用 | 确认 `.env` 中 `DASHSCOPE_API_KEY` 已配置 | 未配置 → `EmbeddingsFactory` 静默回退 `MockEmbeddings` |
| **断言非 mock** | 评估脚本启动时探测 provider，若为 mock 则**直接 fail 退出** | 防止"用假向量跑出结论"这个最大的坑 |
| 快照自检 | 跑一次 `search`，检查 `score` 分布是否合理（不应全为相同值或全为 0） | Mock 向量下分数分布异常 |

> **第 3 条是本方案唯一的强制断言。** 项目已有"禁止静默降级"的规范（AGENTS.md §3.4），此断言是该规范在评估场景的延伸。

---

## 6. 核心设计四：零代码改动的 A/B 执行流程

### 6.1 关键前提（已核实）

`POST /api/v1/knowledge-bases/{kb}/ingest` 的签名（`app/server.py:352-360`）已包含 `strategy` 参数：

```
kb, file, strategy=auto, store_type=chroma, provider=auto, enable_cleaning=true
```

因此**不需要修改任何一行代码**，靠 `kb 名分桶 + strategy 参数` 即可完成 4 种策略的隔离对比。

`kb` 名合法字符集为 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`（`app/server.py:143`），`eval__header_aware` 合法。

### 6.2 执行流程

```text
# 阶段一：按策略分桶入库（每策略一个独立 kb，零代码改动）
for s in sliding_window, header_aware, parent_child, auto:
    POST /api/v1/knowledge-bases/eval__{s}/ingest
      file=examples/test.md
      strategy={s}                # ← 策略在此注入，已支持
      provider=dashscope          # ← 必须非 mock
      store_type=chroma
      enable_cleaning=true

# 阶段二：同一批 query 分别检索
for q in golden.queries:
    for s in strategies:
        POST /api/v1/knowledge-bases/eval__{s}/search
          {"query": q.query, "k": 5, "provider": "dashscope", "store_type": "chroma"}
        → 用 q.answer_spans 判定命中，累加指标

# 阶段三：输出对比矩阵
```

### 6.3 注意事项

- **重复运行需先清库**：`ingest` 是增量写入，重复跑会重复入库 → 清 `./data/{kb}/` 目录，或每次用带时间戳的 kb 名。
- **脚本位置**：`tests/eval/`，**独立于 `app/`**，不污染服务代码，不进入 FastAPI 路由。
- **不使用 `/api/v1/jobs` 异步路径**：评估用文档应控制在 5MB 内，走同步端点更简单（异步会引入轮询逻辑的干扰）。

---

## 7. 实施步骤与验收标准

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M0 前置门禁** | 装 `vectordb` extra、配 DashScope Key、脚本内加 mock 断言 | 断言在 mock 状态下**能正确 fail**；真实 provider 下 `search` 返回的 score 分布合理（非全同值） |
| **M1 最小闭环** | 黄金集 20 条（单文档）+ Hit@5 + **仅跑 2 种策略**（`sliding_window` vs `header_aware`） | 产出**第一张对比表 + 一条可复述的结论**（例："在跨章节 query 上 header_aware 的 Hit@5 高 X 个百分点"） |
| **M2 完整矩阵** | 4 策略全跑 + MRR@k + noise@k + L1 结构指标 | 产出完整矩阵 + 按 query 类型的**分项结论**（对照 §3.3 的预期表，逐类说明是否符合预期） |
| **M3 参数敏感性** | `chunk_size` × `chunk_overlap` 扫描（如 256/512/1024 × 0/64/128） | 回答"**切多大合适**"——这是分块知识里最常被问、也最需要实测的问题 |

**M1 是最小可交付**：20 条标注 + 一个 30 行左右的打分脚本 + 2 种策略，就能产生第一个真实结论。后续 M2/M3 是扩展，不是前提。

---

## 8. 明确不做（避免过度设计）

| 不做 | 理由 |
|---|---|
| 引入 Ragas / TruLens / DeepEval | 属 L3 生成层评估，需 LLM judge，成本高且会掩盖切块差异 → 留给 Phase 5 |
| LLM-as-judge / Faithfulness / Answer Relevance | 同上 |
| 多文档混合入库 | 会引入跨文档干扰，混淆"策略差异"与"文档差异" |
| LLM 自动生成 query | 生成的 query 分布不真实（往往过于贴近原文措辞），人工标注虽慢但可信 |
| 自动评分与 CI 集成 | 先手工跑通、产出结论，稳定后再考虑自动化 |

---

## 9. 交付物与结论沉淀

| 交付物 | 路径 | 说明 |
|---|---|---|
| 黄金集 | `tests/eval/golden/*.yaml` | 按 §3.2 schema |
| 评估脚本 | `tests/eval/run_eval.py` | 独立于 `app/`；含 mock 断言 |
| 结果报告 | `tests/eval/reports/{date}-{commit}.md` | 含 run manifest + 对比矩阵 + **逐条明细** + 分项结论 |
| 结论回流 | `design.md` 决策记录 / `RAG_ROADMAP.md` §8.3 勾选 | **评估的价值在于沉淀结论**，不是跑出数字 |

**最重要的是最后一行**：评估跑完若不把结论写回设计文档，下次还会重复"凭印象选策略"。本方案的目标产出是**一条条可复述的结论**（如"对 Markdown 技术文档，`header_aware` 在跨章节 query 上显著优于 `sliding_window`，但噪声率更高"），而不是一堆数字。
