import json
import zipfile
from pathlib import Path

from app.loaders import ArchiveLoader, DirectoryLoader, load_batch


def test_loaders():
    print(">>> 1. 构造测试目录与文件 (sample_dir)...")
    sample_dir = Path("tests/sample_dir")
    sample_dir.mkdir(exist_ok=True)
    sub_dir = sample_dir / "sub"
    sub_dir.mkdir(exist_ok=True)

    # 写入测试文件
    (sample_dir / "doc1.txt").write_text("这是第一个测试文件内容", encoding="utf-8")
    (sub_dir / "doc2.json").write_text(json.dumps({"name": "张三", "age": 20}), encoding="utf-8")
    # 写入被排除的文件
    (sample_dir / ".git").mkdir(exist_ok=True)
    (sample_dir / ".git" / "dummy.txt").write_text("git ignore", encoding="utf-8")

    print(">>> 2. 测试 DirectoryLoader 目录递归扫描...")
    dir_loader = DirectoryLoader(directory_path=sample_dir, recursive=True)
    batch_res = dir_loader.load()

    assert len(batch_res.documents) == 2
    file_names = {doc.file_name for doc in batch_res.documents}
    assert "doc1.txt" in file_names
    assert "doc2.json" in file_names
    print("DirectoryLoader 测试成功！解析文件:", file_names)

    print(">>> 3. 测试 ArchiveLoader 压缩包解压与解析...")
    zip_path = Path("tests/sample_archive.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("zip_doc1.txt", "压缩包内部文档1内容")
        zf.writestr("folder/zip_doc2.txt", "压缩包嵌套子目录文档2内容")

    arch_loader = ArchiveLoader(archive_path=zip_path)
    arch_res = arch_loader.load()

    assert len(arch_res.documents) == 2
    zip_file_names = {doc.file_name for doc in arch_res.documents}
    assert "zip_doc1.txt" in zip_file_names
    assert "zip_doc2.txt" in zip_file_names
    print("ArchiveLoader 压缩包安全解压解析成功！")

    print(">>> 4. 测试 load_batch 智能分发与 LangChain Document 合并...")
    batch_zip = load_batch(zip_path)
    langchain_docs = batch_zip.to_langchain_documents()
    assert len(langchain_docs) >= 2
    print(f"load_batch 导出了 {len(langchain_docs)} 个 LangChain Document 节点")

    # 清理临时测试文件
    if (sample_dir / "doc1.txt").exists():
        (sample_dir / "doc1.txt").unlink()
    if (sub_dir / "doc2.json").exists():
        (sub_dir / "doc2.json").unlink()
    if (sample_dir / ".git" / "dummy.txt").exists():
        (sample_dir / ".git" / "dummy.txt").unlink()
    if (sample_dir / ".git").exists():
        (sample_dir / ".git").rmdir()
    if sub_dir.exists():
        sub_dir.rmdir()
    if sample_dir.exists():
        sample_dir.rmdir()
    if zip_path.exists():
        zip_path.unlink()

    print("\n[OK] 批量加载器与 ZIP 压缩包解析器全部测试成功通过！")


if __name__ == "__main__":
    test_loaders()
