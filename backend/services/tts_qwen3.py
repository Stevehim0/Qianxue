"""Qwen3-TTS 后端 — 调用本地 Qwen3-TTS OpenAI 兼容 API."""

import logging
from typing import AsyncGenerator, Optional

import httpx

from .tts_backend import TTSBackend

logger = logging.getLogger(__name__)


class Qwen3TTSBackend(TTSBackend):
    """Qwen3-TTS 本地引擎（OpenAI 兼容 API，~97ms TTFB，流式 PCM）."""

    def __init__(self, api_url: str, model: str = "tts-1-zh",
                 voice: str = "Serena", timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0))

    async def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """完整合成，返回 WAV bytes."""
        payload = {
            "model": self.model,
            "voice": voice or self.voice,
            "input": text,
            "response_format": "wav",
        }
        resp = await self._client.post(f"{self.api_url}/v1/audio/speech", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Qwen3-TTS HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.content

    async def synthesize_stream(self, text: str, voice: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """流式合成，yield 24kHz 16-bit mono PCM chunks."""
        payload = {
            "model": self.model,
            "voice": voice or self.voice,
            "input": text,
            "response_format": "pcm",
            "stream": True,
        }
        async with self._client.stream(
            "POST", f"{self.api_url}/v1/audio/speech", json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(f"Qwen3-TTS HTTP {resp.status_code}: {body[:200]}")
            async for chunk in resp.aiter_bytes(chunk_size=2400):
                if chunk:
                    yield chunk

    async def synthesize_stream_pcm(self, text: str, voice: Optional[str] = None) -> AsyncGenerator[bytes, None]:
        """流式合成，yield 原始 PCM chunks — 覆盖基类默认实现，走真流式."""
        async for chunk in self.synthesize_stream(text, voice):
            yield chunk

    async def health_check(self) -> bool:
        """检查 Qwen3-TTS 服务是否可用."""
        try:
            resp = await self._client.get(f"{self.api_url}/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False
