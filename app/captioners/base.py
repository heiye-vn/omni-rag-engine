from abc import ABC, abstractmethod
from pathlib import Path


class BaseCaptioner(ABC):
    """多模态视觉大模型图片描述器抽象基类"""

    @abstractmethod
    def describe_image(self, image_input: str | bytes | Path, prompt: str | None = None) -> str:
        """
        对给定的图片输入生成自然语言上下文描述

        Args:
            image_input: 图片路径 (str/Path) 或图片二进制字节流 (bytes) 或图片 base64
            prompt: 自定义提示词，若为 None 则使用默认的图文描述 Prompt

        Returns:
            生成的图片自然语言描述文本
        """
        pass
