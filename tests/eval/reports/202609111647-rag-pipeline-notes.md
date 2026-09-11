# omni-rag-engine 检索层评估报告

> 生成时间：2026-09-11T16:48:13+08:00
>
> 本报告由 `tests/eval/run_eval.py` 自动生成，解读口径见 `eval-design.md` §4

## 1. 运行清单（Run Manifest）

```yaml
timestamp: 2026-09-11T16:48:13+08:00
base_url: http://in-process
mode: in-process (ASGITransport)
corpus: tests\eval\corpus\rag-pipeline-notes.md
corpus_lines: 151
golden: tests\eval\golden\rag-pipeline-notes.yaml
query_count: 20
strategies: sliding_window, header_aware
kb_prefix: eval202609111647
top_k: 5
store_type: chroma
embedding_provider: dashscope
embedding_class: DashScopeEmbeddings
embedding_dim: 1024
embedding_separation: 0.458
enable_cleaning: True
```

## 2. 前置门禁

- 嵌入引擎：`DashScopeEmbeddings`（1024 维，语义区分度 +0.4580，需 > +0.05）
- 服务健康：`{"status": "ok", "job_store": "memory", "object_store": "local"}`

## 3. 入库概况

| 策略 | 知识库 | 切片数 |
| --- | --- | --- |
| `sliding_window` | `eval202609111647__sliding_window` | 8 |
| `header_aware` | `eval202609111647__header_aware` | 20 |

## 4. 总览指标矩阵

| 策略 | Hit@k | recall | MRR@k | noise@k | 解读 |
| --- | --- | --- | --- | --- | --- |
| `sliding_window` | 1.000 | 0.957 | 0.847 | 0.750 | 块偏碎（命中多但噪声高）→ 考虑增大 chunk_size |
| `header_aware` | 1.000 | 1.000 | 0.829 | 0.770 | 块偏碎（命中多但噪声高）→ 考虑增大 chunk_size |

## 5. 按 query 类型分解

| 类型 | 条数 | `sliding_window` Hit@k | `header_aware` Hit@k | 预期占优 |
| --- | --- | --- | --- | --- |
| fact | 7 | 1.000 | 1.000 | `sliding_window` |
| summary | 4 | 1.000 | 1.000 | `header_aware` |
| table | 3 | 1.000 | 1.000 | `header_aware` |
| cross_section | 3 | 1.000 | 1.000 | `header_aware` |
| paraphrase | 3 | 1.000 | 1.000 | `（校准组）` |

## 6. 预期符合情况

| query | 类型 | 预期占优 | 实际最优 | 是否符合 |
| --- | --- | --- | --- | --- |
| q001 | fact | `sliding_window` | `sliding_window` | ✅ |
| q002 | fact | `sliding_window` | `sliding_window` | ✅ |
| q003 | fact | `sliding_window` | `sliding_window` | ✅ |
| q004 | fact | `sliding_window` | `sliding_window` | ✅ |
| q005 | fact | `sliding_window` | `sliding_window` | ✅ |
| q006 | fact | `sliding_window` | `header_aware` | ⚠️ |
| q007 | fact | `sliding_window` | `sliding_window` | ✅ |
| q008 | summary | `header_aware` | `sliding_window` | ⚠️ |
| q009 | summary | `header_aware` | `sliding_window` | ⚠️ |
| q010 | summary | `header_aware` | `sliding_window` | ⚠️ |
| q011 | summary | `header_aware` | `sliding_window` | ⚠️ |
| q012 | table | `header_aware` | `sliding_window` | ⚠️ |
| q013 | table | `header_aware` | `sliding_window` | ⚠️ |
| q014 | table | `header_aware` | `sliding_window` | ⚠️ |
| q015 | cross_section | `header_aware` | `sliding_window` | ⚠️ |
| q016 | cross_section | `header_aware` | `header_aware` | ✅ |
| q017 | cross_section | `header_aware` | `sliding_window` | ⚠️ |

预期符合率：**7/17**（预期仅供参考——与预期不符本身就是有价值的发现）

## 7. 逐条明细

> 小样本下必须看明细：哪条 query 在哪个策略失败，比均值更有信息量。

| query | 类型 | 问题 | `sliding_window` | `header_aware` |
| --- | --- | --- | --- | --- |
| q001 | fact | chunk_overlap 的默认值是多少 | ✅ #2 (噪声80%) | ✅ #2 (噪声80%) |
| q002 | fact | 判断两条文本重复时使用的海明距离阈值是多少 | ✅ #1 (噪声60%) | ✅ #1 (噪声60%) |
| q003 | fact | text-embedding-v3 这个嵌入模型的向量维度是多少 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q004 | fact | 那个不需要 API、可以在本地运行的嵌入模型是多少维 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q005 | fact | 默认检索返回条数是多少 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q006 | fact | 上下文嵌入配合重排序模型可以把检索失败率降低多少 | ✅ #2 (噪声80%) | ✅ #1 (噪声80%) |
| q007 | fact | 标题层级感知切块会在元数据中记录什么字段，格式是什么样 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q008 | summary | RAG 前处理在文档进入向量库之前，一共包含哪几个处理环节 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q009 | summary | 文档切块有哪些策略，各自分别适用什么类型的文档 | ✅ #1 (噪声80%) | ✅ #2 (噪声80%) |
| q010 | summary | 数据清洗管线里包含哪几类处理 | ✅ #1 (噪声60%) | ✅ #3 (噪声60%) |
| q011 | summary | 为什么向量检索需要建立索引，不建索引会有什么后果 | ✅ #1 (噪声60%) | ✅ #1 (噪声80%) |
| q012 | table | 三种切块策略在语义完整性和噪声风险上分别表现如何 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q013 | table | 环境变量表里都定义了哪些变量，各自默认值是多少 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q014 | table | 父子块策略的块粒度是怎么描述的 | ✅ #2 (噪声80%) | ✅ #2 (噪声80%) |
| q015 | cross_section | 清洗和切块的先后顺序是怎样的，脱敏为什么必须放在向量化之前 | ✅ #1 (噪声60%) | ✅ #1 (噪声60%) |
| q016 | cross_section | 评价一个切块策略好不好，应该关注哪些方面 | ✅ #5 (噪声80%) | ✅ #2 (噪声80%) |
| q017 | cross_section | 上下文前缀注入这种方法有什么代价 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |
| q018 | paraphrase | 怎么同时兼顾召回准确度和喂给模型的上下文完整度 | ✅ #4 (噪声80%) | ✅ #4 (噪声80%) |
| q019 | paraphrase | 块离开原文之后指代不明该怎么处理 | ✅ #1 (噪声60%) | ✅ #1 (噪声80%) |
| q020 | paraphrase | 怎样让表格里的数据在检索时也能被理解 | ✅ #1 (噪声80%) | ✅ #1 (噪声80%) |

## 9. 结论沉淀

- 把成立的结论写回 `design.md` 的决策记录，并勾选 `RAG_ROADMAP.md` §8.3。
- 小样本（N≈20）下差异 < 20% 视为噪声，不要据此下结论。
- `paraphrase` 组是校准组：若该组普遍失败，问题在 embedding 而非切块策略。
