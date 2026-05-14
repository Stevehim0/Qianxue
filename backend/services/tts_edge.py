"""Edge TTS 后端实现."""

import asyncio
import io
import logging
from typing import AsyncGenerator, Optional

from .tts_backend import TTSBackend

logger = logging.getLogger(__name__)


class EdgeTTSBackend(TTSBackend):
    """Edge TTS 引擎（微软云端，免费）."""

    def __init__(self, default_voice: str, rate: str, volume: str, timeout: int = 30):
        self.default_voice = default_voice
        self.rate = rate
        self.volume = volume
        self.timeout = timeout

    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """完整合成，返回 MP3 bytes."""
        import edge_tts

        voice_name = voice or self.default_voice
        communicate = edge_tts.Communicate(text, voice_name, rate=self.rate, volume=self.volume)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        data = buffer.getvalue()
        if not data:
            raise RuntimeError("Edge TTS 生成了空音频")
        return data

    async def synthesize_stream(self, text: str, voice: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """流式合成，逐 MP3 chunk yield."""
        import edge_tts

        voice_name = voice or self.default_voice
        communicate = edge_tts.Communicate(text, voice_name, rate=self.rate, volume=self.volume)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk["data"]:
                yield chunk["data"]
