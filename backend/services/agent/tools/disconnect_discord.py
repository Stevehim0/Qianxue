"""断开 Discord 工具 -- AI 主动断开 Discord 连接，同时断开语音频道."""

import logging
from typing import Dict

from .base import Tool

logger = logging.getLogger(__name__)


class DisconnectDiscordTool(Tool):
    """AI 通过此工具主动断开 Discord 连接.

    D-01: AI decides when to connect/disconnect.
    断开时会同步断开语音频道连接（DiscordSource.disconnect 处理）。
    """

    @property
    def name(self) -> str:
        return "disconnect_discord"

    @property
    def description(self) -> str:
        return "断开 Discord 连接。类似于人类'关闭 Discord App'。无需任何参数。"

    @property
    def arguments(self) -> list:
        return []

    async def execute(self, **kwargs) -> Dict:
        from backend.services.agent.sources.discord_source import discord_source
        from backend.services.voice_player import voice_player

        if discord_source is None:
            return {"success": False, "message": "Discord 模块未初始化"}

        if not discord_source.is_connected():
            return {"success": True, "message": "当前未连接 Discord。"}

        try:
            was_voice_connected = voice_player.is_connected()
            await discord_source.disconnect()
            voice_msg = "，语音频道已断开" if was_voice_connected else ""
            return {"success": True, "message": f"已断开 Discord 连接{voice_msg}。"}
        except Exception as e:
            logger.error(f"Discord 断开失败: {e}")
            return {
                "success": False,
                "message": f"断开 Discord 失败：{e}"
            }
