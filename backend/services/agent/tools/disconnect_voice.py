"""断开语音频道工具 -- AI 主动离开 Discord 语音频道（不断开文字连接）."""

import logging
from typing import Dict

from .base import Tool

logger = logging.getLogger(__name__)


class DisconnectVoiceTool(Tool):
    """AI 通过此工具离开 Discord 语音频道，文字消息不受影响。"""

    @property
    def name(self) -> str:
        return "disconnect_voice"

    @property
    def description(self) -> str:
        return (
            "离开 Discord 语音频道，停止收听和说话。"
            "Discord 文字消息不受影响，仍然可以收发。"
            "当语音对话结束、不需要继续听语音时调用。无需任何参数。"
        )

    @property
    def arguments(self) -> list:
        return []

    async def execute(self, **kwargs) -> Dict:
        from backend.services.voice_player import voice_player

        if not voice_player.is_connected():
            return {"success": True, "message": "当前未连接语音频道。"}

        try:
            await voice_player.disconnect()
            return {"success": True, "message": "已离开语音频道。Discord 文字消息仍然正常。"}
        except Exception as e:
            logger.error(f"断开语音频道失败: {e}")
            return {"success": False, "message": f"离开语音频道失败: {e}"}
