import json
import os
import sys


def inspect_local_chroma(persist_directory: str = "./chroma_db", collection_name: str = "omni_rag_collection"):
    """
    终端可视化检查小工具：
    优雅打印本地 Chroma / 快照向量库中的 Collection 记录数、文本内容与 Metadata 元数据。
    """
    print("=" * 70)
    print(f"  [Omni-RAG-Engine] 本地向量数据库可视化 inspect 终端面板")
    print("=" * 70)

    dump_path = os.path.join(persist_directory, f"{collection_name}.json")
    if not os.path.exists(dump_path):
        print(f"[提示] 未在 '{persist_directory}' 中发现快照文件 '{collection_name}.json'")
        print("建议先运行 ParsedDocument.to_vectorstore() 进行切片持久化落盘！")
        return

    with open(dump_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"数据快照路径: {dump_path}")
    print(f"存储集合名称: {collection_name}")
    print(f"总持久化切片数: {len(records)} 条\n")

    for idx, item in enumerate(records, 1):
        content = item.get("page_content", "")
        metadata = item.get("metadata", {})
        vector = item.get("vector", [])

        # 取文本前 80 字符作为预览
        preview_text = content.replace("\n", " ")[:80] + ("..." if len(content) > 80 else "")

        print(f"--- [切片 #{idx}] ---")
        print(f"  - 文本预览: {preview_text}")
        print(f"  - 元数据 (Metadata): {metadata}")
        print(f"  - 向量维度: {len(vector)} 维 (前 3 维: {vector[:3] if vector else []})\n")

    print("=" * 70)


if __name__ == "__main__":
    dir_path = sys.argv[1] if len(sys.argv) > 1 else "./chroma_db"
    coll_name = sys.argv[2] if len(sys.argv) > 2 else "omni_rag_collection"
    inspect_local_chroma(dir_path, coll_name)
