"""TTS 后端抽象基类."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class TTSBackend(ABC):
    """TTS 引擎抽象接口，所有 TTS 实现继承此类."""

    @abstractmethod
    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """完整合成，返回音频 bytes."""

    @abstractmethod
    async def synthesize_stream(self, text: str, voice: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """流式合成，逐 chunk yield 音频 bytes."""

    async def synthesize_stream_pcm(self, text: str, voice: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """流式合成，yield 原始 PCM chunks（24kHz 16-bit mono LE）.

        默认实现：调 synthesize() 返回完整音频作为单个 chunk。
        支持原生流式的后端（Qwen3-TTS）应覆盖此方法。
        """
        audio = await self.synthesize(text, voice)
        yield audio
