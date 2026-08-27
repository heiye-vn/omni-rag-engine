import os
import tempfile
from pathlib import Path

import ffmpeg
import whisper

from app.models import Element, Location, ParsedDocument
from .base import BaseParser


class VideoParser(BaseParser):
    """视频文件解析器（使用 FFmpeg 提取音轨 + Whisper ASR 语音转文字，支持时间戳定位）"""

    # 支持的视频格式
    SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

    def __init__(self, model_name: str = "base"):
        """
        初始化 Whisper 模型

        Args:
            model_name: Whisper 模型大小，可选 tiny/base/small/medium/large
        """
        self._model_name = model_name
        self._model = None

    def _get_model(self):
        """延迟加载 Whisper 模型"""
        if self._model is None:
            self._model = whisper.load_model(self._model_name)
        return self._model

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)

        # 1. 使用 FFmpeg 获取视频元信息
        video_metadata = self._get_video_metadata(str(path.absolute()))

        # 2. 使用 FFmpeg 从视频中提取音频轨到临时 WAV 文件
        temp_audio_path = self._extract_audio(str(path.absolute()))

        elements: list[Element] = []
        full_text_parts: list[str] = []
        detected_language = "unknown"

        try:
            # 3. 使用 Whisper 对音频进行 ASR 转录
            model = self._get_model()
            result = model.transcribe(
                temp_audio_path,
                language=None,
                verbose=False,
            )

            detected_language = result.get("language", "unknown")

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
        finally:
            # 清理临时音频文件
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)

        doc_metadata = {
            "language": detected_language,
            "whisper_model": self._model_name,
            "segments_count": len(elements),
        }
        doc_metadata.update(video_metadata)

        return ParsedDocument(
            file_name=path.name,
            file_type="video",
            raw_text="\n".join(full_text_parts),
            file_path=str(path.absolute()),
            metadata=doc_metadata,
            elements=elements,
        )

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_audio(video_path: str) -> str:
        """使用 FFmpeg 从视频中提取音频轨为临时 WAV 文件，返回临时文件路径"""
        temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)

        try:
            (
                ffmpeg
                .input(video_path)
                .output(temp_path, acodec="pcm_s16le", ac=1, ar="16000")
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as e:
            # 清理失败的临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise RuntimeError(f"FFmpeg 音频提取失败: {e.stderr}") from e

        return temp_path

    @staticmethod
    def _get_video_metadata(video_path: str) -> dict:
        """使用 FFmpeg probe 获取视频的基础元信息"""
        metadata: dict = {}
        try:
            probe = ffmpeg.probe(video_path)

            # 视频流信息
            video_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
            if video_streams:
                vs = video_streams[0]
                metadata["video_width"] = vs.get("width")
                metadata["video_height"] = vs.get("height")
                metadata["video_codec"] = vs.get("codec_name")
                # 帧率
                r_frame_rate = vs.get("r_frame_rate", "0/1")
                if "/" in str(r_frame_rate):
                    num, den = r_frame_rate.split("/")
                    metadata["fps"] = round(int(num) / max(int(den), 1), 2)

            # 时长
            duration = probe.get("format", {}).get("duration")
            if duration:
                metadata["total_duration_seconds"] = round(float(duration), 2)

            # 音频流信息
            audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
            if audio_streams:
                metadata["audio_codec"] = audio_streams[0].get("codec_name")

        except Exception:
            pass

        return metadata
