"""连接 Discord 工具 -- AI 主动连接 Discord，开始接收消息."""

import logging
from typing import Dict

from .base import Tool

logger = logging.getLogger(__name__)


class ConnectDiscordTool(Tool):
    """AI 通过此工具主动连接 Discord。

    D-01: AI decides when to connect/disconnect.
    D-02: Connecting Discord is mainly for voice (Phase 20), text is a side feature.
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

        if discord_source is None:
            return {"success": False, "message": "Discord 模块未初始化"}

        if discord_source.is_connected():
            return {"success": True, "message": "已连接到 Discord，正在监听配置的频道。"}

        try:
            await discord_source.connect()
            return {
                "success": True,
                "message": "已连接到 Discord，正在监听配置的频道。"
            }
        except Exception as e:
            logger.error(f"Discord 连接失败: {e}")
            return {
                "success": False,
                "message": f"连接 Discord 失败：{e}"
            }
