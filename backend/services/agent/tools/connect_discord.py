"""连接 Discord 工具 -- AI 主动连接 Discord，开始接收消息和语音频道交互."""

import asyncio
import logging
from typing import Dict

from .base import Tool

logger = logging.getLogger(__name__)


class ConnectDiscordTool(Tool):
    """AI 通过此工具主动连接 Discord。

    D-01: AI decides when to connect/disconnect.
    D-02: Connecting Discord is mainly for voice (Phase 20), text is a side feature.
    连接成功后，如果配置了 voice_channel_id，会自动加入语音频道。
    """

    @property
    def name(self) -> str:
        return "connect_discord"

    @property
    def description(self) -> str:
        return (
            "连接到 Discord。连接后可以接收和发送文字消息，以及监听语音频道。"
            "类似于人类'打开 Discord App'。无需任何参数。"
        )

    @property
    def arguments(self) -> list:
        return []  # No parameters -- token from config

    async def execute(self, **kwargs) -> Dict:
        from backend.services.agent.sources.discord_source import discord_source
        from backend.services.voice_player import voice_player

        if discord_source is None:
            return {"success": False, "message": "Discord 模块未初始化"}

        if discord_source.is_connected():
            voice_status = "语音频道已连接" if voice_player.is_connected() else "未连接语音频道"
            return {"success": True, "message": f"已连接到 Discord，{voice_status}。"}

        try:
            await discord_source.connect()
            # 等待 Bot 就绪（on_ready 回调会处理 voice_player.set_bot 和自动连语音频道）
            for _ in range(10):
                if discord_source.is_connected():
                    break
                await asyncio.sleep(1)

            voice_status = "语音频道已连接" if voice_player.is_connected() else "未连接语音频道"
            return {
                "success": True,
                "message": f"已连接到 Discord，{voice_status}。"
            }
        except Exception as e:
            logger.error(f"Discord 连接失败: {e}")
            return {
                "success": False,
                "message": f"连接 Discord 失败：{e}"
            }
