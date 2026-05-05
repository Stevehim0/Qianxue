"""语音播放器 - 管理语音频道连接和音频播放."""

import logging
from typing import List

logger = logging.getLogger(__name__)


class VoicePlayer:
    """语音播放器单例。

    Phase 18: 框架实现，is_connected() 始终返回 False。
    Phase 20: 实现 Discord 语音频道连接和音频播放。
    """

    def __init__(self):
        self._connected = False

    def is_connected(self) -> bool:
        """是否已连接到语音频道。"""
        return self._connected

    async def play_sentences(self, audio_chunks: List[bytes]) -> bool:
        """播放音频块队列。

        Args:
            audio_chunks: MP3 bytes 列表，每个元素是一句话的音频

        Returns:
            是否播放成功
        """
        if not self._connected:
            return False
        # Phase 20: 实际播放逻辑（Discord voice client）
        logger.warning("voice_player.play_sentences called but not implemented (Phase 20)")
        return False

    async def connect(self, channel_id: str) -> bool:
        """连接到语音频道（Phase 20 实现）。"""
        logger.warning("voice_player.connect not implemented (Phase 20)")
        return False

    async def disconnect(self):
        """断开语音频道连接（Phase 20 实现）。"""
        self._connected = False


# Module-level singleton
voice_player = VoicePlayer()
