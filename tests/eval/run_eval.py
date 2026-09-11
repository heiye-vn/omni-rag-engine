#!/usr/bin/env python
"""
omni-rag-engine 检索层评估脚本（retrieval-level eval）

设计依据：eval-design.md §3~§6
定位：RAG_ROADMAP.md §8.3 的 Phase 0 前置层 —— 只评检索，不评生成，零 LLM 依赖。

核心思路：
  1. 黄金集标注的是「原文区间」（start_line / end_line），与切块策略无关；
  2. 靠 kb 名分桶（如 eval__header_aware）隔离不同策略，不需要改动任何服务端代码；
  3. 命中判定 = 召回 chunk 的 location 区间与标注区间有交集；
  4. 同时报告 Hit@k 与 noise@k —— 只看 Hit 会得出「块越小越好」的错误结论。

用法（在仓库根目录执行）：
    # 推荐：进程内模式，无需预先启动服务，不经过网络套接字
    uv run python tests/eval/run_eval.py --in-process

    # M1 最小闭环：只对比两种策略（默认即此配置）
    uv run python tests/eval/run_eval.py --in-process

    # 收紧召回以提升区分度（语料较短时 top_k 过大会导致 Hit@k 饱和）
    uv run python tests/eval/run_eval.py --in-process --top-k 3

    # 完整四策略
    uv run python tests/eval/run_eval.py --in-process \
        --strategies sliding_window,parent_child,header_aware,auto

    # 对已启动的 HTTP 服务评估（默认模式）
    uv run python tests/eval/run_eval.py --base-url http://localhost:8000

前置条件：
    - 依赖：uv sync --extra dashscope（缺 dashscope SDK 时嵌入会静默降级为 Mock 向量）
    - 已配置真实嵌入模型（.env 中 DASHSCOPE_API_KEY）
    - 脚本会以「语义自检」主动拦截 Mock 向量，防止用假向量得出结论；仅当确需验证链路时
      才使用 --allow-mock
    - 依赖 pyyaml（随项目传递依赖安装）。未安装时 `uv add pyyaml`
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 允许从仓库根目录直接执行
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows 控制台默认 GBK，显式切到 UTF-8 避免中文输出报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

try:
    import httpx
except ImportError:  # pragma: no cover
    print("[FAIL] 缺少 httpx（项目 dev 依赖组已包含，请用 `uv run python ...` 执行）")
    raise SystemExit(2)

try:
    import yaml
except ImportError:  # pragma: no cover
    print("[FAIL] 缺少 pyyaml，请执行：uv add pyyaml")
    raise SystemExit(2)


# --------------------------------------------------------------------------- #
#  配置
# --------------------------------------------------------------------------- #

DEFAULT_GOLDEN = "tests/eval/golden/rag-pipeline-notes.yaml"
DEFAULT_REPORT_DIR = "tests/eval/reports"
DEFAULT_STRATEGIES = "sliding_window,header_aware"  # M1 只跑这两种
DATA_ROOT = Path("./data")  # 与服务端 _default_store_kwargs 的落盘约定一致


# --------------------------------------------------------------------------- #
#  黄金集加载与校验
# --------------------------------------------------------------------------- #


def load_golden(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """加载黄金集，并做结构校验（行号合法性 / 区间方向 / id 唯一）"""
    if not path.exists():
        raise SystemExit(f"[FAIL] 黄金集不存在: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    meta = raw.get("meta", {})
    queries = raw.get("queries", [])
    if not queries:
        raise SystemExit("[FAIL] 黄金集没有任何 query")

    seen: set[str] = set()
    for q in queries:
        qid = q.get("id", "")
        if not qid or qid in seen:
            raise SystemExit(f"[FAIL] query id 缺失或重复: {qid!r}")
        seen.add(qid)

        spans = q.get("answer_spans") or []
        if not spans:
            raise SystemExit(f"[FAIL] {qid} 没有 answer_spans")
        for s in spans:
            if set(s.keys()) != {"start_line", "end_line"}:
                raise SystemExit(f"[FAIL] {qid} 的区间字段必须是 start_line/end_line: {s}")
            if int(s["start_line"]) > int(s["end_line"]):
                raise SystemExit(f"[FAIL] {qid} 区间方向错误: {s}")

    # 区间必须落在语料行数范围内，否则标注必然无法命中
    corpus_rel = meta.get("document")
    if corpus_rel:
        corpus_path = Path(corpus_rel)
        if corpus_path.exists():
            total = len(corpus_path.read_text(encoding="utf-8").splitlines())
            for q in queries:
                for s in q["answer_spans"]:
                    if int(s["end_line"]) > total:
                        raise SystemExit(
                            f"[FAIL] {q['id']} 标注行号 {s['end_line']} 超出语料总行数 {total}"
                        )
        else:
            print(f"[WARN] 黄金集声明的语料不存在: {corpus_path}")

    return meta, queries


# --------------------------------------------------------------------------- #
#  前置门禁：拦截 Mock 向量（本脚本最重要的一道防线）
# --------------------------------------------------------------------------- #


def _cosine(v1: list[float], v2: list[float]) -> float:
    """余弦相似度（自行实现，避免依赖向量库客户端）"""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return dot / (n1 * n2) if n1 and n2 else 0.0


def gate_embeddings(provider: str, allow_mock: bool) -> tuple[dict[str, Any], list[str]]:
    """
    在脚本进程内探测嵌入引擎的真实性，返回 (探测信息, 问题列表)。

    必须同时探测两条路径，缺一不可：
      - **单条路径**（embed_query）：检索时使用
      - **批量路径**（embed_documents）：入库时使用

    为什么不能只做 isinstance 检查：
      DashScopeEmbeddings 在调用失败时是「内部 catch 后返回 Mock 向量」，对象类型不变。
      缺 SDK、缺 Key、网络不通三种情况都无法靠类型判断识别。

    为什么必须单独测批量路径（实测教训）：
      DashScope 的 embedding 接口单次批量上限为 20 条。语料变长后单批入库很容易超过该限制，
      此时 embed_documents 返回 400 并在内部静默降级为 1536 维 Mock 向量，
      而 embed_query 仍是真实的 1024 维向量 —— 两者维度不一致导致相似度恒为 0，
      全部检索指标崩坏，且**只有一行 Warning 作为信号**。

    该门禁是 eval-design.md §5.2 的强制项，也是 AGENTS.md §3.4「禁止静默降级」的延伸。
    """
    try:
        from app.vectorstores.embeddings import EmbeddingsFactory, MockEmbeddings
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[FAIL] 无法导入嵌入模块，请确认从仓库根目录执行: {exc}") from exc

    engine = EmbeddingsFactory.get_embeddings(provider=provider)
    cls = type(engine).__name__
    problems: list[str] = []

    probe_a, probe_b, probe_c = "文档切块策略", "文档应该怎么切分", "红烧肉的家常做法"

    # 路径 1：单条查询
    vec_a = engine.embed_query(probe_a)
    dim_query = len(vec_a)
    sep_query = _cosine(vec_a, engine.embed_query(probe_b)) - _cosine(
        vec_a, engine.embed_query(probe_c)
    )

    # 路径 2：批量入库（刻意超过 20 条以触及供应商批量上限）
    filler = [f"批量探针填充文本第 {i} 段，用于触发供应商批量限制" for i in range(22)]
    batch = engine.embed_documents([probe_a, probe_b, *filler, probe_c])
    dim_batch = len(batch[0]) if batch else 0
    sep_batch = (
        _cosine(batch[0], batch[1]) - _cosine(batch[0], batch[-1]) if len(batch) >= 2 else 0.0
    )

    if isinstance(engine, MockEmbeddings):
        problems.append(f"引擎类型为 MockEmbeddings（provider={provider!r} 未取到真实引擎）")
    if sep_query <= 0.05:
        problems.append(f"单条路径无语义（区分度 {sep_query:+.4f}，需 > +0.05）")
    if dim_batch != dim_query:
        problems.append(
            f"批量路径维度 {dim_batch} 与单条路径 {dim_query} 不一致 —— "
            "入库时已静默降级为 Mock 向量（常见原因：超出供应商单批上限，如 DashScope 为 20 条）"
        )
    elif sep_batch <= 0.05:
        problems.append(f"批量路径无语义（区分度 {sep_batch:+.4f}，需 > +0.05）")

    info = {
        "class": cls,
        "dim_query": dim_query,
        "sep_query": round(sep_query, 4),
        "dim_batch": dim_batch,
        "sep_batch": round(sep_batch, 4),
        "batch_size": len(batch),
    }

    if problems:
        detail = (
            f"        单条路径：{dim_query} 维，语义区分度 {sep_query:+.4f}\n"
            f"        批量路径：{dim_batch} 维，语义区分度 {sep_batch:+.4f}（已提交 {len(batch)} 条）\n"
        )
        if allow_mock:
            print("[WARN] 嵌入引擎未通过门禁，但已指定 --allow-mock：")
            print(detail.rstrip())
            print("       本次结果无任何语义意义，仅可用于验证脚本链路！")
        else:
            raise SystemExit(
                "\n[FAIL] 嵌入引擎未通过门禁 —— 评估已中止。\n"
                f"       当前引擎：{cls}，provider={provider!r}\n"
                f"{detail}"
                "        检出问题：\n"
                + "".join(f"          - {p}\n" for p in problems)
                + "        排查方向：\n"
                "          1. 未安装 SDK ：uv sync --extra dashscope\n"
                "          2. 未配置密钥 ：在 .env 中设置 DASHSCOPE_API_KEY\n"
                "          3. 网络不通   ：确认可访问供应商 API\n"
                "          4. 超出批量上限：入库批次超过供应商限制（DashScope 为 20 条），\n"
                "             需在上游做分批提交 —— 这属于被评估引擎的缺陷，而非评测脚本问题\n"
                "        若向量无语义或维度不一致，Hit@k / MRR 均为随机数，结论无效。\n"
            )

    return info, problems


def build_client(args: argparse.Namespace) -> tuple[httpx.AsyncClient, str]:
    """
    构造 HTTP 客户端并返回 (client, base_url)。

    --in-process 模式通过 ASGITransport 直接调用 FastAPI 应用，不经过任何网络套接字：
      - 仍然完整走真实应用的路由、端点逻辑、解析、切块、嵌入与落盘链路；
      - 但无需预先启动 uvicorn，也不受本机网络环境影响，适合 CI 与受限环境。
    """
    if args.in_process:
        try:
            from app.server import app
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"[FAIL] 进程内模式导入 app.server 失败: {exc}") from exc
        transport = httpx.ASGITransport(app=app)
        return (
            httpx.AsyncClient(transport=transport, base_url="http://in-process", timeout=args.timeout),
            "http://in-process",
        )

    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    return (
        httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout, headers=headers),
        args.base_url,
    )


async def gate_server(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    """确认服务可访问，并回显健康信息"""
    try:
        resp = await client.get(f"{base_url}/health")
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"[FAIL] 无法访问引擎 {base_url}/health: {exc}\n"
            "       请先启动服务：uv run uvicorn app.server:app --reload --port 8000\n"
            "       或改用进程内模式：--in-process（无需启动服务）"
        ) from exc
    return resp.json()


# --------------------------------------------------------------------------- #
#  打分逻辑
# --------------------------------------------------------------------------- #


def chunk_interval(metadata: dict[str, Any]) -> tuple[int, int] | None:
    """
    从 chunk metadata 中取出行号区间。
    切块时 header_aware 等策略已把首元素 start_line 与末元素 end_line 合并写入 metadata
    （见 app/chunkers/sliding_window.py::_build_chunk），此处直接复用该契约。
    """
    start = metadata.get("start_line")
    if start is None:
        return None
    end = metadata.get("end_line")
    if end is None:
        end = start
    try:
        return int(start), int(end)
    except (TypeError, ValueError):
        return None


def intersects(chunk_span: tuple[int, int], gold_span: dict[str, Any]) -> bool:
    """区间相交判定（含端点）"""
    cs, ce = chunk_span
    gs, ge = int(gold_span["start_line"]), int(gold_span["end_line"])
    return cs <= ge and gs <= ce


def score_query(
    results: list[dict[str, Any]], gold_spans: list[dict[str, Any]]
) -> dict[str, Any]:
    """对单条 query 的一次检索结果打分"""
    hit_flags: list[bool] = []
    for item in results:
        span = chunk_interval(item.get("metadata") or {})
        hit_flags.append(bool(span and any(intersects(span, g) for g in gold_spans)))

    first_hit_rank = next((i + 1 for i, h in enumerate(hit_flags) if h), None)
    covered = sum(1 for g in gold_spans if any(hit_flags[i] for i in _ranks_matching(results, g)))

    return {
        "hit": first_hit_rank is not None,
        "first_hit_rank": first_hit_rank,
        "reciprocal_rank": (1.0 / first_hit_rank) if first_hit_rank else 0.0,
        "noise": (len(hit_flags) - sum(hit_flags)) / len(hit_flags) if hit_flags else 0.0,
        "returned": len(results),
        "spans_total": len(gold_spans),
        "spans_covered": covered,
    }


def _ranks_matching(results: list[dict[str, Any]], gold: dict[str, Any]) -> list[int]:
    """返回与指定标注区间相交的结果下标，用于多区间覆盖率统计"""
    idx: list[int] = []
    for i, item in enumerate(results):
        span = chunk_interval(item.get("metadata") or {})
        if span and intersects(span, gold):
            idx.append(i)
    return idx


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    """把逐 query 结果聚合成策略级指标"""
    n = len(rows)
    if n == 0:
        return {}
    spans_total = sum(r["spans_total"] for r in rows)
    spans_covered = sum(r["spans_covered"] for r in rows)
    return {
        "hit@k": sum(1 for r in rows if r["hit"]) / n,
        "recall": spans_covered / spans_total if spans_total else 0.0,
        "mrr": sum(r["reciprocal_rank"] for r in rows) / n,
        "noise@k": sum(r["noise"] for r in rows) / n,
    }


# --------------------------------------------------------------------------- #
#  HTTP 交互
# --------------------------------------------------------------------------- #


async def ingest(
    client: httpx.AsyncClient,
    base_url: str,
    kb: str,
    corpus: Path,
    strategy: str,
    store_type: str,
    provider: str,
) -> int:
    """调用入库端点，返回写入的切片数。strategy 由服务端端点原生支持，无需改代码。"""
    resp = await client.post(
        f"{base_url}/api/v1/knowledge-bases/{kb}/ingest",
        files={"file": (corpus.name, corpus.read_bytes(), "text/markdown")},
        data={
            "strategy": strategy,
            "store_type": store_type,
            "provider": provider,
            "enable_cleaning": "true",
        },
    )
    if resp.status_code >= 400:
        raise SystemExit(f"[FAIL] ingest 失败 ({kb}, {resp.status_code}): {resp.text[:400]}")
    return int(resp.json().get("chunk_count", 0))


async def search(
    client: httpx.AsyncClient,
    base_url: str,
    kb: str,
    query: str,
    top_k: int,
    store_type: str,
    provider: str,
) -> list[dict[str, Any]]:
    """调用检索端点，返回结果列表"""
    resp = await client.post(
        f"{base_url}/api/v1/knowledge-bases/{kb}/search",
        json={"query": query, "k": top_k, "store_type": store_type, "provider": provider},
    )
    if resp.status_code >= 400:
        raise SystemExit(f"[FAIL] search 失败 ({kb}, {resp.status_code}): {resp.text[:400]}")
    return resp.json().get("results", [])


# --------------------------------------------------------------------------- #
#  离线校验：黄金集标注是否真的可被切块覆盖（不依赖任何密钥与向量库）
# --------------------------------------------------------------------------- #


def run_validate(args: argparse.Namespace) -> int:
    """
    离线校验黄金集与语料的匹配性，**不需要任何 API Key、向量库或已启动的服务**。

    校验内容：每条 query 标注的原文区间，是否至少被某个切块结果覆盖。
    若某个区间没有被任何块覆盖，说明该标注落在被切块丢弃或错位的内容上，
    该 query 将永远无法命中 —— 属于标注错误，必须在跑评估前修掉。
    """
    try:
        from app.loaders.helper import load_batch
        from app.chunkers.auto import AutoChunker
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[FAIL] 导入解析或切块模块失败: {exc}") from exc

    meta, queries = load_golden(Path(args.golden))
    corpus = Path(meta.get("document", ""))
    if not corpus.exists():
        raise SystemExit(f"[FAIL] 语料不存在: {corpus}")

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]

    print("=" * 74)
    print("黄金集离线校验（不需要密钥 / 向量库 / 服务）")
    print("=" * 74)
    print(f"语料    : {corpus}  ({len(corpus.read_text(encoding='utf-8').splitlines())} 行)")
    print(f"黄金集  : {args.golden}  ({len(queries)} 条 query)")
    print(f"策略    : {', '.join(strategies)}")
    print("-" * 74)

    doc = load_batch(
        str(corpus), enable_cleaning=True, enable_describe_images=False
    ).documents[0]
    chunker = AutoChunker()

    intervals: dict[str, list[tuple[int, int]]] = {}
    for s in strategies:
        res = chunker.split_document(doc, strategy=s)
        docs = res[0] if isinstance(res, tuple) else res
        spans = []
        for d in docs:
            span = chunk_interval(d.metadata or {})
            if span:
                spans.append(span)
        intervals[s] = spans
        lens = sorted(len(d.page_content) for d in docs)
        tiny = sum(1 for d in docs if len(d.page_content) < 50)
        print(
            f"[{s}] 块数={len(docs):3}  有行号定位的块={len(spans):3}  "
            f"长度 min={lens[0] if lens else 0} 中位={lens[len(lens)//2] if lens else 0} "
            f"max={lens[-1] if lens else 0}  <50字符碎片块={tiny}"
        )

    print("-" * 74)
    rows, unreachable = [], []
    for q in queries:
        cells = []
        for s in strategies:
            spans = intervals[s]
            covered = sum(
                1
                for g in q["answer_spans"]
                if any(intersects(iv, g) for iv in spans)
            )
            cells.append(covered)
            if covered < len(q["answer_spans"]):
                unreachable.append((q["id"], s, covered, len(q["answer_spans"])))
        rows.append((q, cells))

    print(f"{'query':8}{'类型':16}" + "".join(f"{s[:16]:>18}" for s in strategies))
    for q, cells in rows:
        total = len(q["answer_spans"])
        marks = "".join(
            f"{('✅' if c == total else '⚠️') + f' {c}/{total}':>18}" for c in cells
        )
        print(f"{q['id']:8}{q.get('type','-'):16}{marks}")

    fully_ok = all(all(c == len(q["answer_spans"]) for c in cells) for q, cells in rows)
    print("-" * 74)
    if fully_ok:
        print("✅ 全部标注区间在所有策略下均可被覆盖 —— 黄金集与语料匹配良好。")
    else:
        print("⚠️ 存在无法被完全覆盖的标注，逐条如下：")
        for qid, s, c, t in unreachable:
            print(f"   - {qid} @ {s}: 仅覆盖 {c}/{t} 个区间")
    print()
    print("说明: 此处只校验「标注是否落在切块结果内」，不代表检索能否命中。")
    return 0


# --------------------------------------------------------------------------- #
#  结果解读
# --------------------------------------------------------------------------- #


def read_matrix(hit: float, noise: float) -> str:
    """按 eval-design.md §4.1 的解读矩阵给出结论"""
    hi_hit, hi_noise = hit >= 0.6, noise >= 0.5
    if hi_hit and not hi_noise:
        return "理想"
    if hi_hit and hi_noise:
        return "块偏碎（命中多但噪声高）→ 考虑增大 chunk_size"
    if not hi_hit and not hi_noise:
        return "块偏大（语义稀释）→ 考虑减小 chunk_size 或改用 header_aware"
    return "双指标劣化 → 建议更换策略"


def build_report(
    manifest: dict[str, Any],
    gates: dict[str, Any],
    ingest_info: dict[str, int],
    k_map: dict[str, int],
    queries: list[dict[str, Any]],
    detail: dict[str, list[dict[str, Any]]],
    strategies: list[str],
    warnings: list[str],
) -> str:
    """生成 markdown 报告：清单 + 总览矩阵 + 分类矩阵 + 逐条明细 + 结论"""
    lines: list[str] = []
    add = lines.append

    add("# omni-rag-engine 检索层评估报告")
    add("")
    add(f"> 生成时间：{manifest['timestamp']}")
    add(">")
    add("> 本报告由 `tests/eval/run_eval.py` 自动生成，解读口径见 `eval-design.md` §4")
    add("")

    # --- run manifest（可复现性必备） ---
    add("## 1. 运行清单（Run Manifest）")
    add("")
    add("```yaml")
    for k, v in manifest.items():
        add(f"{k}: {v}")
    add("```")
    add("")

    # --- 门禁结果 ---
    add("## 2. 前置门禁")
    add("")
    emb = gates["embedding"]
    add(f"- 引擎：`{emb['class']}`（provider={manifest['embedding_provider']}）")
    add(
        f"- 单条检索路径：{emb['dim_query']} 维，语义区分度 {emb['sep_query']:+.4f}（需 > +0.05）"
    )
    add(
        f"- 批量入库路径：{emb['dim_batch']} 维，语义区分度 {emb['sep_batch']:+.4f}"
        f"（探测时提交 {emb['batch_size']} 条文本）"
    )
    if gates["problems"]:
        add("")
        add("> ❌ **门禁检出问题（借助 `--allow-mock` 强行继续，以下所有指标不可用于任何判断）：**")
        for p in gates["problems"]:
            add(f"> - {p}")
    add(f"- 服务健康：`{json.dumps(gates['health'], ensure_ascii=False)}`")
    if gates["allow_mock"]:
        add(
            "- ⚠️ **已启用 `--allow-mock`，或嵌入引擎未通过门禁："
            "本次结果基于伪随机向量，无任何语义意义，仅可用于验证脚本链路。**"
        )
    add("")

    # --- 入库概况 ---
    add("## 3. 入库概况")
    add("")
    add("> `覆盖率` = k / 切片数。该值过高（如 > 40%）时 Hit@k 会趋于饱和，失去区分力。")
    add("")
    add("| 策略 | 知识库 | 切片数 | k | 覆盖率 |")
    add("| --- | --- | --- | --- | --- |")
    for s in strategies:
        kb = f"{manifest['kb_prefix']}__{s}"
        n = ingest_info.get(s, 0)
        k = k_map.get(s, 0)
        ratio = f"{k / n * 100:.1f}%" if n else "-"
        add(f"| `{s}` | `{kb}` | {n} | {k} | {ratio} |")
    add("")

    # --- 总览矩阵 ---
    add("## 4. 总览指标矩阵")
    add("")
    add("| 策略 | Hit@k | recall | MRR@k | noise@k | 解读 |")
    add("| --- | --- | --- | --- | --- | --- |")
    agg = {s: aggregate(detail[s]) for s in strategies}
    for s in strategies:
        a = agg[s]
        add(
            f"| `{s}` | {a['hit@k']:.3f} | {a['recall']:.3f} | {a['mrr']:.3f} "
            f"| {a['noise@k']:.3f} | {read_matrix(a['hit@k'], a['noise@k'])} |"
        )
    saturated_all = len(strategies) > 1 and all(agg[s]["hit@k"] >= 0.95 for s in strategies)
    if saturated_all:
        add("")
        add("> ⚠️ **Hit@k 已饱和（全部策略均为 1.000），本表无法区分策略优劣。**")
        add("> 饱和度通常源于 `top_k` 相对语料切片数过大 —— 此时应改看 MRR@k / noise@k，")
        add("> 并降低 `--top-k` 或加长语料后重跑，否则任何「某策略更优」的结论都不成立。")
    add("")

    # --- 按类型分解（把"对比"变成"有假设的验证"） ---
    add("## 5. 按 query 类型分解")
    add("")
    types = list(dict.fromkeys(q.get("type", "unknown") for q in queries))
    add("| 类型 | 条数 | " + " | ".join(f"`{s}` Hit@k" for s in strategies) + " | 预期占优 |")
    add("| --- | --- | " + " | ".join("---" for _ in strategies) + " | --- |")
    for t in types:
        rows = {s: [r for r in detail[s] if r["type"] == t] for s in strategies}
        cnt = len(rows[strategies[0]])
        cells = " | ".join(f"{aggregate(rows[s])['hit@k']:.3f}" for s in strategies)
        exp = next(
            (q.get("expected_advantage") or "（校准组）" for q in queries if q.get("type") == t),
            "-",
        )
        add(f"| {t} | {cnt} | {cells} | `{exp}` |")
    add("")

    # --- 预期符合情况 ---
    add("## 6. 预期符合情况")
    add("")
    add("| query | 类型 | 预期占优 | 实际最优 | 是否符合 |")
    add("| --- | --- | --- | --- | --- |")
    agree = total_exp = 0
    for q in queries:
        exp = q.get("expected_advantage")
        if not exp:
            continue
        total_exp += 1
        ranks = {s: next(r for r in detail[s] if r["qid"] == q["id"]) for s in strategies}
        best = min(
            (s for s in strategies if ranks[s]["hit"]),
            key=lambda s: ranks[s]["first_hit_rank"] or 9_999,
            default=None,
        )
        ok = best == exp
        agree += int(ok)
        add(
            f"| {q['id']} | {q.get('type')} | `{exp}` | "
            f"{f'`{best}`' if best else '未命中'} | {'✅' if ok else '⚠️'} |"
        )
    add("")
    add(f"预期符合率：**{agree}/{total_exp}**（预期仅供参考——与预期不符本身就是有价值的发现）")
    if saturated_all:
        add("")
        add("> ⚠️ 由于 Hit@k 已饱和，上表「实际最优」实际比较的是首个命中排名的细微差异")
        add("> （多为 #1 与 #2 之别），该差异落在噪声范围内（见 eval-design.md §4.3），")
        add("> 因此**本节结论不可用于选型判断**，仅可用于观察失败模式。")
    add("")

    # --- 逐条明细 ---
    add("## 7. 逐条明细")
    add("")
    add("> 小样本下必须看明细：哪条 query 在哪个策略失败，比均值更有信息量。")
    add("")
    add("| query | 类型 | 问题 | " + " | ".join(f"`{s}`" for s in strategies) + " |")
    add("| --- | --- | --- | " + " | ".join("---" for _ in strategies) + " |")
    for q in queries:
        cells = []
        for s in strategies:
            r = next(x for x in detail[s] if x["qid"] == q["id"])
            mark = f"✅ #{r['first_hit_rank']}" if r["hit"] else "❌"
            cells.append(f"{mark} (噪声{r['noise']:.0%})")
        add(f"| {q['id']} | {q.get('type')} | {q.get('query')} | " + " | ".join(cells) + " |")
    add("")

    # --- 警告 ---
    if warnings:
        add("## 8. 自动检查告警")
        add("")
        for w in warnings:
            add(f"- {w}")
        add("")

    add("## 9. 结论沉淀")
    add("")
    add("- 把成立的结论写回 `design.md` 的决策记录，并勾选 `RAG_ROADMAP.md` §8.3。")
    add("- 小样本（N≈20）下差异 < 20% 视为噪声，不要据此下结论。")
    add("- `paraphrase` 组是校准组：若该组普遍失败，问题在 embedding 而非切块策略。")
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  主流程
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="omni-rag-engine 检索层评估")
    p.add_argument("--base-url", default=os.getenv("OMNI_BASE_URL", "http://localhost:8000"))
    p.add_argument("--golden", default=DEFAULT_GOLDEN)
    p.add_argument("--provider", default="dashscope", help="嵌入引擎: dashscope / mock / auto")
    p.add_argument("--store-type", default="chroma")
    p.add_argument("--strategies", default=DEFAULT_STRATEGIES)
    p.add_argument("--top-k", type=int, default=0, help="0 表示取黄金集 meta.top_k")
    p.add_argument(
        "--k-ratio",
        type=float,
        default=0.0,
        help=(
            "按切片数归一化 k（如 0.2 表示 k = 切片数的 20%%）。0 表示使用固定 top-k。"
            "各策略切片数差异较大时建议启用，以消除『块切得越碎越易命中』的偏向"
        ),
    )
    p.add_argument("--k-min", type=int, default=3, help="归一化 k 的下限")
    p.add_argument("--kb-prefix", default="eval")
    p.add_argument("--run-id", default="", help="留空则按时间生成，避免重复入库")
    p.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--api-key", default=os.getenv("API_KEYS", "").split(",")[0].strip())
    p.add_argument("--allow-mock", action="store_true", help="仅验证链路，结论不可用")
    p.add_argument("--reset", action="store_true", help="评估前清理本次 kb 的落盘目录")
    p.add_argument(
        "--in-process",
        action="store_true",
        help="进程内 ASGI 调用：无需预先启动服务，不经过网络套接字（推荐用于 CI）",
    )
    p.add_argument(
        "--validate-golden",
        action="store_true",
        help="仅离线校验黄金集标注能否被切块覆盖（不需要密钥/向量库/服务）",
    )
    return p.parse_args()


async def run(args: argparse.Namespace) -> int:
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    golden_path = Path(args.golden)
    meta, queries = load_golden(golden_path)

    corpus_rel = meta.get("document")
    if not corpus_rel:
        raise SystemExit("[FAIL] 黄金集 meta 缺少 document 字段")
    corpus = Path(corpus_rel)
    if not corpus.exists():
        raise SystemExit(f"[FAIL] 语料不存在: {corpus}")

    top_k = args.top_k or int(meta.get("top_k", 5))
    run_id = args.run_id or datetime.now().strftime("%Y%m%d%H%M")
    kb_prefix = f"{args.kb_prefix}{run_id}"

    print("=" * 74)
    print("omni-rag-engine 检索层评估")
    print("=" * 74)
    print(f"语料      : {corpus}  ({len(corpus.read_text(encoding='utf-8').splitlines())} 行)")
    print(f"黄金集    : {golden_path}  ({len(queries)} 条 query)")
    print(f"策略      : {', '.join(strategies)}")
    print(f"kb 前缀   : {kb_prefix}  (top_k={top_k}, provider={args.provider})")
    print("-" * 74)

    # 门禁 1：探测嵌入引擎 —— 必须同时覆盖「单条检索路径」与「批量入库路径」
    emb_info, emb_problems = gate_embeddings(args.provider, args.allow_mock)
    print(
        f"[门禁] 嵌入引擎 {emb_info['class']} | "
        f"单条 {emb_info['dim_query']}维(区分度 {emb_info['sep_query']:+.4f}) | "
        f"批量 {emb_info['dim_batch']}维(区分度 {emb_info['sep_batch']:+.4f})"
    )
    if emb_problems:
        print(f"[门禁] 检出 {len(emb_problems)} 项问题: " + "; ".join(emb_problems))

    warnings: list[str] = []
    client, base_url = build_client(args)
    if args.in_process:
        print("[模式] 进程内 ASGI 调用（不经过网络套接字）")

    async with client:
        # 门禁 2：服务可达
        health = await gate_server(client, base_url)
        print(f"[门禁] 服务健康 {health}")

        # 可选清理落盘目录，避免重复入库
        if args.reset:
            for s in strategies:
                kb_dir = DATA_ROOT / f"{kb_prefix}__{s}"
                if kb_dir.exists() and kb_dir.name.startswith(args.kb_prefix):
                    shutil.rmtree(kb_dir)
                    print(f"[清理] 已删除 {kb_dir}")

        # 步骤 1：按策略分桶入库
        ingest_info: dict[str, int] = {}
        print("-" * 74)
        for s in strategies:
            kb = f"{kb_prefix}__{s}"
            count = await ingest(
                client, base_url, kb, corpus, s, args.store_type, args.provider
            )
            ingest_info[s] = count
            print(f"[入库] {s:<16} → kb={kb:<34} 切片数={count}")

        counts = set(ingest_info.values())
        if len(counts) == 1 and len(strategies) > 1:
            warnings.append(
                f"各策略切片数完全相同（{counts.pop()}），策略参数可能未生效，请检查该语料是否只有一个语义节点。"
            )

        # 按切片数归一化 k：消除"块切得越碎、命中概率天然越高"的偏向
        if args.k_ratio > 0:
            k_map = {
                s: max(args.k_min, round(args.k_ratio * ingest_info[s])) for s in strategies
            }
            print(
                "[k 归一化] "
                + ", ".join(f"{s}={k_map[s]}(/{ingest_info[s]}块)" for s in strategies)
            )
        else:
            k_map = {s: top_k for s in strategies}

        # 步骤 2：逐 query × 逐策略检索并打分
        print("-" * 74)
        detail: dict[str, list[dict[str, Any]]] = {s: [] for s in strategies}
        degenerate = 0
        for q in queries:
            for s in strategies:
                kb = f"{kb_prefix}__{s}"
                results = await search(
                    client, base_url, kb, q["query"], k_map[s], args.store_type, args.provider
                )
                sc = score_query(results, q["answer_spans"])
                sc.update({"qid": q["id"], "type": q.get("type", "unknown")})
                detail[s].append(sc)
                if len(results) == 0:
                    degenerate += 1

        if degenerate:
            warnings.append(f"有 {degenerate} 次检索返回空结果，可能入库未生效或 provider/dim 不一致。")

        # 向量退化检测：若所有噪声率完全相同，通常意味着相似度全部相等
        for s in strategies:
            noises = {round(r["noise"], 6) for r in detail[s]}
            if len(detail[s]) > 3 and len(noises) == 1:
                warnings.append(f"策略 `{s}` 的噪声率在所有 query 上完全一致，相似度可能退化为常量。")

        # 指标饱和检测：Hit@k 触顶时无法区分策略，属评测设计问题而非模型问题
        aggs = {s: aggregate(detail[s]) for s in strategies}
        saturated = [s for s in strategies if aggs[s]["hit@k"] >= 0.95]
        if len(saturated) == len(strategies) and len(strategies) > 1:
            warnings.append(
                "全部策略的 Hit@k 均已饱和（>=0.95），本次评估 **无法区分策略优劣**。"
                "常见原因是 k 相对语料切片数过大 —— k 覆盖了语料很大比例时，命中是必然的。"
                "建议降低 k、加长语料，或改以 MRR@k / noise@k 为主要判据。"
            )
        elif saturated:
            warnings.append(
                f"策略 {', '.join(f'`{s}`' for s in saturated)} 的 Hit@k 已饱和，跨策略比较不公平。"
            )

        # 切片数差异悬殊 → 固定 k 对不同策略的筛选强度不等价，属混淆变量
        counts_all = list(ingest_info.values())
        if (
            args.k_ratio <= 0
            and len(set(counts_all)) > 1
            and max(counts_all) >= 2 * min(counts_all)
        ):
            warnings.append(
                f"各策略切片数差异悬殊（{min(counts_all)} vs {max(counts_all)}），"
                f"固定 k={top_k} 对不同策略的筛选强度并不等价，跨策略比较需谨慎。"
                "建议启用 --k-ratio（如 0.2）按切片数归一化 k。"
            )

    # 步骤 3：汇总输出
    manifest = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": base_url,
        "mode": "in-process (ASGITransport)" if args.in_process else "http",
        "corpus": str(corpus),
        "corpus_lines": len(corpus.read_text(encoding="utf-8").splitlines()),
        "golden": str(golden_path),
        "query_count": len(queries),
        "strategies": ", ".join(strategies),
        "kb_prefix": kb_prefix,
        "top_k": top_k,
        "k_ratio": args.k_ratio,
        "k_by_strategy": ", ".join(f"{s}={k_map[s]}" for s in strategies),
        "store_type": args.store_type,
        "embedding_provider": args.provider,
        "embedding_class": emb_info["class"],
        "embedding_dim_query": emb_info["dim_query"],
        "embedding_separation_query": emb_info["sep_query"],
        "embedding_dim_batch": emb_info["dim_batch"],
        "embedding_separation_batch": emb_info["sep_batch"],
        "gate_problem_count": len(emb_problems),
        "enable_cleaning": True,
    }
    gates = {
        "embedding": emb_info,
        "problems": emb_problems,
        "health": health,
        "allow_mock": args.allow_mock,
    }

    print("=" * 74)
    print("总览指标")
    print("=" * 74)
    print(f"{'策略':<18}{'Hit@k':>9}{'recall':>10}{'MRR@k':>9}{'noise@k':>10}   解读")
    for s in strategies:
        a = aggregate(detail[s])
        print(
            f"{s:<18}{a['hit@k']:>9.3f}{a['recall']:>10.3f}{a['mrr']:>9.3f}"
            f"{a['noise@k']:>10.3f}   {read_matrix(a['hit@k'], a['noise@k'])}"
        )

    report = build_report(
        manifest, gates, ingest_info, k_map, queries, detail, strategies, warnings
    )
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}-{meta.get('name', 'eval')}.md"
    report_path.write_text(report, encoding="utf-8")

    print("-" * 74)
    for w in warnings:
        print(f"[告警] {w}")
    print(f"\n报告已写入: {report_path}")
    if args.allow_mock:
        print("⚠️ 本次使用 --allow-mock，结论不可用于任何选型判断。")
    return 0


def main() -> int:
    """同步入口：解析参数并驱动主流程"""
    args = parse_args()
    if args.validate_golden:
        return run_validate(args)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
