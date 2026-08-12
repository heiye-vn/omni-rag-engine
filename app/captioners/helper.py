import os
from typing import Any

from app.models import ParsedDocument
from .base import BaseCaptioner
from .dashscope_vlm import DashScopeCaptioner
from .mock_vlm import MockCaptioner
from .ollama_vlm import OllamaCaptioner
from .openai_vlm import OpenAICaptioner


class ImageCaptioner:
    """
    图片多模态描述统一适配工厂
    """

    @classmethod
    def get_captioner(
        cls,
        provider: str = "auto",
        api_key: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> BaseCaptioner:
        """
        根据供应商选择或环境变量实例化图片描述器

        Args:
            provider: 供应商模式 ("auto", "dashscope", "openai", "ollama", "mock")
            api_key: API 密钥 (若为 None 则尝试从环境变量读取)
            model: 模型名称
            **kwargs: 传给特定 Captioner 的选填参数

        Returns:
            BaseCaptioner 实例
        """
        p = provider.lower()

        if p == "dashscope":
            return DashScopeCaptioner(api_key=api_key, model=model or "qwen-vl-max", **kwargs)
        elif p == "openai":
            return OpenAICaptioner(api_key=api_key, model=model or "gpt-4o-mini", **kwargs)
        elif p == "ollama":
            return OllamaCaptioner(model=model or "llava", **kwargs)
        elif p == "mock":
            return MockCaptioner()
        elif p == "auto":
            # 自动探测环境变量中的配置
            if api_key or os.getenv("DASHSCOPE_API_KEY"):
                return DashScopeCaptioner(api_key=api_key, model=model, **kwargs)
            elif os.getenv("OPENAI_API_KEY"):
                return OpenAICaptioner(api_key=api_key, model=model, **kwargs)
            else:
                # 零配置安全降级
                return MockCaptioner()

        raise ValueError(f"不受支持的 Captioner provider: '{provider}'")


def describe_document_images(
    doc: ParsedDocument,
    captioner: BaseCaptioner | None = None,
    provider: str = "auto",
    **kwargs: Any,
) -> ParsedDocument:
    """
    遍历 ParsedDocument 中的所有 type="image" 图片节点，
    使用多模态大模型为图片生成自然语言描述并更新到 element.content 中。

    Args:
        doc: 原始 ParsedDocument 对象
        captioner: 自定义的 BaseCaptioner 实例；若为 None 则通过 ImageCaptioner 工厂实例化
        provider: 当 captioner 为 None 时调用的供应商名称 ("auto", "dashscope", "openai", "ollama", "mock")

    Returns:
        包含更新后图片描述的 ParsedDocument 实例
    """
    if captioner is None:
        captioner = ImageCaptioner.get_captioner(provider=provider, **kwargs)

    for elem in doc.elements:
        if elem.type == "image":
            # 优先从 elem.metadata['file_path'] 或 elem.content 中提取可用路径
            img_target = elem.metadata.get("file_path") or elem.metadata.get("src") or doc.file_path

            if img_target:
                try:
                    caption = captioner.describe_image(img_target)
                    elem.content = caption
                    elem.metadata["caption_generated"] = True
                except Exception as e:
                    # 遭遇报错时安全回退降级为 Mock 说明
                    fallback = MockCaptioner().describe_image(img_target)
                    elem.content = f"{fallback} (Error: {e})"
                    elem.metadata["caption_generated"] = False

    return doc
