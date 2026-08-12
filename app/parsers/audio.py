import os
import tempfile
from pathlib import Path

import whisper

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class AudioParser(BaseParser):
    """音频文件解析器（基于 OpenAI Whisper 进行语音识别 ASR，支持时间戳定位）"""

    # 支持的音频格式
    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac"}

    def __init__(self, model_name: str = "base"):
        """
        初始化 Whisper 模型

        Args:
            model_name: Whisper 模型大小，可选 tiny/base/small/medium/large
        """
        self._model_name = model_name
        self._model = None  # 延迟加载

    def _get_model(self):
        """延迟加载 Whisper 模型（首次调用时加载，后续复用）"""
        if self._model is None:
            self._model = whisper.load_model(self._model_name)
        return self._model

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)
        model = self._get_model()

        # Whisper 转录（启用 word_timestamps 获取精确时间戳）
        result = model.transcribe(
            str(path.absolute()),
            language=None,  # 自动检测语言
            verbose=False,
        )

        elements: list[Element] = []
        full_text_parts: list[str] = []
        detected_language = result.get("language", "unknown")

        # 按 segment 逐段提取（每个 segment 约对应一句话或一个语音段落）
        for seg_idx, segment in enumerate(result.get("segments", [])):
            text = segment.get("text", "").strip()
            if not text:
                continue

            start_time = round(segment.get("start", 0.0), 2)
            end_time = round(segment.get("end", 0.0), 2)
            full_text_parts.append(text)

            elements.append(
                Element(
                    type="paragraph",
                    content=text,
                    raw_content=text,
                    location=Location(
                        start_time=start_time,
                        end_time=end_time,
                    ),
                    metadata={
                        "segment_id": seg_idx,
                        "start_time": start_time,
                        "end_time": end_time,
                    },
                )
            )

        # 计算总时长（秒）
        total_duration: float | None = None
        segments = result.get("segments", [])
        if segments:
            total_duration = round(segments[-1].get("end", 0.0), 2)

        return ParsedDocument(
            file_name=path.name,
            file_type="audio",
            raw_text="\n".join(full_text_parts),
            file_path=str(path.absolute()),
            metadata={
                "language": detected_language,
                "total_duration_seconds": total_duration,
                "whisper_model": self._model_name,
                "segments_count": len(elements),
            },
            elements=elements,
        )
