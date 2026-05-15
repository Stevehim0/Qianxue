"""统一语音管理器 — 所有语音相关功能的唯一入口.

职责：
- STT（语音识别）：SenseVoice 离线 / FunASR 2pass
- TTS（语音合成）：委托给 VoiceService
- Discord 语音频道：委托给 VoicePlayer
- 电脑前端全双工语音会话管理
- 打断控制
"""

import asyncio
import logging
import time
from typing import Optional

from backend.config.loader import settings

logger = logging.getLogger(__name__)


class VoiceError(Exception):
    pass


class VoiceManager:
    """统一语音管理器."""

    def __init__(self):
        import httpx
        from backend.services.voice_service import voice_service
        from backend.services.voice_player import voice_player

        self.service = voice_service
        self.player = voice_player

        # 持久 HTTP 客户端（复用 TCP 连接，省掉 ~250ms 握手）
        self._stt_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0))

        # 电脑前端全双工语音会话
        self._computer_audio_buffer: bytearray = bytearray()
        self._computer_voice_active: bool = False
        self._stt_backend: str = settings.voice.stt_backend

    # ------------------------------------------------------------------
    # STT：语音识别
    # ------------------------------------------------------------------

    async def transcribe(self, pcm_16k: bytes) -> str:
        """转写完整音频段（16kHz mono 16-bit PCM）.

        根据 stt_backend 配置自动选择引擎：
        - sensevoice: 离线推理，~50ms 处理 3s 音频
        - funasr: 2pass 流式（回退）
        """
        t0 = time.monotonic()
        if self._stt_backend == "sensevoice":
            text = await self._transcribe_sensevoice(pcm_16k)
        else:
            text = await self.service.transcribe(pcm_16k)
        dt = int((time.monotonic() - t0) * 1000)
        audio_ms = len(pcm_16k) // 32  # 16kHz mono 16-bit: 2 bytes/sample, 1000 samples/s → len/32 ≈ ms
        logger.info(f"[STT_PERF] engine={self._stt_backend} audio={audio_ms}ms infer={dt}ms")
        return text

    async def _transcribe_sensevoice(self, pcm_16k: bytes) -> str:
        """通过 SenseVoice HTTP 服务转写.

        HTTP POST 直传 PCM，复用持久连接。
        """
        import httpx

        stt_url = self._get_sensevoice_url()
        timeout = settings.voice.funasr_timeout

        try:
            resp = await self._stt_client.post(stt_url, content=pcm_16k)
            if resp.status_code != 200:
                raise RuntimeError(f"SenseVoice HTTP {resp.status_code}")
            data = resp.json()
            return data.get("text", "")
        except Exception as e:
            logger.warning(f"SenseVoice 失败，降级到 FunASR: {e}")
            return await self.service.transcribe(pcm_16k)

    def _get_sensevoice_url(self) -> str:
        """获取 SenseVoice HTTP URL。"""
        url = settings.voice.sensevoice_websocket_url
        return url.replace("ws://", "http://").replace("wss://", "https://") + "/stt"

    # ------------------------------------------------------------------
    # 电脑前端全双工语音会话
    # ------------------------------------------------------------------

    def start_computer_voice(self) -> bool:
        """开始电脑前端语音输入会话."""
        if self._computer_voice_active:
            logger.debug("VoiceManager: 语音会话已在进行中")
            return True
        self._computer_audio_buffer.clear()
        self._computer_voice_active = True
        logger.info("VoiceManager: 电脑语音会话开始")
        return True

    def feed_computer_audio(self, pcm_16k: bytes) -> None:
        """缓冲前端发来的音频 chunk."""
        if self._computer_voice_active:
            self._computer_audio_buffer.extend(pcm_16k)

    async def end_computer_voice(self) -> str:
        """结束语音输入，转写并返回文本.

        返回空字符串表示转写失败或音频太短。
        """
        if not self._computer_voice_active:
            return ""

        audio = bytes(self._computer_audio_buffer)
        self._computer_audio_buffer.clear()
        self._computer_voice_active = False

        if len(audio) < 3200:  # < 100ms at 16kHz mono 16-bit
            logger.info("VoiceManager: 音频太短，丢弃")
            return ""

        logger.info(f"VoiceManager: 开始转写 {len(audio)} bytes 音频")
        try:
            text = await self.transcribe(audio)
            return text
        except Exception as e:
            logger.error(f"VoiceManager: 转写失败: {e}")
            return ""

    def cancel_computer_voice(self) -> None:
        """取消当前语音输入."""
        self._computer_audio_buffer.clear()
        self._computer_voice_active = False
        logger.info("VoiceManager: 语音输入已取消")

    async def interrupt_computer(self) -> None:
        """打断电脑前端的 TTS 播放."""
        from backend.services.agent.streaming.message_manager import message_manager
        message_manager.cancel_current_reply()
        logger.info("VoiceManager: 电脑 TTS 已打断")

    @property
    def computer_voice_active(self) -> bool:
        return self._computer_voice_active

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """检查语音服务健康状态."""
        from backend.services.voice_health import check_voice_dependencies
        return await check_voice_dependencies()

    async def close(self) -> None:
        """清理资源."""
        self.cancel_computer_voice()
        await self._stt_client.aclose()


voice_manager = VoiceManager()
