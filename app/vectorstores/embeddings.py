import hashlib
import os
from typing import Any


class MockEmbeddings:
    """
    零依赖 Mock 降级向量引擎：
    基于文本 MD5 生成伪随机的指定维度 (默认 1536 维) 浮点数归一化向量，
    用于本地无 Key 或无网络环境下的极速测试。
    """

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        vec = []
        # 以 text 为 seed 生成确定性向量
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
        for i in range(self.dimension):
            # 伪随机浮点数范式
            val = ((seed + i * 10007) % 20003) / 10000.0 - 1.0
            vec.append(round(val, 6))
        return vec


class DashScopeEmbeddings:
    """阿里百炼 DashScope 高精度文本向量引擎 (默认 text-embedding-v3)"""

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or os.getenv(
            "DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3"
        )
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            return MockEmbeddings().embed_documents(texts)

        try:
            import dashscope

            dashscope.api_key = self.api_key
            resp = dashscope.TextEmbedding.call(
                model=self.model,
                input=texts,
                text_type="document",
            )
            if resp.status_code == 200:
                embeddings = [item["embedding"] for item in resp.output["embeddings"]]
                return embeddings
            else:
                print(
                    f"[Warning] DashScope TextEmbedding 异常: {resp.message}，降级使用 Mock 向量"
                )
                return MockEmbeddings().embed_documents(texts)
        except Exception as e:
            print(f"[Warning] DashScope Embeddings 调用失败 ({e})，降级使用 Mock 向量")
            return MockEmbeddings().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        res = self.embed_documents([text])
        return res[0] if res else []


class EmbeddingsFactory:
    """向量计算引擎工厂"""

    @classmethod
    def get_embeddings(cls, provider: str = "auto", **kwargs: Any) -> Any:
        provider = provider.lower()
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")

        if provider in ("dashscope", "qwen", "auto"):
            if dashscope_key:
                return DashScopeEmbeddings(**kwargs)
            elif provider in ("dashscope", "qwen"):
                print("[Warning] 未设置 DASHSCOPE_API_KEY，降级使用 Mock 向量引擎")
                return MockEmbeddings()

        return MockEmbeddings()
