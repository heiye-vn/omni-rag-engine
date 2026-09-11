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

---

## 10. M1 执行记录与发现（2026-09-11）

M1 已跑通并产出首份报告（`tests/eval/reports/`）。**结论是：评测装置本身还不足以裁决策略**——这本身就是有价值的产出。

### 10.1 交付物

| 文件 | 说明 |
| --- | --- |
| `tests/eval/corpus/rag-pipeline-notes.md` | 冻结评估语料（151 行 / 8895 字符），内容为 RAG 前处理知识，兼具学习材料作用 |
| `tests/eval/golden/rag-pipeline-notes.yaml` | 黄金集 20 条（fact 7 / summary 4 / table 3 / cross_section 3 / paraphrase 3），共 23 个标注区间 |
| `tests/eval/run_eval.py` | 评估脚本，含语义自检门禁、按策略分桶、四项指标、Markdown 报告 |
| `tests/eval/reports/*.md` | 运行报告（含 run manifest 与逐条明细） |

> 原计划的被评文档 `examples/test.md` 不可用：仅 41 行 / 702 字符，且内容是「一级标题」「无序列表项 1」这类格式占位符，无语义信息，任何策略都只切出 1~2 块，无法体现差异。故改为新建冻结语料。

### 10.2 门禁的实际价值：抓到了两次静默降级

设计中的「拦截 Mock 向量」门禁，在实际执行中被证明**必须用语义自检而非 `isinstance` 判断**：

| 现象 | `isinstance` 检查 | 语义自检 |
| --- | --- | --- |
| 缺 `dashscope` SDK（未装 `--extra dashscope`） | ✅ 误判通过（类名仍是 `DashScopeEmbeddings`） | ❌ 正确拦截（相近对 cos=-0.17 < 无关对 cos=0.87） |
| 维度特征 | 未检查 | 1536（降级）vs 1024（真实），可作辅助判据 |

原因：`DashScopeEmbeddings.embed_documents()` 在调用失败时是**内部 catch 后返回 Mock 向量**，对象类型不变。因此缺 SDK、缺 Key、网络不通三种情况都无法靠类型判断识别。脚本最终采用「语义区分度 > +0.05」作为门禁，实测真实引擎为 **+0.458**。

### 10.3 核心发现：Hit@k 饱和，指标无法区分策略

首次运行（`top_k=5`）结果：

| 策略 | 切片数 | Hit@5 | recall | MRR@5 | noise@5 |
| --- | --- | --- | --- | --- | --- |
| `sliding_window` | **8** | 1.000 | 0.957 | 0.847 | 0.750 |
| `header_aware` | **20** | 1.000 | 1.000 | 0.829 | 0.770 |

**两个策略的 Hit@5 双双触顶，全部 20 条 query 无一失败。** 根因是一个评测设计缺陷：

> **`top_k` 固定为 5，但两策略的切片数是 8 与 20。** 对 8 块的 `sliding_window` 而言，`top_k=5` 等于覆盖 62% 的语料，命中是必然的——**固定 `top_k` 对不同策略的筛选强度并不等价，这是一个混淆变量。**

收紧到 `--top-k 3` 后开始出现区分度，但仍未脱离饱和：

| 策略 | Hit@3 | recall | MRR@3 | noise@3 |
| --- | --- | --- | --- | --- |
| `sliding_window` | 0.900 | 0.870 | 0.825 | 0.617 |
| `header_aware` | 0.950 | 0.957 | 0.817 | 0.650 |

### 10.4 由此确立的三条修正（进入 M2）

1. **加长语料**至各策略切片数均 ≥ 30（当前 8895 字符 → 目标 25000 字符量级），使 `top_k` 成为真正的筛选器。
2. **按切片数归一化 k**（如 `k = max(3, round(0.2 × n_chunks))`），消除"块切得越碎越易命中"的偏向。
3. **报告在指标饱和时主动告警**（已实现），并明确标注 §6「预期符合情况」在饱和时**不可用于选型**——该节的"实际最优"实际比较的是 #1 与 #2 的排名差异，落在 §4.3 所述的噪声范围内。

### 10.5 附带发现（工程环境）

- 仓库 `.venv` 处于**残缺状态**：`paddleocr` / `whisper` / `docling` 等重依赖已装，但 `fastapi` / `uvicorn` / `slowapi` / `sqlalchemy` / `minio` 全部缺失。这意味着 README 中的 `uv run uvicorn app.server:app` 在同步依赖前**无法启动**。已通过 `uv sync --extra dashscope` 修复。
- `--in-process` 模式（ASGITransport）比 HTTP 模式更适合评估：无需预启动服务、不经过网络套接字、时序确定，可直接用于 CI。

---

## 11. M2 语料扩容与发现（2026-09-11）

目标是让语料体量足以支撑公平对比，并让语料**按结构覆盖矩阵**设计，而非单纯加长。

### 11.1 交付物

| 文件 | 说明 |
| --- | --- |
| `tests/eval/corpus/safety-dual-prevention-manual.md` | 新语料，11835 字符 / 454 行（双预防体系实施手册，含 64 个标题、6 张表格、2 个代码块） |
| `tests/eval/golden/safety-dual-prevention-manual.yaml` | 新黄金集 28 条（fact 9 / summary 5 / table 5 / cross_section 5 / paraphrase 4），38 个区间，其中 10 条为多区间 |
| `run_eval.py::run_validate()` | **新增离线校验模式** `--validate-golden`：不依赖密钥/向量库/服务，校验每个标注区间能否被切块覆盖 |
| `run_eval.py --k-ratio` | **新增 k 归一化**：按切片数比例设定各策略的 k，消除"块越碎越易命中"的偏向 |

M1 语料只有 **3373 字符**（`8895` 是字节数，中文 3 字节/字 —— 这是 M1 规模估算出错的原因），导致 `sliding_window` 仅 8 块、`top_k=5` 覆盖 62% 语料。M2 语料后的实测：

| 策略 | 块数 | k=5 覆盖率 | 备注 |
| --- | --- | --- | --- |
| `sliding_window` | 26 | **19.2%** | 由 62% 降至 19.2%，k 成为真正的筛选器 |
| `header_aware` | 64 | 7.8% | 含 12 个 <50 字符碎片块（见 11.3） |
| `parent_child` | 58 | 8.6% | 含 2 个碎片块 |

### 11.2 结构覆盖矩阵

语料按以下矩阵刻意设计，每条 query 在黄金集中用 `coverage_intent` 字段标注其考察意图：

| 结构场景 | 设计落点 | 能暴露什么 |
| --- | --- | --- |
| `long_table` | 职责分工表（9 行）、风险等级表、速查表、字段模板表 | 表格被从中间切断 |
| `table_after_head` | 表格紧跟标题、无过渡段落 | 表头是否与数据行同块 |
| `heading_depth` | 3.3.1 / 3.3.2 四级标题 | 标题感知切块的层级处理 |
| `cross_ref` | 4.5↔4.6、9.1↔9.4、4.4↔4.7、7.1↔7.2 | 块跨越章节边界 |
| `short_section` | 8.1（极短小节） | 是否产生碎片块 |
| `code_block` | 5.5 的 YAML 配置与 curl 命令 | 代码块是否被截断 |
| `multi_mention` / `faq_echo` | 延期次数、培训档案期限在正文与附录 C 各出现一次 | 需用 recall 而非仅 Hit 才能体现 |

### 11.3 发现一：`HeaderAwareChunker` 产生 12 个碎片块

**现象**：每个 `## 章标题` 被单独切成一个只含标题文本的块（6~11 字符）。根因是章标题后紧跟 `### 子标题`、中间没有正文段落，于是章标题自成一块。64 个块中有 **12 个 <50 字符**。

**后果**：这些碎片会被向量化入库，成为语义极弱的必然噪声（却可能匹配到「第二章 组织机构与职责」这类 query），直接推高 `noise@k`。

**验证**：实测确认了 §1.3 早已写下的风险 —— "标题层级过深或小节过短时，会产生大量极小的块，此时应设置最小块长度阈值并与相邻块合并"。修复方向即该条：加最小块长度阈值并与相邻块合并。

### 11.4 发现二（严重）：批量入库静默降级为假向量

**现象**：语料变长后，ingest 阶段打印

```
[Warning] DashScope TextEmbedding 异常: <400> InternalError.Algo.InvalidParameter:
Value error, batch size is invalid, it should not be larger than 20.: input.contents，降级使用 Mock 向量
```

**根因链条**：

1. `DashScopeEmbeddings.embed_documents()` 把**整批切片一次性提交**（`app/vectorstores/embeddings.py`）；
2. DashScope 单次批量上限为 **20 条**，超过即返回 400；
3. 该方法是内部 `except` 后返回 `MockEmbeddings` 结果，**对象类型不变、只有一行 Warning**；
4. 于是**入库向量是 1536 维假向量，而查询向量（`embed_query` 单条）仍是 1024 维真向量**；
5. `_cosine_similarity` 在维度不等时返回 0.0 → 全部相似度恒为 0；
6. 实测指标：`sliding_window` Hit@k=0.107，`header_aware` Hit@k=0.000 且噪声率在所有 query 上完全一致（1.000）。

**严重性**：这是**生产级缺陷**，不是评测脚本问题。任何超过 20 个切片的文档入库后，检索都会完全失效，且**不抛异常、不中断服务**。M1 语料只有 8~20 块恰好未触发，属侥幸。

**门禁的第二次加固**：M1 的语义自检只探测了 `embed_query`（单条），因此**放行了这个批量路径已损坏的引擎**。现已改为**两条路径分别探测**并比对维度：

```
单条检索路径：1024 维，语义区分度 +0.4579
批量入库路径：1536 维，语义区分度 -1.0387（提交 25 条）
→ 维度不一致，判定为入库静默降级，评估中止
```

### 11.5 当前状态与阻塞项

- ✅ 语料与黄金集已通过 `--validate-golden` 离线校验：28 条 query 的 38 个标注区间在两种策略下**全部可覆盖**，无标注错位。
- ⛔ **真实评估被 11.4 的批量上限缺陷阻塞**。在 `app/vectorstores/embeddings.py` 的 `embed_documents()` 中按 ≤20 分批提交之前，M2 无法产出可用的策略对比结论。
- 该缺陷同时暴露了一条通用原则：**门禁必须覆盖被测对象的全部调用路径**（本例中即"单条"与"批量"两条），只测一条会漏掉另一条上的静默降级。

