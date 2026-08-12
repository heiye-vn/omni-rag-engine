"""
文档解析器入口：自动根据输入路径（单文件 / 文件夹 / ZIP 压缩包）选择解析器，并将结果批量适配转换为 LangChain Document 列表
"""

import sys
from pathlib import Path
from typing import Any

# 将项目根目录加入 sys.path，确保直接运行该脚本或从任意目录调用时均能正确导入 app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.loaders import load_batch


def parse_to_langchain_docs(target_path: str, enable_cleaning: bool = True, **kwargs) -> list[Any]:
    """
    通用解析函数：自动识别目标路径类型（单文件 / 文件夹 / ZIP 压缩包），批量解析并转换为 LangChain Document 列表
    """
    batch_result = load_batch(target_path, enable_cleaning=enable_cleaning, **kwargs)
    return batch_result.to_langchain_documents()


def parse_and_chunk_to_langchain_docs(
    target_path: str,
    strategy: str = "auto",
    enable_cleaning: bool = True,
    **kwargs: Any,
) -> list[Any]:
    """
    端到端通用函数：自动解析 ➔ 数据清洗 ➔ 智能切块 (Auto/Parent-Child/SlidingWindow/HeaderAware) ➔ 导出 LangChain Document 列表

    Args:
        target_path: 目标路径 (单文件、目录或 ZIP 压缩包)
        strategy: 切片策略，可选 'auto', 'sliding_window', 'parent_child', 'header_aware'
        enable_cleaning: 是否开启数据清洗管道

    Returns:
        包含切块后 page_content 与完整 metadata 的 LangChain Document 对象列表
    """
    from app.chunkers import AutoChunker

    batch_result = load_batch(target_path, enable_cleaning=enable_cleaning, **kwargs)
    chunker = AutoChunker()

    all_chunk_docs = []
    for doc in batch_result.documents:
        res = chunker.split_document(doc, strategy=strategy)
        if isinstance(res, tuple):
            child_docs, _ = res  # Parent-Child 策略返回 (child_docs, parent_store)
            all_chunk_docs.extend(child_docs)
        else:
            all_chunk_docs.extend(res)

    return all_chunk_docs


def main():
    # 优先从命令行参数读取文件/文件夹/ZIP 路径 (如: uv run app/main.py examples/)
    if len(sys.argv) > 1:
        sample_path = sys.argv[1]
    else:
        sample_path = "examples/"
        if not Path(sample_path).exists():
            sample_path = "tests/sample.txt"

    print(f"============================================================")
    print(f" 正在加载与解析路径: {sample_path}")
    print(f"============================================================")

    # 1. 批量加载解析文件并直接适配为 LangChain Document 列表
    langchain_docs = parse_to_langchain_docs(sample_path)

    print(
        f"\n[OK] 解析成功！共聚合并转换为 {len(langchain_docs)} 个 LangChain Document 节点:\n"
    )

    # 2. 遍历打印转化后的前 5 个 LangChain Document 对象结构
    preview_limit = 5
    for i, doc in enumerate(langchain_docs[:preview_limit], 1):
        print(f"--- [LangChain Document #{i}] ---")
        content_preview = (
            doc.page_content[:100] + "..."
            if len(doc.page_content) > 100
            else doc.page_content
        )
        print(f"page_content: {content_preview!r}")
        print(f"metadata: {doc.metadata}\n")

    if len(langchain_docs) > preview_limit:
        print(f"... 剩余 {len(langchain_docs) - preview_limit} 个节点已省略打印。")


if __name__ == "__main__":
    main()
